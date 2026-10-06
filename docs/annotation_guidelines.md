# Annotation guidelines (v1, 2026-10-07)

Used by every labeller (the coding agent, the OpenAI judges, and any later human). Source for the definitions: FAR
52.202-1, 52.212-5, 52.252-1, 52.252-2 and the RFO model deviation (acquisition.gov, accessed 2026-10-02); the schema is
plan section 9.

## Two levels
**Mention role** (one per candidate clause number at one place in the document):

| role | meaning | binds? |
|---|---|---|
| INCORPORATED_BY_REFERENCE | listed as incorporated by reference: a "clauses incorporated by reference" list or table row, "the following clauses apply", SF 1449 block 27a with its box marked | yes |
| FULL_TEXT | the heading of a clause or provision whose full text follows in the document | yes |
| CHECKLIST_SELECTED | an item of a checklist clause (52.212-5, 52.213-4, 252.212-7001, 52.244-6, agency checklists) with a marked box (X, ⟦X⟧, "X (4)", "CHECKED") | yes |
| CHECKLIST_NOT_SELECTED | such an item with an empty box (⟦ ⟧, "__", "[ ]") | no |
| EXPLICITLY_EXCLUDED | the text says the clause is deleted, reserved, does not apply, or is replaced ("in lieu of") | no, and overrides |
| INTERNAL_REFERENCE | cited inside the text of another clause or prescription ("has the meaning given in the clause at 52.204-25", "flow down in accordance with paragraph (e) of 52.226-6") | no |
| NARRATIVE_MENTION | cited in instructions, evaluation text, the statement of work or other narrative | no |
| INDEX_ENTRY | table of contents, index, running header or footer | no |
| NOT_A_CLAUSE | not a clause reference (an amount, a version, a fragment such as "252.232" from a wrapped number) | no |
| UNCLEAR | the context does not allow a decision (a lost checkbox, a garbled form page); excluded from scoring and counted | n/a |

**Document ledger** (one decision per distinct clause number): B (binds) if any mention is INCORPORATED_BY_REFERENCE,
FULL_TEXT or CHECKLIST_SELECTED and no mention is EXPLICITLY_EXCLUDED; N otherwise; U when the evidence shown cannot decide.
Alternates ("Alternate II of 52.219-9") are separate entries; the number-level gold ignores them.

## Rules that decide most cases
1. **A box beats the heading.** A checklist item line's box state decides CHECKLIST_SELECTED / NOT_SELECTED even if the
   nearest heading says "incorporated by reference". Items without any box glyph in a checklist whose other items carry X marks are
   NOT_SELECTED only if the list uses X-or-blank (the "__" and "[ ]" forms); with a lost glyph use UNCLEAR.
2. **Table rows are listings.** A row or two-line group of clause number, title and date under a clauses heading (Section I, "incorporated
   by reference", an RFO deviation table) is INCORPORATED_BY_REFERENCE, wherever extraction placed the heading.
3. **Statements of applicability bind.** "The following clauses apply", "is incorporated herein by reference", "applies to this
   acquisition", "found herein" (the clause is in the document) make the cited number INCORPORATED_BY_REFERENCE.
4. **Roman-numeral flow-down lists inside 52.212-5 are INTERNAL_REFERENCE** (they list what flows down, not what the contract itself incorporates).
5. **Conditional text does not bind:** "if the solicitation includes FAR 52.213-1", "applies only if the clause at 52.225-1 is included".
6. **SF 1449 block 27a** with its box marked incorporates 52.212-1, -4, -3 and -5; with the box empty it does not; with the
   state lost it is UNCLEAR. Block 27b is the contract-side twin.
7. A fragment ("52.212", "252.232" before a line break) is NOT_A_CLAUSE.

## The open policy question (D-024): referenced requirements
Solicitation narrative often cites a provision as a requirement without listing it ("In accordance with FAR 52.204-7,
registration is required", "the offeror shall fill out FAR provision 52.204-24"). The schema calls these NARRATIVE_MENTION
(not binding on its own), and the agent labelled them N or U; the OpenAI judges often labelled them B. From the next gold
round on, annotators use a fourth ledger label **R** (referenced requirement: narrative states the clause or provision applies or
must be followed, without listing or incorporating it). Reported: the **binding set** (B) as primary, and the **applicable set**
(B or R) as secondary. Until then, results that differ by labeller on exactly these items are reported as such, not averaged away.
