import pytest

from fedproc_ledger.extract.privacy import find_markings, redact


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Contact John at john.doe@agency.gov for questions", "Contact John at [EMAIL] for questions"),
        ("Call (202) 555-0100 or 202-555-0101 or 202.555.0102.", "Call [PHONE] or [PHONE] or [PHONE]."),
        ("Phone: +1 703 555 0199 x123", "Phone: [PHONE]"),
        ("1-800-555-0100", "[PHONE]"),
    ],
)
def test_contact_details_are_redacted(raw, expected):
    assert redact(raw) == expected


@pytest.mark.parametrize(
    "keep",
    [
        "FAR 52.212-4 and 252.204-7012 apply",
        "DFARS 252.225-7001, 252.239-7010 and 252.211-7003 (Item Unique Identification)",
        "Offers are due 12/31/2026 at 2:00 PM",
        "The estimated value is $1,234,567.89",
        "Zip 22202-3456 and CAGE 1ABC2",
        "Solicitation 36C10X24Q0123, amendment 0002",
        "NAICS 541330, PSC R425",
        "page 12 of 2024-2026",
    ],
)
def test_clause_numbers_dates_amounts_and_ids_are_not_redacted(keep):
    assert redact(keep) == keep


def test_markings_are_reported_by_name():
    assert find_markings("This document is CUI. Distribution Statement D applies.") == ["CUI", "distribution_statement"]
    assert find_markings("Source Selection Information - See FAR 2.101 and 3.104") == ["source_selection"]
    assert find_markings("Export Controlled technical data (ITAR)") == ["export_control"]
    assert find_markings("A plain solicitation for janitorial services") == []
    assert find_markings("Distribution Statement A: approved for public release") == []  # A is public release
