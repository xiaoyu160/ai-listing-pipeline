"""Prompt 模板：外置到 YAML，用 $var 占位（规避 JSON 大括号与 str.format 冲突）。"""

from __future__ import annotations

from pathlib import Path
from string import Template

import yaml

from .config import Config


class PromptTemplate:
    def __init__(self, system: str, user: str):
        self._system = Template(system)
        self._user = Template(user)

    @classmethod
    def load(cls, path: Path) -> "PromptTemplate":
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "system" not in data or "user" not in data:
            raise ValueError(f"Prompt 模板缺少 system/user 字段：{path}")
        return cls(data["system"], data["user"])

    def render(self, ctx: dict[str, object]) -> tuple[str, str]:
        safe = {k: ("" if v is None else str(v)) for k, v in ctx.items()}
        return self._system.safe_substitute(safe), self._user.safe_substitute(safe)


def build_context(cfg: Config, row: dict[str, str]) -> dict[str, object]:
    return {
        "name": row.get("name", ""),
        "category": row.get("category", ""),
        "attributes": row.get("attributes", "") or "无",
        "keywords": row.get("keywords", "") or "无",
        "style": row.get("style", "") or "简洁",
        "title_min": cfg.get("rules.title_min_chars", 12),
        "title_max": cfg.get("rules.title_max_chars", 60),
        "sp_min": cfg.get("rules.selling_points_min", 3),
        "sp_max": cfg.get("rules.selling_points_max", 5),
        "sp_max_chars": cfg.get("rules.selling_point_max_chars", 40),
        "kw_min": cfg.get("rules.keywords_min", 3),
        "kw_max": cfg.get("rules.keywords_max", 8),
    }


def render(template: PromptTemplate, cfg: Config, row: dict[str, str]) -> tuple[str, str]:
    return template.render(build_context(cfg, row))
