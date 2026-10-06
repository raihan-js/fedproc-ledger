import hashlib
import json

import httpx

from fedproc_ledger.acquire.download import DiskCapReached, Journal, download_notice, fetch_to_store
from fedproc_ledger.acquire.ratelimit import TokenBucket

PDF = b"%PDF-1.7\n" + b"x" * 200


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True, max_redirects=5)


def test_redirect_is_followed_with_get_and_the_file_is_stored_by_sha256(tmp_path):
    seen = []

    def handler(req):
        seen.append((req.method, str(req.url)))
        if "front-door" in str(req.url):
            return httpx.Response(303, headers={"location": "https://s3.example/obj?sig=1"})
        return httpx.Response(200, content=PDF, headers={"content-disposition": 'attachment; filename="RFP.pdf"'})

    res = fetch_to_store(
        client(handler), "https://front-door.example/f/1", tmp_path, filename="x", max_bytes=10_000, bucket=None
    )
    sha = hashlib.sha256(PDF).hexdigest()
    assert res["status"] == "ok" and res["sha256"] == sha and res["ext"] == ".pdf" and res["name"] == "RFP.pdf"
    assert (tmp_path / f"{sha}.pdf").read_bytes() == PDF
    assert [m for m, _ in seen] == ["GET", "GET"]  # never HEAD


def test_oversize_by_header_and_by_stream_are_skipped_and_leave_nothing_behind(tmp_path):
    big = httpx.Response(200, content=b"%PDF-" + b"x" * 5000, headers={"content-length": "5005"})
    assert (
        fetch_to_store(client(lambda r: big), "https://x/1", tmp_path, filename="a", max_bytes=1000, bucket=None)[
            "reason"
        ]
        == "too_large"
    )
    nolen = httpx.Response(200, content=b"%PDF-" + b"x" * 5000)
    res = fetch_to_store(client(lambda r: nolen), "https://x/2", tmp_path, filename="a", max_bytes=1000, bucket=None)
    assert res["reason"] == "too_large" and list(tmp_path.iterdir()) == []


