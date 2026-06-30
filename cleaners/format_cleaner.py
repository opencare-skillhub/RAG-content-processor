"""
Stage 1: Format Cleaner (参考 baoyu-format-markdown)

职责：
- 清理残留的 CSS 样式
- 修复混乱的标题层级
- 移除各种格式噪音
- 清理空链接和图片
- 清除微信特有 UI 残留、版权声明、javascript:void 链接等
"""

import re
from typing import List, Tuple


class FormatCleaner:
    """第一阶段：格式清理器"""

    # CSS 残留模式
    # 注意：花括号块 `{...}` 不在此列，改由 _remove_css_braces 保守处理，
    # 避免误删正文中的 JSON / LaTeX / 含中文的花括号内容。
    CSS_PATTERNS = [
        (r'<!--\s*[\w\s:;#-]+-->', 'CSS 注释'),  # <!-- CSS comments -->
        (r'<style[^>]*>.*?</style>', 'style 标签'),  # <style> blocks
        (r'class="[^"]*"', 'class 属性'),  # class attributes
        (r'style="[^"]*"', 'style 属性'),  # style attributes
        (r'data-[\w-]+="[^"]*"', 'data 属性'),  # data-* attributes
    ]

    # 围栏代码块标记（``` 或 ~~~ 开头）
    CODE_FENCE_RE = re.compile(r'^\s*(```|~~~)')

    # 单条 CSS 声明：标识符 + 冒号 + 值（如 color: red、margin-top: 0）
    _CSS_DECL_RE = re.compile(r'^[a-zA-Z-]+\s*:\s*[^;{}]+$')
    # CJK 字符
    _CJK_RE = re.compile(r'[\u4e00-\u9fff]')

    # 格式噪音模式（整行跳过）
    NOISE_PATTERNS = [
        (r'\*{4,}', '过多星号'),  # **** or more
        (r'_{4,}', '过多下划线'),  # ____ or more
        (r'#{4,}\s*$', '过多井号'),  # #### or more (图片删除后的占位)
        (r'#{7,}', '无效标题'),  # ####### or more (invalid heading)
        (r'\[.*?\]\(#\)', '空链接'),  # Empty links
        (r'!\[.*?\]\(\)', '空图片'),  # Empty images
        # 微信 CDN 图片整行（对文本 QA 无价值）
        (r'^!\[.*?\]\(https?://[^)]*qpic\.cn[^)]*\)\s*$', '微信 CDN 图片'),
        # 无描述图片 ![](url) 整行
        (r'^!\[\]\(https?://[^)]+\)\s*$', '无描述图片'),
        (r'<br\s*/?>', 'HTML 换行'),  # <br> tags
        (r'&nbsp;', 'HTML 空格'),  # &nbsp;
        (r'&lt;', '<'),  # HTML 实体
        (r'&gt;', '>'),  # HTML 实体
        (r'&amp;', '&'),  # HTML 实体
        (r'\* \* \*', '装饰分隔线'),  # * * * decorative
    ]

    # 微信特有噪音（行内清理/替换）
    WECHAT_NOISE_PATTERNS = [
        (r'!\[.*?\]\(data:image/[^)]+\)', '内联图片'),  # Inline base64 images
        (r'<img[^>]*>', 'img 标签'),  # <img> tags
        (r'<div[^>]*>', 'div 标签'),  # <div> tags
        (r'</div>', 'div 结束标签'),  # </div> tags
        (r'<span[^>]*>', 'span 标签'),  # <span> tags
        (r'</span>', 'span 结束标签'),  # </span> tags
        (r'<p[^>]*>', 'p 标签'),  # <p> tags
        (r'</p>', 'p 结束标签'),  # </p> tags
        # javascript:void 链接（含转义括号） -> 只保留文本，清理尾部 ;)
        (r'\[([^\]]*?)\]\(javascript:void[^)]*\)[^]\s]*\s*', 'JS void 链接', r'\1'),
    ]

    # 微信正文残留行（整行跳过——纯 UI，无信息价值）
    WECHAT_UI_LINES = [
        r'^预览时标签不可点\s*$',
        r'^微信扫一扫[可]?[以]?\s*$',
        r'^关注该公众号\s*$',
        r'^使用完整服务\s*$',
        r'^使用小程序\s*$',
        r'^在小说阅读器读本章\s*$',
        r'^去阅读\s*$',
        r'^(阅读|查看)?原文(链接|地址)?[：:]\s*$',
        r'^阅读全文\s*$',
        r'^×\s*分析\s*$',
        r'^分享\s+留言\s+收藏\s+听过\s*$',
        r'^分享\s+收藏\s+留言\s*$',
        r'^赞\s*，\s*轻点两下取消赞\s*$',
        r'^在看\s*，\s*轻点两下取消在看\s*$',
        r'^微信扫一扫可打开此内容[，,]?\s*$',
        r'^：\s*(，\s*)+.*(视频|小程序|赞|在看)',
        r'^小程序\s*$',
        r'^作者头像\s*$',
        r'^____+$',
        r'^[\w\u4e00-\u9fff]+\s*;\)\s*$',  # JS void 残留（如"药融圈 ;)"）
    ]

    def __init__(self):
        self.stats = {
            'css_removed': 0,
            'noise_removed': 0,
            'headings_fixed': 0,
            'lines_processed': 0,
            'ui_lines_removed': 0,
            'images_removed': 0,
        }

    def clean(self, content: str) -> Tuple[str, dict]:
        """清理 Markdown 格式，返回 (清理后的内容, 统计信息)。"""
        self.stats = {
            'css_removed': 0,
            'noise_removed': 0,
            'headings_fixed': 0,
            'lines_processed': 0,
            'ui_lines_removed': 0,
            'images_removed': 0,
        }

        # 预清理：版权声明等大段噪音
        content = self._pre_clean_body(content)

        # 按行处理
        lines = content.split('\n')
        cleaned_lines = []
        in_code_fence = False

        for line in lines:
            self.stats['lines_processed'] += 1

            # 围栏代码块：进入/退出时保留标记行，块内整体跳过所有清洗
            if self.CODE_FENCE_RE.match(line):
                in_code_fence = not in_code_fence
                cleaned_lines.append(line)
                continue
            if in_code_fence:
                cleaned_lines.append(line)
                continue

            # 跳过空行
            if not line.strip():
                cleaned_lines.append('')
                continue

            # 清理 CSS 残留
            cleaned_line = self._remove_css(line)

            # 检测并跳过格式噪音
            if self._is_noise(cleaned_line):
                self.stats['noise_removed'] += 1
                continue

            # 检测并跳过微信 UI 残留行
            if self._is_wechat_ui_line(cleaned_line):
                self.stats['ui_lines_removed'] += 1
                continue

            # 修复标题层级
            cleaned_line = self._fix_heading(cleaned_line)

            # 清理微信特有噪音（行内替换）
            cleaned_line = self._remove_wechat_noise(cleaned_line)

            cleaned_lines.append(cleaned_line)

        # 合并连续空行（最多保留 1 个）
        content = '\n'.join(cleaned_lines)
        content = re.sub(r'\n{3,}', '\n\n', content)

        # 后清理
        content = self._post_clean_body(content)

        return content.strip(), self.stats

    def _remove_css(self, line: str) -> str:
        """清理 CSS 残留"""
        for pattern, desc in self.CSS_PATTERNS:
            matches = re.findall(pattern, line)
            if matches:
                self.stats['css_removed'] += len(matches)
                line = re.sub(pattern, '', line)
        # 保守清理花括号块（仅疑似 CSS，保留 JSON/LaTeX/含中文内容）
        line = self._remove_css_braces(line)
        return line.strip()

    def _remove_css_braces(self, line: str) -> str:
        """保守删除花括号块。

        仅当 `{...}` 内容“看起来像 CSS 声明”时才删除，避免误删正文中的
        JSON、LaTeX（如 \\frac{a}{b}）或含中文的花括号内容。
        """
        def _repl(match: 're.Match') -> str:
            inner = match.group(1)
            if self._looks_like_css(inner):
                self.stats['css_removed'] += 1
                return ''
            return match.group(0)

        # 仅匹配不含嵌套花括号的最内层块
        return re.sub(r'\{([^{}]*)\}', _repl, line)

    def _looks_like_css(self, inner: str) -> bool:
        """判断花括号内容是否疑似 CSS 声明块。

        规则（需同时满足）：
        - 不含中文（CSS 属性/值不含中文，正文花括号常含中文）
        - 含冒号
        - 按 `;` 拆分后，每个非空片段都形如 `ident: value`（CSS 声明）
        """
        if not inner.strip():
            return False
        if self._CJK_RE.search(inner):
            return False
        if ':' not in inner:
            return False
        parts = [p.strip() for p in inner.split(';') if p.strip()]
        if not parts:
            return False
        return all(self._CSS_DECL_RE.match(p) for p in parts)

    def _is_noise(self, line: str) -> bool:
        """检测格式噪音"""
        for pattern, desc in self.NOISE_PATTERNS:
            if re.search(pattern, line):
                return True
        return False

    def _is_wechat_ui_line(self, line: str) -> bool:
        """检测微信 UI 残留行"""
        for pattern in self.WECHAT_UI_LINES:
            if re.search(pattern, line):
                return True
        return False

    def _remove_wechat_noise(self, line: str) -> str:
        """清理微信特有噪音（行内替换/删除）"""
        for item in self.WECHAT_NOISE_PATTERNS:
            pattern = item[0]
            # 三元素条目有替换值；两元素条目直接替换为空
            replacement = item[2] if len(item) > 2 else ''
            matches = re.findall(pattern, line)
            if matches:
                self.stats['noise_removed'] += len(matches)
                line = re.sub(pattern, replacement, line)
        return line.strip()

    def _fix_heading(self, line: str) -> str:
        """修复标题层级"""
        match = re.match(r'^(#{1,10})\s+(.+)$', line)
        if not match:
            return line

        level = len(match.group(1))
        text = match.group(2).strip()

        # 修复过多 # 号（限制为 1-6）
        if level > 6:
            level = 6
            self.stats['headings_fixed'] += 1

        # 修复标题文本中的多余空格
        text = ' '.join(text.split())

        return f"{'#' * level} {text}"

    def _pre_clean_body(self, content: str) -> str:
        """清理前的大段噪音（版权声明、转载声明等段落）"""
        # 版权声明整行（含转载、删除、双空格等变体，匹配到行尾）
        content = re.sub(
            r'^版权[权权]?声[明名][：:].*$',
            '', content, flags=re.MULTILINE
        )
        # 来源/转载/投稿声明行
        content = re.sub(
            r'^本文[转来][载自][：:].*$',
            '', content, flags=re.MULTILINE
        )
        content = re.sub(
            r'^来源[：:].*$',
            '', content, flags=re.MULTILINE
        )
        # 投稿/商务合作行
        content = re.sub(
            r'^(投稿|商务合作|媒体合作)[：:].*$',
            '', content, flags=re.MULTILINE
        )
        return content

    def _post_clean_body(self, content: str) -> str:
        """后清理：整段移除已完成信息提取的微信噪音"""
        lines = content.split('\n')
        cleaned = []
        for line in lines:
            s = line.strip()
            # 微信日期地点行：_2026年06月13日 10:30_ __ _ _ _ _ _ 浙江  _
            if re.match(r'^_\d{4}年.*?_\s*_{2,}.*', s):
                self.stats['ui_lines_removed'] += 1
                continue
            # 仅剩标点符号的行（微信交互按钮残留）
            if re.match(r'^[：，。、：:,\s]+$', s):
                self.stats['ui_lines_removed'] += 1
                continue
            # 多余的 ____ 下划线
            if re.match(r'^_{2,}\s*$', s):
                self.stats['ui_lines_removed'] += 1
                continue
            cleaned.append(line)
        content = '\n'.join(cleaned)
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content
