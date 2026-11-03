import json

import pytest

from ai_listing.schema import Listing, SchemaError, extract_json


def test_extract_plain_json():
    obj = extract_json('{"title": "纯棉T恤 220g重磅 宽松落肩"}')
    assert obj["title"].startswith("纯棉")


def test_extract_from_code_block():
    text = '好的，结果如下：\n```json\n{"title": "A", "selling_points": ["x"]}\n```\n以上。'
    assert extract_json(text)["title"] == "A"


def test_extract_with_noise_around():
    text = '模型思考…… {"title": "B"} 结束'
    assert extract_json(text)["title"] == "B"


def test_extract_empty_raises():
    with pytest.raises(SchemaError):
        extract_json("   ")


def test_listing_normalize():
    payload = {"title": " 测试商品 ", "selling_points": ["a", "a", "b，"], "keywords": "k1"}
    lst = Listing.from_payload(payload)
    assert lst.title == "测试商品"
    assert lst.selling_points == ["a", "b"]
    assert lst.keywords == ["k1"]


def test_missing_title_raises():
    with pytest.raises(SchemaError):
        Listing.from_payload({"selling_points": []})


def test_roundtrip_dict():
    lst = Listing(title="t", selling_points=["a"], keywords=["k"], reason="r")
    assert Listing(**json.loads(json.dumps(lst.to_dict(), ensure_ascii=False))) == lst
