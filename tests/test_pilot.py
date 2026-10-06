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
    assert PL.slice_a_truth("⟦X⟧", "CHECKLIST") == "CHECKLIST_SELECTED"
    assert PL.slice_a_truth("⟦ ⟧", "CHECKLIST") == "CHECKLIST_NOT_SELECTED"
    assert PL.slice_a_truth("⟦?⟧", "CHECKLIST") is None and PL.slice_a_truth("⟦X⟧", "OTHER") is None
    assert PL.slice_a_truth(None, "CHECKLIST") is None


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
