"""表格读写：输入 CSV / XLSX，输出结果表。列名映射走配置，不写死在代码里。"""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

CANONICAL = ["id", "name", "category", "attributes", "keywords", "style"]
REQUIRED = ["name"]


def _read_csv(path: Path) -> list[dict[str, str]]:
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with path.open(encoding=enc, newline="") as f:
                return [dict(r) for r in csv.DictReader(f)]
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别 CSV 编码：{path}")


def _read_xlsx(path: Path) -> list[dict[str, str]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    out = []
    for r in rows[1:]:
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        out.append({header[i]: ("" if v is None else str(v).strip()) for i, v in enumerate(r) if i < len(header)})
    return out


def read_table(path: str | Path, columns: dict[str, str]) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"输入文件不存在：{p}")
    raw = _read_xlsx(p) if p.suffix.lower() in (".xlsx", ".xlsm") else _read_csv(p)

    rows: list[dict[str, str]] = []
    for i, r in enumerate(raw, start=1):
        item = {}
        for key in CANONICAL:
            header = columns.get(key, key)
            item[key] = str(r.get(header, r.get(key, "")) or "").strip()
        if not item["id"]:
            item["id"] = f"R{i:04d}"
        missing = [k for k in REQUIRED if not item[k]]
        if missing:
            raise ValueError(f"第 {i} 行缺少必填列：{missing}（表头：{list(raw[0].keys())}）")
        rows.append(item)
    return rows


def write_results(
    results: list,  # list[pipeline.RowResult]
    path: str | Path,
    title: str = "AI 文案生成结果",
) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "商品ID", "商品名称", "类目", "生成标题", "标题字数", "卖点1", "卖点2", "卖点3", "卖点4", "卖点5",
        "关键词", "校验状态", "问题明细", "耗时(ms)", "tokens", "状态",
    ]
    wb = Workbook()
    ws = wb.active
    ws.title = "生成结果"
    ws.append(headers)

    head_fill = PatternFill("solid", fgColor="1F3864")
    for c in ws[1]:
        c.font = Font(color="FFFFFF", bold=True, size=10)
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center")

    for r in results:
        lst = r.listing
        sp = (lst.selling_points + [""] * 5)[:5] if lst else [""] * 5
        ws.append([
            r.row.get("id", ""),
            r.row.get("name", ""),
            r.row.get("category", ""),
            lst.title if lst else "",
            len(lst.title) if lst else 0,
            *sp,
            " / ".join(lst.keywords) if lst else "",
            r.status,
            "；".join(str(i) for i in r.issues)[:500],
            r.latency_ms,
            r.tokens,
            "成功" if r.ok else "失败",
        ])

    widths = [10, 26, 12, 34, 9, 20, 20, 20, 20, 20, 28, 10, 40, 10, 8, 8]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "B2"
    wb.save(p)
    return p
