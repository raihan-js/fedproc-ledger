import pytest

from fedproc_ledger.registry.dates import normalize_clause_date, trailing_paren_date


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("(OCT 2022)", "2022-10"),
        ("(Oct 2022)", "2022-10"),
        ("OCT 2022", "2022-10"),
        ("OCT. 2022", "2022-10"),
        ("10/2022", "2022-10"),
        ("October 2022", "2022-10"),
        ("JULY 2014", "2014-07"),
        ("SEPT 2023", "2023-09"),
        ("2022-10", "2022-10"),
        ("MAR 2026", "2026-03"),
    ],
)
def test_formats_seen_in_solicitations(raw, expected):
    assert normalize_clause_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "2022", "FOO 2022", "13/2022", "no date here"])
def test_unparseable_is_none_not_a_guess(raw):
    assert normalize_clause_date(raw) is None


def test_trailing_parenthesis():
    assert trailing_paren_date("Limitations on Subcontracting (OCT 2022)") == "2022-10"
    assert trailing_paren_date("Clauses Incorporated by Reference (FEB 1998)\n") == "1998-02"
    assert trailing_paren_date("(End of clause)") is None
    assert trailing_paren_date("Title with (aside) in the middle and no date") is None
