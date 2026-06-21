"""基础内容清理器"""
from abc import ABC, abstractmethod


class BaseCleaner(ABC):
    """内容清理器基类"""
    
    @abstractmethod
    def clean(self, content: str) -> str:
        """清理内容
        
        Args:
            content: 原始内容
            
        Returns:
            清理后的内容
        """
        pass
    
    def remove_extra_whitespace(self, text: str) -> str:
        """移除多余的空白字符"""
        if not text:
            return ""
        
        # 移除行首行尾空白
        lines = [line.strip() for line in text.split('\n')]
        # 移除空行（保留单个空行）
        cleaned_lines = []
        prev_empty = False
        for line in lines:
            if not line:
                if not prev_empty:
                    cleaned_lines.append("")
                prev_empty = True
            else:
                cleaned_lines.append(line)
                prev_empty = False
        
        return '\n'.join(cleaned_lines).strip()
