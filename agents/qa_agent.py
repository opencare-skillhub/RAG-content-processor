"""知识库一期 QA 整理 Agent。

一期核心流程：人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库。

设计目标：
- 单一 Agent + 提示词，不引入多 Agent 框架。
- 评分与标签规则来自 YAML rubric，便于后续迭代。
- 默认使用 OpenAI-compatible 接口，模型从环境变量读取，不在代码里写死。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from agents.redline import RedlineChecker
from agents.rubric import DEFAULT_RUBRIC_PATH, RubricConfig

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "qwen"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TIMEOUT = 60


@dataclass
class QAReport:
    """单篇文章的一期 QA 整理报告。"""

    identifier: str
    qa_score: int
    passed: bool
    grade: str
    library_action: str = "询问"
    qa_weight: float = 0.0
    title: str = ""
    article_id: str = ""
    article_type: str = ""
    domain: str = "medical"
    display_tags: list[str] = field(default_factory=list)
    structured_tags: dict = field(default_factory=dict)
    qa_pairs: list[dict] = field(default_factory=list)
    score_detail: dict[str, int] = field(default_factory=dict)
    summary: str = ""
    deduction_reasons: list[str] = field(default_factory=list)
    redlines: list[dict] = field(default_factory=list)
    version: str = "v0.1"
    raw: Optional[dict] = field(default=None, repr=False)

    # 兼容旧测试/旧调用：report.score
    @property
    def score(self) -> int:
        return self.qa_score

    @score.setter
    def score(self, value: int):
        self.qa_score = value

    @property
    def tags(self) -> list[str]:
        return self.display_tags

    @tags.setter
    def tags(self, value: list[str]):
        self.display_tags = list(value)

    @property
    def dimensions(self) -> dict[str, int]:
        return self.score_detail

    @dimensions.setter
    def dimensions(self, value: dict[str, int]):
        self.score_detail = dict(value)

    @property
    def suggestions(self) -> list[str]:
        return self.deduction_reasons

    @suggestions.setter
    def suggestions(self, value: list[str]):
        self.deduction_reasons = list(value)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, ensure_ascii: bool = False, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii, indent=indent)


class KnowledgeBaseQAAgent:
    """知识库一期 QA 整理 Agent。"""

    SYSTEM_PROMPT = (
        "你是一个严谨的医学/健康知识库内容整理员。"
        "你的任务不是营销推广，而是把人工精选文章整理成可入库的 QA 知识。"
        "请严格遵循：人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库。"
        "所有标签、QA 和评分都必须来自正文，不得凭空扩展。"
        "不要夸大疗效，不制造焦虑，不鼓吹神药、海外就医或非规范治疗。"
        "输出必须是一个 JSON 对象，不要输出 markdown 代码块或额外解释。"
    )

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        threshold: Optional[int] = None,
        provider: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        rubric_path: Optional[str] = None,
    ):
        self.model = model or os.getenv("QA_AGENT_MODEL")
        self.base_url = base_url or os.getenv("QA_AGENT_BASE_URL", DEFAULT_BASE_URL)
        self.api_key = api_key or os.getenv("QA_AGENT_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        self.provider = (provider or os.getenv("QA_AGENT_PROVIDER", DEFAULT_PROVIDER)).lower()
        self.timeout = int(os.getenv("QA_AGENT_TIMEOUT", timeout))
        self.rubric_path = rubric_path or os.getenv("QA_AGENT_RUBRIC", str(DEFAULT_RUBRIC_PATH))
        self.rubric = RubricConfig.from_yaml(self.rubric_path)
        self.threshold = int(threshold if threshold is not None else self.rubric.threshold)
        self.redline_checker = RedlineChecker(self.rubric)

        if not self.api_key:
            logger.warning(
                "未配置 QA_AGENT_API_KEY / DASHSCOPE_API_KEY，"
                "调用 LLM 将失败。请先在 .env 或 shell 环境中设置。"
            )

    def evaluate(self, content: str, identifier: str = "<unknown>") -> QAReport:
        """对文章执行一期流程，返回结构化报告。"""
        redlines = self.redline_checker.check(content)
        user_prompt = self.rubric.build_prompt(content)
        raw_text = self._call_llm(user_prompt)
        parsed = self._parse_json(raw_text)
        return self._build_report(identifier, parsed, raw_text, redlines)

    def should_upload(self, report: QAReport) -> bool:
        """综合分达到阈值且权重大于 0 才允许自动上传。"""
        return report.qa_score >= self.threshold and report.qa_weight > 0

    def _call_llm(self, user_prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("缺少 API Key：请配置 QA_AGENT_API_KEY 或 DASHSCOPE_API_KEY。")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 openai 依赖，请执行：python3 -m pip install openai") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        logger.info("QA Agent 调用 %s @ %s (provider=%s)", self.model, self.base_url, self.provider)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""

    def _parse_json(self, text: str) -> dict:
        """解析模型输出为 dict，兼容代码块或额外文字。"""
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        cleaned = text.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return {}

    def _build_report(
        self,
        identifier: str,
        parsed: dict,
        raw_text: str,
        redlines: Optional[list[dict]] = None,
    ) -> QAReport:
        redlines = redlines or []
        score_result = self.rubric.evaluate_result(parsed, redlines)
        passed = self.should_upload(
            QAReport(
                identifier=identifier,
                qa_score=score_result.qa_score,
                passed=False,
                grade=score_result.grade,
                qa_weight=score_result.qa_weight,
            )
        )

        return QAReport(
            identifier=identifier,
            qa_score=score_result.qa_score,
            passed=passed,
            grade=score_result.grade,
            library_action=score_result.library_action,
            qa_weight=score_result.qa_weight,
            title=str(parsed.get("title", "")),
            article_id=str(parsed.get("article_id", identifier)),
            article_type=str(parsed.get("article_type", "")),
            domain=str(parsed.get("domain", "medical")),
            display_tags=[str(t) for t in parsed.get("display_tags", []) if t],
            structured_tags=parsed.get("structured_tags", {}) or {},
            qa_pairs=parsed.get("qa_pairs", []) or [],
            score_detail=score_result.score_detail,
            summary=str(parsed.get("summary", "")),
            deduction_reasons=score_result.deduction_reasons,
            redlines=redlines,
            version=self.rubric.version,
            raw={"text": raw_text, "parsed": parsed},
        )

    # 兼容旧测试
    @staticmethod
    def _grade_from_score(score: int, raw_grade: Optional[str] = None) -> str:
        g = str(raw_grade or "").strip().upper()
        if g in {"A", "B", "C", "D"}:
            return g
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        return "D"


def _cli() -> None:
    import argparse

    p = argparse.ArgumentParser(description="知识库一期 QA 整理 Agent")
    p.add_argument("file", help="待整理的 Markdown 文件路径")
    p.add_argument("--threshold", type=int, default=None, help="自动上传准入分数阈值，默认读取 rubric")
    p.add_argument("--rubric", default=None, help="评分配置 YAML 路径")
    p.add_argument("--dry-run", action="store_true", help="不调用 LLM，仅打印提示词")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = os.path.abspath(args.file)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    agent = KnowledgeBaseQAAgent(threshold=args.threshold, rubric_path=args.rubric)
    prompt = agent.rubric.build_prompt(content)

    if args.dry_run:
        print("=== SYSTEM PROMPT ===")
        print(agent.SYSTEM_PROMPT)
        print("\n=== USER PROMPT ===")
        print(prompt)
        print(f"\n(threshold={agent.threshold}, model={agent.model}, rubric={agent.rubric_path})")
        return

    report = agent.evaluate(content, identifier=path)
    print(report.to_json())


if __name__ == "__main__":
    _cli()
