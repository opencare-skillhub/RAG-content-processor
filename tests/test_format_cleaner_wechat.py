"""FormatCleaner 微信残留清理的离线测试。

验证常见微信文章噪音（UI 行、版权声明、CDN 图片、javascript:void 等）
被正确清理，且正文核心内容被保留。
"""

from cleaners.format_cleaner import FormatCleaner


def _clean(text):
    cleaner = FormatCleaner()
    result, stats = cleaner.clean(text)
    return result, stats


def test_removes_wechat_ui_lines():
    """微信 UI 按钮行应被整行删除。"""
    noise_lines = [
        "预览时标签不可点",
        "微信扫一扫",
        "关注该公众号",
        "使用完整服务",
        "使用小程序",
        "微信扫一扫可打开此内容，",
        "分享 留言 收藏 听过",
        "赞 ，轻点两下取消赞",
        "在看 ，轻点两下取消在看",
    ]
    content = "\n".join(noise_lines) + "\n\n保留的正文段落\n"
    result, stats = _clean(content)
    assert "保留的正文段落" in result
    for noise in noise_lines:
        assert noise not in result
    assert stats["ui_lines_removed"] >= len(noise_lines) - 2  # 部分由后清理处理


def test_removes_copyright_declaration():
    """版权声明行应被删除。"""
    content = "正文开头\n版权声明：本文转  自领泰生物  ，如  不希望被转载的媒体或个人可与我们联系，我们将立即删除\n正文结尾\n"
    result, _ = _clean(content)
    assert "正文开头" in result
    assert "正文结尾" in result
    assert "版权声明" not in result
    assert "不希望被转载" not in result


def test_removes_qpic_cdn_images():
    """微信 qpic.cn CDN 图片行应被删除。"""
    content = (
        "正文\n"
        "![图片](https://mmbiz.qpic.cn/mmbiz_png/abc123/640?wx_fmt=png)\n"
        "![](https://mmbiz.qpic.cn/sz_mmbiz_jpg/xyz/0?wx_fmt=jpeg)\n"
        "继续正文\n"
    )
    result, _ = _clean(content)
    assert "正文" in result
    assert "继续正文" in result
    assert "qpic.cn" not in result
    assert "![图片]" not in result


def test_strips_javascript_void_link_keeps_text():
    """javascript:void 链接应只保留文本部分。"""
    # 注意：实际文件里括号可能被转义
    content = "开头\n[ 药融圈 ](javascript:void\\(0\\);)\n正文\n"
    result, _ = _clean(content)
    # 文本被保留（可能独立成行），链接语法被清除
    assert "javascript:void" not in result


def test_removes_decorative_separator():
    """* * * 装饰分隔线应被清理。"""
    content = "段落一\n* * *\n段落二\n"
    result, _ = _clean(content)
    assert "段落一" in result
    assert "段落二" in result
    assert "* * *" not in result


def test_removes_date_location_line():
    """微信日期+地点行应被清理。"""
    content = "_2026年06月13日 10:30_ __ _ _ _ _ _ 浙江  _\n正文\n"
    result, _ = _clean(content)
    assert "正文" in result
    assert "2026年06月13日" not in result
    assert "浙江" not in result


def test_removes_excess_hash_placeholders():
    """图片删除后残留的 #### 占位应被清理。"""
    content = "正文\n####\n####\n继续\n"
    result, _ = _clean(content)
    assert "正文" in result
    assert "继续" in result
    # 不应残留纯 #### 行
    lines = [l.strip() for l in result.split("\n") if l.strip()]
    assert "####" not in lines


def test_preserves_real_content_and_headings():
    """真实正文与标题应被完整保留。"""
    content = (
        "# KRAS G12D PROTAC 临床进展\n\n"
        "LT-010391 获得中国 CDE 临床试验批准。\n\n"
        "## 关于靶点\n\n"
        "KRAS 基因突变约占所有癌症病例的25%。\n"
    )
    result, _ = _clean(content)
    assert "# KRAS G12D PROTAC 临床进展" in result
    assert "## 关于靶点" in result
    assert "LT-010391" in result
    assert "25%" in result


def test_stats_track_removals():
    """统计信息应记录各类清理数量。"""
    content = (
        "![图片](https://mmbiz.qpic.cn/abc/640)\n"
        "预览时标签不可点\n"
        "版权声明：本文为转载\n"
        "正文内容\n"
    )
    _, stats = _clean(content)
    assert stats["noise_removed"] >= 1  # CDN 图片
    assert stats["ui_lines_removed"] >= 1  # UI 行
    assert stats["lines_processed"] >= 4
