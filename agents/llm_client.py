"""共享 LLM 客户端层。

为非 QA 评分类任务（如 frontmatter 富化）提供轻量级 LLM 调用。
配置采用「前缀 + 回退」语义：优先读 `<PREFIX>_*`，缺失时回退到 `QA_AGENT_*`，
API key 还会再回退到厂商环境变量（智谱 ZHIPUAI_API_KEY / 通义 DASHSCOPE_API_KEY）。

这样富化器默认复用 QA 评分的配置，开箱即用；若想用更便宜/更快的模型
（如 glm-4.5-air、step-3.5-flash），只需设置 ENRICHER_MODEL 等即可覆盖。
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM 调用配置。"""
    model: Optional[str]
    base_url: Optional[str]
    api_key: Optional[str]
    provider: str
    timeout: int


def build_llm_config(prefix: str = "ENRICHER",
                     fallback_prefix: str = "QA_AGENT",
                     default_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
                     default_provider: str = "qwen",
                     default_timeout: int = 60) -> LLMConfig:
    """按前缀链读取 LLM 配置。

    读取顺序：`<PREFIX>_*` → `<FALLBACK_PREFIX>_*` → 厂商环境变量 → 默认值。
    API key 三段回退：`<PREFIX>_API_KEY` → `ZHIPUAI_API_KEY` → `DASHSCOPE_API_KEY`。
    """
    def _env(key: str) -> Optional[str]:
        v = os.getenv(key)
        return v if v else None

    model = _env(f"{prefix}_MODEL") or _env(f"{fallback_prefix}_MODEL")
    base_url = (_env(f"{prefix}_BASE_URL") or _env(f"{fallback_prefix}_BASE_URL")
                or default_base_url)
    api_key = (_env(f"{prefix}_API_KEY") or _env("ZHIPUAI_API_KEY")
               or _env(f"{fallback_prefix}_API_KEY") or _env("DASHSCOPE_API_KEY"))
    provider = (_env(f"{prefix}_PROVIDER") or _env(f"{fallback_prefix}_PROVIDER")
                or default_provider).lower()
    timeout = int(_env(f"{prefix}_TIMEOUT") or default_timeout)

    return LLMConfig(
        model=model,
        base_url=base_url,
        api_key=api_key,
        provider=provider,
        timeout=timeout,
    )


def build_enricher_config() -> LLMConfig:
    """构建富化器 LLM 配置，支持多模型优先级自动选择。

    用户可通过 ENRICHER_* 显式覆盖。未显式设置时，按以下优先级自动选择：
    1. qwen3.6-flash（DASHSCOPE_API_KEY 存在时，速度最快，适合翻译/标签化）
    2. glm-4.5-air（ZHIPUAI_API_KEY 存在时，免费）
    3. step-3.5-flash（SILICONFLOW_API_KEY 存在时，低成本）
    4. 回退到 build_llm_config()（QA_AGENT_*）
    """
    # 用户显式配置了 ENRICHER_MODEL，优先尊重
    if os.getenv("ENRICHER_MODEL"):
        return build_llm_config(prefix="ENRICHER", fallback_prefix="QA_AGENT")

    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    zhipu_key = os.getenv("ZHIPUAI_API_KEY")
    silicon_key = os.getenv("SILICONFLOW_API_KEY")

    # 优先级 1：qwen3.6-flash（dashscope，速度最快）
    if dashscope_key:
        return LLMConfig(
            model="qwen3.6-flash",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=dashscope_key,
            provider="qwen",
            timeout=60,
        )

    # 优先级 2：glm-4.5-air（智谱，免费）
    if zhipu_key:
        return LLMConfig(
            model="glm-4.5-air",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key=zhipu_key,
            provider="zhipu",
            timeout=60,
        )

    # 优先级 3：step-3.5-flash（硅基流动，低成本）
    if silicon_key:
        return LLMConfig(
            model="step-3.5-flash",
            base_url="https://api.siliconflow.cn",
            api_key=silicon_key,
            provider="stepfun",
            timeout=60,
        )

    # 回退到通用配置（可能只有 QA_AGENT_*）
    return build_llm_config(prefix="ENRICHER", fallback_prefix="QA_AGENT")


def parse_llm_json(text: str) -> dict:
    """解析模型输出为 dict，兼容代码块或额外文字。

    与 qa_agent.QAReport._parse_json 保持一致的容错策略。
    """
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    cleaned = text.strip().strip("`")
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def call_llm_json(config: LLMConfig, system: str, user: str,
                  temperature: float = 0.2) -> dict:
    """调用 LLM 并返回解析后的 dict。

    要求模型输出 JSON。失败时抛 RuntimeError。
    """
    if not config.api_key:
        raise RuntimeError(
            f"缺少 API Key：请配置 {('ENRICHER_API_KEY / ')}ZHIPUAI_API_KEY / "
            f"QA_AGENT_API_KEY / DASHSCOPE_API_KEY。"
        )
    if not config.model:
        raise RuntimeError("缺少模型名：请配置 ENRICHER_MODEL 或 QA_AGENT_MODEL。")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 依赖，请执行：python3 -m pip install openai") from exc

    client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout)
    logger.info("LLM 调用 %s @ %s (provider=%s)", config.model, config.base_url, config.provider)
    resp = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or ""
    return parse_llm_json(raw)
