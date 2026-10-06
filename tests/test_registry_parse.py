from pathlib import Path

import pytest

from fedproc_ledger.registry.parse import parse_part_xml

FIXTURE = Path(__file__).parent / "fixtures" / "ecfr_part52_snippets.xml"
SECS = parse_part_xml(FIXTURE.read_bytes())

# kind hand-checked against the prescription sentence of each section in the fixture (real eCFR text, 2026-10-02):
# "As prescribed in ..., insert the following clause|provision:" and the closing "(End of clause|provision)".
KINDS = {
    "52.203-13": "clause",
    "52.204-21": "clause",
    "52.209-5": "provision",
    "52.212-1": "provision",
    "52.212-3": "provision",
    "52.212-4": "clause",
    "52.212-5": "clause",
    "52.215-1": "provision",
    "52.219-9": "clause",
    "52.219-14": "clause",
    "52.222-26": "clause",
    "52.252-1": "provision",
    "52.252-2": "clause",
}


def test_the_fixture_is_real_ecfr_structure():
    assert len(SECS) == 14 and "52.219-14" in SECS


@pytest.mark.parametrize("number,kind", sorted(KINDS.items()))
def test_kind_is_read_from_the_prescription_and_agrees_with_the_end_marker(number, kind):
    s = SECS[number]
    assert s.kind == kind and s.kind_source == "prescription", (number, s.prescription)


def test_clause_title_date_and_prescribed_in():
    s = SECS["52.219-14"]
    assert s.title == "Limitations on Subcontracting" and s.clause_title == "Limitations on Subcontracting (OCT 2022)"
    assert s.clause_date == "2022-10" and s.prescribed_in == ["19.507(e)"]
    assert SECS["52.252-2"].clause_date == "1998-02" and SECS["52.212-1"].clause_date == "2023-09"


def test_alternates_are_found_with_their_dates():
    alts = {a["name"]: a["date"] for a in SECS["52.219-9"].alternates}
    assert alts.get("Alternate I") == "2016-11" and alts.get("Alternate II") == "2016-11"
    assert alts.get("Alternate III") == "2025-01" and alts.get("Alternate IV") == "2025-01"
    assert {a["name"]: a["date"] for a in SECS["52.212-3"].alternates}["Alternate I"] == "2024-02"
    assert SECS["52.219-14"].alternates == []


def test_reserved_sections_are_flagged_and_have_no_kind():
    s = SECS["52.203-1"]
    assert s.reserved and s.kind == "unknown" and s.clause_date is None


def test_kind_stays_unknown_when_the_sources_disagree_or_say_nothing():
    xml = (
        '<ECFR><DIV8 N="1.1" TYPE="SECTION"><HEAD>1.1 A.</HEAD>'
        "<P>As prescribed in 1.2, insert the following clause:</P>"
        "<EXTRACT><HD1>A (JAN 2020)</HD1></EXTRACT><HD3>(End of provision)</HD3></DIV8>"
        '<DIV8 N="1.2" TYPE="SECTION"><HEAD>1.2 B.</HEAD><P>Use this wherever you like.</P></DIV8>'
        '<DIV8 N="1.3" TYPE="SECTION"><HEAD>1.3 C.</HEAD>'
        "<P>Insert the following provision and the following clause:</P></DIV8></ECFR>"
    )
    s = parse_part_xml(xml)
    assert s["1.1"].kind == "unknown" and s["1.2"].kind == "unknown" and s["1.3"].kind == "unknown"


def test_end_marker_is_used_only_when_the_prescription_is_silent():
    xml = (
        '<ECFR><DIV8 N="9.9" TYPE="SECTION"><HEAD>9.9 Z.</HEAD><P>Some agencies prescribe this elsewhere.</P>'
        "<EXTRACT><HD1>Z (MAR 2021)</HD1></EXTRACT><HD3>(End of clause)</HD3></DIV8></ECFR>"
    )
    s = parse_part_xml(xml)["9.9"]
    assert s.kind == "clause" and s.kind_source == "end_marker" and s.clause_date == "2021-03"


def test_dfars_style_section_without_an_extract_wrapper_gets_its_date_from_the_title_paragraph():
    xml = (
        '<ECFR><DIV8 N="252.204-7021" TYPE="SECTION"><HEAD>252.204-7021 Contractor Compliance With the CMMC Requirements.</HEAD>'
        "<P>As prescribed in 204.7504(a), use the following clause:</P>"
        "<P>CONTRACTOR COMPLIANCE WITH THE CMMC REQUIREMENTS (NOV 2025)</P><P>(a) Definitions. As used in this clause-</P>"
        "<HD3>(End of clause)</HD3></DIV8></ECFR>"
    )
    s = parse_part_xml(xml)["252.204-7021"]
    assert (
        s.kind == "clause" and s.clause_date == "2025-11" and s.clause_title.endswith("(NOV 2025)") and s.prescription
    )
