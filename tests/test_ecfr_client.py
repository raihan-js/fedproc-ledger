import json

import httpx
import pytest

from fedproc_ledger.registry.ecfr import EcfrClient, EcfrError, cache_key


def client(handler, tmp_path):
    sleeps: list[float] = []
    c = EcfrClient(tmp_path, transport=httpx.MockTransport(handler), rate_per_s=1000.0, sleep=sleeps.append)
    return c, sleeps


def test_second_identical_request_is_served_from_the_cache(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, json={"content_versions": [{"identifier": "52.1"}]})

    c, _ = client(handler, tmp_path)
    assert c.versions(part="52", **{"issue_date[gte]": "2020-01-01"}) == [{"identifier": "52.1"}]
    assert c.versions(**{"issue_date[gte]": "2020-01-01"}, part="52") == [
        {"identifier": "52.1"}
    ]  # same params, other order
    assert len(calls) == 1 and c.requests == 1 and c.cache_hits == 1
    index = [json.loads(line) for line in (tmp_path / "index.jsonl").read_text().splitlines()]
    assert len(index) == 1 and index[0]["endpoint"] == "/versions/title-48.json"


def test_transient_errors_are_retried_and_other_errors_raise(tmp_path):
    n = {"c": 0}

    def flaky(req):
        n["c"] += 1
        return httpx.Response(503) if n["c"] < 3 else httpx.Response(200, content=b"<xml/>")

    c, sleeps = client(flaky, tmp_path)
    assert c.full_xml("2026-10-02", part="52") == b"<xml/>" and n["c"] == 3 and len(sleeps) == 2
    c2, _ = client(lambda r: httpx.Response(404), tmp_path / "other")
    with pytest.raises(EcfrError):
        c2.structure("2026-10-02")


def test_cache_key_ignores_parameter_order():
    assert cache_key("/x", {"a": 1, "b": 2}) == cache_key("/x", {"b": 2, "a": 1}) != cache_key("/x", {"a": 1, "b": 3})
