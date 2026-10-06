"""Registry tests that need the built registry (data/processed/registry.parquet): plan section 6.4. Skipped without it."""

from pathlib import Path

import pandas as pd
import pytest

PATH = Path(__file__).parent.parent / "data" / "processed" / "registry.parquet"
pytestmark = pytest.mark.skipif(not PATH.exists(), reason="registry not built (fl registry build)")


@pytest.fixture(scope="module")
def reg():
    df = pd.read_parquet(PATH)
    assert df["number"].is_unique
    return df.set_index("number")


RESOLVE = [
    "52.212-4", "52.212-5", "52.204-21", "52.219-14", "52.252-2", "252.204-7012", "252.204-7021", "252.212-7001", "52.212-1", "52.212-3",
    "52.215-1", "52.203-13", "52.204-7", "52.204-13", "52.209-5", "52.219-8", "52.219-9", "52.222-26", "52.222-50", "52.225-13",
    "52.232-33", "52.244-6", "52.252-1", "252.225-7001", "252.225-7048", "252.239-7010", "252.204-7000", "252.203-7001", "52.204-25",
    "252.246-7008",
]  # fmt: skip
# hand-checked against the prescription sentence in eCFR as of 2026-10-02 ("insert|use the following clause|provision")
KIND = {
    "52.212-1": "provision", "52.212-3": "provision", "52.212-4": "clause", "52.215-1": "provision", "52.204-21": "clause",
    "52.219-14": "clause", "52.252-1": "provision", "52.252-2": "clause", "252.204-7012": "clause", "252.204-7021": "clause",
    "52.203-13": "clause", "52.204-7": "provision", "52.204-13": "clause", "52.209-5": "provision", "52.222-26": "clause",
    "52.225-13": "clause", "252.225-7001": "clause", "252.239-7010": "clause", "252.204-7000": "clause", "252.246-7008": "clause",
}  # fmt: skip


def test_thirty_well_known_numbers_resolve(reg):
    assert [n for n in RESOLVE if n not in reg.index] == []
    assert (
        reg.loc["252.212-7001", "status"] == "reserved"
    )  # reserved in the current DFARS text (listed under a range id)


def test_kind_is_correct_for_twenty_hand_checked_numbers(reg):
    assert len(KIND) == 20
    assert {n: reg.loc[n, "kind"] for n in KIND} == KIND


def test_52_219_14_has_several_clause_dates_since_2017(reg):
    dates = {
        v["clause_date"]
        for v in reg.loc["52.219-14", "versions"]
        if v["clause_date"] and v["effective_from"] >= "2017-01-01"
    }
    assert len(dates) > 1 and "2022-10" in dates and reg.loc["52.219-14", "current_date"] == "2022-10"


def test_dates_alternates_and_ranges(reg):
    assert reg.loc["52.212-4", "current_date"] == "2023-11" and reg.loc["252.204-7021", "current_date"] == "2025-11"
    assert any(a["name"] == "Alternate I" for a in reg.loc["52.219-9", "alternates"])
    assert reg.loc["52.208-2", "status"] in ("reserved", "removed") and reg.loc["52.208-2", "source_range"]


def test_every_active_section_has_one_known_kind_value_and_the_counts_are_plausible(reg):
    assert set(reg["kind"]) <= {"clause", "provision", "unknown"}
    assert set(reg["status"]) == {"active", "reserved", "removed", "rfo_only"}
    assert reg["regulation"].isin(["FAR", "DFARS"]).sum() > 1000 and (reg["status"] == "active").sum() > 2000


def test_the_rfo_layer(reg):
    assert (
        reg.loc["52.212-5", "rfo_status"] == "reserved" and reg.loc["52.212-5", "status"] == "active"
    )  # eCFR still has it
    assert reg.loc["52.219-14", "rfo_status"] == "text"
    assert reg.loc["52.240-90", "status"] == "rfo_only" and reg.loc["52.240-90", "kind"] == "provision"
    assert (reg["status"] == "rfo_only").sum() == 10 and pd.isna(reg.loc["252.204-7012", "rfo_status"])
