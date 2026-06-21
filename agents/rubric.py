"""质检评分配置加载与一期评分引擎。

一期核心流程：人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库。

本模块负责：
- 加载 YAML 配置
- 根据配置生成 LLM 输出 schema / 提示词片段
- 计算 QA 分数、等级、入库动作、入库权重
- 做标签质量的本地扣分校验
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import json

import yaml


DEFAULT_RUBRIC_PATH = Path(__file__).parent / "rubrics" / "medical.yaml"
GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1}


@dataclass
class ScoreResult:
    """评分结果。"""

    qa_score: int
    grade: str
    library_action: str
    qa_weight: float
    score_detail: dict[str, int]
    deduction_reasons: list[str]


class RubricConfig:
    """YAML 评分配置。"""

    def __init__(self, data: dict[str, Any], path: Optional[Path] = None):
        self.data = data
        self.path = path
        self.version = data.get("version", "v0.1")
        self.profile = data.get("profile", "medical_phase1")
        self.threshold = int(data.get("threshold", 85))
        self._validate()

    @classmethod
    def from_yaml(cls, path: Optional[str | Path] = None) -> "RubricConfig":
        p = Path(path) if path else DEFAULT_RUBRIC_PATH
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(data, p)

    def _validate(self):
        """轻量校验，避免配置明显错误。"""
        required = ["qa_generation", "tag_generation", "score_detail_schema", "grading"]
        missing = [k for k in required if k not in self.data]
        if missing:
            raise ValueError(f"Rubric 配置缺少字段: {missing}")

        score_schema = self.data.get("score_detail_schema", {})
        total = sum(int(v.get("max", 0)) for v in score_schema.values())
        if total != 100:
            raise ValueError(f"score_detail_schema max 总和必须为 100，当前为 {total}")

        count = self.display_tags_count
        if count["min"] > count["max"]:
            raise ValueError("display_tags_count.min 不能大于 max")

    @property
    def display_tags_count(self) -> dict[str, int]:
        cfg = self.data.get("tag_generation", {}).get("display_tags_count", {})
        return {"min": int(cfg.get("min", 8)), "max": int(cfg.get("max", 10))}

    @property
    def score_keys(self) -> list[str]:
        return list(self.data.get("score_detail_schema", {}).keys())

    def build_output_schema(self) -> dict[str, Any]:
        """构造要求 LLM 输出的 JSON schema 描述。"""
        return {
            "article_id": "str，可用文件名/标题生成的稳定标识",
            "title": "str，文章标题",
            "article_type": "str，文章类型，例如 medical_education / treatment_progress / nutrition_support / patient_experience",
            "domain": "str，默认 medical",
            "display_tags": f"list[str]，{self.display_tags_count['min']}-{self.display_tags_count['max']} 个展示标签",
            "structured_tags": self.data.get("tag_generation", {}).get("tag_types", {}),
            "qa_pairs": self.data.get("qa_generation", {}).get("qa_pair_schema", {}),
            "qa_score": "int 0-100，基于 score_detail 汇总",
            "grade": "str，A/B/C/D",
            "library_action": "str，高权重入库/标准入库/低权重入库/人工复核/不建议入库",
            "qa_weight": "float，0-1",
            "summary": "str，一句话说明文章适合整理成什么 QA",
            "score_detail": self.data.get("score_detail_schema", {}),
            "deduction_reasons": "list[str]，扣分原因",
            "version": self.version,
        }

    def build_prompt(self, content: str) -> str:
        """根据配置生成一期 Agent 提示词。"""
        return (
            "请按一期流程处理这篇人工精选文章：\n"
            "人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库。\n\n"
            "输出必须是一个 JSON 对象，不要输出 markdown 代码块或额外解释。\n\n"
            "一、QA 生成要求：\n"
            f"{json.dumps(self.data.get('qa_generation', {}), ensure_ascii=False, indent=2)}\n\n"
            "二、标签生成要求：\n"
            f"{json.dumps(self.data.get('tag_generation', {}), ensure_ascii=False, indent=2)}\n\n"
            "三、QA 评分要求：\n"
            f"{json.dumps(self.data.get('score_detail_schema', {}), ensure_ascii=False, indent=2)}\n\n"
            "四、信源与风险规则：\n"
            f"{json.dumps(self.data.get('source_quality_rules', {}), ensure_ascii=False, indent=2)}\n"
            f"{json.dumps(self.data.get('risk_redlines', []), ensure_ascii=False, indent=2)}\n\n"
            "五、输出 schema：\n"
            f"{json.dumps(self.build_output_schema(), ensure_ascii=False, indent=2)}\n\n"
            "待处理文章：\n"
            "----- 内容开始 -----\n"
            f"{content}\n"
            "----- 内容结束 -----"
        )

    def evaluate_result(self, parsed: dict[str, Any], redline_hits: Optional[list[dict]] = None) -> ScoreResult:
        """根据 LLM 结果 + 本地红线命中，计算最终分级和入库权重。"""
        redline_hits = redline_hits or []
        score_detail = self._normalize_score_detail(parsed.get("score_detail", {}))
        score = self._extract_or_sum_score(parsed, score_detail)
        deduction_reasons = [str(x) for x in parsed.get("deduction_reasons", []) if x]

        tag_penalty, tag_reasons = self.calculate_tag_penalty(parsed.get("display_tags", []))
        if tag_penalty:
            score -= tag_penalty
            deduction_reasons.extend(tag_reasons)

        score, redline_reasons, forced_grade = self.apply_redlines(score, redline_hits)
        deduction_reasons.extend(redline_reasons)

        score = max(0, min(100, int(round(score))))
        grade = self.resolve_grade(score)
        if forced_grade:
            grade = self.lower_grade(grade, forced_grade)
        action, weight = self.resolve_action_and_weight(grade)

        return ScoreResult(
            qa_score=score,
            grade=grade,
            library_action=action,
            qa_weight=weight,
            score_detail=score_detail,
            deduction_reasons=deduction_reasons,
        )

    def _normalize_score_detail(self, raw: dict[str, Any]) -> dict[str, int]:
        result = {}
        schema = self.data.get("score_detail_schema", {})
        for key, cfg in schema.items():
            max_score = int(cfg.get("max", 100))
            try:
                value = int(raw.get(key, 0))
            except (TypeError, ValueError):
                value = 0
            result[key] = max(0, min(max_score, value))
        return result

    def _extract_or_sum_score(self, parsed: dict[str, Any], score_detail: dict[str, int]) -> int:
        try:
            score = int(parsed.get("qa_score", parsed.get("score")))
        except (TypeError, ValueError):
            score = sum(score_detail.values())
        return max(0, min(100, score))

    def calculate_tag_penalty(self, display_tags: list[Any]) -> tuple[int, list[str]]:
        """根据一期规则计算标签质量扣分。"""
        tags = [str(t).strip() for t in display_tags if str(t).strip()]
        rules = self.data.get("tag_deduction_rules", {})
        blacklist = self.data.get("marketing_tag_blacklist", [])
        count = self.display_tags_count
        penalty = 0
        reasons = []

        if len(tags) < count["min"]:
            p = int(rules.get("insufficient_tags", {}).get("penalty", 3))
            penalty += p
            reasons.append(f"display_tags 少于 {count['min']} 个，扣 {p} 分")

        marketing_hits = [t for t in tags if any(w in t for w in blacklist)]
        if marketing_hits:
            p = int(rules.get("marketing_tags", {}).get("penalty", 8))
            penalty += p
            reasons.append(f"display_tags 含营销/夸大词 {marketing_hits}，扣 {p} 分")

        generic = {"健康", "科普", "癌症", "治疗"}
        generic_count = sum(1 for t in tags if t in generic)
        if tags and generic_count / len(tags) > 0.3:
            p = int(rules.get("too_generic_tags", {}).get("penalty", 3))
            penalty += p
            reasons.append(f"display_tags 过泛标签占比过高，扣 {p} 分")

        return penalty, reasons

    def apply_redlines(self, score: int, hits: list[dict]) -> tuple[int, list[str], Optional[str]]:
        """应用红线：一期以降级/拒绝为主。"""
        reasons = []
        forced_grade = None
        final_score = score
        for hit in hits:
            action = hit.get("action")
            name = hit.get("name", hit.get("id", "红线"))
            if action == "reject":
                final_score = min(final_score, 0)
                forced_grade = "D"
                reasons.append(f"命中红线：{name}，不建议入库")
            elif action == "downgrade":
                max_grade = hit.get("max_grade", "C")
                forced_grade = self.lower_grade(forced_grade or "A", max_grade)
                reasons.append(f"命中红线：{name}，最高等级限制为 {max_grade}")
        return final_score, reasons, forced_grade

    def resolve_grade(self, score: int) -> str:
        for item in sorted(self.data.get("grading", []), key=lambda x: int(x.get("min_score", 0)), reverse=True):
            if score >= int(item.get("min_score", 0)):
                return item.get("grade", "D")
        return "D"

    def resolve_action_and_weight(self, grade: str) -> tuple[str, float]:
        for item in self.data.get("grading", []):
            if item.get("grade") == grade:
                return item.get("library_action", "询问"), float(item.get("qa_weight", 0.0))
        return "询问", 0.0

    @staticmethod
    def lower_grade(current: Optional[str], max_grade: str) -> str:
        if not current:
            return max_grade
        return current if GRADE_ORDER.get(current, 0) <= GRADE_ORDER.get(max_grade, 0) else max_grade
