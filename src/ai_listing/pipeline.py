"""流水线核心：并发调用 → 容错解析 → 规则校验 → 一次自动修复 → 断点续跑。

一次商品的处理链路：
    prompt 渲染 → LLM（可重试）→ 解析 JSON（容错）→ schema 校验
        └─ 规则校验不通过 → 带着问题清单再问一次（最多 1 轮修复）
    结果落 checkpoint（jsonl），中断后重跑自动跳过已完成行
"""

from __future__ import annotations

import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Config
from .llm import LLMClient, LLMError
from .prompts import PromptTemplate, build_context
from .schema import Listing, SchemaError, extract_json
from .validator import Issue, has_error, validate


@dataclass
class RowResult:
    row: dict[str, str]
    listing: Listing | None = None
    status: str = "ok"  # ok | repaired | failed
    issues: list[Issue] = field(default_factory=list)
    latency_ms: int = 0
    tokens: int = 0
    attempts: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.listing is not None and self.status != "failed"

    def to_record(self) -> dict:
        return {
            "id": self.row.get("id"),
            "status": self.status,
            "listing": self.listing.to_dict() if self.listing else None,
            "issues": [i.__dict__ for i in self.issues],
            "latency_ms": self.latency_ms,
            "tokens": self.tokens,
            "attempts": self.attempts,
            "error": self.error,
        }

    @classmethod
    def from_record(cls, row: dict[str, str], rec: dict) -> "RowResult":
        payload = rec.get("listing")
        return cls(
            row=row,
            listing=Listing(**payload) if payload else None,
            status=rec.get("status", "failed"),
            issues=[Issue(**i) for i in rec.get("issues", [])],
            latency_ms=rec.get("latency_ms", 0),
            tokens=rec.get("tokens", 0),
            attempts=rec.get("attempts", 0),
            error=rec.get("error", ""),
        )


class Checkpoint:
    """jsonl 追加写；已成功的行在下次运行直接复用。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.done: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("status") in ("ok", "repaired"):
                    self.done[rec.get("id")] = rec

    def add(self, rec: dict) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if rec.get("status") in ("ok", "repaired"):
                self.done[rec.get("id")] = rec

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self.done.clear()


class Pipeline:
    def __init__(self, cfg: Config, client: LLMClient, template: PromptTemplate,
                 banned_words: list[str] | None = None,
                 on_progress: Callable[[int, int, RowResult], None] | None = None):
        self.cfg = cfg
        self.client = client
        self.template = template
        self.banned_words = banned_words or []
        self.on_progress = on_progress
        self.workers = int(cfg.get("batch.workers", 4))
        self.retries = int(cfg.get("batch.retries", 3))
        self.backoff_base = float(cfg.get("batch.backoff_base", 1.6))
        self.rules = cfg.get("rules", {}) or {}
        self.price_in = float(cfg.get("provider.price_per_1k_input", 0))
        self.price_out = float(cfg.get("provider.price_per_1k_output", 0))

    # ---------- 单条处理 ----------
    def _call_llm(self, system: str, user: str) -> tuple[str, int, int]:
        """带指数退避的重试，只对可重试错误生效。"""
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                t0 = time.perf_counter()
                res = self.client.chat(system, user)
                res.latency_ms = res.latency_ms or int((time.perf_counter() - t0) * 1000)
                return res.text, res.latency_ms, res.total_tokens
            except LLMError as exc:
                last = exc
                if attempt == self.retries:
                    break
                sleep = self.backoff_base ** attempt + random.uniform(0, 0.4)
                time.sleep(sleep)
        raise LLMError(str(last))

    def process(self, row: dict[str, str]) -> RowResult:
        ctx = build_context(self.cfg, row)
        system, user = self.template.render(ctx)
        result = RowResult(row=row)
        total_tokens = 0
        total_ms = 0

        try:
            text, ms, tk = self._call_llm(system, user)
            total_ms += ms
            total_tokens += tk
            result.attempts = 1
            listing = Listing.from_payload(extract_json(text))
            issues = validate(listing, row, self.rules, self.banned_words)

            if has_error(issues):
                # 一轮修复：把问题清单回灌给模型，要求只改不合格的地方
                repair_user = (
                    f"{user}\n\n你上一次的输出是：\n{text}\n\n"
                    "审核发现以下问题：\n"
                    + "\n".join(f"- {i.message}" for i in issues if i.level == "error")
                    + "\n请严格按要求修正后，重新输出完整 JSON（不要解释）。"
                )
                text2, ms2, tk2 = self._call_llm(system, repair_user)
                total_ms += ms2
                total_tokens += tk2
                result.attempts = 2
                listing2 = Listing.from_payload(extract_json(text2))
                issues2 = validate(listing2, row, self.rules, self.banned_words)
                if len([i for i in issues2 if i.level == "error"]) < len(
                    [i for i in issues if i.level == "error"]
                ):
                    listing, issues, result.status = listing2, issues2, "repaired"

            result.listing = listing
            result.issues = issues
            if has_error(issues):
                result.status = "failed"
                result.error = "；".join(i.message for i in issues if i.level == "error")[:200]
        except (SchemaError, LLMError, RuntimeError, ValueError) as exc:
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"[:240]
        finally:
            result.latency_ms = total_ms
            result.tokens = total_tokens
        return result

    # ---------- 批量 ----------
    def run(self, rows: list[dict[str, str]], resume: bool = True) -> list[RowResult]:
        ckpt_path = self.cfg.path(self.cfg.get("batch.checkpoint", "out/checkpoint.jsonl"))
        ckpt = Checkpoint(ckpt_path)
        if not resume:
            ckpt.reset()

        results: dict[str, RowResult] = {}
        todo: list[dict[str, str]] = []
        for row in rows:
            rec = ckpt.done.get(row.get("id"))
            if rec:
                results[row["id"]] = RowResult.from_record(row, rec)
            else:
                todo.append(row)

        done = len(results)
        total = len(rows)

        def handle(res: RowResult) -> None:
            nonlocal done
            results[res.row["id"]] = res
            ckpt.add(res.to_record())
            done += 1
            if self.on_progress:
                self.on_progress(done, total, res)

        if self.workers <= 1:
            for row in todo:
                handle(self.process(row))
        else:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = [pool.submit(self.process, row) for row in todo]
                for fut in as_completed(futures):
                    handle(fut.result())

        return [results[r["id"]] for r in rows if r["id"] in results]

    # ---------- 统计 ----------
    def summarize(self, results: list[RowResult]) -> dict:
        ok = [r for r in results if r.ok]
        tk_in = tk_out = 0
        # 简化：按 70/30 拆输入输出 token 估算成本
        for r in ok:
            tk_in += int(r.tokens * 0.7)
            tk_out += int(r.tokens * 0.3)
        cost = tk_in / 1000 * self.price_in + tk_out / 1000 * self.price_out
        return {
            "total": len(results),
            "ok": len(ok),
            "failed": len(results) - len(ok),
            "repaired": len([r for r in results if r.status == "repaired"]),
            "warn_only": len([r for r in ok if r.issues]),
            "tokens": sum(r.tokens for r in ok),
            "cost_yuan": round(cost, 4),
            "avg_latency_ms": int(sum(r.latency_ms for r in ok) / len(ok)) if ok else 0,
            "pass_rate": round(len(ok) / len(results), 4) if results else 0.0,
        }
