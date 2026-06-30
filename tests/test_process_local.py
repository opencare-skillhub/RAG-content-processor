"""process-local 命令的离线端到端测试（不调 LLM、不上传）。"""

from argparse import Namespace

import main


def _args(tmp_path, **over):
    base = dict(
        input=str(tmp_path),
        output=str(tmp_path / "out"),
        extensions=".md,.txt,.html",
        no_enrich=True,
        dataset_id=None,
        dry_run=False,
    )
    base.update(over)
    return Namespace(**base)


def _seed(tmp_path):
    (tmp_path / "a.md").write_text("# 标题\n\n正文内容 {color: red}\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("编辑：张三\n正文段落\n长按识别二维码关注我们\n", encoding="utf-8")
    (tmp_path / "c.html").write_text(
        '<html><body><div id="js_content"><p>HTML正文</p></div>'
        '<div class="article_comment">评论区</div></body></html>',
        encoding="utf-8",
    )


def test_process_local_cleans_mixed_extensions(tmp_path):
    _seed(tmp_path)
    main.cmd_process_local(_args(tmp_path))

    out = tmp_path / "out"
    # 三类文件统一输出为 .md
    assert (out / "a.md").exists()
    assert (out / "b.md").exists()
    assert (out / "c.md").exists()

    a = (out / "a.md").read_text(encoding="utf-8")
    assert a.startswith("---\n")          # 已加 frontmatter
    assert "color" not in a               # 疑似 CSS 被清除
    assert "正文内容" in a

    c = (out / "c.md").read_text(encoding="utf-8")
    assert "HTML正文" in c                # html 提取正文
    assert "评论区" not in c              # 噪音被去除


def test_process_local_dry_run_writes_nothing(tmp_path):
    _seed(tmp_path)
    main.cmd_process_local(_args(tmp_path, dry_run=True))
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# clean-wechat 重构后复用 ContentCleaningPipeline（spec §4 / task 7）
# ---------------------------------------------------------------------------

def _clean_args(tmp_path, **over):
    base = dict(
        input=str(tmp_path),
        output=str(tmp_path / "out"),
        extensions=".md",
        no_enrich=True,
    )
    base.update(over)
    return Namespace(**base)


def test_clean_wechat_uses_pipeline_and_keeps_filename_url(tmp_path):
    (tmp_path / "x.md").write_text(
        "# 文章标题\n\n正文一段 {color: red}\n\n预览时标签不可点\n",
        encoding="utf-8",
    )
    main.cmd_clean_wechat(_clean_args(tmp_path))

    out = tmp_path / "out" / "x.md"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "color" not in text                 # 疑似 CSS 清除
    assert "预览时标签不可点" not in text       # 微信 UI 行清除
    assert "original_url: x.md" in text        # 文件名作标识（向后兼容）
    assert "正文一段" in text
