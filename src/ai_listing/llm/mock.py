"""离线模拟客户端：不联网也能跑通全链路，用于单元测试与现场演示。

注意：它只做「模板拼装」，不代表真实模型质量，README 里会明确标注。
"""

from __future__ import annotations

import random
import re

from .base import ChatResult, LLMClient, now_ms

_FIELD = {
    "name": re.compile(r"商品名称[:：]\s*(.+)"),
    "category": re.compile(r"类目[:：]\s*(.+)"),
    "attributes": re.compile(r"属性/规格[:：]\s*(.+)"),
    "keywords": re.compile(r"参考关键词[:：]\s*(.+)"),
    "style": re.compile(r"文案风格[:：]\s*(.+)"),
}

_STYLE_WORDS = {
    "简洁": ["简洁耐看", "日常百搭", "轻量好用"],
    "种草": ["高级感拉满", "氛围感直接拉满", "拍照很出片"],
    "专业": ["参数透明", "用料扎实", "工艺稳定"],
}


class MockClient(LLMClient):
    model = "mock-listing-v1"

    def __init__(self, seed: int = 7):
        self._rnd = random.Random(seed)

    @staticmethod
    def _parse(user: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, pattern in _FIELD.items():
            m = pattern.search(user)
            out[key] = m.group(1).strip() if m else ""
        return out

    @staticmethod
    def _sanitize(text: str) -> str:
        """模拟一个「懂平台规则」的模型：自己先把极限词去掉。"""
        for bad in ("100%", "全网最低", "顶级", "绝对"):
            text = text.replace(bad, "")
        return re.sub(r"\s+", " ", text).strip()

    def chat(self, system: str, user: str) -> ChatResult:
        start = now_ms()
        f = self._parse(user)
        name = f["name"] or "商品"
        category = f["category"] or "通用"
        attrs = [a.strip() for a in re.split(r"[，,；;/]", f["attributes"]) if a.strip()][:3]
        style = f["style"] or "简洁"

        core = re.sub(r"[（(].*?[)）]", "", name).strip()
        parts = [p.strip() for p in category.split("/") if p.strip()]
        audience = parts[0] if parts else ""
        main = parts[-1] if parts else category

        pieces: list[str] = []
        for piece in [core, *attrs, f"{audience}{main}"]:
            piece = piece.strip()
            if piece and not any(piece in x for x in pieces):
                pieces.append(piece)
        title = self._sanitize(" ".join(pieces))
        if len(title) > 58:
            title = title[:58].rsplit(" ", 1)[0]

        base = _STYLE_WORDS.get(style, _STYLE_WORDS["简洁"])
        sp = [
            f"{attrs[0]}，{base[0]}" if attrs else f"{base[0]}，适合日常使用",
            f"{attrs[1]}，{base[1]}" if len(attrs) > 1 else f"{base[1]}，通勤居家都合适",
            f"{main}场景专用，{base[2]}",
            "出厂全检，支持7天无理由退换",
        ]
        sp = [self._sanitize(s) for s in sp]

        kw_src = f["keywords"] + " " + core
        keywords: list[str] = []
        for w in re.split(r"[，,、\s/]+", kw_src):
            w = w.strip()
            if not w or len(w) < 2 or w in keywords:
                continue
            if re.search(r"\d|%|mm", w):  # 带数字的是规格，不是搜索词
                continue
            if w in (audience, main, category):
                continue
            keywords.append(w)
        for w in attrs:  # 兜底补足到 3 个
            if len(keywords) >= 3:
                break
            if not re.search(r"\d|%", w) and w not in keywords:
                keywords.append(w)

        payload = {
            "title": title,
            "selling_points": sp[:4],
            "keywords": keywords[:6],
            "reason": "品类词前置+属性补充，保证检索命中与可读性",
        }
        import json

        text = json.dumps(payload, ensure_ascii=False)
        return ChatResult(
            text=text,
            model=self.model,
            prompt_tokens=self._estimate_tokens(system + user),
            completion_tokens=self._estimate_tokens(text),
            latency_ms=now_ms() - start,
        )
