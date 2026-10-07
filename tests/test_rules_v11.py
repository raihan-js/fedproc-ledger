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


def test_para_a_skips_boxed_items(tmp_path, monkeypatch):
    lines = [
        "(a) The Contractor shall comply with the following FAR clauses:",
        "⟦?⟧ (3) 52.204-25, Prohibition on Contracting for Certain Telecommunications",
    ]
    _make(tmp_path, monkeypatch, lines, [(1, "52.204-25")])
    assert LC.para_a_ids("d") == set()  # a glyph line is the box rule's business


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
