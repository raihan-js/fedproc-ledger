# FedProc-Ledger: integration contract for VETR (draft v0.1, 2026-10-07)

Audience: the VETR team. Status: **proposal; nothing is deployed, nothing in the VETR repository was changed** (read-only
access, `FarClauseDetectionService.php` only read for the parity port). Numbers below are from this repository's results
files; where a number is a development result, it says so.

## 1. What it does, and what it must not be used for
Input: one solicitation document (PDF or DOCX) or its extracted text. Output: a **clause ledger**: for every FAR/DFARS
clause number found, whether the document *binds* the contract to it (incorporated by reference, full text included, or a
selected checklist item), a probability, and the evidence lines. It also decides checklist boxes (`⟦X⟧`, `⟦ ⟧`, `__ (43)`,
`X (44)`) by rule, which is objective.
Not for: legal advice; deciding obligations without a person; documents without a text layer (about 3% are scanned: the
extractor flags them, no ledger is produced); clause ranges ("52.219-1 through 52.219-4") and alternates' dates are not
resolved in this version.

## 2. Evidence for its usefulness (read D-023 to D-028 before deciding)
- **Objective, annotator-free (D-026):** in 925 documents, 14.6% of the entries the VETR-style regexes would list (8,710 of 59,623)
  are clause numbers whose every mention is a checklist item with an **empty** box; 327 of the 388 documents with a decided
  checklist are affected (median 31 clauses). Lower bound; describes the ported regexes, not VETR's current ledger logic.
- **Frozen test (D-028, 32 documents, 679 labelled numbers, majority of three LLM annotators, not human experts):** model F1
  0.912 [0.847, 0.956] against 0.891 [0.829, 0.935] for the status-quo regexes (difference +0.020 [-0.005, +0.046]: non-inferior,
  **not shown better**); recall 0.945 vs 0.963; share of non-binding numbers correctly left out 38% vs 4%. A rules-only baseline (B1) is
  far worse (F1 0.560). Pre-registered hypotheses H2 and H4 **failed** (see D-028).
- **Recommendation:** adopt the checkbox rule first (zero-risk, objective). Use the model for *ranking and flagging*, not for
  silently removing clauses: show every number, with its tier and probability.

## 3. Interface (sidecar service; the model never runs inside PHP)
`POST /v1/ledger` with `{"document": <bytes or text_layout pages>, "posted_date": "YYYY-MM-DD"}` returns:
```json
{
  "contract_version": "0.1",
  "model": {"name": "role_model", "sha256": "…", "trained_on": "n mentions / m documents"},
  "document": {"pages": 12, "scanned": false, "extraction_warnings": []},
  "entries": [
    {
      "number": "52.204-21", "alternate": null, "cited_date": "2021-11",
      "tier": "BINDING | NOT_BINDING | UNDETERMINED",
      "q": 0.97,
      "decided_by": "box_rule | model",
      "registry": {"status": "active|reserved|removed|rfo_only|unknown", "version_in_force": "2021-11",
                   "currency": "matches|older|newer|no_date"},
      "evidence": [{"page": 3, "line": 41, "role": "INCORPORATED_BY_REFERENCE", "p": 0.95, "text": "…"}]
    }
  ],
  "summary": {"binding": 41, "not_binding": 22, "undetermined": 6, "box_rule_share": 0.61}
}
```
Rules: `q` is the noisy-OR over mentions of the binding probability (calibrated by temperature scaling; development ECE 0.06);
`tier` = BINDING if `q >= 0.7`, NOT_BINDING if `q <= 0.3`, otherwise UNDETERMINED (a person decides); the thresholds are
configuration, not constants. Box-rule entries have `q` 1.0 or 0.0. The model **never creates a clause number**: numbers come from
regex candidates validated against the eCFR registry.

## 4. Operating numbers (measured here, CPU only)
Model file 0.86 MB; 115 ms per document including parsing and feature building (12-core desktop, 60 documents, 6,038 mentions);
extraction with PyMuPDF is separate (seconds for a long PDF). No GPU, no LLM, no network at inference. Reproduce: `fl model train`,
`fl model predict`, `scripts/ledger_eval.py`.

## 5. What VETR must provide / decide
1. A **gold sample from the product**: 200 documents with the ledger the VETR reviewers accept. This repository's gold is LLM-annotated
   and sampled from a frame that under-represents checklist-heavy documents; product acceptance should rest on VETR's own data.
2. The policy question in D-024: should a narrative requirement ("in accordance with FAR 52.204-7, registration is required") appear in the
   ledger? The model separates INCORPORATED/FULL_TEXT/SELECTED from NARRATIVE/INTERNAL; the product decides how to show the second group.
3. Cost of a false inclusion versus a miss (it sets the `tier` thresholds; development: q >= 0.7 gives precision 0.96 at recall 0.84 on the majority dev gold).

## 6. Acceptance tests before any production use
a. Parity: the ported regexes reproduce the VETR PHP outputs on 403 cases (`tests/test_vetr_parity.py`); re-run on VETR's current service.
b. On VETR's gold sample: ledger precision, recall and F1 with a cluster bootstrap over documents; the model must be non-inferior to the current
   ledger on F1 and recall (margin to be set by VETR) before it affects any customer-visible output.
c. Shadow mode for four weeks: log differences (entries only the model includes or excludes), review a weekly sample.
d. Drift monitors: share of box-rule decisions, mean `q`, share UNDETERMINED, share of documents with `scanned` true; alert on a shift above 10 points.

## 7. Data, privacy, licence
Solicitation documents are public SAM.gov attachments; the extractor redacts personal data patterns (emails, phones) before any text is
stored for training or release (`extract/privacy.py`). Training excerpts stay inside this repository's `data/` (git-ignored). A public release
would contain derived tables only (ledger entries, role labels, short evidence lines) and needs the owner's approval; the company's written
permission to publish is an open item (docs/EXECUTION_PLAN.md, section 4).

## 8. Versioning
`contract_version` changes when fields change; `model.sha256` identifies the weights; the registry snapshot date is recorded in
`data/processed/manifest_registry.json`. A new RFO deviation date or a new agency checklist format means re-running `fl registry build`
and, if the box forms change, extending `label/pilot.py: typed_item_state` (its tests list the supported forms).
