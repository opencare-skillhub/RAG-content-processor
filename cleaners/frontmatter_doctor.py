"""
Stage 2: Frontmatter Doctor (参考 markdown-frontmatter-doctor)

职责：
- 补齐缺失的 frontmatter 字段
- 统一 6 个核心字段：title / author / summary / description / tags / original_url
- 把正文中的"原文地址"信息搬进 frontmatter
- 删除与标题重复的一级标题
- 清理被污染的 summary/description
- 检测正文是否被截断
"""

import re
import yaml
from typing import Dict, Any, Tuple, Optional
from datetime import datetime


class FrontmatterDoctor:
    """第二阶段：Frontmatter 标准化器"""
    
    # 6 个核心字段
    CORE_FIELDS = ['title', 'author', 'summary', 'description', 'tags', 'original_url']
    
    # 截断检测模式
    TRUNCATION_PATTERNS = [
        r'\.{3,}$',  # 以 ... 结尾
        r'…$',  # 以 … 结尾
        r'\[阅读更多\]',  # [阅读更多]
        r'\[查看全文\]',  # [查看全文]
        r'\[阅读全文\]',  # [阅读全文]
        r'\[继续阅读\]',  # [继续阅读]
        r'\[点击这里\]',  # [点击这里]
        r'未完待续',  # 未完待续
    ]
    
    # 原文地址模式
    ORIGINAL_URL_PATTERNS = [
        r'原文地址[：:]\s*(https?://[^\s]+)',
        r'原文链接[：:]\s*(https?://[^\s]+)',
        r'来源[：:]\s*(https?://[^\s]+)',
        r'原文[：:]\s*(https?://[^\s]+)',
        r'本文链接[：:]\s*(https?://[^\s]+)',
    ]
    
    def __init__(self):
        self.stats = {
            'fields_added': 0,
            'fields_updated': 0,
            'url_extracted': False,
            'title_deduplicated': False,
            'truncation_detected': False
        }
    
    def standardize(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any], dict]:
        """
        标准化 frontmatter
        
        Args:
            content: Markdown 内容（可能已有 frontmatter）
            metadata: 额外的元数据（如从微信抓取时获得的）
            
        Returns:
            (标准化后的内容, frontmatter 数据, 统计信息)
        """
        metadata = metadata or {}
        self.stats = {
            'fields_added': 0,
            'fields_updated': 0,
            'url_extracted': False,
            'title_deduplicated': False,
            'truncation_detected': False
        }
        
        # 解析现有的 frontmatter
        frontmatter, body = self._parse_frontmatter(content)
        
        # 从正文中提取信息
        extracted = self._extract_from_body(body)
        
        # 构建标准化的 frontmatter
        standardized_fm = self._build_standardized_frontmatter(
            existing_fm=frontmatter,
            extracted=extracted,
            metadata=metadata
        )
        
        # 清理正文
        cleaned_body = self._clean_body(body, standardized_fm)
        
        # 检测截断
        if self._is_truncated(cleaned_body):
            self.stats['truncation_detected'] = True
        
        # 重新组装
        result = self._assemble(standardized_fm, cleaned_body)
        
        return result, standardized_fm, self.stats
    
    def _parse_frontmatter(self, content: str) -> Tuple[Dict[str, Any], str]:
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
    
    def _extract_from_body(self, body: str) -> Dict[str, Any]:
        """从正文中提取信息"""
        extracted = {}
        
        # 提取标题（第一个一级标题）
        title_match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
        if title_match:
            extracted['title'] = title_match.group(1).strip()
        
        # 提取原文地址
        for pattern in self.ORIGINAL_URL_PATTERNS:
            match = re.search(pattern, body, re.MULTILINE)
            if match:
                extracted['original_url'] = match.group(1)
                self.stats['url_extracted'] = True
                break
        
        # 提取作者（如果存在"作者："或"author："模式）
        author_match = re.search(r'(?:作者|author)[：:]\s*([^\n]+)', body, re.IGNORECASE)
        if author_match:
            extracted['author'] = author_match.group(1).strip()

        # 提取公众号名（如 `[ 药融圈 ](javascript:void...)`），优先级低于显式"作者："
        if 'author' not in extracted:
            mp_match = re.search(r'\[\s*([^\]]+?)\s*\]\(javascript:void[^)]*\)', body)
            if mp_match:
                mp_name = mp_match.group(1).strip()
                # 过滤掉无意义的占位文本
                if mp_name and mp_name not in ('作者头像',):
                    extracted['author'] = mp_name

        return extracted
    
    def _build_standardized_frontmatter(
        self,
        existing_fm: Dict[str, Any],
        extracted: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建标准化的 frontmatter"""
        
        # 优先级：metadata > extracted > existing > 默认值
        
        standardized = {}
        
        # title
        title = (
            metadata.get('title') or
            extracted.get('title') or
            existing_fm.get('title') or
            '无标题'
        )
        if title != existing_fm.get('title'):
            self.stats['fields_updated'] += 1
        standardized['title'] = title
        
        # author
        author = (
            metadata.get('author') or
            extracted.get('author') or
            existing_fm.get('author') or
            '未知作者'
        )
        if 'author' not in existing_fm:
            self.stats['fields_added'] += 1
        elif author != existing_fm.get('author'):
            self.stats['fields_updated'] += 1
        standardized['author'] = author
        
        # summary
        summary = (
            metadata.get('summary') or
            existing_fm.get('summary') or
            self._generate_summary(existing_fm.get('description', ''))
        )
        if 'summary' not in existing_fm:
            self.stats['fields_added'] += 1
        elif summary != existing_fm.get('summary'):
            self.stats['fields_updated'] += 1
        standardized['summary'] = self._clean_summary(summary)
        
        # description
        description = (
            metadata.get('description') or
            existing_fm.get('description') or
            existing_fm.get('summary') or
            ''
        )
        if 'description' not in existing_fm:
            self.stats['fields_added'] += 1
        elif description != existing_fm.get('description'):
            self.stats['fields_updated'] += 1
        standardized['description'] = self._clean_description(description)
        
        # tags
        tags = (
            metadata.get('tags') or
            existing_fm.get('tags') or
            []
        )
        if 'tags' not in existing_fm:
            self.stats['fields_added'] += 1
        standardized['tags'] = self._normalize_tags(tags)
        
        # original_url
        original_url = (
            metadata.get('original_url') or
            metadata.get('url') or
            extracted.get('original_url') or
            existing_fm.get('original_url') or
            ''
        )
        if 'original_url' not in existing_fm:
            self.stats['fields_added'] += 1
        standardized['original_url'] = original_url
        
        return standardized
    
    def _clean_body(self, body: str, frontmatter: Dict[str, Any]) -> str:
        """清理正文"""
        
        # 删除与标题重复的一级标题
        title = frontmatter.get('title', '')
        if title:
            # 匹配第一个一级标题，如果与 frontmatter.title 相同则删除
            pattern = rf'^#\s+{re.escape(title)}\s*$'
            match = re.search(pattern, body, re.MULTILINE)
            if match:
                body = body[:match.start()] + body[match.end():]
                self.stats['title_deduplicated'] = True
        
        # 删除原文地址信息（已搬进 frontmatter）
        if self.stats['url_extracted']:
            for pattern in self.ORIGINAL_URL_PATTERNS:
                body = re.sub(pattern + r'[^\n]*', '', body)
        
        # 移除多余空行
        body = re.sub(r'\n{3,}', '\n\n', body)
        
        return body.strip()
    
    def _is_truncated(self, body: str) -> bool:
        """检测正文是否被截断"""
        for pattern in self.TRUNCATION_PATTERNS:
            if re.search(pattern, body, re.MULTILINE):
                return True
        return False
    
    def _assemble(self, frontmatter: Dict[str, Any], body: str) -> str:
        """重新组装 frontmatter 和正文"""
        fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return f"---\n{fm_yaml}---\n\n{body}"
    
    def _generate_summary(self, description: str) -> str:
        """从 description 生成 summary"""
        if not description:
            return ''
        
        # 取前 200 字符
        summary = description[:200]
        
        # 如果截断在单词中间，找到最后一个完整句子
        if len(description) > 200:
            last_period = summary.rfind('。')
            if last_period > 100:
                summary = summary[:last_period + 1]
            else:
                summary = summary.rstrip() + '...'
        
        return summary
    
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
            if tag and tag not in cleaned:
                cleaned.append(tag)
        
        return cleaned
