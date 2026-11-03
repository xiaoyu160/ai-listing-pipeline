"""OpenAI Chat Completions 兼容客户端（DeepSeek / 通义 / Kimi / OpenAI 均可）。"""

from __future__ import annotations

import os
import time

import requests

from .base import ChatResult, LLMClient, LLMError, now_ms


class OpenAICompatClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float = 0.7,
        max_tokens: int = 800,
        timeout: int = 60,
        json_mode: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.json_mode = json_mode
        self._session = requests.Session()

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise LLMError(
                f"未设置环境变量 {self.api_key_env}，请在 .env 中配置或先用 --provider mock 跑通链路"
            )
        return key

    def chat(self, system: str, user: str) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        start = now_ms()
        try:
            resp = self._session.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise LLMError(f"请求超时：{exc}") from exc
        except requests.RequestException as exc:
            raise LLMError(f"网络异常：{exc}") from exc

        if resp.status_code in (429, 500, 502, 503, 504):
            raise LLMError(f"上游限流或不可用 HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            # 4xx（除 429）多半是参数/鉴权问题，重试无意义
            raise RuntimeError(f"调用失败 HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"返回体缺少 choices: {str(data)[:200]}")
        text = (choices[0].get("message") or {}).get("content", "")
        usage = data.get("usage") or {}
        return ChatResult(
            text=text,
            model=data.get("model", self.model),
            prompt_tokens=int(usage.get("prompt_tokens") or self._estimate_tokens(system + user)),
            completion_tokens=int(usage.get("completion_tokens") or self._estimate_tokens(text)),
            latency_ms=now_ms() - start,
        )
