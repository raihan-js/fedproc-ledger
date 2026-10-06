import pandas as pd

from fedproc_ledger.acquire.stats import acquisition_stats, build_documents

NOTICES = pd.DataFrame(
    [
        {
            "notice_id": "n1",
            "solicitation_number": "S1",
            "posted_date": "2025-03-04",
            "agency": "A",
            "department": "VA",
            "notice_type": "Solicitation",
        },
        {
            "notice_id": "n2",
            "solicitation_number": "S2",
            "posted_date": "2025-04-05",
            "agency": "B",
            "department": "GSA",
            "notice_type": "Solicitation",
        },
    ]
)


def ok(nid, sha, ext=".pdf", n=100):
    return {
        "event": "file",
        "status": "ok",
        "notice_id": nid,
        "sha256": sha * 64,
        "ext": ext,
        "bytes": n,
        "ts": "t",
        "name": "f" + ext,
        "resource_id": "r",
        "source_url": "u",
    }


JOURNAL = [
    ok("n1", "a"),
    {"event": "file", "status": "skipped", "reason": "extension", "notice_id": "n1"},
    {"event": "notice_done", "notice_id": "n1", "n_stored": 1},
    ok("n2", "a"),  # same bytes as n1's file
    ok("n2", "b", ".docx", 50),
    {"event": "file", "status": "failed", "reason": "gone_404", "notice_id": "n2"},
    {"event": "notice_done", "notice_id": "n2", "n_stored": 2},
    {"event": "notice_failed", "notice_id": "n3"},
]


def test_documents_mark_duplicate_content_and_keep_the_unknown_license_flag():
    docs = build_documents(JOURNAL, NOTICES)
    assert list(docs["doc_id"]) == ["a" * 16, "a" * 16, "b" * 16]
    assert list(docs["duplicate"]) == [False, True, False]
    assert set(docs["license_flag"]) == {"unknown"} and docs.iloc[2]["file_type"] == "docx"


def test_stats_count_what_happened_to_every_file():
    docs = build_documents(JOURNAL, NOTICES)
    s = acquisition_stats(
        JOURNAL,
        docs,
        NOTICES,
        [{"path": "/opportunities/search", "status": 200}, {"path": "/opportunities/x/attachments", "status": 429}],
    )
    assert s["notices_done"] == 2 and s["notices_failed_attachment_list"] == 1
    assert s["files_by_status"] == {"ok": 3, "skipped": 1, "failed": 1}
    assert s["files_not_stored_by_reason"] == {"skipped:extension": 1, "failed:gone_404": 1}
    assert s["documents_rows"] == 3 and s["documents_unique_sha256"] == 2 and s["bytes_unique"] == 150
    assert s["api_calls"]["total"] == 2 and s["api_calls"]["by_status"] == {"200": 1, "429": 1}
