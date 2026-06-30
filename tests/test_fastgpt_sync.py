"""FastGPT 同步器的离线测试。

不发起真实网络请求：通过 monkeypatch `requests.post` 捕获上传 payload，
验证可选 QA 元数据正确进入 `metadata` 字段，且默认行为保持 `metadata={}`。
"""

import json
from unittest.mock import MagicMock
from urllib.parse import quote

from fastgpt_sync import FastGPTSyncer


def _make_syncer(tmp_path):
    """构造一个不触碰真实状态的 syncer。"""
    state = tmp_path / "state.json"
    return FastGPTSyncer(
        base_url="https://example.com",
        api_key="fake-key",
        dataset_id="dataset-123",
        state_file=str(state),
    )


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"code": 200}

    def json(self):
        return self._payload


def test_upload_file_sends_qa_metadata(monkeypatch, tmp_path):
    syncer = _make_syncer(tmp_path)
    # 跳过集合创建的网络调用
    monkeypatch.setattr(syncer, "_get_or_create_collection", lambda name: "collection-id")

    captured = {}

    def fake_post(url, headers=None, files=None, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = json.loads(data["data"])
        return _FakeResponse(200, {"code": 200})

    monkeypatch.setattr("fastgpt_sync.requests.post", fake_post)

    f = tmp_path / "art.md"
    f.write_text("正文\n", encoding="utf-8")

    result = syncer.upload_file(
        str(f),
        collection_name="胰腺癌化疗",
        metadata={"qa_score": 90, "qa_weight": 1.0, "qa_grade": "A"},
    )

    assert result == "success"
    assert captured["data"]["datasetId"] == "dataset-123"
    assert captured["data"]["parentId"] is None
    assert captured["data"]["metadata"] == {"qa_score": 90, "qa_weight": 1.0, "qa_grade": "A"}
    assert captured["url"].endswith("/core/dataset/collection/create/localFile")


def test_upload_file_default_metadata_is_empty(monkeypatch, tmp_path):
    syncer = _make_syncer(tmp_path)
    monkeypatch.setattr(syncer, "_get_or_create_collection", lambda name: "collection-id")

    captured = {}

    def fake_post(url, headers=None, files=None, data=None, timeout=None):
        captured["data"] = json.loads(data["data"])
        return _FakeResponse(200, {"code": 200})

    monkeypatch.setattr("fastgpt_sync.requests.post", fake_post)

    f = tmp_path / "art.md"
    f.write_text("正文\n", encoding="utf-8")

    # 不传 metadata：保持旧行为，metadata 为空字典
    result = syncer.upload_file(str(f))
    assert result == "success"
    assert captured["data"]["metadata"] == {}


def test_upload_file_missing_file_returns_failed(tmp_path):
    syncer = _make_syncer(tmp_path)
    result = syncer.upload_file(str(tmp_path / "nope.md"))
    assert result == "failed"


def test_create_dataset_uses_env_default_vlm_model(monkeypatch, tmp_path):
    syncer = _make_syncer(tmp_path)
    captured = {}

    class _Resp:
        status_code = 200
        text = "ok"

        def json(self):
            return {"code": 200, "data": {"_id": "dataset-001"}}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(syncer.session, "post", fake_post)
    monkeypatch.setenv("FASTGPT_VLM_MODEL", "step-1o-turbo-vision")

    result = syncer.create_dataset("测试")

    assert result == {"_id": "dataset-001"}
    assert captured["json"]["vlmModel"] == "step-1o-turbo-vision"


def test_create_dataset_overrides_vlm_model_argument(monkeypatch, tmp_path):
    syncer = _make_syncer(tmp_path)
    captured = {}

    class _Resp:
        status_code = 200
        text = "ok"

        def json(self):
            return {"code": 200, "data": {"_id": "dataset-001"}}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(syncer.session, "post", fake_post)

    result = syncer.create_dataset("测试", vlm_model="custom-vlm")

    assert result == {"_id": "dataset-001"}
    assert captured["json"]["vlmModel"] == "custom-vlm"


def test_create_dataset_falls_back_to_env_vlm_model(monkeypatch, tmp_path):
    syncer = _make_syncer(tmp_path)
    captured = {}

    class _Resp:
        status_code = 200
        text = "ok"

        def json(self):
            return {"code": 200, "data": {"_id": "dataset-001"}}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    monkeypatch.setenv("FASTGPT_VLM_MODEL", "step-1o-turbo-vision")
    monkeypatch.setattr(syncer.session, "post", fake_post)

    result = syncer.create_dataset("测试", vlm_model=None)

    assert result == {"_id": "dataset-001"}
    assert captured["json"]["vlmModel"] == "step-1o-turbo-vision"


# ---------------------------------------------------------------------------
# upload_file 去重行为（spec §5 / §6）
# ---------------------------------------------------------------------------

def test_upload_file_skips_unchanged_content(monkeypatch, tmp_path):
    syncer = _make_syncer(tmp_path)
    monkeypatch.setattr(syncer, "_get_or_create_collection", lambda name: "cid")
    monkeypatch.setattr(
        "fastgpt_sync.requests.post",
        lambda *a, **k: _FakeResponse(200, {"code": 200}),
    )
    f = tmp_path / "art.md"
    f.write_text("正文\n", encoding="utf-8")
    meta = {"original_url": "https://e.com/1"}

    assert syncer.upload_file(str(f), metadata=meta) == "success"
    # 同 url、同内容 → 跳过
    assert syncer.upload_file(str(f), metadata=meta) == "skipped"


def test_upload_file_update_renames_collection_and_warns(monkeypatch, tmp_path, caplog):
    syncer = _make_syncer(tmp_path)
    captured_names = []

    def fake_post(url, headers=None, files=None, data=None, timeout=None):
        # files['file'] = (filename, fileobj)；localFile 以文件名作为集合名
        captured_names.append(files['file'][0])
        return _FakeResponse(200, {"code": 200})

    monkeypatch.setattr("fastgpt_sync.requests.post", fake_post)
    f = tmp_path / "art.md"
    meta = {"original_url": "https://e.com/1"}

    f.write_text("正文 v1\n", encoding="utf-8")
    assert syncer.upload_file(str(f), collection_name="doc", metadata=meta) == "success"

    # 同 url、内容变化 → 视为更新：改名上传 + warn，不覆盖旧集合
    f.write_text("正文 v2 已更新\n", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert syncer.upload_file(str(f), collection_name="doc", metadata=meta) == "success"

    assert captured_names[0] == "doc.md"
    assert captured_names[1].startswith("doc-") and captured_names[1].endswith(".md")
    assert captured_names[1] != "doc.md"
    assert any("内容更新" in r.message for r in caplog.records)


def test_upload_file_encodes_chinese_filename(monkeypatch, tmp_path):
    """中文文件名应被 encode（避免 multipart 乱码）。"""
    syncer = _make_syncer(tmp_path)
    captured = {}

    def fake_post(url, headers=None, files=None, data=None, timeout=None):
        captured["filename"] = files['file'][0]
        return _FakeResponse(200, {"code": 200})

    monkeypatch.setattr("fastgpt_sync.requests.post", fake_post)
    f = tmp_path / "中文文章.md"
    f.write_text("正文\n", encoding="utf-8")

    assert syncer.upload_file(str(f)) == "success"
    # 发送的文件名应为百分号编码（纯 ASCII），且可还原为原名
    assert captured["filename"] == quote("中文文章.md")
    from urllib.parse import unquote
    assert unquote(captured["filename"]) == "中文文章.md"


def test_upload_file_dedup_by_url_across_paths(monkeypatch, tmp_path):
    syncer = _make_syncer(tmp_path)
    monkeypatch.setattr(syncer, "_get_or_create_collection", lambda name: "cid")
    monkeypatch.setattr(
        "fastgpt_sync.requests.post",
        lambda *a, **k: _FakeResponse(200, {"code": 200}),
    )
    f1 = tmp_path / "a.md"
    f2 = tmp_path / "b.md"
    f1.write_text("同样的正文\n", encoding="utf-8")
    f2.write_text("同样的正文\n", encoding="utf-8")
    meta = {"original_url": "https://e.com/x"}

    assert syncer.upload_file(str(f1), metadata=meta) == "success"
    # 不同路径，但相同 url + 内容 → 跳过（旧实现按绝对路径会重传）
    assert syncer.upload_file(str(f2), metadata=meta) == "skipped"
