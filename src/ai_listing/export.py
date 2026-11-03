"""产出物：可直接导入的上架表 CSV + 运行报告 Markdown。"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .pipeline import RowResult

EXPORT_HEADERS = [
    "商品ID", "上架标题", "卖点文案", "搜索关键词", "类目", "审核状态", "需人工处理原因",
]


def write_export(results: list[RowResult], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(EXPORT_HEADERS)
        for r in results:
            if not r.listing:
                w.writerow([r.row.get("id", ""), "", "", "", r.row.get("category", ""), "失败", r.error])
                continue
            errors = [i.message for i in r.issues if i.level == "error"]
            warns = [i.message for i in r.issues if i.level == "warn"]
            status = "可直接上架" if not errors and not warns else ("待人工确认" if not errors else "不可用")
            w.writerow([
                r.row.get("id", ""),
                r.listing.title,
                " | ".join(r.listing.selling_points),
                ",".join(r.listing.keywords[:5]),
                r.row.get("category", ""),
                status,
                "；".join(errors + warns)[:200],
            ])
    return p


def write_report(results: list[RowResult], stats: dict, path: str | Path,
                 model: str = "", input_file: str = "") -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 运行报告",
        "",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- 输入文件：`{input_file}`",
        f"- 模型：`{model}`",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 总条数 | {stats['total']} |",
        f"| 通过 | {stats['ok']} |",
        f"| 其中自动修复后通过 | {stats['repaired']} |",
        f"| 失败 | {stats['failed']} |",
        f"| 通过率 | {stats['pass_rate']:.1%} |",
        f"| 平均耗时 | {stats['avg_latency_ms']} ms |",
        f"| 累计 tokens | {stats['tokens']} |",
        f"| 估算成本 | ￥{stats['cost_yuan']} |",
        "",
    ]

    warns = [(r, i) for r in results for i in r.issues if i.level == "warn"]
    if warns:
        lines += ["## 需关注的条目", "", "| 商品ID | 问题 |", "| --- | --- |"]
        lines += [f"| {r.row.get('id')} | {i.message} |" for r, i in warns[:20]]
        lines.append("")

    fails = [r for r in results if not r.ok]
    if fails:
        lines += ["## 失败条目", "", "| 商品ID | 原因 |", "| --- | --- |"]
        lines += [f"| {r.row.get('id')} | {r.error} |" for r in fails[:20]]
        lines.append("")

    p.write_text("\n".join(lines), encoding="utf-8")
    return p
