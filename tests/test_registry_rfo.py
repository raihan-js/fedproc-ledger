import pandas as pd

from fedproc_ledger.registry.rfo import merge_rfo

REG = pd.DataFrame(
    [
        {
            "number": "52.212-5",
            "regulation": "FAR",
            "regulation_name": "Ch 1",
            "chapter": "1",
            "part": "52",
            "status": "active",
            "kind": "clause",
        },
        {
            "number": "52.219-14",
            "regulation": "FAR",
            "regulation_name": "Ch 1",
            "chapter": "1",
            "part": "52",
            "status": "active",
            "kind": "clause",
        },
        {
            "number": "252.204-7012",
            "regulation": "DFARS",
            "regulation_name": "Ch 2",
            "chapter": "2",
            "part": "252",
            "status": "active",
            "kind": "clause",
        },
    ]
)
RFO = pd.DataFrame(
    [
        {"number": "52.212-5", "rfo_title": "[Reserved]", "rfo_status": "reserved", "rfo_kind": "unknown"},
        {
            "number": "52.219-14",
            "rfo_title": "Limitations on Subcontracting",
            "rfo_status": "text",
            "rfo_kind": "clause",
        },
        {
            "number": "52.240-90",
            "rfo_title": "Security Prohibitions and Exclusions",
            "rfo_status": "text",
            "rfo_kind": "provision",
        },
        {"number": "52.000", "rfo_title": "Scope of part", "rfo_status": "text", "rfo_kind": "unknown"},
    ]
)


def test_rfo_status_is_added_to_far_sections_and_rfo_only_numbers_get_rows():
    out = merge_rfo(REG, RFO).set_index("number")
    assert out.loc["52.212-5", "rfo_status"] == "reserved" and out.loc["52.219-14", "rfo_status"] == "text"
    assert out.loc["252.204-7012", "rfo_status"] is None  # DFARS is not covered by the FAR model deviation
    assert (
        out.loc["52.240-90", "status"] == "rfo_only"
        and out.loc["52.240-90", "kind"] == "provision"
        and out.loc["52.240-90", "regulation"] == "FAR"
    )
    assert "52.000" not in out.index  # only numbered clause sections are added


def test_merge_is_idempotent():
    once = merge_rfo(REG, RFO)
    twice = merge_rfo(once, RFO)
    assert sorted(once["number"]) == sorted(twice["number"]) and (twice["status"] == "rfo_only").sum() == 1
