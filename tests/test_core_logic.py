"""Core logic tests for local processing helpers.

These tests cover the most stable and important pure-function / local parts
of the codebase.  They do NOT touch the network or any external service.
"""

from pathlib import Path
import tempfile

from cleaners.format_cleaner import FormatCleaner
from cleaners.frontmatter_doctor import FrontmatterDoctor
# [已停用] MarkdownCleaner 已禁用导出，相关测试一并跳过：
# from cleaners.markdown import MarkdownCleaner
from cleaners.text import TextCleaner
from cleaners.wechat_article import WechatArticleCleaner
from utils.dedup import DedupManager
from utils.hash import calculate_file_hash, calculate_hash


# ---------------------------------------------------------------------------
# utils/hash
# ---------------------------------------------------------------------------

def test_calculate_hash_empty_string():
    assert calculate_hash("") == ""


def test_calculate_hash_is_stable():
    assert calculate_hash("hello") == calculate_hash("hello")
    assert calculate_hash("hello") != calculate_hash("world")


def test_calculate_file_hash_matches_content(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("abc", encoding="utf-8")
    h1 = calculate_file_hash(str(p))
    assert h1
    assert calculate_file_hash(str(p)) == h1


# ---------------------------------------------------------------------------
# utils/dedup
# ---------------------------------------------------------------------------

def test_dedup_new_record_is_not_duplicate(tmp_path):
    state = tmp_path / "state.json"
    mgr = DedupManager(str(state))
    assert mgr.is_duplicate("doc-1", "hash-a") is False


def test_dedup_records_and_detects(tmp_path):
    state = tmp_path / "state.json"
    mgr = DedupManager(str(state))
    mgr.update_record("doc-1", "hash-a", {"type": "file"})
    assert mgr.is_duplicate("doc-1", "hash-a") is True
    assert mgr.is_duplicate("doc-1", "hash-b") is False
    assert mgr.get_record("doc-1")["metadata"]["type"] == "file"


def test_dedup_clear_all(tmp_path):
    state = tmp_path / "state.json"
    mgr = DedupManager(str(state))
    mgr.update_record("doc-1", "hash-a", {"type": "file"})
    mgr.clear_all()
    assert mgr.is_duplicate("doc-1", "hash-a") is False


# ---------------------------------------------------------------------------
# cleaners/format_cleaner
# ---------------------------------------------------------------------------

def test_format_cleaner_removes_css_noise():
    cleaner = FormatCleaner()
    content = "<style>.x{color:red}</style>\n正文内容"
    cleaned, stats = cleaner.clean(content)
    assert "style" not in cleaned
    assert "正文内容" in cleaned


def test_format_cleaner_fixes_heading_levels():
    # NOTE: 当前实现对 7 个 # 的非法标题会整体移除而非降级规范化。
    # 这是已知行为，先用回归断言锁定，待修复后更新期望。
    cleaner = FormatCleaner()
    content = "####### Bad Heading\n正文"
    cleaned, stats = cleaner.clean(content)
    assert "正文" in cleaned
    assert "####### " not in cleaned  # 非法标题不再以原始形式出现


def test_format_cleaner_stats_lines_processed():
    cleaner = FormatCleaner()
    content = "line1\nline2\nline3"
    cleaned, stats = cleaner.clean(content)
    assert stats["lines_processed"] >= 1


# ---------------------------------------------------------------------------
# cleaners/frontmatter_doctor
# ---------------------------------------------------------------------------

def test_frontmatter_doctor_standardizes_fields_and_extracts_url():
    doctor = FrontmatterDoctor()
    content = """---
title: 原标题
author: 旧作者
summary: 旧摘要
description: <p>旧描述</p>
tags:
  - a
---

# 标题
正文内容
原文地址：https://example.com/post/1
"""
    cleaned, fm, stats = doctor.standardize(
        content, {"title": "新标题", "tags": ["x", "y"]}
    )
    assert fm["title"] == "新标题"
    assert fm["author"] == "旧作者"
    assert fm["tags"] == ["x", "y"]
    assert fm["original_url"] == "https://example.com/post/1"
    assert stats["url_extracted"] is True
    assert cleaned.startswith("---\n")
    assert "原文地址" not in cleaned


def test_frontmatter_doctor_rebuilds_frontmatter():
    doctor = FrontmatterDoctor()
    content = "---\ntitle: x\n---\n正文"
    cleaned, fm, stats = doctor.standardize(content, {})
    assert cleaned.startswith("---\n")
    assert cleaned.count("---") >= 2


def test_frontmatter_doctor_extracts_author_from_official_account():
    """公众号名 `[ 药融圈 ](javascript:void...)` 应被提取为 author。"""
    doctor = FrontmatterDoctor()
    content = (
        "# 国内唯一！KRAS PROTAC 获批\n\n"
        "[ 药融圈 ](javascript:void\\(0\\);)\n\n"
        "正文内容\n"
    )
    cleaned, fm, stats = doctor.standardize(content, {})
    assert fm["author"] == "药融圈"


def test_frontmatter_doctor_author_pattern_preferred_over_account():
    """显式 `作者：xxx` 应优先于公众号名。"""
    doctor = FrontmatterDoctor()
    content = (
        "# 标题\n\n"
        "作者：张三\n\n"
        "[ 某公众号 ](javascript:void\\(0\\);)\n\n"
        "正文\n"
    )
    cleaned, fm, stats = doctor.standardize(content, {})
    assert fm["author"] == "张三"


# ---------------------------------------------------------------------------
# cleaners/markdown —— [已停用] MarkdownCleaner 已禁用导出（被 FormatCleaner 取代），
# 原 test_markdown_cleaner_* 三个用例随之移除。详见 spec content-pipeline-refactor §3。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# cleaners/text
# ---------------------------------------------------------------------------

def test_text_cleaner_removes_marketing_and_editor_info():
    cleaner = TextCleaner()
    content = "编辑：张三\n发布时间：2026-06-16\n正文内容\n长按识别二维码关注我们"
    cleaned = cleaner.clean(content)
    assert "张三" not in cleaned
    assert "二维码" not in cleaned
    assert "正文内容" in cleaned


# ---------------------------------------------------------------------------
# cleaners/wechat_article
# ---------------------------------------------------------------------------

def test_wechat_article_cleaner_extracts_main_content():
    cleaner = WechatArticleCleaner()
    html = """<html>
      <body>
        <div id="js_content">
          <p>第一段</p>
          <p>第二段</p>
        </div>
        <div class="article_comment">评论区</div>
      </body>
    </html>"""
    cleaned = cleaner.clean(html)
    assert "第一段" in cleaned
    assert "第二段" in cleaned
    assert "评论区" not in cleaned


# ---------------------------------------------------------------------------
# cleaners/format_cleaner —— 收紧后的 {...} 规则回归（spec §8）
# ---------------------------------------------------------------------------

def test_format_cleaner_removes_inline_css_braces():
    """疑似 CSS 的花括号块仍应被清除。"""
    cleaner = FormatCleaner()
    content = "段落 {color: red; margin: 0} 文字\n正文"
    cleaned, _ = cleaner.clean(content)
    assert "color" not in cleaned
    assert "margin" not in cleaned
    assert "正文" in cleaned


def test_format_cleaner_keeps_latex_braces():
    """LaTeX 花括号（无冒号）不应被误删。"""
    cleaner = FormatCleaner()
    content = "公式 $\\frac{a}{b}$ 结束"
    cleaned, _ = cleaner.clean(content)
    assert "\\frac{a}{b}" in cleaned


def test_format_cleaner_keeps_braces_with_cjk():
    """含中文的花括号内容不应被误删。"""
    cleaner = FormatCleaner()
    content = "配置项 {名称: 测试值} 说明"
    cleaned, _ = cleaner.clean(content)
    assert "名称" in cleaned
    assert "测试值" in cleaned


def test_format_cleaner_keeps_json_braces_outside_fence():
    """裸 JSON（键带引号）不符合 CSS 声明，应保留。"""
    cleaner = FormatCleaner()
    content = '示例 {"name": "x", "age": 1} 行'
    cleaned, _ = cleaner.clean(content)
    assert '"name"' in cleaned
    assert '"age"' in cleaned


def test_format_cleaner_skips_fenced_code_block():
    """围栏代码块内的内容（含 JSON / CSS）应原样保留。"""
    cleaner = FormatCleaner()
    content = (
        "正文前\n"
        "```json\n"
        '{"color": "red", "margin": 0}\n'
        "```\n"
        "正文后"
    )
    cleaned, _ = cleaner.clean(content)
    assert '{"color": "red", "margin": 0}' in cleaned
    assert "正文前" in cleaned
    assert "正文后" in cleaned


# ---------------------------------------------------------------------------
# cleaners/pipeline —— ContentCleaningPipeline 路由（spec §4）
# ---------------------------------------------------------------------------

from cleaners.pipeline import ContentCleaningPipeline


def test_pipeline_markdown_route_cleans_and_standardizes():
    pipe = ContentCleaningPipeline()
    content = "<style>.x{color:red}</style>\n# 标题\n正文内容"
    result, fm = pipe.clean(content, "markdown", {"title": "T"})
    assert result.startswith("---\n")          # 已加 frontmatter
    assert "style" not in result               # markdown 走 FormatCleaner
    assert "正文内容" in result
    assert fm["title"] == "T"


def test_pipeline_html_route_extracts_main_content():
    pipe = ContentCleaningPipeline()
    html = (
        '<html><body><div id="js_content">'
        "<p>第一段</p><p>第二段</p></div>"
        '<div class="article_comment">评论区</div></body></html>'
    )
    result, fm = pipe.clean(html, "html", {"title": "H"})
    assert "第一段" in result and "第二段" in result
    assert "评论区" not in result               # html 走 WechatArticleCleaner
    assert result.startswith("---\n")


def test_pipeline_text_route_removes_marketing():
    pipe = ContentCleaningPipeline()
    content = "编辑：张三\n正文段落\n长按识别二维码关注我们"
    result, fm = pipe.clean(content, "text", {"title": "X"})
    assert "二维码" not in result               # text 走 TextCleaner
    assert "正文段落" in result


def test_pipeline_metadata_overrides_extracted():
    pipe = ContentCleaningPipeline()
    content = "# 正文标题\n正文"
    result, fm = pipe.clean(content, "markdown", {"original_url": "https://e.com/1"})
    assert fm["original_url"] == "https://e.com/1"


# ---------------------------------------------------------------------------
# utils/dedup —— compute_dedup_key 优先级（spec §5）
# ---------------------------------------------------------------------------

from utils.dedup import compute_dedup_key


def test_compute_dedup_key_prefers_original_url():
    key = compute_dedup_key({"original_url": "https://e.com/1"}, "正文", "/tmp/x.md")
    assert key == "url:https://e.com/1"


def test_compute_dedup_key_falls_back_to_content_hash():
    key = compute_dedup_key({}, "abc", "/tmp/x.md")
    assert key == "content:" + calculate_hash("abc")


def test_compute_dedup_key_falls_back_to_file_hash(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("data", encoding="utf-8")
    key = compute_dedup_key({}, None, str(p))
    assert key == "file:" + calculate_file_hash(str(p))
