"""命令行入口：

    ai-listing run --input data/sample_products.csv --provider mock
    ai-listing run --input 商品表.xlsx --limit 20 --no-resume
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config
from .export import write_export, write_report
from .llm import build_client
from .pipeline import Pipeline, RowResult
from .prompts import PromptTemplate
from .tableio import read_table, write_results
from .validator import load_banned_words


def _progress(done: int, total: int, res: RowResult) -> None:
    flag = "OK  " if res.ok else "FAIL"
    if res.status == "repaired":
        flag = "FIX "
    preview = res.listing.title[:34] if res.listing else (res.error or "")[:34]
    print(f"[{done:>3}/{total}] {flag} {res.row.get('id',''):<8} {preview}")


def cmd_run(args: argparse.Namespace) -> int:
    cfg = Config.load(args.config)
    rows = read_table(args.input, cfg.get("columns", {}) or {})
    if args.limit:
        rows = rows[: args.limit]

    template = PromptTemplate.load(cfg.path(cfg.get("prompt.template")))
    banned = load_banned_words(cfg.path(cfg.get("rules.banned_words_file", "")))
    client = build_client(cfg, args.provider)

    print(f"模型：{client.model} | 条数：{len(rows)} | 并发：{cfg.get('batch.workers')} | 断点续跑：{not args.no_resume}")

    pipe = Pipeline(cfg, client, template, banned, on_progress=_progress)
    results = pipe.run(rows, resume=not args.no_resume)
    stats = pipe.summarize(results)

    outdir = Path(args.outdir) if args.outdir else cfg.path("out")
    outdir.mkdir(parents=True, exist_ok=True)
    xlsx = write_results(results, outdir / "listings.xlsx")
    export = write_export(results, cfg.path(cfg.get("export.filename", "out/listing_export.csv")))
    report = write_report(results, stats, outdir / "report.md", client.model, str(args.input))

    print(
        f"\n完成：通过 {stats['ok']}/{stats['total']}（修复后通过 {stats['repaired']}），"
        f"平均 {stats['avg_latency_ms']}ms，{stats['tokens']} tokens，约 ￥{stats['cost_yuan']}"
    )
    print(f"结果表：{xlsx}\n上架表：{export}\n报告：{report}")
    return 0 if stats["failed"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ai-listing", description="AI 商品标题/卖点批量生成流水线")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="批量生成")
    r.add_argument("--input", required=True, help="CSV / XLSX 商品表")
    r.add_argument("--config", default="config/default.yaml")
    r.add_argument("--outdir", default=None)
    r.add_argument("--limit", type=int, default=0, help="只跑前 N 行，调试用")
    r.add_argument("--provider", default=None, choices=["openai_compat", "mock"])
    r.add_argument("--no-resume", action="store_true", help="忽略 checkpoint 全量重跑")
    r.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
