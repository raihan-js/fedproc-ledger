"""Rules v1.1 (D-034): paragraph (a) of 52.212-5, inherited sub-item state, SF 1449 block 27. Snippets are cut from real round-2/3 documents."""

import pandas as pd
import pytest

from fedproc_ledger.label import commands as LC


def _make(tmp_path, monkeypatch, lines, numbers):
    """One page of `lines`; one candidate per (line index, number) in `numbers`."""
    rules_dir, pages_dir = tmp_path / "rules", tmp_path / "pages"
    rules_dir.mkdir()
    pages_dir.mkdir()
    rows = []
    for k, (li, num) in enumerate(numbers):
        rows.append(
            {
                "cand_id": f"d-p1-{k}",
                "page": 1,
                "line_no": li,
                "number": num,
                "raw": num,
                "line_text": lines[li],
                "char_start": k,
                "from_range": False,
            }
        )
    pd.DataFrame(rows).to_parquet(rules_dir / "d.parquet")
    pd.DataFrame([{"page": 1, "text_layout": "\n".join(lines)}]).to_parquet(pages_dir / "d.parquet")
    monkeypatch.setattr(LC, "PROCESSED", tmp_path)
    return {r["cand_id"]: r["number"] for r in rows}


def test_para_a_items_are_binding_but_roman_flowdown_is_not(tmp_path, monkeypatch):
    lines = [
        "(a) The Contractor shall comply with the following Federal Acquisition Regulation (FAR) clauses,",
        "(1) 52.203-19, Prohibition on Requiring Certain Internal Confidentiality Agreements (Jan 2017)",
        "(2) 52.204-23, Prohibition on Contracting for Hardware, Software, and Services (Dec 2023)",
        "(b) Subject to the terms of this contract, the clauses below are incorporated:",
        "(xii) 52.222-41, Service Contract Labor Standards (Aug 2018)",
    ]
    ids = _make(tmp_path, monkeypatch, lines, [(1, "52.203-19"), (2, "52.204-23"), (4, "52.222-41")])
    got = {ids[c] for c in LC.para_a_ids("d")}
    assert got == {"52.203-19", "52.204-23"}


def test_para_a_takes_lost_marker_lines_but_not_real_boxes(tmp_path, monkeypatch):
    lines = [
        "(a) The Contractor shall comply with the following FAR clauses:",
        "⟦?⟧ (3) 52.204-25, Prohibition on Contracting for Certain Telecommunications",
        "⟦ ⟧ (4) 52.209-10, Prohibition on Contracting with Inverted Domestic Corporations",
    ]
    ids = _make(tmp_path, monkeypatch, lines, [(1, "52.204-25"), (2, "52.209-10")])
    assert {ids[c] for c in LC.para_a_ids("d")} == {
        "52.204-25"
    }  # no checkbox exists in (a): a lost marker is an artefact


def test_para_a_survives_non_breaking_spaces_and_wrapped_heading(tmp_path, monkeypatch):
    lines = [
        "(a)\xa0The Contractor\xa0shall\xa0comply with the following Federal\xa0Acquisition\xa0Regulation (FAR) clauses:",
        "(1)\xa052.203-19, Prohibition on Requiring Certain Internal Confidentiality Agreements",
        "(6)\xa0\xa0\xa052.233-3, Protest After Award (Aug 1996)",
    ]
    ids = _make(tmp_path, monkeypatch, lines, [(1, "52.203-19"), (2, "52.233-3")])
    assert {ids[c] for c in LC.para_a_ids("d")} == {"52.203-19", "52.233-3"}


@pytest.mark.parametrize(
    ("parent", "expected"),
    [("_X_ (36)", "CHECKLIST_SELECTED"), ("__ (35)", "CHECKLIST_NOT_SELECTED"), ("⟦X⟧ (39)", "CHECKLIST_SELECTED")],
)
def test_lost_marker_subitem_inherits_parent_state(tmp_path, monkeypatch, parent, expected):
    lines = [parent, "⟦?⟧ (i) 52.222-36, Equal Opportunity for Workers with Disabilities (Jun 2020)"]
    ids = _make(tmp_path, monkeypatch, lines, [(1, "52.222-36")])
    assert LC.inherited_ids("d") == {next(iter(ids)): expected}


def test_block_27_glyph_decides_numbers_on_its_lines(tmp_path, monkeypatch):
    lines = [
        "⟦X⟧ 27a. SOLICITATION INCORPORATES BY REFERENCE (FEDERAL ACQUISITION REGULATION) FAR 52.212-1, 52.212-4.",
        "AND 52.212-5 ARE ATTACHED.     ADDENDA",
        "⟦ ⟧ 27b. CONTRACT/PURCHASE ORDER INCORPORATES BY REFERENCE FAR 52.212-4. FAR 52.212-5 IS ATTACHED.",
        "⟦ ⟧ ARE",
    ]
    ids = _make(tmp_path, monkeypatch, lines, [(0, "52.212-1"), (1, "52.212-5"), (2, "52.212-4")])
    got = LC.inherited_ids("d")
    by_num = {ids[c]: s for c, s in got.items()}
    assert by_num["52.212-1"] == "CHECKLIST_SELECTED"
    assert by_num["52.212-5"] == "CHECKLIST_SELECTED"  # continuation line of block 27a
    assert by_num["52.212-4"] == "CHECKLIST_NOT_SELECTED"  # block 27b is empty


