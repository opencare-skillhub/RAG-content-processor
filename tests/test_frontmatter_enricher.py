"""FrontmatterEnricher 的离线测试。

通过 mock call_llm_json 验证富化逻辑：正常生成、正文截断、frontmatter 剥离、
LLM 失败降级为空、输出规范化。不发起真实网络请求。
"""

import pytest

from agents.frontmatter_enricher import FrontmatterEnricher
from agents.llm_client import LLMConfig


def _make_config():
    return LLMConfig(
        model="glm-4.5-air",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key="fake-key",
        provider="zhipu",
        timeout=60,
    )


def test_enrich_normal_generation(monkeypatch):
    """正常 LLM 输出应被规范化为 summary/description/tags。"""
    enricher = FrontmatterEnricher(config=_make_config())

    def fake_call(config, system, user, temperature=0.2):
        return {
            "summary": "  领泰生物口服 KRAS G12D PROTAC 获 CDE 临床批准  ",
            "description": "国内首个口服 KRAS 抑制剂",
            "tags": ["KRAS", "PROTAC", "  肿瘤  ", "KRAS", "临床"],
        }

    monkeypatch.setattr("agents.frontmatter_enricher.call_llm_json", fake_call)
    result = enricher.enrich("# 标题\n\n这是一篇关于 KRAS 的文章。")

    assert "获 CDE 临床批准" in result["summary"]
    assert result["description"] == "国内首个口服 KRAS 抑制剂"
    assert result["tags"] == ["KRAS", "PROTAC", "肿瘤", "临床"]  # 去重 + 去空白


def test_enrich_strips_frontmatter(monkeypatch):
    """enrich 应剥离 frontmatter，只把正文传给 LLM。"""
    enricher = FrontmatterEnricher(config=_make_config())
    captured = {}

    def fake_call(config, system, user, temperature=0.2):
        captured["user"] = user
        return {"summary": "s", "description": "d", "tags": []}

    monkeypatch.setattr("agents.frontmatter_enricher.call_llm_json", fake_call)
    content = "---\ntitle: 标题\nauthor: 作者\n---\n\n这是正文。"
    enricher.enrich(content)

    assert "这是正文。" in captured["user"]
    assert "title: 标题" not in captured["user"]


def test_enrich_truncates_long_input(monkeypatch):
    """超长正文应被截断，不超过 max_input_chars。"""
    enricher = FrontmatterEnricher(config=_make_config(), max_input_chars=100)
    captured = {}

    def fake_call(config, system, user, temperature=0.2):
        captured["user_len"] = len(user)
        return {"summary": "s", "description": "d", "tags": []}

    monkeypatch.setattr("agents.frontmatter_enricher.call_llm_json", fake_call)
    long_body = "正文" * 200  # 远超 100
    enricher.enrich(long_body)

    assert captured["user_len"] <= 100


def test_enrich_returns_empty_on_llm_failure(monkeypatch):
    """LLM 调用失败（RuntimeError）时应降级为空 dict，不抛异常。"""
    enricher = FrontmatterEnricher(config=_make_config())

    def fake_call(config, system, user, temperature=0.2):
        raise RuntimeError("网络错误")

    monkeypatch.setattr("agents.frontmatter_enricher.call_llm_json", fake_call)
    result = enricher.enrich("有内容的正文")

    assert result == {}


def test_enrich_returns_empty_on_empty_body():
    """空正文应直接返回空，不调 LLM。"""
    config = _make_config()
    enricher = FrontmatterEnricher(config=config)
    result = enricher.enrich("")
    assert result == {}


def test_enrich_normalizes_non_string_tags():
    """tags 含非字符串元素时应转字符串。"""
    enricher = FrontmatterEnricher(config=_make_config())
    result = enricher._normalize({"tags": ["a", 123, None, "b"], "summary": "s"})
    assert result["tags"] == ["a", "123", "None", "b"]


def test_enrich_normalizes_missing_fields():
    """LLM 输出缺字段时，缺失项应为空字符串/空列表。"""
    enricher = FrontmatterEnricher(config=_make_config())
    result = enricher._normalize({"summary": "只有摘要"})
    assert result["summary"] == "只有摘要"
    assert result["description"] == ""
    assert result["tags"] == []
