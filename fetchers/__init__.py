"""内容抓取模块"""
from .file import FileFetcher
from .wechat_mcp import WeChatMCPDownloader

# WechatArticleFetcher（fetchers/wechat_article.py）已停用（改为 .bak）：
# 微信实时抓取受反爬限制基本失效，下载统一走 WeChatMCPDownloader。
# FileFetcher 保留并在新管线（ContentCleaningPipeline）中复用。

__all__ = ['FileFetcher', 'WeChatMCPDownloader']
