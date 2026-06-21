"""WeChatMCPDownloader 的离线测试。

不发起真实网络请求：通过 monkeypatch `_call_mcp` 和 `_download_file`
验证时间戳子目录隔离、白名单文件清单、url→file 映射。
"""

from pathlib import Path

from fetchers.wechat_mcp import WeChatMCPDownloader


def _fake_mcp_result(title="测试文章", download_filename="article.md"):
    """构造一个 MCP 服务成功响应，模拟 _call_mcp 的返回值。"""
    return {
        "result": {
            "content": [
                {
                    "text": __import__("json").dumps({
                        "status": "success",
                        "title": title,
                        "urls": [f"https://example.com/download/{download_filename}"],
                    })
                }
            ]
        }
    }


def _make_fake_download_file(output_dir: Path):
    """返回一个 fake _download_file，把文件写入指定目录。"""
    def fake_download(url):
        basename = url.rsplit("/", 1)[-1]
        file_path = output_dir / basename
        file_path.write_text(f"# {basename}\n正文内容\n", encoding="utf-8")
        return file_path
    return fake_download


def test_batch_download_creates_run_subdir(tmp_path):
    """batch_download 应创建带时间戳的子目录。"""
    base = tmp_path / "downloads"
    downloader = WeChatMCPDownloader(output_dir=str(base), run_subdir="20260617_070700")
    assert downloader.run_subdir == "20260617_070700"
    assert downloader.output_dir == base / "20260617_070700"
    assert downloader.output_dir.exists()


def test_batch_download_auto_generates_subdir(tmp_path):
    """不传 run_subdir 时，应自动按时间戳生成子目录名。"""
    base = tmp_path / "downloads"
    downloader = WeChatMCPDownloader(output_dir=str(base))
    # 时间戳格式 YYYYMMDD_HHMMSS，长度固定 15
    assert len(downloader.run_subdir) == 15
    assert "_" in downloader.run_subdir
    assert downloader.output_dir == base / downloader.run_subdir


def test_batch_download_files_whitelist_only_current_run(tmp_path, monkeypatch):
    """白名单 files 应只含本次下载的文件，不含 base 目录下的历史残留。"""
    base = tmp_path / "downloads"
    base.mkdir(parents=True, exist_ok=True)
    # 预放一个旧文件作为诱饵（历史残留）
    (base / "old_article.md").write_text("旧文件\n", encoding="utf-8")
    old_run = base / "20260616_101700"
    old_run.mkdir(parents=True)
    (old_run / "previous.md").write_text("上次下载\n", encoding="utf-8")

    run_subdir = "20260617_070700"
    downloader = WeChatMCPDownloader(output_dir=str(base), run_subdir=run_subdir)

    # monkeypatch：MCP 返回成功，_download_file 写入子目录
    monkeypatch.setattr(
        downloader,
        "_call_mcp",
        lambda tool_name, arguments: _fake_mcp_result(title="新文章", download_filename="new.md"),
    )
    monkeypatch.setattr(
        downloader,
        "_download_file",
        _make_fake_download_file(downloader.output_dir),
    )

    result = downloader.batch_download(
        ["https://mp.weixin.qq.com/s/test1"],
        formats=("md",),
    )

    assert result["success"] == 1
    assert result["run_dir"] == str(base / run_subdir)
    assert result["run_subdir"] == run_subdir

    # 白名单只含本次下载的文件
    assert len(result["files"]) == 1
    assert "new.md" in result["files"][0]
    # 不含旧文件
    for f in result["files"]:
        assert "old_article.md" not in f
        assert "previous.md" not in f


def test_batch_download_url_file_map(tmp_path, monkeypatch):
    """url_file_map 应正确映射 url→files。"""
    base = tmp_path / "downloads"
    downloader = WeChatMCPDownloader(output_dir=str(base), run_subdir="20260617_070700")

    def fake_mcp(tool_name, arguments):
        url = arguments.get("url", "")
        filename = "a.md" if "url1" in url else "b.md"
        return _fake_mcp_result(title=f"标题{filename}", download_filename=filename)

    monkeypatch.setattr(downloader, "_call_mcp", fake_mcp)
    monkeypatch.setattr(downloader, "_download_file", _make_fake_download_file(downloader.output_dir))

    urls = ["https://mp.weixin.qq.com/s/url1", "https://mp.weixin.qq.com/s/url2"]
    result = downloader.batch_download(urls, formats=("md",))

    assert result["success"] == 2
    assert len(result["url_file_map"]) == 2
    # 每个 url 对应一个文件
    for url in urls:
        assert url in result["url_file_map"]
        assert len(result["url_file_map"][url]) == 1

    # 验证 main.py 中 _find_url_for_file 能用这个 map 反查
    files = result["files"]
    from main import _find_url_for_file
    for f in files:
        found_url = _find_url_for_file(result["url_file_map"], f)
        assert found_url is not None
        assert found_url in urls


def test_batch_download_failed_url_not_in_files(tmp_path, monkeypatch):
    """下载失败的 url 不应出现在 files 和 url_file_map 中。"""
    base = tmp_path / "downloads"
    downloader = WeChatMCPDownloader(output_dir=str(base), run_subdir="20260617_070700")

    # 第一次成功，第二次失败（MCP 返回异常）
    call_count = [0]
    def fake_mcp(tool_name, arguments):
        call_count[0] += 1
        if call_count[0] == 1:
            return _fake_mcp_result(title="成功", download_filename="ok.md")
        return {"result": {"content": [{"text": '{"status": "failed", "message": "解析失败"}'}]}}

    monkeypatch.setattr(downloader, "_call_mcp", fake_mcp)
    monkeypatch.setattr(downloader, "_download_file", _make_fake_download_file(downloader.output_dir))

    result = downloader.batch_download(
        ["https://mp.weixin.qq.com/s/ok", "https://mp.weixin.qq.com/s/fail"],
        formats=("md",),
    )

    assert result["success"] == 1
    assert result["failed"] == 1
    assert len(result["files"]) == 1
    # 失败的 url 不在 map 中
    assert "https://mp.weixin.qq.com/s/fail" not in result["url_file_map"]
