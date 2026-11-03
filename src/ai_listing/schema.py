"""模型输出的数据结构与解析。

设计要点：LLM 返回的是「一段文本」，不是对象。所以这里做三件事：
1. 容错解析：直接 json / Markdown 代码块 / 前后有废话，都能抠出 JSON；
2. 结构校验：字段缺失、类型错误 → 抛出 SchemaError，交给上层决定「重试」还是「修复」；
3. 归一化：去空白、去重、截断超长列表，保证下游拿到的对象是干净的。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any


class SchemaError(ValueError):
    """模型输出不符合约定结构。"""


_CODE_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict[str, Any]:
    """从任意文本里抠出第一个 JSON 对象。"""
    if not text or not text.strip():
        raise SchemaError("模型返回为空")

    candidates: list[str] = []
    m = _CODE_BLOCK.search(text)
    if m:
        candidates.append(m.group(1))
    candidates.append(text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for raw in candidates:
        raw = raw.strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise SchemaError(f"无法从模型返回中解析出 JSON：{text[:120]!r}")


def _clean_list(value: Any, name: str, limit: int = 12) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise SchemaError(f"字段 {name} 应为数组，实际为 {type(value).__name__}")
    out: list[str] = []
    for item in value:
        s = str(item).strip().strip("，,。.;；")
        if s and s not in out:
            out.append(s)
    return out[:limit]


@dataclass
class Listing:
    title: str
    selling_points: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    reason: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Listing":
        if not isinstance(payload, dict):
            raise SchemaError("payload 不是对象")
        title = str(payload.get("title", "")).strip()
        if not title:
            raise SchemaError("缺少 title 字段")
        return cls(
            title=title,
            selling_points=_clean_list(payload.get("selling_points"), "selling_points"),
            keywords=_clean_list(payload.get("keywords"), "keywords"),
            reason=str(payload.get("reason", "")).strip()[:120],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
