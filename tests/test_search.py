import gzip
import json
from datetime import date

import httpx
import pytest

from fedproc_ledger.acquire.budget import CallBudget
from fedproc_ledger.acquire.govcon import BudgetStop, GovConClient
from fedproc_ledger.acquire.search import day_path, fetch_day, with_quota_wait

CFG = {
    "search": {"notice_types": ["Solicitation"], "fields": {"list": ["notice_id", "title"]}},
    "sampling": {"per_day_limit": 2},
}


def client(handler, **kw):
    return GovConClient("k", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def test_fetch_day_pages_and_writes_one_file(tmp_path):
    def handler(req):
        off = int(req.url.params["offset"])
        recs = [{"notice_id": f"n{off}"}, {"notice_id": f"n{off + 1}"}]
        return httpx.Response(
            200, json={"data": recs, "pagination": {"total": 4, "total_is_estimate": False, "has_next": off == 0}}
        )

    c = client(handler)
    res = fetch_day(c, date(2026, 9, 1), CFG, tmp_path)
    assert res["n"] == 4 and res["pages"] == 2 and res["total"] == 4
    with gzip.open(day_path(tmp_path, date(2026, 9, 1)), "rt") as f:
        saved = json.load(f)
    assert [r["notice_id"] for r in saved["data"]] == ["n0", "n1", "n2", "n3"]
    assert saved["params"]["posted_from"] == saved["params"]["posted_to"] == "2026-09-01"
    assert "contact_email" not in saved["params"]["fields"]


def test_fetch_day_is_resumable(tmp_path):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"data": [], "pagination": {"has_next": False}})

    c = client(handler)
    fetch_day(c, date(2026, 9, 2), CFG, tmp_path)
    assert fetch_day(c, date(2026, 9, 2), CFG, tmp_path) == {"day": "2026-09-02", "skipped": True}
    assert calls["n"] == 1


def test_quota_wait_retries_after_the_quota_comes_back():
    state = {"remaining": 100}

    def handler(req):
        return httpx.Response(200, json={"data": []}, headers={"X-RateLimit-Remaining": str(state["remaining"])})

    c = client(handler, budget=CallBudget(reserve=200, remaining=100))
    sleeps: list[float] = []

    def sleep(s):
        sleeps.append(s)
        state["remaining"] = 900  # the vendor's counter resets while we wait

    out = with_quota_wait(c, lambda: c.search(q="x"), sleep=sleep, log=lambda m: None, wait_s=5)
    assert out == {"data": []} and sleeps == [5]


def test_quota_wait_does_not_wait_out_a_local_ceiling():
    c = client(lambda req: httpx.Response(200, json={"data": []}), budget=CallBudget(max_calls=1))
    c.search(q="1")
    with pytest.raises(BudgetStop):
        with_quota_wait(c, lambda: c.search(q="2"), sleep=lambda s: None, log=lambda m: None)
