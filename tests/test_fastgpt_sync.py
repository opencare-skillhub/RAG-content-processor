"""FastGPT 同步器的离线测试。

不发起真实网络请求：通过 monkeypatch `requests.post` 捕获上传 payload，
验证可选 QA 元数据正确进入 `metadata` 字段，且默认行为保持 `metadata={}`。
"""

import json
from unittest.mock import MagicMock

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
    assert captured["data"]["parentId"] == "collection-id"
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
