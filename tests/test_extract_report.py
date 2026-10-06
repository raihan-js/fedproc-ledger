from fedproc_ledger.extract.report import build_report, choose_pages, highlight


def test_markers_are_highlighted_and_text_is_escaped():
    out = highlight("⟦X⟧ 52.203-6 <b>& co</b> ⟦ ⟧ and ⟦?⟧")
    assert (
        '<span class="chk">⟦X⟧</span>' in out
        and '<span class="unc">⟦ ⟧</span>' in out
        and '<span class="unk">⟦?⟧</span>' in out
    )
    assert "&lt;b&gt;&amp; co&lt;/b&gt;" in out and "<b>" not in out


def test_page_choice_shows_each_source_then_fills_with_the_busiest():
    def c(i, src, total, checklist=1):
        return {"doc_id": f"d{i}", "page": i, "by_source": {src: total}, "total": total, "checklist": checklist}

    cands = [
        c(1, "glyph", 9),
        c(2, "widget", 4),
        c(3, "drawing", 5),
        c(4, "lost", 6),
        c(5, "glyph", 8),
        c(6, "glyph", 3, 0),
    ]
    got = [x["page"] for x in choose_pages(cands, 5)]
    assert got[:4] == [2, 1, 3, 4] and got[4] == 5 and 6 not in got


def test_report_contains_the_counts_table_and_every_page():
    html_doc = build_report(
        [{"title": "a.pdf", "page": 3, "layout": "⟦X⟧ x", "image_b64": "AAAA", "counts": {"glyph:X": 1}}],
        {"extracted": 2, "pages": 9, "box_counts_by_source_and_state": {"glyph:X": 1}},
    )
    assert "a.pdf | page 3" in html_doc and "glyph:X" in html_doc and "data:image/png;base64,AAAA" in html_doc
