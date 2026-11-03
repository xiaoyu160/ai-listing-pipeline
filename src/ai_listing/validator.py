"""规则校验：把「平台规范和运营经验」写成可执行的检查，模型输出不合格就回炉。

分两类：
- error：标题超长、缺必含词、命中极限词 —— 必须修复，否则不可上架；
- warn：与原名重合度高、卖点条数不足 —— 记录但不阻断。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .schema import Listing

_EMOJI = re.compile(
    "[" "\U0001f300-\U0001faff" "\U00002700-\U000027bf" "\U0001f1e6-\U0001f1ff" "★☆♥♦●◆■▶" "]"
)
_HTML = re.compile(r"<[a-zA-Z/][^>]*>")
_MARKETING = re.compile(r"[!！]{2,}|[★☆●◆]{2,}")


@dataclass
class Issue:
    code: str
    message: str
    level: str = "error"  # error | warn

    def __str__(self) -> str:  # pragma: no cover
        tag = "ERROR" if self.level == "error" else "WARN"
        return f"[{tag}] {self.code}: {self.message}"


def load_banned_words(path: Path | None) -> list[str]:
    if not path or not path.exists():
        return []
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.append(line)
    return words


def char_len(text: str) -> int:
    """按「人眼字符」计数：中文 1 个，英文/数字按 0.5 计并向上取整。"""
    zh = sum(1 for ch in text if ord(ch) > 127)
    other = sum(1 for ch in text if ord(ch) <= 127 and not ch.isspace())
    return zh + (other + 1) // 2


def _split_words(text: str) -> list[str]:
    return [w.strip() for w in re.split(r"[,，、;；|\s]+", text or "") if w.strip()]


def validate(
    listing: Listing,
    row: dict[str, str],
    rules: dict,
    banned_words: list[str] | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    banned_words = banned_words or []

    # --- 标题 ---
    t_len = char_len(listing.title)
    if t_len < int(rules.get("title_min_chars", 12)):
        issues.append(Issue("title_too_short", f"标题 {t_len} 字符，低于下限"))
    if t_len > int(rules.get("title_max_chars", 60)):
        issues.append(Issue("title_too_long", f"标题 {t_len} 字符，超出上限"))

    for w in banned_words:
        if w and w in listing.title:
            issues.append(Issue("banned_word", f"标题命中禁用词「{w}」"))
    for w in banned_words:
        for sp in listing.selling_points:
            if w and w in sp:
                issues.append(Issue("banned_word", f"卖点命中禁用词「{w}」"))
                break

    must = list(rules.get("must_include") or []) + _split_words(row.get("keywords", ""))
    missing = [w for w in must if w and w not in listing.title and w not in " ".join(listing.keywords)]
    if missing:
        issues.append(Issue("missing_keyword", f"缺少必含词：{'、'.join(missing[:4])}"))

    # --- 卖点 ---
    sp_min, sp_max = int(rules.get("selling_points_min", 3)), int(rules.get("selling_points_max", 5))
    if len(listing.selling_points) < sp_min:
        issues.append(Issue("sp_too_few", f"卖点仅 {len(listing.selling_points)} 条，少于 {sp_min}", "warn"))
    if len(listing.selling_points) > sp_max:
        issues.append(Issue("sp_too_many", f"卖点 {len(listing.selling_points)} 条，多于 {sp_max}"))
    sp_limit = int(rules.get("selling_point_max_chars", 40))
    for sp in listing.selling_points:
        if char_len(sp) > sp_limit:
            issues.append(Issue("sp_too_long", f"卖点超长（{char_len(sp)} 字）：{sp[:20]}…"))

    # --- 关键词 ---
    kw_min, kw_max = int(rules.get("keywords_min", 3)), int(rules.get("keywords_max", 8))
    if len(listing.keywords) < kw_min:
        issues.append(Issue("kw_too_few", f"关键词仅 {len(listing.keywords)} 个，少于 {kw_min}"))
    if len(listing.keywords) > kw_max:
        issues.append(Issue("kw_too_many", f"关键词 {len(listing.keywords)} 个，多于 {kw_max}"))

    # --- 表达规范 ---
    if rules.get("forbid_emoji", True):
        if _EMOJI.search(listing.title):
            issues.append(Issue("emoji_in_title", "标题含表情/装饰符号"))
        if any(_EMOJI.search(sp) for sp in listing.selling_points):
            issues.append(Issue("emoji_in_sp", "卖点含表情/装饰符号"))
    if _HTML.search(listing.title) or any(_HTML.search(sp) for sp in listing.selling_points):
        issues.append(Issue("html_tag", "输出含 HTML 标签"))
    if _MARKETING.search(listing.title):
        issues.append(Issue("marketing_symbol", "标题含夸张营销符号"))

    # --- 与原标题的重复度（防“原文照抄”） ---
    origin = (row.get("name") or "").strip()
    if origin:
        ratio = SequenceMatcher(None, origin, listing.title).ratio()
        limit = float(rules.get("max_repeat_ratio", 0.65))
        if ratio > limit:
            issues.append(
                Issue("too_similar", f"与原商品名重合度 {ratio:.0%}，改写幅度不够", "warn")
            )

    # --- 卖点重复 ---
    norm = [re.sub(r"\s+", "", sp) for sp in listing.selling_points]
    if len(set(norm)) != len(norm):
        issues.append(Issue("duplicate_sp", "卖点存在重复表述"))

    return issues


def has_error(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
