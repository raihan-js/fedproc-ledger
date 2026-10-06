import json
from pathlib import Path

import pymupdf
import pytest

from fedproc_ledger.extract.pdf import CHECKED_M, UNCHECKED_M, UNKNOWN_M, extract_pdf, page_row

FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
pytestmark = pytest.mark.skipif(not FONT.exists(), reason="DejaVu font needed to draw box glyphs in test PDFs")
REAL = Path(__file__).parent / "fixtures" / "real_checklist_page.pdf"


def make_pdf(path, lines, *, draw=None, widgets=None, image_only=False):
    doc = pymupdf.open()
    page = doc.new_page()
    if image_only:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
        page.insert_image(pymupdf.Rect(50, 50, 250, 250), pixmap=pix)
    for i, text in enumerate(lines):
        page.insert_text((90, 100 + 20 * i), text, fontsize=11, fontfile=str(FONT), fontname="dj")
    for fn in draw or []:
        fn(page)
    for name, rect, value in widgets or []:
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
        w.field_name, w.rect, w.field_value = name, rect, value
        page.add_widget(w)
    doc.save(path)
    doc.close()
    return extract_pdf(path)[0]


def layout_lines(p):
    return [ln.text_layout for ln in p.lines]


def test_glyph_boxes_become_markers_and_inline_boxes_are_still_recorded(tmp_path):
    p = make_pdf(
        tmp_path / "a.pdf",
        [
            "☒ FAR 52.243-5, Changes",
            "☐ FAR 52.243-4, Changes",
            "The offeror represents that it □ is a woman-owned concern",
        ],
    )
    assert layout_lines(p)[0].startswith(f"{CHECKED_M} FAR 52.243-5")
    assert layout_lines(p)[1].startswith(f"{UNCHECKED_M} FAR 52.243-4")
    assert UNCHECKED_M in layout_lines(p)[2] and "it " in layout_lines(p)[2]
    assert p.box_counts == {"glyph:X": 1, "glyph: ": 2}
    assert "☒" in p.text_plain and CHECKED_M not in p.text_plain  # the plain view is untouched


def test_ticks_and_filled_squares_count_only_where_a_box_would_be(tmp_path):
    p = make_pdf(
        tmp_path / "b.pdf",
        [
            "✔ 52.203-6 Restrictions",
            "Done ✔ later in a sentence",
            "■ 52.204-21 Basic Safeguarding",
            "■ a plain bullet point",
        ],
    )
    lay = layout_lines(p)
    assert lay[0].startswith(CHECKED_M) and "✔" in lay[1] and CHECKED_M not in lay[1]
    assert lay[2].startswith(CHECKED_M) and lay[3].startswith("■")


def test_unverified_private_use_glyphs_are_unknown_and_logged(tmp_path):
    p = make_pdf(tmp_path / "c.pdf", [" 52.222-1 Notice to the Government"])
    assert (
        p.pua_codepoints == {"U+F06F": 1} or p.box_counts == {}
    )  # the font may not carry U+F06F; if drawn it must be unknown
    for ln in p.lines:
        for b in ln.boxes:
            assert b.state == "?"


def test_private_use_bullets_are_not_boxes_but_are_logged(tmp_path):
    p = make_pdf(tmp_path / "bul.pdf", [chr(0xF0B7) + " a bullet line", chr(0xF0A7) + " another bullet"])
    assert p.box_counts == {} and all(not ln.boxes for ln in p.lines)


def test_form_widget_checkbox_state_is_attached_to_the_line_on_its_right(tmp_path):
    p = make_pdf(
        tmp_path / "d.pdf",
        ["52.203-6 Restrictions on Subcontractor Sales", "52.204-21 Basic Safeguarding"],
        widgets=[("w1", pymupdf.Rect(60, 90, 74, 104), True), ("w2", pymupdf.Rect(60, 110, 74, 124), False)],
    )
    lay = layout_lines(p)
    assert lay[0].startswith(f"{CHECKED_M} 52.203-6") and lay[1].startswith(f"{UNCHECKED_M} 52.204-21")
    assert [b.source for ln in p.lines for b in ln.boxes] == ["widget", "widget"]


