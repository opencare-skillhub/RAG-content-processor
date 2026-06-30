"""统一内容清洗管线。

把"按内容类型选清洗器 + Frontmatter 标准化"的逻辑收敛到一处，供
process-local / clean-wechat / download-and-clean 共用，消除各命令里
重复的两阶段清洗循环。

类型路由（与 fetchers.FileFetcher 的类型判定一致）：
- markdown → FormatCleaner（收紧后的正则清洗）
- html     → WechatArticleCleaner（bs4 提取正文）
- text     → TextCleaner（纯文本噪音清理）
- 其他/未知 → 按 text 处理（最保守）

随后统一交给 FrontmatterDoctor 标准化 6 个核心字段。
"""

from typing import Dict, Optional, Tuple

from .format_cleaner import FormatCleaner
from .frontmatter_doctor import FrontmatterDoctor
from .text import TextCleaner
from .wechat_article import WechatArticleCleaner


class ContentCleaningPipeline:
    """来源无关的内容清洗管线：清洗 → Frontmatter 标准化。"""

    def __init__(self):
        self.format_cleaner = FormatCleaner()
        self.text_cleaner = TextCleaner()
        self.html_cleaner = WechatArticleCleaner()
        self.frontmatter_doctor = FrontmatterDoctor()

    def clean(
        self,
        content: str,
        content_type: str = "markdown",
        metadata: Optional[Dict] = None,
        enricher=None,
    ) -> Tuple[str, Dict]:
        """清洗并标准化单篇内容。

        Args:
            content: 原始内容。
            content_type: "markdown" | "html" | "text"（其他按 text 处理）。
            metadata: 额外元数据（author / original_url / 富化字段等），
                优先级高于正文提取，传给 FrontmatterDoctor。
            enricher: 可选的 FrontmatterEnricher。提供时，在"清洗后正文"上调用
                一次 LLM 富化，把非空的 summary/description/tags 合并进 metadata
                （已有 metadata 字段优先，不被覆盖）。富化失败降级为空、不阻断。

        Returns:
            (标准化后的完整 Markdown 文本, frontmatter dict)
        """
        metadata = dict(metadata or {})
        cleaned_body = self._clean_by_type(content, content_type)

        if enricher is not None:
            try:
                enriched = enricher.enrich(cleaned_body)
                for k, v in enriched.items():
                    if v and not metadata.get(k):
                        metadata[k] = v
            except Exception:  # 富化任何异常都不应阻断清洗
                pass

        result, frontmatter, _ = self.frontmatter_doctor.standardize(
            cleaned_body, metadata
        )
        return result, frontmatter

    def _clean_by_type(self, content: str, content_type: str) -> str:
        """按类型选择清洗器，返回清洗后的正文文本。"""
        ctype = (content_type or "").lower()
        if ctype == "markdown":
            cleaned, _ = self.format_cleaner.clean(content)
            return cleaned
        if ctype == "html":
            return self.html_cleaner.clean(content)
        # text 及未知类型
        return self.text_cleaner.clean(content)
