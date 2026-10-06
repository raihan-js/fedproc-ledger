from fedproc_ledger.acquire.files import extension, final_extension, hint_score, select_files, sniff_kind

KEEP = [".pdf", ".docx", ".doc", ".txt"]


def f(name, size=1000, url="u"):
    return {"filename": name, "size_bytes": size, "url": url}


def test_extension_is_lowercased():
    assert extension("RFP.PDF") == ".pdf" and extension("noext") == ""


def test_hints_rank_the_solicitation_above_drawings_and_wage_lists():
    assert (
        hint_score("Solicitation 36C10X24Q0001.pdf")
        > hint_score("Attachment 3 Pricing.pdf")
        > hint_score("Wage Determination.pdf")
    )
    assert hint_score("SF1449 combined synopsis.pdf") > hint_score("SOW.pdf") > 0


def test_selection_caps_files_and_bytes_and_records_reasons():
    files = [
        f("Solicitation.pdf", 5_000_000),
        f("sow.pdf", 2_000_000),
        f("drawing1.pdf", 9_000_000),
        f("price.xlsx", 10),
        f("big.pdf", 60_000_000),
        f("empty.pdf", 0),
        f("nourl.pdf", 5, url=None),
        f("a.pdf", 1),
        f("b.pdf", 1),
        f("c.pdf", 1),
    ]
    sel, skipped = select_files(files, KEEP, max_files=3, max_file_bytes=50_000_000, max_notice_bytes=12_000_000)
    names = [x["filename"] for x in sel]
    assert names[0] == "Solicitation.pdf" and len(sel) == 3
    reasons = {x["filename"]: x["reason"] for x in skipped}
    assert (
        reasons["price.xlsx"] == "extension" and reasons["big.pdf"] == "too_large" and reasons["empty.pdf"] == "empty"
    )
    assert reasons["nourl.pdf"] == "no_url" and "drawing1.pdf" in reasons  # over the byte cap or the file cap


def test_files_without_an_extension_are_kept_for_sniffing():
    sel, _ = select_files([f("download")], KEEP, 6, 50_000_000, 80_000_000)
    assert [x["filename"] for x in sel] == ["download"]


def test_sniffing():
    assert sniff_kind(b"%PDF-1.7\n...") == "pdf"
    assert sniff_kind(b"PK\x03\x04rest") == "zip"
    assert sniff_kind(bytes.fromhex("D0CF11E0A1B11AE1") + b"x") == "doc"
    assert sniff_kind(b"Plain text of a solicitation.\nLine two.\n") == "txt"
    assert sniff_kind(b"\x89PNG\r\n\x1a\n\x00\x00") is None
    assert (
        final_extension("x", "pdf") == ".pdf"
        and final_extension("x", "zip") is None
        and final_extension("x", "zip", True) == ".docx"
    )
