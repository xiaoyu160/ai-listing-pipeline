import json
from pathlib import Path

import pytest

from ai_listing.config import Config
from ai_listing.llm import MockClient
from ai_listing.llm.base import ChatResult, LLMClient, LLMError
from ai_listing.pipeline import Pipeline
from ai_listing.prompts import PromptTemplate

ROOT = Path(__file__).resolve().parents[1]
ROW = {
    "id": "SP0001",
    "name": "纯棉圆领短袖T恤",
    "category": "女装/T恤",
    "attributes": "100%精梳棉,220g重磅",
    "keywords": "短袖t恤,纯棉t恤",
    "style": "简洁",
}


@pytest.fixture()
def cfg(tmp_path):
    c = Config.load(ROOT / "config/default.yaml")
    c.data["batch"]["checkpoint"] = str(tmp_path / "ckpt.jsonl")
    c.data["batch"]["workers"] = 1
    c.data["provider"]["type"] = "mock"
    return c


@pytest.fixture()
def template():
    return PromptTemplate.load(ROOT / "config/prompts/listing.yaml")


def test_mock_run_ok(cfg, template):
    pipe = Pipeline(cfg, MockClient(), template, banned_words=["全网最低"])
    results = pipe.run([ROW], resume=False)
    assert len(results) == 1
    r = results[0]
    assert r.ok and r.listing
    assert r.listing.title
    assert r.tokens > 0


def test_repair_round_called(cfg, template):
    """第一次返回超长标题，第二次修正 —— 走 repaired 分支。"""

    class BadThenGood(LLMClient):
        model = "fake"

        def __init__(self):
            self.calls = 0

        def chat(self, system, user):
            self.calls += 1
            if self.calls == 1:
                payload = {"title": "超长" * 40, "selling_points": ["a", "b", "c"], "keywords": ["x", "y", "z"]}
            else:
                payload = {
                    "title": "女装纯棉短袖T恤 220g重磅宽松",
                    "selling_points": ["精梳棉亲肤", "220g重磅不透", "落肩宽松显瘦"],
                    "keywords": ["短袖t恤", "纯棉t恤", "宽松T恤"],
                }
            return ChatResult(text=json.dumps(payload, ensure_ascii=False), model="fake", prompt_tokens=10, completion_tokens=20)

    client = BadThenGood()
    pipe = Pipeline(cfg, client, template, banned_words=[])
    r = pipe.run([ROW], resume=False)[0]
    assert client.calls == 2
    assert r.status == "repaired" and r.listing


def test_retry_on_llm_error(cfg, template):
    class Flaky(LLMClient):
        model = "flaky"

        def __init__(self):
            self.calls = 0

        def chat(self, system, user):
            self.calls += 1
            if self.calls < 3:
                raise LLMError("429 too many requests")
            return ChatResult(
                text='{"title":"短袖t恤 纯棉t恤 女装220g重磅落肩","selling_points":["精梳棉亲肤","220g不透","落肩显瘦"],"keywords":["短袖t恤","纯棉t恤","白色t恤"]}',
                model="flaky",
            )

    client = Flaky()
    pipe = Pipeline(cfg, client, template, banned_words=[])
    pipe.backoff_base = 1.0  # 测试里不真的等
    r = pipe.run([ROW], resume=False)[0]
    assert client.calls == 3
    assert r.ok


def test_checkpoint_resume(cfg, template):
    pipe = Pipeline(cfg, MockClient(), template, banned_words=[])
    first = pipe.run([ROW], resume=False)
    assert first[0].ok

    class Explode(LLMClient):
        model = "boom"

        def chat(self, system, user):
            raise AssertionError("不应该再调用模型")

    pipe2 = Pipeline(cfg, Explode(), template, banned_words=[])
    second = pipe2.run([ROW], resume=True)
    assert second[0].ok and second[0].listing


def test_summarize(cfg, template):
    pipe = Pipeline(cfg, MockClient(), template, banned_words=[])
    results = pipe.run([ROW, {**ROW, "id": "SP0002", "name": "冰丝阔腿裤"}], resume=False)
    stats = pipe.summarize(results)
    assert stats["total"] == 2
    assert 0 <= stats["pass_rate"] <= 1
    assert stats["tokens"] > 0
