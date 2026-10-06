import json

import httpx
import pytest

from fedproc_ledger.label import openai_chat as O
from fedproc_ledger.label import panel as P


def fake(usage=(1000, 100)):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append((req.headers["authorization"], body))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"labels": []}'}}],
                "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
            },
        )

    return httpx.MockTransport(handler), seen


def test_strict_schema_requires_all_properties_and_forbids_extras():
    s = O.strict_schema(P.schema())
    item = s["properties"]["labels"]["items"]
    assert item["additionalProperties"] is False and item["required"] == ["id", "role"]
    assert s["additionalProperties"] is False and s["required"] == ["labels"]
    assert "additionalProperties" not in P.schema()  # the original is untouched


def test_call_sends_key_schema_and_logs_estimated_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    t, seen = fake((1000, 100))
    chat = O.make_openai_chat(P.schema(), cap_usd=1.0, ledger=tmp_path / "spend.jsonl", transport=t)
    out = chat("gpt-4o-mini", [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    assert out == '{"labels": []}'
    auth, body = seen[0]
    assert (
        auth == "Bearer sk-test"
        and body["temperature"] == 0
        and body["response_format"]["json_schema"]["strict"] is True
    )
    expected = (1000 * 0.15 + 100 * 0.60) / 1e6 * O.SAFETY
    assert O.spent(tmp_path / "spend.jsonl") == pytest.approx(expected)
    assert "sk-test" not in (tmp_path / "spend.jsonl").read_text()  # the key is never logged


def test_cap_blocks_the_call_that_would_exceed_it(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    ledger = tmp_path / "spend.jsonl"
    ledger.write_text(json.dumps({"usd_estimated": 0.999}) + "\n")
    t, seen = fake()
    chat = O.make_openai_chat(P.schema(), cap_usd=1.0, ledger=ledger, transport=t)
    with pytest.raises(O.SpendCapExceeded):
        chat("gpt-4.1-mini", [{"role": "user", "content": "x" * 30000}])
    assert seen == []  # nothing was sent


def test_unknown_model_has_no_price_and_missing_key_is_reported(tmp_path, monkeypatch):
    with pytest.raises(KeyError):
        O.cost("some-new-model", 1, 1)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(O, "load_env", lambda *a, **k: [])
    with pytest.raises(Exception, match="OPENAI_API_KEY"):
        O.make_openai_chat(P.schema(), ledger=tmp_path / "s.jsonl")
