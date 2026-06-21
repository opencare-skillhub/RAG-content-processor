"""共享 LLM 客户端的离线测试。

验证 env fallback 链和 JSON 容错解析，不发起真实网络请求。
"""

import json

from agents.llm_client import build_llm_config, parse_llm_json


def test_build_llm_config_fallback_chain(monkeypatch):
    """ENRICHER_* 未设时应回退到 QA_AGENT_*。"""
    monkeypatch.delenv("ENRICHER_MODEL", raising=False)
    monkeypatch.delenv("ENRICHER_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    monkeypatch.setenv("QA_AGENT_MODEL", "qwen3.7-max")
    monkeypatch.setenv("QA_AGENT_API_KEY", "qwen-key-123")

    config = build_llm_config()
    assert config.model == "qwen3.7-max"
    assert config.api_key == "qwen-key-123"


def test_build_llm_config_enricher_overrides_qa_agent(monkeypatch):
    """ENRICHER_* 设置时应优先于 QA_AGENT_*。"""
    monkeypatch.setenv("ENRICHER_MODEL", "glm-4.5-air")
    monkeypatch.setenv("ENRICHER_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    monkeypatch.setenv("ENRICHER_API_KEY", "zhipu-key-456")
    monkeypatch.setenv("QA_AGENT_MODEL", "qwen3.7-max")
    monkeypatch.setenv("QA_AGENT_API_KEY", "qwen-key-123")

    config = build_llm_config()
    assert config.model == "glm-4.5-air"
    assert config.base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert config.api_key == "zhipu-key-456"


def test_build_llm_config_api_key_three_way_fallback(monkeypatch):
    """API key 三段回退：ENRICHER_API_KEY → ZHIPUAI_API_KEY → DASHSCOPE_API_KEY。"""
    monkeypatch.delenv("ENRICHER_API_KEY", raising=False)
    monkeypatch.delenv("QA_AGENT_API_KEY", raising=False)
    monkeypatch.setenv("ZHIPUAI_API_KEY", "zhipu-only-key")

    config = build_llm_config()
    assert config.api_key == "zhipu-only-key"

    # 没有 ZHIPUAI 时回退到 DASHSCOPE
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-only-key")
    config = build_llm_config()
    assert config.api_key == "dashscope-only-key"


def test_parse_llm_json_plain():
    assert parse_llm_json('{"a": 1}') == {"a": 1}


def test_parse_llm_json_code_fence():
    assert parse_llm_json('```json\n{"b": 2}\n```') == {"b": 2}


def test_parse_llm_json_with_surrounding_text():
    assert parse_llm_json('好的，结果是：{"c": 3} 以上。') == {"c": 3}


def test_parse_llm_json_empty():
    assert parse_llm_json("") == {}
    assert parse_llm_json("not json at all") == {}


def test_call_llm_json_invokes_openai(monkeypatch):
    """mock openai.OpenAI，验证调用参数与 JSON 解析。"""
    from agents import llm_client

    captured = {}

    class FakeResp:
        class choices:
            class _C:
                message = type("m", (), {"content": '{"summary": "测试摘要"}'})()
            __iter__ = lambda self: iter([self._C()]) if False else None
            # 简化：直接构造
        # 用更简单的结构
    # 改用 dict-like 直接 mock

    class FakeMessage:
        def __init__(self, content):
            self.content = content

    class FakeChoice:
        def __init__(self, content):
            self.message = FakeMessage(content)

    class FakeCompletion:
        def __init__(self, content):
            self.choices = [FakeChoice(content)]

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["call_kwargs"] = kwargs
                    return FakeCompletion('{"summary": "测试摘要"}')

    monkeypatch.setattr(llm_client, "OpenAI", FakeClient, raising=False)
    # 注入 openai 模块里的 OpenAI 名称
    import openai
    monkeypatch.setattr(openai, "OpenAI", FakeClient)

    config = type("C", (), {
        "model": "glm-4.5-air", "base_url": "http://x", "api_key": "k",
        "provider": "zhipu", "timeout": 60,
    })()
    result = llm_client.call_llm_json(config, "sys", "usr")

    assert result == {"summary": "测试摘要"}
    assert captured["client_kwargs"]["api_key"] == "k"
    assert captured["call_kwargs"]["model"] == "glm-4.5-air"
    assert captured["call_kwargs"]["response_format"] == {"type": "json_object"}


def test_call_llm_json_missing_api_key(monkeypatch):
    """无 api_key 时抛 RuntimeError。"""
    from agents import llm_client
    monkeypatch.delenv("ENRICHER_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    monkeypatch.delenv("QA_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    config = type("C", (), {
        "model": "glm-4.5-air", "base_url": "http://x", "api_key": None,
        "provider": "zhipu", "timeout": 60,
    })()
    try:
        llm_client.call_llm_json(config, "sys", "usr")
    except RuntimeError as e:
        assert "API Key" in str(e)
        return
    raise AssertionError("应抛 RuntimeError")
