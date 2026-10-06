import gzip
import json

import pytest

from fedproc_ledger.acquire.pool import build_pool, load_search_days


def write_day(d, day, recs):
    with gzip.open(d / f"{day}.json.gz", "wt") as f:
        json.dump({"day": day, "data": recs}, f)


def rec(nid, sol, agency, day, links=("u",)):
    return {
        "notice_id": nid,
        "solicitation_number": sol,
        "agency": agency,
        "posted_date": day,
        "notice_type": "Solicitation",
        "resource_links_array": list(links),
        "description_text": "x",
    }


def test_dedupe_keeps_latest_notice_and_records_lineage(tmp_path):
    write_day(
        tmp_path,
        "2026-09-01",
        [
            rec("a1", "S-1", "VETERANS AFFAIRS, DEPARTMENT OF.VA.X", "2026-09-01"),
            rec("b", "S-2", "DEPT OF DEFENSE.DEPT OF THE ARMY.Y", "2026-09-01"),
        ],
    )
    write_day(tmp_path, "2026-09-03", [rec("a2", "S-1", "VETERANS AFFAIRS, DEPARTMENT OF.VA.X", "2026-09-03")])
    ranked, stats = build_pool(load_search_days(tmp_path), target=10, max_share=1.0, seed=1)
    row = ranked.set_index("solicitation_number").loc["S-1"]
    assert row["notice_id"] == "a2" and sorted(row["lineage_notice_ids"]) == ["a1", "a2"]
    assert stats["notices_fetched"] == 3 and stats["unique_solicitations"] == 2
    assert set(ranked["department"]) == {"VA", "DOD_ARMY"}


def test_notices_without_links_are_dropped_and_missing_solicitation_numbers_fall_back_to_notice_id(tmp_path):
    write_day(
        tmp_path, "2026-09-01", [rec("n1", "", "X.Y", "2026-09-01"), rec("n2", "S-9", "X.Y", "2026-09-01", links=())]
    )
    ranked, _ = build_pool(load_search_days(tmp_path), target=10, max_share=1.0, seed=1)
    assert list(ranked["solicitation_number"]) == ["n1"]


def test_personal_contact_fields_trip_the_wire(tmp_path):
    write_day(tmp_path, "2026-09-01", [{**rec("n1", "S", "X.Y", "2026-09-01"), "contact_email": "a@b.gov"}])
    with pytest.raises(ValueError):
        load_search_days(tmp_path)


def test_missing_agency_and_missing_solicitation_number_do_not_crash_or_drop_rows(tmp_path):
    write_day(
        tmp_path, "2026-09-01", [{**rec("n1", None, None, "2026-09-01")}, {**rec("n2", "S2", "X.Y", "2026-09-01")}]
    )
    ranked, stats = build_pool(load_search_days(tmp_path), target=10, max_share=1.0, seed=1)
    assert sorted(ranked["solicitation_number"]) == ["S2", "n1"] and stats["unique_solicitations"] == 2
    assert set(ranked["department"]) == {"OTHER"}


def test_month_range_restricts_the_pool(tmp_path):
    write_day(tmp_path, "2024-03-12", [rec("e", "S-early", "X.Y", "2024-03-12")])
    write_day(tmp_path, "2025-03-11", [rec("l", "S-late", "X.Y", "2025-03-11")])
    ranked, stats = build_pool(load_search_days(tmp_path), 10, 1.0, 1, month_from="2024-10", month_to="2026-09")
    assert list(ranked["solicitation_number"]) == ["S-late"] and stats["unique_solicitations"] == 1
