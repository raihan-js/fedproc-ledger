from fedproc_ledger.candidates.generate import generate_page_candidates
from fedproc_ledger.rules import baseline as B
from fedproc_ledger.rules import sections as S

DOC = [
    (
        1,
        "TABLE OF CONTENTS\nSECTION A - SOLICITATION/CONTRACT FORM ........ 1\nSECTION I - CONTRACT CLAUSES ........ 35\n52.252-2 Clauses Incorporated by Reference ... 36",
    ),
    (
        2,
        "SECTION A - Solicitation/Contract Form\nSECTION C - Description / Specifications / Statement of Work\nThe contractor shall comply with 52.204-21 in all work.",
    ),
    (
        3,
        "SECTION I - CONTRACT CLAUSES\n52.252-2 CLAUSES INCORPORATED BY REFERENCE\nThis contract incorporates one or more clauses by reference.\n"
        "52.203-3 Gratuities (APR 1984)\n52.204-9 Personal Identity Verification of Contractor Personnel (JAN 2011)\n"
        "CLAUSES INCORPORATED BY FULL TEXT\n"
        "52.212-4 Contract Terms and Conditions--Commercial Products and Commercial Services (NOV 2023)\n(a) Inspection/Acceptance. See also 52.246-2.\n(End of clause)\n"
        "52.212-5 Contract Terms and Conditions Required To Implement Statutes (MAR 2026)\n(b) The Contractor shall comply with the following clauses:\n"
        "⟦X⟧ (1) 52.203-6 Restrictions on Subcontractor Sales\n⟦ ⟧ (2) 52.203-13 Contractor Code of Business Ethics\n(3) 52.204-10 Reporting Executive Compensation\n(End of clause)\n"
        "52.219-14 Limitations on Subcontracting (OCT 2022)\n(a) This clause does not apply to the unrestricted portion.\n(End of clause)",
    ),
    (
        4,
        "SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS\nOfferors must complete 52.204-8 and 52.212-3.\nSECTION M - EVALUATION FACTORS\nPrice is evaluated; see 52.212-2.",
    ),
]


def labels(doc=DOC):
    class ByPrefix(dict):
        def __getitem__(self, key):
            page, prefix = key
            return next(v for (p, text), v in self.items() if p == page and text.startswith(prefix))

    return ByPrefix({(ll.page, ll.text): ll for ll in S.label_document(doc)})


def test_section_labels_follow_the_document_structure():
    lab = labels()
    assert (
        lab[(1, "SECTION I - CONTRACT CLAUSES ...")].label == S.TOC
        and lab[(1, "52.252-2 Clauses Incorporated by")].label == S.TOC
    )
    assert lab[(2, "The contractor shall comply wit")].label == S.SOW
    assert (
        lab[(3, "52.203-3 Gratuities (APR 1984)")].label == S.IBR
        and lab[(3, "52.204-9 Personal Identity Verif")].label == S.IBR
    )
    assert (
        lab[(3, "52.212-4 Contract Terms and Cond")].label == S.FULL_TEXT
        and lab[(3, "52.212-4 Contract Terms and Cond")].heading
    )
    assert lab[(3, "(a) Inspection/Acceptance. See a")].label == S.FULL_TEXT
    assert lab[(3, "⟦X⟧ (1) 52.203-6 Restrictions on")].label == S.CHECKLIST
    assert lab[(3, "(3) 52.204-10 Reporting Executiv")].label == S.CHECKLIST  # a list item whose box was lost
    assert lab[(3, "52.219-14 Limitations on Subcont")].clause == "52.219-14"
    assert (
        lab[(4, "Offerors must complete 52.204-8")].label == S.INSTRUCTIONS
        and lab[(4, "Price is evaluated; see 52.212-2.")].label == S.EVALUATION
    )


def test_a_sentence_that_mentions_a_section_is_not_a_heading():
    out = S.label_document(
        [
            (
                1,
                "SECTION I - CONTRACT CLAUSES\n52.252-2 CLAUSES INCORPORATED BY REFERENCE\nThe payment terms are in Section G of the contract.\n52.203-3 Gratuities (APR 1984)",
            )
        ]
    )
    assert [x.label for x in out][-1] == S.IBR and not out[2].heading


def predictions():
    cands = [c for p, t in DOC for c in generate_page_candidates("d", p, t)]
    return {
        (x.cand.page, x.cand.number, x.cand.line_text[:12]): x
        for x in B.classify_document(cands, S.label_document(DOC))
    }


def test_roles_follow_section_and_box_state():
    pr = predictions()
    role = lambda page, number: next(p.role for k, p in pr.items() if k[0] == page and k[1] == number)  # noqa: E731
    assert role(1, "52.252-2") == B.INDEX
    assert role(2, "52.204-21") == B.NARRATIVE
    assert role(3, "52.203-3") == B.IBR and role(3, "52.204-9") == B.IBR
    assert role(3, "52.212-4") == B.FULL and role(3, "52.246-2") == B.INTERNAL
    assert role(3, "52.203-6") == B.SELECTED and role(3, "52.203-13") == B.NOT_SELECTED
    lost = next(p for k, p in pr.items() if k[1] == "52.204-10" and k[0] == 3)
    assert lost.role == B.SELECTED and lost.confidence == 0.5 and "lost" in lost.reason or "no box" in lost.reason
    assert role(4, "52.204-8") == B.NARRATIVE and role(4, "52.212-2") == B.NARRATIVE


def test_the_ledger_counts_only_binding_roles_and_respects_exclusions():
    preds = list(predictions().values())
    led = B.ledger(preds)
    keys = {k[0] for k in led}
    assert {"52.203-3", "52.204-9", "52.212-4", "52.212-5", "52.203-6", "52.219-14", "52.204-10"} <= keys
    assert "52.203-13" not in keys and "52.246-2" not in keys and "52.204-21" not in keys  # b0 would count them all
    assert "52.252-2" in keys  # the clause that incorporates the others is itself in the contract


def test_explicit_exclusion_removes_the_number_from_the_ledger():
    text = "SECTION I - CONTRACT CLAUSES\n52.252-2 CLAUSES INCORPORATED BY REFERENCE\n52.203-6 (Deleted)\n52.204-9 Personal Identity Verification (JAN 2011)\n52.203-6 Restrictions (JAN 2020)"
    cands = generate_page_candidates("d", 1, text)
    preds = B.classify_document(cands, S.label_document([(1, text)]))
    assert [p.role for p in preds if p.cand.number == "52.203-6"] == [B.EXCLUDED, B.IBR]
    assert {k[0] for k in B.ledger(preds)} == {"52.204-9", "52.252-2"}


def test_non_clause_look_alikes_and_unknown_numbers():
    text = "SECTION I - CONTRACT CLAUSES\n52.252-2 CLAUSES INCORPORATED BY REFERENCE\nThe unit price is $52.212 each.\n52.999-9 Made Up Clause (JAN 2020)"
    cands = generate_page_candidates("d", 1, text, {"52.252-2": "active"})
    preds = B.classify_document(cands, S.label_document([(1, text)]))
    by = {p.cand.number: p for p in preds}
    assert (
        by["52.212"].role == B.NOT_CLAUSE
        and by["52.999-9"].role == B.NOT_CLAUSE
        and by["52.252-2"].role != B.NOT_CLAUSE
    )


def test_b0_counts_every_registry_number_it_finds():
    assert B.b0_ledger(["52.212-4", "52.203-13", "52.999-9"], {"52.212-4": "active", "52.203-13": "active"}) == {
        "52.212-4",
        "52.203-13",
    }
