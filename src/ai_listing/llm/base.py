"""模型客户端抽象：上层流水线只依赖 chat()，换供应商不用改业务代码。"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class ChatResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMError(RuntimeError):
    """可重试的上游错误（限流 / 超时 / 5xx）。"""


class LLMClient:
    model: str = "unknown"

    def chat(self, system: str, user: str) -> ChatResult:  # pragma: no cover - 接口
        raise NotImplementedError

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗估 token：中文约 1 字 1 token，英文约 4 字符 1 token。"""
        zh = sum(1 for ch in text if ord(ch) > 127)
        other = len(text) - zh
        return int(zh + other / 4) + 1

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} model={self.model}>"


def now_ms() -> int:
    return int(time.perf_counter() * 1000)
