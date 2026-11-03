from ai_listing.schema import Listing
from ai_listing.validator import char_len, has_error, validate

RULES = {
    "title_min_chars": 10,
    "title_max_chars": 30,
    "selling_points_min": 3,
    "selling_points_max": 5,
    "selling_point_max_chars": 20,
    "keywords_min": 3,
    "keywords_max": 8,
    "forbid_emoji": True,
    "max_repeat_ratio": 0.9,
}
ROW = {"name": "纯棉圆领短袖T恤", "keywords": "短袖t恤,纯棉", "category": "女装/T恤"}


def make(**kw):
    base = dict(
        title="女装纯棉短袖T恤 220g重磅宽松落肩",
        selling_points=["100%精梳棉，亲肤透气", "220g重磅，不透不塌", "宽松落肩，遮肉显瘦"],
        keywords=["短袖t恤", "纯棉t恤", "白色短袖"],
    )
    base.update(kw)
    return Listing(**base)


def test_pass():
    issues = validate(make(), ROW, RULES, [])
    assert not has_error(issues)


def test_banned_word_error():
    issues = validate(make(title="女装纯棉短袖T恤 全网最低价"), ROW, RULES, ["全网最低"])
    assert has_error(issues)
    assert any(i.code == "banned_word" for i in issues)


def test_title_too_long():
    issues = validate(make(title="纯棉" * 20), ROW, RULES, [])
    assert any(i.code == "title_too_long" for i in issues)


def test_missing_keyword():
    issues = validate(make(keywords=["别的词"]), ROW, RULES, [])
    assert any(i.code == "missing_keyword" for i in issues)


def test_emoji_and_html():
    issues = validate(make(title="纯棉短袖T恤🔥好看"), ROW, RULES, [])
    assert any(i.code == "emoji_in_title" for i in issues)
    issues2 = validate(make(selling_points=["<b>加厚</b>耐磨", "x", "y"]), ROW, RULES, [])
    assert any(i.code == "html_tag" for i in issues2)


def test_too_similar_is_warn_only():
    issues = validate(make(title="纯棉圆领短袖T恤"), ROW, RULES, [])
    sim = [i for i in issues if i.code == "too_similar"]
    assert sim and sim[0].level == "warn"


def test_duplicate_selling_points():
    issues = validate(make(selling_points=["加厚保暖", "加厚保暖", "亲肤"]), ROW, RULES, [])
    assert any(i.code == "duplicate_sp" for i in issues)


def test_char_len_mixed():
    assert char_len("abc") == 2       # 3 个英文 ≈ 1.5 → 2
    assert char_len("中文ab") == 3
