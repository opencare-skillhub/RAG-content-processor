"""纯文本内容清理器"""
import re
from .base import BaseCleaner


class TextCleaner(BaseCleaner):
    """纯文本内容清理器"""
    
    # 常见的营销/广告关键词
    AD_KEYWORDS = [
        '广告', '推广', '促销', '优惠', '折扣', '限时', '特价',
        '点击', '扫码', '关注', '订阅', '转发', '分享',
        '阅读原文', '查看更多', '了解详情'
    ]
    
    # 编辑/作者信息模式
    EDITOR_PATTERNS = [
        r'编辑[：:]\s*\S+',
        r'作者[：:]\s*\S+',
        r'来源[：:]\s*\S+',
        r'发布时间[：:]\s*[\d\-/]+\s*[\d:]?',
        r'阅读\s*\d+',
    ]
    
    def clean(self, content: str) -> str:
        """清理纯文本内容"""
        if not content:
            return ""
        
        # 移除编辑/作者信息
        text = self._remove_editor_info(content)
        
        # 移除营销/广告内容
        text = self._remove_marketing_content(text)
        
        # 移除多余空白
        text = self.remove_extra_whitespace(text)
        
        return text
    
    def _remove_editor_info(self, text: str) -> str:
        """移除编辑/作者信息"""
        for pattern in self.EDITOR_PATTERNS:
            text = re.sub(pattern, '', text)
        return text
    
    def _remove_marketing_content(self, text: str) -> str:
        """移除营销/广告内容"""
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 跳过包含广告关键词的短行（通常是营销内容）
            if len(line) < 50 and any(keyword in line for keyword in self.AD_KEYWORDS):
                continue
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
