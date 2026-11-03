"""配置加载：YAML + .env，支持 --config 覆盖与点号路径取值。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path | None = None) -> None:
    """极简 .env 读取，避免为一个变量引入 python-dotenv。"""
    p = path or (PROJECT_ROOT / ".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("'\"")
        os.environ.setdefault(k, v)


class Config:
    """给嵌套 dict 加一层点号访问，读写都走这里，便于测试注入。"""

    def __init__(self, data: dict[str, Any], root: Path | None = None):
        self.data = data
        self.root = root or PROJECT_ROOT

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        p = Path(path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        load_env()
        with p.open(encoding="utf-8") as f:
            return cls(yaml.safe_load(f) or {}, root=p.parent.parent)

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (self.root / p)
