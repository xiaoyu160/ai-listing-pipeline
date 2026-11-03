"""客户端工厂：按配置返回具体实现，业务层不感知供应商差异。"""

from __future__ import annotations

from ..config import Config
from .base import ChatResult, LLMClient, LLMError
from .mock import MockClient
from .openai_compat import OpenAICompatClient

__all__ = ["ChatResult", "LLMClient", "LLMError", "MockClient", "OpenAICompatClient", "build_client"]


def build_client(cfg: Config, provider_override: str | None = None) -> LLMClient:
    kind = (provider_override or cfg.get("provider.type", "openai_compat")).lower()
    if kind == "mock":
        return MockClient()
    if kind == "openai_compat":
        return OpenAICompatClient(
            base_url=cfg.get("provider.base_url", "https://api.deepseek.com/v1"),
            model=cfg.get("provider.model", "deepseek-chat"),
            api_key_env=cfg.get("provider.api_key_env", "DEEPSEEK_API_KEY"),
            temperature=float(cfg.get("provider.temperature", 0.7)),
            max_tokens=int(cfg.get("provider.max_tokens", 800)),
            timeout=int(cfg.get("provider.timeout", 60)),
            json_mode=bool(cfg.get("provider.json_mode", True)),
        )
    raise ValueError(f"未知 provider 类型：{kind}")
