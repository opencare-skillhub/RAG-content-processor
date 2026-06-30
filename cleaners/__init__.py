"""内容清理模块"""
from .base import BaseCleaner
from .text import TextCleaner
from .wechat_article import WechatArticleCleaner
from .format_cleaner import FormatCleaner
from .frontmatter_doctor import FrontmatterDoctor
from .pipeline import ContentCleaningPipeline

# [已停用 / DEPRECATED] 以下两个清理器已禁用导出，待删除：
# - MarkdownCleaner（cleaners/markdown.py）：被 FormatCleaner 取代，且有已知标题 bug
# - WeChatMarkdownCleaner（cleaners/wechat_markdown.py）：全仓库无调用
# from .markdown import MarkdownCleaner
# from .wechat_markdown import WeChatMarkdownCleaner

__all__ = [
    'BaseCleaner',
    'TextCleaner',
    'WechatArticleCleaner',
    'FormatCleaner',
    'FrontmatterDoctor',
    'ContentCleaningPipeline',
    # 'MarkdownCleaner',        # 已停用
    # 'WeChatMarkdownCleaner',  # 已停用
]
