import pandas as pd

from fedproc_ledger.acquire.sampling import department_of, month_list, sample_days, select_candidates, weekdays


def test_month_list_crosses_years():
    assert month_list("2024-11", "2025-02") == [(2024, 11), (2024, 12), (2025, 1), (2025, 2)]


def test_weekdays_exclude_weekends():
    days = weekdays(2026, 9)
    assert len(days) == 22 and all(d.weekday() < 5 for d in days)


def test_sample_days_are_spread_deterministic_weekdays():
    a = sample_days(2026, 9, 6, seed=1)
    assert a == sample_days(2026, 9, 6, seed=1) and a != sample_days(2026, 9, 6, seed=2)
    assert len(a) == 6 and a == sorted(a) and all(d.weekday() < 5 for d in a)
    assert a[-1].day - a[0].day > 14  # spread over the month, not clustered


def test_department_mapping_splits_dod_and_defaults_to_other():
    assert department_of("DEPT OF DEFENSE.DEPT OF THE ARMY.ACC-APG") == "DOD_ARMY"
    assert department_of("DEPT OF DEFENSE.DEFENSE LOGISTICS AGENCY.DLA LAND") == "DOD_DLA"
    assert department_of("DEPT OF DEFENSE.MISSILE DEFENSE AGENCY.X") == "DOD_OTHER"
    assert department_of("VETERANS AFFAIRS, DEPARTMENT OF.VA.NCO 4") == "VA"
    assert department_of("COURT SERVICES AND OFFENDER SUPERVISION AGENCY.X.Y") == "OTHER"
    assert department_of(None) == "OTHER" and department_of(float("nan")) == "OTHER" and department_of("  ") == "OTHER"


def _frame(n_per_month=60, months=("2024-01", "2024-02", "2024-03")):
    deps = ["DOD_ARMY", "DOD_ARMY", "DOD_ARMY", "VA", "VA", "GSA", "DHS", "HHS", "NASA", "OTHER"]
    rows = []
    for m in months:
        for i in range(n_per_month):
            rows.append({"solicitation_number": f"{m}-{i}", "month": m, "department": deps[i % len(deps)]})
    return pd.DataFrame(rows)


def test_selection_respects_the_department_cap_and_balances_months():
    df = _frame()
    out = select_candidates(df, target=60, max_share=0.25, seed=7)
    sel = out[out["selected"]]
    assert len(sel) == 60
    assert sel["department"].value_counts().max() <= 15  # 25% of 60
    assert sel["month"].value_counts().to_dict() == {"2024-01": 20, "2024-02": 20, "2024-03": 20}
    assert sorted(out["rank"]) == list(range(len(df)))  # every notice ranked, the tail is the reserve list
    assert out.equals(select_candidates(df, target=60, max_share=0.25, seed=7))  # deterministic


def test_when_the_cap_cannot_be_met_fewer_are_selected_rather_than_breaking_it():
    df = _frame()
    df["department"] = ["DOD_ARMY" if i % 2 else "VA" for i in range(len(df))]  # two departments only
    sel = select_candidates(df, target=60, max_share=0.25, seed=7).query("selected")
    assert len(sel) == 30 and sel["department"].value_counts().max() == 15
