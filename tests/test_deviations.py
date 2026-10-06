from fedproc_ledger.registry.deviations import agency_part52_pdfs, dhs_rows, model_dates, part52_sections, pdf_header

INDEX = (
    "<html><body><p>Part 52 - Solicitation Provisions and Contract Clauses Issuance Date: October 28, 2025 "
    "UPDATE: July 1, 2026 Part 53 - Forms Issuance Date: September 30, 2025</p>"
    '<a href="/sites/default/files/page_file_uploads/HHS_RFO_Deviation_Part-3-17-27-45and52.pdf">Health and Human Services (HHS)</a>'
    '<a href="/sites/default/files/page_file_uploads/DoD_RFO_Deviation_Part-5.pdf">Department of Defense (DoD)</a>'
    '<a href="/sites/default/files/page_file_uploads/MCC_RFO_Deviation_Parts-1and52.pdf">Millennium Challenge Corporation (MCC)</a>'
    '<a href="/sites/default/files/page_file_uploads/X_RFO_Deviation_Part-152.pdf">Not part 52 (part 152)</a></body></html>'
)
PART52_HTML = (
    '<div id="FAR_52_204_21"> 52.204-21 [Reserved] (Deviation Date) 52.204-22 [Reserved] (Deviation Date)</div>'
    '<div id="FAR_52_219_14"> 52.219-14 Limitations on Subcontracting. As prescribed in 19.104-3(c), insert the following clause: '
    "Limitations on Subcontracting (Deviation Date) (a) This clause does not apply.</div>"
    '<div id="FAR_52_204_90"> 52.204-90 Offeror Identification. As prescribed in 4.208(c)(1), insert the following provision:</div>'
)


def test_model_deviation_dates_come_from_the_page_text():
    assert model_dates(INDEX) == {"issued": "2025-10-28", "updated": "2026-07-01"}
    assert model_dates("<p>nothing here</p>") == {"issued": None, "updated": None}


def test_rfo_section_status_is_read_from_the_heading():
    rows = {r["number"]: r for r in part52_sections(PART52_HTML)}
    assert rows["52.204-21"]["rfo_status"] == "reserved"
    assert rows["52.219-14"] == {
        "number": "52.219-14",
        "rfo_title": "Limitations on Subcontracting",
        "rfo_status": "text",
        "rfo_kind": "clause",
    }
    assert rows["52.204-90"]["rfo_title"] == "Offeror Identification" and rows["52.204-90"]["rfo_kind"] == "provision"


def test_only_pdfs_that_name_part_52_are_listed():
    got = agency_part52_pdfs(INDEX)
    assert [g["filename"] for g in got] == [
        "HHS_RFO_Deviation_Part-3-17-27-45and52.pdf",
        "MCC_RFO_Deviation_Parts-1and52.pdf",
    ]
    assert got[0]["url"].startswith("https://www.acquisition.gov/sites/default/files/")


def test_pdf_header_uses_explicit_patterns_and_never_reads_a_date_from_a_number():
    hhs = pdf_header(
        "DEPARTMENT OF HEALTH & HUMAN SERVICES FAR CLASS DEVIATION 2025-05 MEMORANDUM TO: Heads ... November 3, 2025"
    )
    assert hhs["deviation_number"] == "2025-05" and hhs["date"] == "2025-11-03" and hhs["parsed"]
    usaid = pdf_header("AAPD No. 25-03 Implementing the Revolutionary FAR Overhaul Issued: August 7, 2025")
    assert usaid["deviation_number"] == "25-03" and usaid["date"] == "2025-08-07"
    mcc = pdf_header("UNCLASSIFIED MEMORANDUM Date: 8 May 2025 From: Lisa M. Smith")
    assert mcc["deviation_number"] is None and mcc["date"] == "2025-05-08" and mcc["parsed"] is False
    assert (
        pdf_header("Class Deviation 2025-05 only, no date at all")["date"] is None
    )  # a year-month in a number is not a date


def test_dhs_conformed_table_rows():
    text = (
        "Page 1 of 467 PART 52 conformed as follows: FAR Class Deviation Date "
        "FAR Class Dev 25-04 for FAR Part 1 in Support of Executive Order May 30, 2025 "
        "FAR Class Dev 25-12 FAR Class Deviation for FAR Part 31 in Support of Executive Order July 31, 2025 "
        "FAR Class Dev 25-18 for FAR Part 26 in Support of EO (changes effective November 3, 2025) August 22, 2025 "
        "FAR Class Dev 25-19, Revision 1 for FAR Part 4 in Support of EO (changes effective November 28, 2025) November 6, 2025"
    )
    rows = {r["part"]: r for r in dhs_rows(text)}
    assert rows["1"] == {
        "regulation": "FAR",
        "deviation_number": "25-04",
        "revision": "",
        "part": "1",
        "date": "2025-05-30",
        "effective": "",
    }
    assert rows["31"]["date"] == "2025-07-31"  # "FAR Class Deviation for FAR Part 31" variant
    assert rows["26"]["date"] == "2025-08-22" and rows["26"]["effective"] == "2025-11-03"  # issue date is the last date
    assert rows["4"]["revision"] == "1" and rows["4"]["date"] == "2025-11-06" and rows["4"]["effective"] == "2025-11-28"
