from fedproc_ledger.registry.build import REG_CODE, _sort_key, dedupe_numbers, expand_ranges, x52_parts


def test_natural_section_order_with_mixed_pieces():
    nums = ["52.219-14", "52.219-9", "52.204-1", "252.204-7012", "52.212-5", "52.2xx-1", "52.219-9a", "52.1"]
    got = sorted(nums, key=_sort_key)
    assert got.index("52.219-9") < got.index("52.219-14") and got.index("52.1") < got.index("52.204-1")
    assert got.index("52.204-1") < got.index("52.212-5") < got.index("52.219-9")


def test_x52_parts_come_from_the_structure_with_their_chapter():
    tree = {
        "type": "title", "identifier": "48",
        "children": [
            {"type": "chapter", "identifier": "1", "label": " Chapter 1\u2014Federal Acquisition Regulation", "children": [
                {"type": "part", "identifier": "52", "label": "Part 52"}, {"type": "part", "identifier": "51", "label": "Part 51"}]},
            {"type": "chapter", "identifier": "14", "label": " Chapter 14\u2014Department of the Interior", "children": [
                {"type": "part", "identifier": "1452", "label": "Part 1452"}]},
        ],
    }  # fmt: skip
    parts = x52_parts(tree)
    assert [(p["part"], p["regulation"]) for p in parts] == [("52", "FAR"), ("1452", "CH14")]
    assert parts[1]["regulation_name"].strip().endswith("Department of the Interior") and "1" in REG_CODE


def test_build_part_end_to_end_with_a_prehistory_snapshot_and_a_removed_section(tmp_path):
    import httpx

    from fedproc_ledger.registry.build import build_part
    from fedproc_ledger.registry.ecfr import EcfrClient

    def xml(*sections):
        return "<ECFR>" + "".join(sections) + "</ECFR>"

    def sec(num, title, kind, date):
        return (
            f'<DIV8 N="{num}" TYPE="SECTION"><HEAD>{num} {title}.</HEAD><P>As prescribed in 1.1, insert the following {kind}:</P>'
            f"<EXTRACT><HD1>{title} ({date})</HD1></EXTRACT><HD3>(End of {kind})</HD3></DIV8>"
        )

    snapshots = {
        "2020-01-01": xml(
            sec("52.100-1", "Alpha", "clause", "JAN 2020"), sec("52.100-2", "Beta", "provision", "JAN 2020")
        ),
        "2023-05-05": xml(sec("52.100-1", "Alpha", "clause", "MAY 2023")),  # Beta removed, Alpha re-dated
        "2026-10-02": xml(sec("52.100-1", "Alpha", "clause", "MAY 2023")),
    }
    versions = [
        {
            "identifier": "52.100-1",
            "date": "2016-12-22",
            "removed": False,
            "issue_date": "2016-12-22",
            "amendment_date": "2016-12-22",
        },
        {
            "identifier": "52.100-1",
            "date": "2020-01-01",
            "removed": False,
            "issue_date": "2020-01-01",
            "amendment_date": "2020-01-01",
        },
        {
            "identifier": "52.100-1",
            "date": "2023-05-05",
            "removed": False,
            "issue_date": "2023-05-05",
            "amendment_date": "2023-05-05",
        },
        {
            "identifier": "52.100-2",
            "date": "2020-01-01",
            "removed": False,
            "issue_date": "2020-01-01",
            "amendment_date": "2020-01-01",
        },
        {
            "identifier": "52.100-2",
            "date": "2023-05-05",
            "removed": True,
            "issue_date": "2023-05-05",
            "amendment_date": "2023-05-05",
        },
    ]

    def handler(req):
        if req.url.path.endswith("/versions/title-48.json"):
            return httpx.Response(200, json={"content_versions": versions})
        day = req.url.path.split("/full/")[1].split("/")[0]
        return httpx.Response(200, content=snapshots[day].encode()) if day in snapshots else httpx.Response(404)

    from datetime import date

    c = EcfrClient(tmp_path, transport=httpx.MockTransport(handler), rate_per_s=1000.0)
    part = {"part": "52", "chapter": "1", "regulation": "FAR", "regulation_name": "Chapter 1"}
    rows, stats = build_part(c, part, "2026-10-02", date(2016, 1, 1), date(2026, 10, 2), log=lambda m: None)
    by = {r["number"]: r for r in rows}
    assert stats["snapshot_unavailable_dates"] == ["2016-12-22"]
    alpha, beta = by["52.100-1"], by["52.100-2"]
    assert alpha["status"] == "active" and alpha["current_date"] == "2023-05" and alpha["kind"] == "clause"
    assert [v["clause_date"] for v in alpha["versions"]] == [None, "2020-01", "2023-05"]
    assert alpha["versions"][0]["snapshot_unavailable"] is True and alpha["versions"][1]["effective_to"] == "2023-05-04"
    assert (
        beta["status"] == "removed"
        and beta["removed"] is True
        and beta["current_date"] is None
        and beta["kind"] == "provision"
    )


def test_range_identified_sections_are_expanded_into_single_numbers():
    base = {"status": "removed", "versions": [], "title": "[Reserved]", "source_range": None}
    rows = [{**base, "number": "52.208-1 - 52.208-3"}, {**base, "number": "52.212-4"}, {**base, "number": "52.203-4 - 52.204-2"},
            {**base, "number": "252.212-7000 - 252.212-7001"}]  # fmt: skip
    got = expand_ranges(rows)
    assert [r["number"] for r in got] == [
        "52.208-1",
        "52.208-2",
        "52.208-3",
        "52.212-4",
        "52.203-4 - 52.204-2",
        "252.212-7000",
        "252.212-7001",
    ]
    assert (
        got[1]["source_range"] == "52.208-1 - 52.208-3"
        and got[3]["source_range"] is None
        and got[0]["status"] == "removed"
    )


def test_a_number_listed_under_two_range_spellings_becomes_one_row_with_the_best_status():
    v = lambda d: {"effective_from": d, "effective_to": None, "removed": False}  # noqa: E731
    rows = [
        {"number": "52.208-2", "status": "removed", "versions": [v("2017-01-01")], "source_range": "52.208-1-52.208-3"},
        {
            "number": "52.208-2",
            "status": "reserved",
            "versions": [v("2017-01-01"), v("2020-05-05")],
            "source_range": "52.208-1 - 52.208-3",
        },
        {"number": "52.212-4", "status": "active", "versions": [v("2017-01-01")], "source_range": None},
    ]
    got = {r["number"]: r for r in dedupe_numbers(rows)}
    assert (
        len(got) == 2
        and got["52.208-2"]["status"] == "reserved"
        and got["52.208-2"]["source_range"] == "52.208-1 - 52.208-3"
    )
    assert [x["effective_from"] for x in got["52.208-2"]["versions"]] == ["2017-01-01", "2020-05-05"]
