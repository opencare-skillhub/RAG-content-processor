"""Frontmatter 富化器。

对清洗后的正文调一次低成本 LLM，生成 summary / description / tags，
用于补齐 frontmatter 中规则无法提取的字段。失败时降级为空，不阻断流程。

推荐配合 glm-4.5-air（智谱免费）或 step-3.5-flash（阶跃低成本）使用，
速度快、成本低。配置见 agents/llm_client.py 的 build_llm_config()。
"""

import logging
import re
from typing import Dict, List, Optional

from agents.llm_client import LLMConfig, build_enricher_config, call_llm_json

logger = logging.getLogger(__name__)

# 输入正文超过该长度时截断（速度优先，摘要不需要全文）
MAX_INPUT_CHARS = 3000

SYSTEM_PROMPT = """你是医学/健康科普内容的元数据提取助手。给定一篇文章正文，生成以下 JSON：
{
  "summary": "50-80 字的中文摘要，概括文章核心信息（事件、对象、结论）",
  "description": "15-30 字的简短描述，用于列表展示",
  "tags": ["5-10 个中文标签，覆盖疾病、疗法、药物、主题等"]
}
要求：
- 只输出 JSON，不要任何解释或代码块标记。
- tags 用中文，简洁（2-6 字），不要重复。
- 若内容与医学无关，tags 可放宽为主题词。"""


class FrontmatterEnricher:
    """调一次 LLM 生成 summary/description/tags 的富化器。"""

    def __init__(self, config: Optional[LLMConfig] = None,
                 max_input_chars: int = MAX_INPUT_CHARS):
        self.config = config or build_enricher_config()
        self.max_input_chars = max_input_chars

    def enrich(self, content: str) -> Dict[str, object]:
        """对正文生成富化字段。

        Args:
            content: 文章正文（含或不含 frontmatter；frontmatter 会被剥离）。

        Returns:
            {"summary": str, "description": str, "tags": list[str]}；
            任一字段可能为空（模型未生成或解析失败时）。
            LLM 调用失败时返回空 dict，不抛异常。
        """
        body = self._strip_frontmatter(content)
        body = self._truncate(body)

        if not body.strip():
            logger.warning("富化器收到空正文，跳过 LLM 调用")
            return {}

        try:
            result = call_llm_json(self.config, SYSTEM_PROMPT, body)
        except RuntimeError as exc:
            logger.warning("Frontmatter 富化失败（已降级为空）: %s", exc)
            return {}
        except Exception as exc:  # 网络错误等
            logger.warning("Frontmatter 富化异常（已降级为空）: %s", exc)
            return {}

        return self._normalize(result)

    def _normalize(self, raw: dict) -> Dict[str, object]:
        """规范化 LLM 输出。"""
        summary = self._clean_str(raw.get("summary"))
        description = self._clean_str(raw.get("description"))
        tags = self._clean_tags(raw.get("tags"))
        return {
            "summary": summary,
            "description": description,
            "tags": tags,
        }

    @staticmethod
    def _clean_str(value) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.split())

    @staticmethod
    def _clean_tags(value) -> List[str]:
        if not isinstance(value, list):
            return []
        cleaned = []
        seen = set()
        for tag in value:
            t = str(tag).strip()
            if t and t not in seen:
                seen.add(t)
                cleaned.append(t)
        return cleaned

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """剥离 frontmatter，只保留正文。"""
        if not content.startswith("---"):
            return content
        end = content.find("---", 3)
        if end == -1:
            return content
        return content[end + 3:].strip()

    def _truncate(self, body: str) -> str:
        """按字符数截断正文（速度优先）。"""
        if len(body) <= self.max_input_chars:
            return body
        return body[:self.max_input_chars]