def test_text_rules(tmp_path, monkeypatch):
    lines = [
        "(f) Buy American Certificate. (Applies only if the clause at Federal Acquisition Regulation (FAR)",
        "52.225-1, Buy American-Supplies, is included in this solicitation.)",
        "(2) Alternate II. If Alternate II to the clause at FAR 52.225-3 is included in this solicitation,",
        '"Covered telecommunications equipment" has the meaning provided in the clause at 52.204-25, Prohibition',
        "in paragraph (c)(2) of the provision at 52.204-26, or in paragraph (v)(2)(ii) of the provision at 52.212-3.",
        "FAR Clause 52.222-55, Minimum Wages for Contractor Workers Under Executive Order 14026",
        "is applicable for this solicitation.",
        "FAR 52.222-41, Service Contract Labor Standards (Aug 2018) lists the rates.",
    ]
    nums = [
        (1, "52.225-1"),
        (2, "52.225-3"),
        (3, "52.204-25"),
        (4, "52.204-26"),
        (4, "52.212-3"),
        (5, "52.222-55"),
        (7, "52.222-41"),
    ]
    ids = _make(tmp_path, monkeypatch, lines, nums)
    got = {ids[c]: v for c, v in LC.text_rule_ids("d").items()}
    assert (
        got["52.225-1"] == "NOT_BINDING"
    )  # wrapped "(Applies only if the clause at ... (FAR)" then number on the next line
    assert got["52.225-3"] == "NOT_BINDING"
    assert got["52.204-25"] == "NOT_BINDING"
    assert got["52.204-26"] == "NOT_BINDING"
    assert got["52.212-3"] == "NOT_BINDING"
    assert got["52.222-55"] == "BINDING"
    assert "52.222-41" not in got  # no applicability statement near it


def test_alternative_reference_with_as_applicable(tmp_path, monkeypatch):
    lines = [
        "assignment is permitted except as expressly permitted by FAR 52.212-4(b) or FAR 52.232-23, as applicable."
    ]
    ids = _make(tmp_path, monkeypatch, lines, [(0, "52.232-23")])
    assert {ids[c]: v for c, v in LC.text_rule_ids("d").items()} == {"52.232-23": "NOT_BINDING"}


def test_bare_list_needs_four_lines_and_no_leaders(tmp_path, monkeypatch):
    lines = [
        "The following FAR clauses apply to this solicitation:",
        "FAR 52.204-12, Unique Entity Identifier Maintenance (Oct 2016)",
        "FAR 52.204-13, System for Award Management Maintenance (Oct 2018)",
        "FAR 52.204-18, Commercial and Government Entity Code Maintenance (Aug 2020)",
        "FAR 52.204-21, Basic Safeguarding of Covered Contractor Information Systems",
        "(Nov 2021)",
        "FAR 52.209-6, Protecting the Government's Interest When Subcontracting",
    ]
    nums = [(1, "52.204-12"), (2, "52.204-13"), (3, "52.204-18"), (4, "52.204-21"), (6, "52.209-6")]
    ids = _make(tmp_path, monkeypatch, lines, nums)
    assert {ids[c] for c in LC.bare_list_ids("d")} == {n for _, n in nums}
    toc = [
        "TABLE OF CONTENTS",
        "52.204-12 Unique Entity Identifier ........ 3",
        "52.204-13 System for Award Management ...... 4",
        "52.204-18 Commercial and Government Entity ...... 5",
        "52.204-21 Basic Safeguarding ........ 6",
    ]
    ids2 = (
        _make(
            tmp_path / "x", monkeypatch, toc, [(1, "52.204-12"), (2, "52.204-13"), (3, "52.204-18"), (4, "52.204-21")]
        )
        if (tmp_path / "x").mkdir() is None
        else {}
    )
    assert ids2 and LC.bare_list_ids("d") == set()


def test_excluded_ids_amendment_deletes(tmp_path, monkeypatch):
    # cut from round-6 doc c284e3 (SF 30 amendment): three clauses deleted in one block
    lines = [
        "N00104-26-Q-NB18  AMEND:  0001        PAGE   2  OF   3",
        "PART I - THE SCHEDULE // SECTION F // DELIVERIES OR PERFORMANCE",
        "CLAUSE 52.247-59 IS DELETED // CLAUSE 52.247-61 IS DELETED // CLAUSE 52.247-65 IS DELETED",
    ]
    ids = _make(tmp_path, monkeypatch, lines, [(2, "52.247-59"), (2, "52.247-61"), (2, "52.247-65")])
    assert set(ids[c] for c in LC.excluded_ids("d")) == {"52.247-59", "52.247-61", "52.247-65"}


def test_excluded_ids_wordings(tmp_path, monkeypatch):
    lines = [
        "52.212-5 is hereby deleted from this solicitation.",
        "FAR 52.219-14 does not apply to this acquisition.",
        "52.222-41 is not applicable to commercial services.",
        "Delete the clause at 52.204-25 in its entirety.",
        "52.212-4, Contract Terms and Conditions (Nov 2021).",
    ]
    nums = [(0, "52.212-5"), (1, "52.219-14"), (2, "52.222-41"), (3, "52.204-25"), (4, "52.212-4")]
    ids = _make(tmp_path, monkeypatch, lines, nums)
    assert set(ids[c] for c in LC.excluded_ids("d")) == {"52.212-5", "52.219-14", "52.222-41", "52.204-25"}


def test_refer_to_clause_is_narrative(tmp_path, monkeypatch):
    # cut from round-6 doc 2ee6d4 (construction spec): pointers, not incorporations
    lines = [
        "Refer to clause 52.211-12 LIQUIDATED DAMAGES in Section 00 70 00 for the amount.",
        "Comply with the clause at FAR 52.236-21 for specifications and drawings.",
    ]
    ids = _make(tmp_path, monkeypatch, lines, [(0, "52.211-12"), (1, "52.236-21")])
    got = {ids[c]: v for c, v in LC.text_rule_ids("d").items()}
    assert got == {"52.211-12": "NOT_BINDING", "52.236-21": "NOT_BINDING"}
