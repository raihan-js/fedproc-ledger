from fedproc_ledger.label import pilot as PL


def row(cid, number, role, tier="unanimous"):
    return {"cand_id": cid, "number": number, "role": role, "tier": tier}


def test_panel_ledger_binds_excludes_and_flags_uncertain_numbers():
    rows = [
        row("1", "52.204-21", "INCORPORATED_BY_REFERENCE"),
        row("2", "52.219-9", "CHECKLIST_SELECTED"),
        row("3", "52.219-9", "EXPLICITLY_EXCLUDED"),
        row("4", "52.222-26", "NARRATIVE_MENTION"),
        row("5", "52.215-1", "UNCLEAR", tier="split"),
    ]
    led, unc = PL.panel_ledger(rows, {"1": None, "2": "Alternate I"})
    assert led == {("52.204-21", None)} and unc == {"52.215-1"}


def test_slice_a_truth_needs_a_checklist_line_and_a_known_box():
    assert PL.slice_a_truth("⟦X⟧", True) == "CHECKLIST_SELECTED"
    assert PL.slice_a_truth("⟦ ⟧", True) == "CHECKLIST_NOT_SELECTED"
    assert PL.slice_a_truth("⟦?⟧", True) is None and PL.slice_a_truth("⟦X⟧", False) is None
    assert PL.slice_a_truth(None, True) is None


def test_checklist_item_lines_are_box_then_number_and_not_sf1449_block_27():
    text = "\n".join(
        [
            "⟦X⟧ (1) 52.203-6 Restrictions on Subcontractor Sales",
            "⟦ ⟧ 52.232-36, Payment by Third Party",
            "⟦ ⟧  Alternate I  (Nov 2025) of 52.212-4",
            "⟦X⟧ 27a. SOLICITATION INCORPORATES BY REFERENCE FAR 52.212-1",
            "⟦?⟧ (2) 52.233-3 Protest",
            "52.204-21 Basic Safeguarding",
        ]
    )
    assert PL.checklist_item_keys([(3, text)]) == {(3, 0), (3, 1), (3, 2)}


def test_role_agreement_counts_exact_roles_and_binding_class():
    got = PL.role_agreement(
        ["CHECKLIST_SELECTED", "FULL_TEXT", "NARRATIVE_MENTION"],
        ["CHECKLIST_SELECTED", "CHECKLIST_SELECTED", "FULL_TEXT"],
    )
    assert got["n"] == 3 and abs(got["role_agreement"] - 1 / 3) < 1e-9 and abs(got["binding_agreement"] - 2 / 3) < 1e-9


def test_scoring_ignores_uncertain_numbers_and_the_decision_rule_follows_plan():
    per = {
        "d1": {"gold": {("a", None), ("b", None)}, "uncertain": {"c"}, "systems": {"S": {("a", None), ("c", None)}}},
        "d2": {"gold": {("a", None)}, "uncertain": set(), "systems": {"S": {("a", None), ("z", None)}}},
    }
    s = PL.score_systems(per)["S"]  # d1: tp1 fn1 (c ignored); d2: tp1 fp1
    assert abs(s["precision"] - 2 / 3) < 1e-9 and abs(s["recall"] - 2 / 3) < 1e-9
    assert PL.decide(0.7, 0.95).startswith("GO_MODEL") and PL.decide(0.9, 0.95).startswith("PIVOT")


def test_typed_checklist_forms_are_decided_by_rule():
    assert PL.typed_item_state("__ (43) 52.225-5, Trade Agreements (Nov 2013)") == "CHECKLIST_NOT_SELECTED"
    assert PL.typed_item_state("[ ] (ii) 252.225-7020, Trade Agreements Certificate.") == "CHECKLIST_NOT_SELECTED"
    assert PL.typed_item_state("___ (7) 52.222-55, Minimum Wages") == "CHECKLIST_NOT_SELECTED"
    assert PL.typed_item_state("X (44) 52.225-13, Restrictions") == "CHECKLIST_SELECTED"
    assert PL.typed_item_state("__X__ (33) 52.222-21, Prohibition of Segregated Facilities") == "CHECKLIST_SELECTED"
    assert PL.typed_item_state("[X]FAR 52.225-13 Restrictions on Certain Foreign Purchases") == "CHECKLIST_SELECTED"
    assert PL.typed_item_state("52.204-21 Basic Safeguarding") is None
    assert PL.typed_item_state("__ Offeror certifies that it is a small business") is None
