"""微信公众号文章 Markdown 清理器（两阶段）

参考技能：
- baoyu-format-markdown: 初步格式化（清理 CSS、修复标题层级、移除格式噪音）
- markdown-frontmatter-doctor: 标准化 frontmatter（6 个核心字段）
"""
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

import yaml
from bs4 import BeautifulSoup
import html2text


class WeChatMarkdownCleaner:
    """微信公众号文章 Markdown 两阶段清理器
    
    第一关：格式清理（参考 baoyu-format-markdown）
    - 清理残留的 CSS 样式
    - 修复混乱的标题层级
    - 移除各种格式噪音
    
    第二关：Frontmatter 标准化（参考 markdown-frontmatter-doctor）
    - 补齐缺失的 frontmatter 字段
    - 统一 6 个核心字段：title / author / summary / description / tags / original_url
    - 把正文中的"原文地址"信息搬进 frontmatter
    - 删除与标题重复的一级标题
    - 清理被污染的 summary/description
    - 去掉冗余字段和导出泄漏的 CSS
    - 检测正文在格式化阶段是否被意外截断
    """
    
    # CSS 残留模式
    CSS_PATTERNS = [
        (r'\{[^}]*:[^}]*\}', 'CSS 块'),  # {property: value}
        (r'<!--\s*[\w\s:;#]+-->', 'CSS 注释'),  # <!-- CSS comments -->
        (r'<style[^>]*>.*?</style>', 'style 标签'),  # <style> blocks
        (r'class="[^"]*"', 'class 属性'),  # class attributes
        (r'style="[^"]*"', 'style 属性'),  # style attributes
    ]
    
    # 格式噪音模式
    NOISE_PATTERNS = [
        r'\*{3,}',  # *** or more
        r'_{3,}',   # ___ or more
        r'-{3,}',   # --- or more (but not HR)
        r'#{7,}',   # ####### or more (invalid heading)
        r'\[.*?\]\(#\)',  # Empty links
        r'!\[.*?\]\(\)',  # Empty images
    ]
    
    # 正文截断检测模式
    TRUNCATION_INDICATORS = [
        r'\.\.\.$',
        r'…$',
        r'未完待续',
        r'阅读全文',
        r'点击查看完整',
    ]
    
    def __init__(self):
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.h2t.ignore_emphasis = False
        self.h2t.body_width = 0  # 不自动换行
    
    def clean(self, content: str, metadata: Optional[dict] = None) -> str:
        """两阶段清理 Markdown 内容
        
        Args:
            content: 原始 Markdown 内容
            metadata: 可选的元数据字典（title, author, url 等）
            
        Returns:
            清理后的 Markdown 内容（含标准化 frontmatter）
        """
        # 第一关：格式清理
        cleaned = self.stage1_format_cleanup(content)
        
        # 第二关：Frontmatter 标准化
        cleaned = self.stage2_frontmatter_standardization(cleaned, metadata)
        
        return cleaned
    
    def clean_html(self, html: str, metadata: Optional[dict] = None) -> str:
        """清理 HTML 并转换为 Markdown
        
        Args:
            html: 原始 HTML 内容
            metadata: 可选的元数据字典
            
        Returns:
            清理后的 Markdown 内容
        """
        # HTML → Markdown
        markdown = self.h2t.handle(html)
        
        # 两阶段清理
        return self.clean(markdown, metadata)
    
    def stage1_format_cleanup(self, content: str) -> str:
        """第一关：格式清理
        
        清理 CSS 残留、修复标题层级、移除格式噪音
        """
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 跳过空行
            if not line.strip():
                cleaned_lines.append('')
                continue
            
            # 清理 CSS 残留
            cleaned_line = self._remove_css(line)
            
            # 跳过格式噪音
            if self._is_noise(cleaned_line):
                continue
            
            # 修复标题层级
            cleaned_line = self._fix_heading(cleaned_line)
            
            cleaned_lines.append(cleaned_line)
        
        # 合并连续空行（最多保留 1 个）
        content = '\n'.join(cleaned_lines)
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return content.strip()
    
    def stage2_frontmatter_standardization(self, content: str, 
                                          metadata: Optional[dict] = None) -> str:
        """第二关：Frontmatter 标准化
        
        补齐缺失字段，统一 6 个核心字段
        """
        metadata = metadata or {}
        
        # 解析现有 frontmatter
        existing_fm, body = self._parse_frontmatter(content)
        
        # 从正文中提取信息
        extracted = self._extract_from_body(body)
        
        # 构建标准化 frontmatter（6 个核心字段）
        frontmatter = {
            'title': (metadata.get('title') or 
                     existing_fm.get('title') or 
                     extracted.get('title') or 
                     '未知标题'),
            
            'author': (metadata.get('author') or 
                      existing_fm.get('author') or 
                      extracted.get('author') or 
                      '未知作者'),
            
            'summary': self._clean_summary(
                metadata.get('summary') or 
                existing_fm.get('summary') or 
                self._generate_summary(body)
            ),
            
            'description': self._clean_description(
                metadata.get('description') or 
                existing_fm.get('description') or 
                existing_fm.get('summary') or 
                ''
            ),
            
            'tags': self._normalize_tags(
                metadata.get('tags') or 
                existing_fm.get('tags') or 
                []
            ),
            
            'original_url': (metadata.get('url') or 
                           metadata.get('original_url') or 
                           existing_fm.get('original_url') or 
                           extracted.get('url') or 
                           ''),
        }
        
        # 清理正文
        cleaned_body = self._clean_body(body, frontmatter)
        
        # 检测截断
        if self._is_truncated(cleaned_body):
            print("⚠️  检测到正文可能被截断")
        
        # 重新组装
        fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)
        result = f"---\n{fm_yaml}---\n\n{cleaned_body}"
        
        return result
    
    def _remove_css(self, line: str) -> str:
        """清理 CSS 残留"""
        for pattern in self.CSS_PATTERNS:
            line = re.sub(pattern, '', line)
        return line.strip()
    
    def _is_noise(self, line: str) -> bool:
        """检测格式噪音"""
        for pattern in self.NOISE_PATTERNS:
            if re.search(pattern, line):
                return True
        return False
    
    def _fix_heading(self, line: str) -> str:
        """修复标题层级"""
        # 匹配标题
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if not match:
            return line
        
        level = len(match.group(1))
        text = match.group(2).strip()
        
        # 修复过多 # 号
        if level > 6:
            level = 6
        
        return f"{'#' * level} {text}"
    
    def _parse_frontmatter(self, content: str) -> tuple:
        """解析 frontmatter"""
        if not content.startswith('---'):
            return {}, content
        
        # 查找第二个 ---
        end_idx = content.find('---', 3)
        if end_idx == -1:
            return {}, content
        
        fm_text = content[3:end_idx].strip()
        body = content[end_idx + 3:].strip()
        
        try:
            fm = yaml.safe_load(fm_text) or {}
            return fm, body
        except:
            return {}, content
    
    def _extract_from_body(self, body: str) -> dict:
        """从正文中提取信息"""
        extracted = {}
        
        # 提取标题（第一个一级标题）
        title_match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
        if title_match:
            extracted['title'] = title_match.group(1).strip()
        
        # 提取原文地址
        url_patterns = [
            r'原文地址[：:]\s*(https?://\S+)',
            r'原文链接[：:]\s*(https?://\S+)',
            r'来源[：:]\s*(https?://\S+)',
        ]
        for pattern in url_patterns:
            match = re.search(pattern, body)
            if match:
                extracted['url'] = match.group(1)
                break
        
        return extracted
    
    def _clean_summary(self, summary: str) -> str:
        """清理 summary"""
        if not summary:
            return ''
        
        # 移除 HTML 标签
        summary = re.sub(r'<[^>]+>', '', summary)
        
        # 移除多余空白
        summary = ' '.join(summary.split())
        
        # 限制长度
        if len(summary) > 200:
            summary = summary[:197] + '...'
        
        return summary
    
    def _clean_description(self, description: str) -> str:
        """清理 description"""
        if not description:
            return ''
        
        # 移除 HTML 标签
        description = re.sub(r'<[^>]+>', '', description)
        
        # 移除多余空白
        description = ' '.join(description.split())
        
        return description
    
    def _normalize_tags(self, tags) -> list:
        """标准化 tags"""
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',')]
        
        if not isinstance(tags, list):
            return []
        
        # 清理每个 tag
        cleaned = []
        for tag in tags:
            tag = str(tag).strip()
            if tag:
                cleaned.append(tag)
        
        return cleaned
    
    def _generate_summary(self, body: str) -> str:
        """从正文生成 summary"""
        # 取前 200 字符
        text = body[:500]
        
        # 移除标题
        text = re.sub(r'^#+\s+.+$', '', text, flags=re.MULTILINE)
        
        # 移除空行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            return ''
        
        # 合并为一段
        summary = ' '.join(lines[:3])
        
        # 限制长度
        if len(summary) > 200:
            summary = summary[:197] + '...'
        
        return summary
    
    def _clean_body(self, body: str, frontmatter: dict) -> str:
        """清理正文"""
        # 删除与标题重复的一级标题
        title = frontmatter.get('title', '')
        if title:
            body = re.sub(rf'^#\s+{re.escape(title)}\s*$', '', body, flags=re.MULTILINE)
        
        # 删除原文地址信息（已搬进 frontmatter）
        body = re.sub(r'原文地址[：:].*$', '', body, flags=re.MULTILINE)
        body = re.sub(r'原文链接[：:].*$', '', body, flags=re.MULTILINE)
        
        # 移除多余空行
        body = re.sub(r'\n{3,}', '\n\n', body)
        
        return body.strip()
    
    def _is_truncated(self, body: str) -> bool:
        """检测正文是否被截断"""
        for pattern in self.TRUNCATION_INDICATORS:
            if re.search(pattern, body, re.MULTILINE):
                return True
        return False
    
    def clean_file(self, file_path: str, metadata: Optional[dict] = None) -> Optional[str]:
        """清理 Markdown 文件
        
        Args:
            file_path: 文件路径
            metadata: 可选的元数据字典
            
        Returns:
            清理后的内容；失败返回 None
        """
        path = Path(file_path)
        if not path.exists():
            print(f"❌ 文件不存在: {file_path}")
            return None
        
        try:
            content = path.read_text(encoding='utf-8')
            cleaned = self.clean(content, metadata)
            return cleaned
        except Exception as e:
            print(f"❌ 清理文件失败: {e}")
            return None
