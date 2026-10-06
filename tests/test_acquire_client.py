import json

import httpx
import pytest

from fedproc_ledger.acquire.budget import CallBudget
from fedproc_ledger.acquire.govcon import BudgetStop, GovConClient, GovConError, PlanLimitError
from fedproc_ledger.acquire.ratelimit import TokenBucket
from fedproc_ledger.envfile import MissingSecret, load_env, parse_env, require

KEY = "sk-test-SECRET-1234567890"


def make(handler, **kw):
    sleeps: list[float] = []
    c = GovConClient(KEY, transport=httpx.MockTransport(handler), sleep=sleeps.append, **kw)
    return c, sleeps


def ok(data=None, remaining=None, **pg):
    headers = {"X-RateLimit-Remaining": str(remaining)} if remaining is not None else {}
    return httpx.Response(200, json={"data": data or [], "pagination": {"has_next": False, **pg}}, headers=headers)


def test_key_is_sent_as_bearer_but_never_logged(tmp_path):
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        return ok([{"notice_id": "a"}], remaining=900)

    log = tmp_path / "calls.jsonl"
    c, _ = make(handler, log_path=log)
    c.search(posted_from="2024-01-01", has_attachments=True)
    assert seen["auth"] == f"Bearer {KEY}"
    text = log.read_text()
    assert KEY not in text and "Authorization" not in text
    entry = json.loads(text.splitlines()[0])
    assert entry["params"]["has_attachments"] == "true" and entry["remaining"] == 900 and entry["status"] == 200


def test_key_never_appears_in_an_exception():
    c, _ = make(lambda req: httpx.Response(404, json={"error": "nope"}))
    with pytest.raises(GovConError) as e:
        c.search(q="x")
    assert KEY not in str(e.value) and e.value.status == 404


def test_429_is_retried_with_retry_after_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "7"}) if calls["n"] < 3 else ok([{"x": 1}])

    c, sleeps = make(handler)
    assert c.search(q="x")["data"] == [{"x": 1}]
    assert calls["n"] == 3 and sleeps == [7.0, 7.0] and c.budget.spent_total == 3


def test_5xx_gives_up_after_max_attempts():
    c, sleeps = make(lambda req: httpx.Response(503), max_attempts=3)
    with pytest.raises(GovConError) as e:
        c.search(q="x")
    assert e.value.status == 503 and c.budget.spent_total == 3 and len(sleeps) == 2


def test_402_is_a_plan_limit_and_is_not_retried():
    c, sleeps = make(lambda req: httpx.Response(402, json={"error": "limit above plan maximum"}))
    with pytest.raises(PlanLimitError):
        c.search(limit=5000)
    assert c.budget.spent_total == 1 and sleeps == []


def test_budget_reserve_stops_before_sending():
    sent = {"n": 0}

    def handler(req):
        sent["n"] += 1
        return ok(remaining=120)

    c, _ = make(handler, budget=CallBudget(reserve=100))
    c.search(q="a")  # remaining 120 > reserve 100
    for _ in range(20):
        c.budget.record(None)  # local decrements: the estimate falls from 120 to 100, the reserve
    with pytest.raises(BudgetStop):
        c.search(q="b")
    assert sent["n"] == 1


def test_unknown_quota_stops_after_the_blind_allowance():
    b = CallBudget(reserve=50, blind_allowance=3)
    c, _ = make(lambda req: ok(), budget=b)
    for _ in range(3):
        c.search(q="x")
    with pytest.raises(BudgetStop):
        c.search(q="x")


def test_local_ceiling_applies_even_without_a_reserve():
    c, _ = make(lambda req: ok(remaining=10_000), budget=CallBudget(max_calls=2))
    c.search(q="1")
    c.search(q="2")
    with pytest.raises(BudgetStop):
        c.search(q="3")


def test_pagination_walks_until_has_next_is_false():
    def handler(req):
        off = int(req.url.params["offset"])
        return httpx.Response(200, json={"data": [{"i": off}] * 2, "pagination": {"has_next": off < 4}})

    c, _ = make(handler)
    pages = list(c.iter_search_pages(2, q="x"))
    assert [o for o, _ in pages] == [0, 2, 4]


def test_token_bucket_waits_for_tokens():
    now = {"t": 0.0}
    waits: list[float] = []

    def sleep(s):
        waits.append(s)
        now["t"] += s

    b = TokenBucket(rate_per_s=2.0, capacity=1.0, clock=lambda: now["t"], sleep=sleep)
    b.acquire()
    b.acquire()
    b.acquire()
    assert waits == [0.5, 0.5]


def test_env_parsing_handles_comments_quotes_and_blank_values(tmp_path):
    text = 'A=1   # note\nB="two words"\n# c\nGOVCON_API_KEY=            # required\nexport D=x\n'
    assert parse_env(text) == {"A": "1", "B": "two words", "GOVCON_API_KEY": "", "D": "x"}
    p = tmp_path / ".env"
    p.write_text("GOVCON_API_KEY=abc # c\nEMPTY=\n")
    env: dict[str, str] = {"PRE": "set"}
    assert load_env(p, env) == ["GOVCON_API_KEY"] and env["GOVCON_API_KEY"] == "abc"
    with pytest.raises(MissingSecret) as e:
        require("NOPE", env)
    assert "abc" not in str(e.value)


def test_refresh_quota_works_at_the_reserve_and_updates_remaining():
    c, _ = make(lambda req: ok(remaining=777), budget=CallBudget(reserve=1000, remaining=5))
    with pytest.raises(BudgetStop):
        c.search(q="x")
    assert c.refresh_quota() == 777
    c.budget.reserve = 100
    assert c.budget.stop_reason() is None