def test_wrong_bytes_gone_and_denied_are_recorded_not_raised(tmp_path):
    png = httpx.Response(200, content=b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    assert fetch_to_store(
        client(lambda r: png), "https://x/1", tmp_path, filename="a.pdf", max_bytes=1000, bucket=None
    )["reason"].startswith("not_a_kept_type")
    assert (
        fetch_to_store(
            client(lambda r: httpx.Response(404)), "https://x/2", tmp_path, filename="a", max_bytes=1000, bucket=None
        )["reason"]
        == "gone_404"
    )
    assert (
        fetch_to_store(
            client(lambda r: httpx.Response(403)), "https://x/3", tmp_path, filename="a", max_bytes=1000, bucket=None
        )["reason"]
        == "denied_403"
    )


def test_transient_errors_are_retried_then_recorded(tmp_path):
    n = {"c": 0}

    def flaky(req):
        n["c"] += 1
        return httpx.Response(503) if n["c"] < 3 else httpx.Response(200, content=PDF)

    assert (
        fetch_to_store(client(flaky), "https://x/1", tmp_path, filename="a", max_bytes=10_000, bucket=None)["status"]
        == "ok"
        and n["c"] == 3
    )
    res = fetch_to_store(
        client(lambda r: httpx.Response(500)), "https://x/2", tmp_path, filename="a", max_bytes=10_000, bucket=None
    )
    assert res["status"] == "failed" and res["reason"].startswith("transient")


def test_duplicate_content_is_stored_once(tmp_path):
    a = fetch_to_store(
        client(lambda r: httpx.Response(200, content=PDF)),
        "https://x/1",
        tmp_path,
        filename="a",
        max_bytes=10_000,
        bucket=None,
    )
    b = fetch_to_store(
        client(lambda r: httpx.Response(200, content=PDF)),
        "https://x/2",
        tmp_path,
        filename="b",
        max_bytes=10_000,
        bucket=None,
    )
    assert a["duplicate"] is False and b["duplicate"] is True and len(list(tmp_path.iterdir())) == 1


def test_notice_is_journaled_and_resumable_and_disk_cap_stops(tmp_path):
    j = Journal(tmp_path / "j.jsonl")
    notice = {"notice_id": "n1", "solicitation_number": "S1"}
    sel = [{"url": "https://x/1", "filename": "a.pdf", "resource_id": "r1", "size_bytes": 205}]
    skipped = [{"filename": "p.xlsx", "resource_id": "r2", "reason": "extension"}]
    files = tmp_path / "files"
    download_notice(
        client(lambda r: httpx.Response(200, content=PDF)),
        notice,
        sel,
        skipped,
        files,
        j,
        TokenBucket(1000.0),
        10_000,
        10**9,
    )
    events = [json.loads(line) for line in (tmp_path / "j.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == ["file", "file", "notice_done"] and events[-1]["n_stored"] == 1
    assert Journal(tmp_path / "j.jsonl").done_notices == {"n1"}
    try:
        download_notice(
            client(lambda r: httpx.Response(200, content=PDF)),
            {"notice_id": "n2"},
            sel,
            [],
            files,
            j,
            None,
            10_000,
            cap_bytes=100,
        )
    except DiskCapReached:
        pass
    else:
        raise AssertionError("the disk cap must stop the run")


def test_run_download_end_to_end_with_mocks(tmp_path):
    from fedproc_ledger.acquire.download import run_download
    from fedproc_ledger.acquire.govcon import GovConClient

    def api(req):
        nid = req.url.path.split("/")[-2]
        if nid == "bad":
            return httpx.Response(404, json={"error": "no such notice"})
        files = [
            {
                "url": f"https://files.example/{nid}/a",
                "filename": "Solicitation.pdf",
                "resource_id": "r",
                "size_bytes": 209,
            },
            {"url": f"https://files.example/{nid}/b", "filename": "data.xlsx", "resource_id": "s", "size_bytes": 50},
        ]
        return httpx.Response(200, json={"files": files}, headers={"X-RateLimit-Remaining": "900"})

    def files(req):
        return httpx.Response(200, content=PDF + str(req.url).encode())

    c = GovConClient("k", transport=httpx.MockTransport(api), sleep=lambda s: None)
    cfg = {
        "files": {"max_per_notice": 6, "max_bytes_per_notice_mb": 80, "max_total_gb": 1},
        "download": {"keep_extensions": [".pdf", ".docx", ".doc", ".txt"], "max_file_mb": 50},
    }
    j = Journal(tmp_path / "j.jsonl")
    notices = [{"notice_id": "n1"}, {"notice_id": "bad"}, {"notice_id": "n2"}]
    out = run_download(c, client(files), notices, cfg, j, tmp_path / "files", workers=2, log=lambda m: None)
    assert out["notices"] == 2 and out["attachments_failed"] == 1 and out["stopped"] is None
    assert Journal(tmp_path / "j.jsonl").done_notices == {
        "n1",
        "n2",
    }  # the failed one is not done, so a re-run retries it
    assert len(list((tmp_path / "files").iterdir())) == 2
    # a second run does nothing for finished notices
    again = run_download(
        c, client(files), notices, cfg, Journal(tmp_path / "j.jsonl"), tmp_path / "files", workers=2, log=lambda m: None
    )
    assert again["notices"] == 0 and again["attachments_failed"] == 1


def test_a_file_that_takes_too_long_is_skipped_not_waited_for(tmp_path):
    t = {"now": 0.0}

    def clock():
        t["now"] += 100.0  # every read of the clock is 100 s later
        return t["now"]

    body = b"%PDF-" + b"x" * 5000
    res = fetch_to_store(
        client(lambda r: httpx.Response(200, content=body)),
        "https://x/1",
        tmp_path,
        filename="a",
        max_bytes=10**6,
        bucket=None,
        max_seconds=50,
        clock=clock,
    )
    assert res == {"status": "skipped", "reason": "too_slow"} and list(tmp_path.iterdir()) == []
