import json
from pathlib import Path

import pytest

from fedproc_ledger.candidates.generate import generate_page_candidates
from fedproc_ledger.candidates.patterns import extract_clause_numbers

REG = {"52.243-5": "active", "52.212-4": "active", "52.203-1": "reserved", "252.204-7012": "active"}


def gen(text, reg=REG):
    return generate_page_candidates("doc", 1, text, reg)


def nums(text):
    return [c.number for c in gen(text)]


def test_a_checked_checklist_line_from_a_real_solicitation():
    (c,) = gen("⟦X⟧ FAR 52.243-5, Changes and Changed Conditions (Nov 2025)")
    assert (c.number, c.regulation, c.prefix, c.box_marker, c.cited_date) == (
        "52.243-5",
        "FAR",
        "FAR",
        "⟦X⟧",
        "2025-11",
    )
    assert c.in_registry is True and c.registry_status == "active" and c.alternate is None and not c.from_range


def test_an_alternate_written_before_the_number_with_its_own_date():
    (c,) = gen("⟦ ⟧ Alternate I (Nov 2025) of 52.212-4")
    assert (
        c.number == "52.212-4" and c.alternate == "Alternate I" and c.cited_date == "2025-11" and c.box_marker == "⟦ ⟧"
    )
    (d,) = gen("52.219-9, Small Business Subcontracting Plan (JAN 2025) Alternate II")
    assert d.alternate == "Alternate II" and d.cited_date == "2025-01"


def test_hyphen_variants_and_stray_spaces_that_vetr_misses():
    assert nums("52.212‑4") == ["52.212-4"] and nums("52.212–4") == ["52.212-4"] and nums("52.212−4") == ["52.212-4"]
    assert nums("52. 212-4") == ["52.212-4"] and nums("52.212 -4") == ["52.212-4"] and nums("52.212- 4") == ["52.212-4"]
    assert extract_clause_numbers("52.212‑4") == ["52.212"]  # what the status quo returns for the same text


def test_prefix_words_and_supplements():
    c = gen("DFARS 252.204-7012 and NFS1852.219-73 and clause 52.203-13")
    assert [(x.number, x.prefix, x.regulation) for x in c] == [
        ("252.204-7012", "DFARS", "DFARS"),
        ("1852.219-73", "NFS", "NFS"),
        ("52.203-13", "clause", "FAR"),
    ]


def test_subparagraph_references_keep_the_base_number():
    (c,) = gen("52.212-5(b)(16) applies")
    assert c.number == "52.212-5" and c.subpara == "(b)(16)" and c.raw == "52.212-5(b)(16)"


def test_ranges_are_expanded_and_flagged():
    got = gen("clauses 52.219-1 through 52.219-4 apply")
    assert [(c.number, c.from_range) for c in got] == [
        ("52.219-1", False),
        ("52.219-2", True),
        ("52.219-3", True),
        ("52.219-4", False),
    ]
    short = gen("52.219-1 thru -3")
    assert [(c.number, c.from_range) for c in short] == [("52.219-1", False), ("52.219-2", True), ("52.219-3", True)]
    assert len(gen("52.219-1 through 52.219-500")) == 2  # absurdly long ranges are not expanded


def test_non_clause_look_alikes_are_emitted_with_hints():
    assert gen("Price is $52.212 total")[0].nonclause_hints == ["money"]
    assert "longer_number" in gen("Total of 1,252.204 units")[0].nonclause_hints
    assert (
        nums("version 52.1.3") == []
        and nums("1852.219-73")[0] == "1852.219-73"
        and "52.219-73" not in nums("1852.219-73")
    )


def test_deviation_marker_and_a_date_that_wrapped_to_the_next_line():
    (c,) = gen("52.219-14 Limitations on Subcontracting (DEVIATION OCT 2025)")
    assert c.deviation_marker.startswith("(DEVIATION") and c.cited_date == "2025-10"
    (w,) = gen("52.204-21 Basic Safeguarding\n(NOV 2021) rest of text")
    assert w.cited_date == "2021-11"


def test_offsets_point_at_the_number_in_the_page_text():
    page = "line one\n⟦ ⟧ FAR 52.203-6 Restrictions\nline three 252.204-7012"
    for c in gen(page):
        assert page[c.char_start : c.char_end].startswith(c.number[:6])
    assert [page[c.char_start : c.char_end] for c in gen(page)] == ["52.203-6", "252.204-7012"]


def test_unknown_numbers_are_in_registry_false_and_reserved_is_kept_distinct():
    c = gen("52.203-1 and 52.999-9")
    assert (c[0].in_registry, c[0].registry_status) == (True, "reserved") and (
        c[1].in_registry,
        c[1].registry_status,
    ) == (False, None)
    assert gen("52.212-4", None)[0].in_registry is None  # no registry given


CASES = json.loads((Path(__file__).parent / "fixtures" / "vetr_parity_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("text", CASES)
def test_every_number_the_status_quo_finds_is_found_or_extended_never_lost(text):
    ours = {c.number for c in gen(text)}
    for v in extract_clause_numbers(text):
        assert v in ours or any(o.startswith(v) for o in ours), (text, v, ours)
