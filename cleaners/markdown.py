"""[已停用 / DEPRECATED] Markdown 文件清理器

⚠️ 本模块已停用，待删除：已被 `cleaners/format_cleaner.py` 取代，且存在已知的
标题规范化 bug（"##标题" 会变成 "# #标题"）。已从 `cleaners/__init__.py` 移除导出。
保留源码仅供复核，确认无碍后可整文件删除。
"""
import re
from .base import BaseCleaner


class MarkdownCleaner(BaseCleaner):
    """Markdown 文件清理器"""
    
    # YAML Front Matter 模式
    FRONT_MATTER_PATTERN = r'^---\n.*?\n---\n'
    
    # 元数据注释模式
    METADATA_PATTERNS = [
        r'<!--\s*.*?\s*-->',
        r'\{:\s*.*?\s*\}',
    ]
    
    def clean(self, content: str) -> str:
        """清理 Markdown 内容"""
        if not content:
            return ""
        
        # 移除 YAML Front Matter
        text = self._remove_front_matter(content)
        
        # 移除元数据注释
        text = self._remove_metadata(text)
        
        # 规范化标题
        text = self._normalize_headings(text)
        
        # 移除多余空白
        text = self.remove_extra_whitespace(text)
        
        return text
    
    def _remove_front_matter(self, text: str) -> str:
        """移除 YAML Front Matter"""
        return re.sub(self.FRONT_MATTER_PATTERN, '', text, flags=re.DOTALL)
    
    def _remove_metadata(self, text: str) -> str:
        """移除元数据注释"""
        for pattern in self.METADATA_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.DOTALL)
        return text
    
    def _normalize_headings(self, text: str) -> str:
        """规范化标题格式"""
        lines = text.split('\n')
        normalized = []
        
        for line in lines:
            # 确保标题 # 后有空格
            if line.startswith('#') and not line.startswith('# '):
                line = '# ' + line[1:].strip()
            normalized.append(line)
        
        return '\n'.join(normalized)