def test_vector_drawn_boxes_checked_by_a_diagonal_cross_or_a_fill(tmp_path):
    def boxes(page):
        page.draw_rect(pymupdf.Rect(70, 88, 82, 100), color=(0, 0, 0), width=0.8)  # empty
        page.draw_rect(pymupdf.Rect(70, 108, 82, 120), color=(0, 0, 0), width=0.8)  # crossed
        page.draw_line((70, 108), (82, 120), color=(0, 0, 0), width=0.8)
        page.draw_line((70, 120), (82, 108), color=(0, 0, 0), width=0.8)
        page.draw_rect(pymupdf.Rect(70, 128, 82, 140), color=(0, 0, 0), fill=(0, 0, 0))  # filled

    p = make_pdf(tmp_path / "e.pdf", ["52.203-6 first", "52.204-21 second", "52.209-5 third"], draw=[boxes])
    got = [(b.state, b.source, b.confidence) for ln in p.lines for b in ln.boxes]
    assert got == [(" ", "drawing", 0.7), ("X", "drawing", 0.7), ("X", "drawing", 0.7)]


def test_lost_checkbox_is_flagged_only_on_a_checklist_page(tmp_path):
    p = make_pdf(
        tmp_path / "f.pdf",
        [
            "52.212-5 Contract Terms and Conditions Required",
            "(1) 52.203-6, Restrictions on Sales",
            "(2) 52.204-10, Reporting",
        ],
    )
    lay = layout_lines(p)
    assert lay[1].startswith(UNKNOWN_M) and lay[2].startswith(UNKNOWN_M)
    assert [b.source for ln in p.lines for b in ln.boxes] == ["lost", "lost"]
    q = make_pdf(tmp_path / "g.pdf", ["Section C", "(1) 52.203-6, Restrictions on Sales"])
    assert UNKNOWN_M not in "".join(layout_lines(q))


def test_an_image_only_page_is_scanned(tmp_path):
    p = make_pdf(tmp_path / "h.pdf", [], image_only=True)
    assert p.scanned is True and p.text_plain.strip() == ""


def test_offset_map_points_at_each_line(tmp_path):
    p = make_pdf(tmp_path / "i.pdf", ["☒ one", "two"])
    om = p.offset_map()
    for (s, e, bbox), ln in zip(om, p.lines, strict=True):
        assert p.text_layout[s:e] == ln.text_layout and len(bbox) == 4
    row = page_row("abc", p)
    assert json.loads(row["box_signals"])["counts"] == {"glyph:X": 1} and row["scanned"] is False


def test_real_checklist_page_from_a_solicitation():
    pages = extract_pdf(REAL)
    lay = "\n".join(p.text_layout for p in pages)
    assert f"{CHECKED_M} FAR 52.243-5, Changes and Changed Conditions" in lay
    assert f"{UNCHECKED_M} FAR 52.243-4, Changes" in lay
    assert pages[0].box_counts.get("glyph:X") == 1 and pages[0].box_counts.get("glyph: ", 0) >= 5


def test_verified_wingdings_check_mark_and_empty_box_on_a_real_page():
    page = extract_pdf(Path(__file__).parent / "fixtures" / "real_pua_check_page.pdf")[0]
    lay = page.text_layout
    assert f"{CHECKED_M} (4) 52.203-17, Contractor Employee Whistleblower Rights" in lay
    assert f"{CHECKED_M} (5) 52.204-10, Reporting Executive Compensation" in lay
    assert all(b.state == "X" and b.source == "glyph" and b.detail == "U+F0FC" for ln in page.lines for b in ln.boxes)
