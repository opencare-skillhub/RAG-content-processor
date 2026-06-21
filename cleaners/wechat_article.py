"""微信公众号文章清理器"""
import re
from bs4 import BeautifulSoup
from .base import BaseCleaner


class WechatArticleCleaner(BaseCleaner):
    """微信公众号文章清理器"""
    
    # 需要移除的 HTML 标签/类名
    REMOVE_SELECTORS = [
        'script', 'style', 'iframe',  # 脚本和样式
        '.qr_code_pc_outer', '#js_pc_qr_code',  # 二维码
        '.rich_media_tool', '#js_toobar',  # 工具栏
        '.reward_area', '#js_reward',  # 打赏区域
        '.article_comment', '#js_comment',  # 评论区
        '.profile_container', '#js_profile',  # 公众号资料
        '.read_more_wrap', '#js_view_source',  # 阅读原文
        '.wx_follow_nickname', '.wx_follow_time',  # 关注信息
        '.like_area', '#js_like_area',  # 点赞区域
    ]
    
    # 需要移除的文本模式
    REMOVE_TEXT_PATTERNS = [
        r'长按识别二维码.*?关注',
        r'点击.*?关注.*?公众号',
        r'长按.*?识别图中二维码',
        r'微信扫一扫.*?关注',
        r'阅读原文.*?阅读\s*\d+',
        r'喜欢此内容的人还喜欢',
        r'写留言',
        r'精选留言',
        r'已无更多数据',
    ]
    
    def clean(self, html_content: str) -> str:
        """清理微信公众号文章 HTML"""
        if not html_content:
            return ""
        
        # 解析 HTML
        soup = BeautifulSoup(html_content, 'lxml')
        
        # 移除不需要的元素
        for selector in self.REMOVE_SELECTORS:
            for element in soup.select(selector):
                element.decompose()
        
        # 提取正文内容（通常在 #js_content 中）
        content_div = soup.find('div', id='js_content')
        if not content_div:
            content_div = soup.find('div', class_='rich_media_content')
        
        if not content_div:
            return ""
        
        # 转换为纯文本
        text = content_div.get_text(separator='\n', strip=True)
        
        # 移除营销/广告文本
        text = self._remove_marketing_text(text)
        
        # 规范化格式
        text = self._normalize_format(text)
        
        # 移除多余空白
        text = self.remove_extra_whitespace(text)
        
        return text
    
    def _remove_marketing_text(self, text: str) -> str:
        """移除营销/广告文本"""
        for pattern in self.REMOVE_TEXT_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        return text
    
    def _normalize_format(self, text: str) -> str:
        """规范化文本格式"""
        lines = text.split('\n')
        normalized = []
        
        for line in lines:
            # 跳过空行和只包含特殊字符的行
            if not line.strip():
                normalized.append("")
                continue
            
            # 移除行首行尾的特殊字符
            line = line.strip(' \t\n\r\f\v')
            
            # 跳过只包含标点或符号的行
            if re.match(r'^[\s\W]+$', line) and len(line) < 10:
                continue
            
            normalized.append(line)
        
        return '\n'.join(normalized)
