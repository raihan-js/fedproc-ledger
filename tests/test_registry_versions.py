from datetime import date

import httpx

from fedproc_ledger.registry import versions as V
from fedproc_ledger.registry.ecfr import EcfrClient
from fedproc_ledger.registry.versions import fetch_part_versions, section_intervals


def rec(ident, d, removed=False, issue=None):
    return {"identifier": ident, "date": d, "amendment_date": d, "issue_date": issue or d, "removed": removed}


def test_windows_are_halved_until_no_response_hits_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(V, "CAP", 3)
    all_records = [rec("52.1", f"2020-01-{d:02d}") for d in range(1, 11)]  # 10 records, cap 3

    def handler(req):
        gte, lte = req.url.params["issue_date[gte]"], req.url.params["issue_date[lte]"]
        got = [r for r in all_records if gte <= r["issue_date"] <= lte][:3]  # the API truncates at the cap
        return httpx.Response(200, json={"content_versions": got})

    c = EcfrClient(tmp_path, transport=httpx.MockTransport(handler), rate_per_s=1000.0)
    warnings: list[str] = []
    got = fetch_part_versions(c, "52", date(2020, 1, 1), date(2020, 1, 31), warnings)
    assert sorted(r["date"] for r in got) == sorted(r["date"] for r in all_records) and warnings == []


def test_a_single_day_at_the_cap_is_reported_not_hidden(tmp_path, monkeypatch):
    monkeypatch.setattr(V, "CAP", 2)
    day = [rec("a", "2020-01-01"), rec("b", "2020-01-01")]
    c = EcfrClient(
        tmp_path,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"content_versions": day})),
        rate_per_s=1000.0,
    )
    warnings: list[str] = []
    fetch_part_versions(c, "52", date(2020, 1, 1), date(2020, 1, 1), warnings)
    assert len(warnings) == 1 and "cap" in warnings[0]


def test_intervals_end_the_day_before_the_next_version():
    recs = [
        rec("52.219-14", "2017-01-01"),
        rec("52.219-14", "2019-06-03"),
        rec("52.219-14", "2022-10-28"),
        rec("52.203-1", "2017-01-01"),
        rec("52.203-1", "2018-02-02", removed=True),
    ]
    iv = section_intervals(recs)
    assert iv["52.219-14"] == [
        {"effective_from": "2017-01-01", "effective_to": "2019-06-02", "removed": False},
        {"effective_from": "2019-06-03", "effective_to": "2022-10-27", "removed": False},
        {"effective_from": "2022-10-28", "effective_to": None, "removed": False},
    ]
    assert iv["52.203-1"][-1] == {"effective_from": "2018-02-02", "effective_to": None, "removed": True}
