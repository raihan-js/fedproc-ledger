<!-- Copied verbatim from research-learn/fedproc-v1.md (written 2026-10-06) with Section 3 moved to CLAUDE.md. Do not edit; record deviations in docs/decisions.md. -->

# FedProc-Ledger v1 — Build Instructions for the AI Coding Agent

> **Who this is for:** an AI coding agent (Claude Code, OpenCode, or similar) working on Raihan's machine, with Raihan as the human in the loop.
> **What it builds:** a research project, an open dataset, an open model, a paper, and an integration contract for VETR Proposal.
> **Owner:** Akteruzzaman Raihan Sikder (Lead AI Engineer, VETR Proposal / Acu-Elligent LLC). HF: `raihan-js`. GitHub: `raihan-js`.
> **Written:** 6 October 2026. Re-check every external API, library version and regulation detail at build time. Things change.

---

## 0. Read this first (agent rules)

1. **Read this whole file before writing any code.** Then copy Section 3 ("Project rules") into the new repo's `CLAUDE.md`, and copy the rest into `docs/PLAN.md`.
2. **Work phase by phase.** Each phase ends with a **checkpoint**. At a checkpoint, stop, show Raihan the outputs listed, and wait for his OK before continuing.
3. **Never invent numbers.** Every number in any README, model card, article or paper must come from a file in `results/` produced by code in this repo. Tables are generated from those files by `fl report`, never typed by hand.
4. **Never invent citations.** Every paper you cite must be found on arXiv, ACL Anthology or Semantic Scholar first, with the link saved in `paper/refs.bib`. If you can't find it, don't cite it.
5. **Never invent regulation facts.** Clause numbers, dates, prescriptions, the structure of 52.212-5, and Revolutionary FAR Overhaul (RFO) deviations must come from eCFR, acquisition.gov or an agency deviation page fetched at build time, with the URL and fetch date recorded.
6. **Secrets** live only in `.env` (gitignored). Never print keys in logs. Never commit `data/`.
7. **Ask before:** spending money (LLM API calls over $5 in one run, rented GPUs), deleting anything in `data/raw/`, adding a dependency not listed here, pushing to GitHub or Hugging Face, or changing the label schema after annotation has started.
8. **Raihan's time is the scarcest resource.** Automate everything except the human judgements this plan reserves for him (annotation, go/no-go decisions, publishing).

---

## 1. Why this project exists (the problem in plain words)

VETR Proposal helps small businesses bid on US federal contracts. A solicitation (RFP) lists the FAR and DFARS **clauses** that will be part of the contract. Those clauses are the legal obligations: cybersecurity rules, subcontracting limits, labour standards, reporting duties.

VETR today finds clauses with regular expressions (`app/Services/FarClauseDetectionService.php`, 16 patterns covering FAR, DFARS and 14 agency supplements). That finds **clause numbers** well. But **a clause number appearing in a solicitation does not mean the clause binds the contract.** In real solicitations:

- **FAR 52.212-5** (and 52.213-4, DFARS 252.212-7001, and agency equivalents) contains a long list of clauses. The contracting officer **checks only the ones that apply**. Regex counts all of them.
- Clauses are bound in different ways: **incorporated by reference** (listed under 52.252-2), **included in full text**, or **selected in a checklist**.
- Clauses are often only **mentioned**: in instructions to offerors, in the statement of work, inside the text of another clause, in a table of contents, or in a sentence saying a clause does **not** apply.
- Each citation carries a **date** and sometimes an **alternate** (for example "52.219-14 (OCT 2022)" or "Alternate I"), and since 2025 many agencies issue clauses under **RFO class deviations**. The same clause number can mean different text depending on the date and the deviation.
- Some numbers are **provisions** (they govern the offer, such as representations and certifications), not **clauses** (they govern performance after award).

VETR's applicability engine (`app/Support/FarClauseApplicability.php`) returns `UNDETERMINED` whenever it lacks a fact. Commercial status is hard-coded to `null` in `FarClauseController::solicitationContext()`, so every Part 12 clause is undetermined today.

**FedProc-Ledger turns every solicitation into a verified ledger of exactly which clauses and provisions bind it**, how each is bound, at which date and alternate, under which deviation, with the page and sentence that proves it, and checked against eCFR's version history.

**Why it is research, not just a feature:**
- The task (incorporation status, not mention extraction) is new as far as we know. Verify with the literature search in Phase 9 before claiming it.
- It needs layout (checkboxes) plus language plus symbolic knowledge (registry, version history), which makes it a clean neuro-symbolic study.
- It produces real-world measurements nobody has published: how much regex over-counts, how often checkbox state is lost in text extraction, how often solicitations cite superseded or deviated clause versions during the RFO transition, and how often SAM.gov set-aside metadata disagrees with the set-aside clauses actually incorporated.

**Relationship to FedProc v0:** v0 (`raihan-js/fedproc-180m-v0`, `raihan-js/fedproc-bench`) extracted clause-number mentions. That is the easy half, and regex already does it. v1 asks what each mention *means*. The v0 source code is lost. **It is not needed**: v1 uses standard Hugging Face classes. The v0 encoder weights can be reused as one ablation (Phase 8).

---

## 2. Final deliverables

| # | Deliverable | Where |
|---|---|---|
| D1 | Code repo `fedproc-ledger`, Apache-2.0 | `github.com/raihan-js/fedproc-ledger` |
| D2 | Dataset `fedproc-ledger-bench`: gold documents, mention labels, document ledgers, splits, datasheet | `huggingface.co/datasets/raihan-js/fedproc-ledger-bench` |
| D3 | Model `fedproc-ledger-v1` (PyTorch + ONNX int8), model card | `huggingface.co/raihan-js/fedproc-ledger-v1` |
| D4 | eCFR clause registry with version history (FAR + supplements in Title 48) | inside D2, also `results/registry/` |
| D5 | Paper (LaTeX, ACL template) for arXiv cs.CL | `paper/` |
| D6 | Article (dev.to) + Japanese summary (Zenn) | `docs/article/` |
| D7 | Integration contract for VETR (API schema, hooks) | `docs/INTEGRATION.md` (deployment to GovCloud is a separate, later instruction) |

---

## 3. Project rules

Moved to [`../CLAUDE.md`](../CLAUDE.md) (the spec asks for it to live there).

---

## 4. Environment setup (Phase 0, ~½ day)

1. Create the repo **outside** the VETR repo and outside the interview-prep app, for example `~/code/fedproc-ledger`. `git init`, Apache-2.0 `LICENSE`, `.gitignore` (include `data/`, `.env`, `*.onnx` over 100MB, `wandb/`, `mlruns/`).
2. `uv init` with Python 3.11. Add the stack from Section 3.
3. GPU check: print `torch.cuda.is_available()`, device name, VRAM. Raihan has an RTX 3060 12GB (also a 4060). Write the result to `docs/decisions.md`.
   - On Windows, everything except vLLM works natively. vLLM needs Linux or WSL2. If the machine is Windows, set up WSL2 Ubuntu for the local-LLM baseline only.
   - ModernBERT runs with PyTorch SDPA. `flash-attn` is optional (Linux only); don't block on it.
4. `.env.example`:
   ```
   GOVCON_API_KEY=            # required (govconapi.com, Bearer token)
   GOVCON_BASE_URL=https://govconapi.com/api/v1
   SAM_API_KEY=               # optional, only if attachment downloads start failing
   ANTHROPIC_API_KEY=         # optional, LLM baselines + silver labels
   HF_TOKEN=                  # for pushing at the end
   ```
5. Typer CLI skeleton `fl` with `--help`. pytest, ruff, mypy, pre-commit. A GitHub Actions workflow running tests and ruff (no data needed).
6. Create `docs/decisions.md`, `docs/preregistration.md` (empty template), `docs/PLAN.md` (this file minus Section 3).

**Checkpoint 0:** show the tree, `fl --help`, the GPU line, and passing tests.

---

## 5. Phase 1 — Data acquisition with GovCon API (~2 days of agent time, mostly unattended)

### 5.1 What GovCon API provides (verified 6 Oct 2026; re-check the docs)

- Auth header: `Authorization: Bearer $GOVCON_API_KEY`. Base: `https://govconapi.com/api/v1`.
- **Search:** `GET /opportunities/search` with `notice_type` (comma-separated OR, e.g. `Solicitation,Combined Synopsis/Solicitation`), `posted_from`, `posted_to` (YYYY-MM-DD), `agency` (partial match), `set_aside`, `naics`, `psc`, `has_attachments=true`, `limit` (max 1,000 on paid plans), `offset`, `fields`, `sort_by=posted_date`. Response: `data[]` with `notice_id`, `solicitation_number`, `title`, `notice_type`, `posted_date`, `agency`, `set_aside_type`, `naics`, `psc`, `description_text`, `resource_links_array`, `sam_url`; and `pagination` (`total` capped at 10,000, `has_next`).
- **Pro plan only:** `content=` full-text search inside attachments (PDF, Word, Excel, OCR). Ask Raihan which plan he has. If Pro, use `content="52.212-5"` to oversample checklist solicitations. If not, filter after download.
- **Attachments:** `GET /opportunities/{notice_id}/attachments` → `files[]` with `url` (direct SAM.gov download link), `resource_id`, `filename`, `size_bytes`, `file_type`.
- Rate limits: Developer plan about 1,000 requests/hour. Budget every run with a token bucket and log calls used. VETR already treats GovCon calls as a budget (`app/Support/GovConCallBudget.php`).
- Docs: https://govconapi.com/api-guide , https://govconapi.com/api-guide/search-endpoint , https://govconapi.com/api-guide/attachments

### 5.2 Downloading files

The `url` values are direct SAM.gov links that redirect to S3/CloudFront. VETR's `app/Jobs/ImportRfpFromUrl.php` fetches them **without an API key**, following redirects. Do the same:
- httpx, follow redirects (max 5), timeout 60s, `User-Agent: fedproc-ledger-research/1.0 (contact: araihansikder@gmail.com)`.
- Politeness: at most 1 download per second, exponential backoff on 429/5xx (tenacity), resume-safe (skip files whose sha256 is already stored).
- Keep only `.pdf`, `.docx`, `.doc`, `.txt`. Record but skip spreadsheets and images. Skip files over 50 MB.
- Only if downloads start returning 401/403, append `api_key=$SAM_API_KEY` and record that in `docs/decisions.md`.

### 5.3 Sampling plan

Goal: a **pool** of about 3,000 unique solicitations with clause-bearing attachments, diverse in agency and time.

1. Query month by month from **2024-01** to the most recent full month, `notice_type=Solicitation,Combined Synopsis/Solicitation`, `has_attachments=true`.
2. Stratify by top-level department (DoD components, VA, GSA, DHS, HHS, DOE, NASA, USDA, DOI, DOJ, DOT, others). Cap any department at 25% of the pool.
3. **Deduplicate on `solicitation_number`** (one solicitation has many `notice_id`s). Keep the most recent notice and record the others in `notice_lineage`. Amendments are out of scope for v1; record them for v2.
4. Also store `description_text` as a pseudo-document. Combined synopsis/solicitations often list clauses directly in the description.
5. After download and extraction (Phase 3), mark a document **clause-bearing** if it contains at least 3 regex clause candidates.
6. If the plan allows `content=`, run a separate oversample of solicitations containing `52.212-5` or `252.212-7001`, tagged `oversample=true` so statistics can be reweighted.

### 5.4 Legal and privacy filter (do not skip)

SAM.gov public attachments are mostly US government works (not copyrightable under 17 U.S.C. §105), but some attachments are contractor-authored or carry markings.
- Flag and **exclude from the public release** any document containing: `CUI`, `Controlled Unclassified Information`, `FOUO`, `Proprietary`, `Source Selection Information`, `Distribution Statement` B/C/D/E/F, or `Export Controlled` / `ITAR` / `EAR`. They may still be used for internal statistics; record counts.
- In released text, **redact personal emails and phone numbers** (contracting officer contact details) with a tested regex, replacing them with `[EMAIL]` and `[PHONE]`.
- Record `license_flag` per document: `government_work`, `excluded_marking`, or `unknown`.

### 5.5 Outputs

- `data/raw/files/{sha256}.{ext}`: the original bytes.
- `data/interim/notices.parquet`: one row per kept notice with all search fields.
- `data/interim/documents.parquet`: `doc_id` (first 16 hex of sha256), `notice_id`, `solicitation_number`, `resource_id`, `filename`, `file_type`, `size_bytes`, `posted_date`, `agency`, `department`, `set_aside_type`, `naics`, `notice_type`, `source_url`, `download_ts`, `sha256`, `license_flag`, `oversample`.
- `results/acquisition_stats.json`: counts by department, month, file type, failures by reason, API calls used.

**Checkpoint 1:** show `acquisition_stats.json` plus 10 random documents (title, agency, size). Confirm disk use with Raihan (expect 10–40 GB).

---

## 6. Phase 2 — Clause registry with version history from eCFR (~1.5 days)

### 6.1 Sources

eCFR versioner API (base `https://www.ecfr.gov`). Verify paths at https://www.ecfr.gov/developers/documentation/api/v1 before coding. Expected endpoints:
- `GET /api/versioner/v1/titles.json`
- `GET /api/versioner/v1/structure/{date}/title-48.json`
- `GET /api/versioner/v1/versions/title-48.json?part=52` (also `section=52.219-14`): the dates each section changed
- `GET /api/versioner/v1/full/{date}/title-48.xml?part=52&section=52.219-14`: section XML as of a date

eCFR point-in-time history starts in **January 2017**. Record the earliest date you actually get.

### 6.2 What to build

For every "x52" part in Title 48 (FAR part 52, DFARS 252, and each agency supplement present in eCFR, such as GSAM 552, VAAR 852, HSAR 3052, NFS 1852, DOSAR 652, AIDAR 752, DEAR 952, HHSAR 352, AGAR 452, AFARS 5152, DAFFARS 5352, NMCARS 5252, HUDAR 2452), build `registry.parquet`:

| field | meaning |
|---|---|
| `number` | canonical, e.g. `52.219-14`, `252.204-7012` |
| `regulation` | FAR, DFARS, GSAM, … (map eCFR chapter → supplement name; DLAD and others not in eCFR are listed as `not_in_ecfr`) |
| `title` | section heading without the number |
| `kind` | `provision` or `clause`, parsed from the prescription text ("insert the following provision/clause"). If unparseable, `unknown`, never guessed |
| `prescribed_in` | the prescribing section reference, if present |
| `current_date` | the clause date in the current text, e.g. `OCT 2022` |
| `alternates` | list of `{name: "Alternate I", date: "NOV 2011"}` |
| `versions` | list of `{effective_from, effective_to, clause_date, alternates}` built from the versions endpoint, by fetching the section at each change date |
| `removed` | true if the section no longer exists in the current eCFR |

Also build `deviations.parquet` **by hand-curated scraping**, not inference: for RFO class deviations to Part 52 from DoD (DPAP DARS), DHS, DOE and GSA pages, record agency, deviation number, date, affected clause numbers and the URL. If a page can't be parsed reliably, record the URL and ask Raihan. This table is used only to *label* a citation as "under deviation", never to change the ledger. Starting URLs (verify):
- https://www.acq.osd.mil/dpap/dars/dfars_far_overhaul_class_deviations.html
- https://www.dhs.gov/publication/cpo-rfo-deviation-far-part-52
- https://www.acquisition.gov/far-overhaul

### 6.3 Date normalisation

Clause dates appear as `(OCT 2022)`, `(Oct 2022)`, `OCT 2022`, `10/2022`, `October 2022`. Normalise to `YYYY-MM`. Unit tests from real snippets.

### 6.4 Tests

- 30 well-known numbers resolve (52.212-4, 52.212-5, 52.204-21, 52.219-14, 52.252-2, 252.204-7012, 252.204-7021, 252.212-7001, …).
- `kind` is correct for 20 hand-checked numbers (for example 52.212-1 provision, 52.212-4 clause, 52.212-3 provision).
- For 52.219-14, the versions list contains more than one clause date since 2017 (verify against eCFR).

**Checkpoint 2:** registry counts per regulation, `kind` distribution, number of unknowns, 10 sampled rows with their eCFR URLs.

---

## 7. Phase 3 — Layout-aware text extraction (~3 days)

The core technical insight: **checkbox state is layout, not language**, and today's production extractor (Smalot PdfParser in `app/Jobs/ParseRfpDocument.php`) throws most of it away. So FedProc-Ledger extracts text itself, from the original bytes, and makes checkbox state explicit.

### 7.1 Two text views per page (both kept, for the ablation)

- `text_plain`: plain reading-order text (PyMuPDF `get_text("text")`). This approximates what VETR sees today.
- `text_layout`: the same text plus **explicit markers** inserted at the start of the line they belong to:
  - `⟦X⟧` checked box, `⟦ ⟧` unchecked box, `⟦?⟧` a box exists but its state couldn't be determined.

### 7.2 Where checkbox state hides (detect all four, record which one fired)

1. **Form widgets:** PyMuPDF `page.widgets()`, checkbox fields with `field_value` (on/off). Map each widget rectangle to the nearest text line to its right on the same baseline.
2. **Glyphs:** ☐ ☑ ☒ ■ □ ✓ ✔ ✗, Wingdings/ZapfDingbats private-use code points (collect the actual code points you encounter, log them, add tests), `[X]`, `[ ]`, `(X)`, `_X_`, `__`, `X` alone in a left column.
3. **Vector drawings:** `page.get_drawings()`: small near-square rectangles (side 5–14 pt) at line starts; diagonal strokes or a filled path inside → checked. Heuristic, so record a confidence.
4. **Lost:** the line looks like a checklist item (starts with `(n)` or `(n)(i)` and contains a clause number inside a checklist section) but no box signal was found → `⟦?⟧`.

Measure on the gold set later: share of checklist items recovered by each source, and share lost. **This is Finding F2 in the paper.**

### 7.3 DOCX

python-docx plus raw XML: content-control checkboxes (`w14:checkbox`, `w14:checked`), legacy form checkboxes (`w:ffData/w:checkBox`), and symbol runs (`w:sym` with Wingdings). Same markers. Convert `.doc` with LibreOffice headless if available; otherwise skip and count.

### 7.4 Scanned PDFs

If a page has no text layer, mark the document `scanned=true`. v1: exclude scanned documents from gold and training, and report the share. (OCR is a v2 item; don't spend time on it now.)

### 7.5 Offsets

Every character of `text_layout` maps back to `(page, x0, y0, x1, y1)` and to `text_plain` offsets. Evidence spans in the final ledger must point to a page and a bounding box so VETR can highlight them later.

### 7.6 Outputs

`data/processed/pages.parquet`: `doc_id`, `page`, `text_plain`, `text_layout`, `box_signals` (counts by source), `offset_map` (compressed), `scanned`.

**Checkpoint 3:** a small HTML report rendering 5 checklist pages side by side (page image | `text_layout` with markers highlighted), plus counts of each box source over the pool.

---

## 8. Phase 4 — Candidates and the rules baseline (~2 days)

### 8.1 Candidate generator (symbolic, high recall)

Port VETR's 16 patterns from `app/Services/FarClauseDetectionService.php` (ordered longest-prefix-first) to Python, then extend:
- hyphen variants (`-`, `‑` U+2011, `–` en dash, `—` em dash), stray spaces (`52. 219-14`, `52.219 -14`)
- prefixes `FAR`, `DFARS`, `Clause`, `Provision`, `Section`
- subparagraph references `52.212-5(b)(16)` → base number + `subpara`
- ranges `52.219-1 through 52.219-9` → expand, flag `from_range`
- obvious non-clauses (money like `$52.212`, phone numbers, CAGE/UEI) → still emitted, so the model learns `NOT_A_CLAUSE`

Each candidate records: `cand_id`, `doc_id`, `page`, `char_start`, `char_end`, `raw`, `number`, `regulation`, `subpara`, `line_text`, `cited_date` (parsed from the same line), `alternate` (`Alternate I`–`V`, `Alt II`), `deviation_marker` (`DEVIATION` + number on the line), `box_marker` (the marker on the line, if any), `in_registry` (bool).

**Candidate recall on gold is reported in the paper.** A clause the generator misses is an end-to-end error.

### 8.2 Section detector (rules)

Tag line ranges as: `TOC`, `CLAUSE_LIST_IBR` (under 52.252-2 or "clauses incorporated by reference"), `CHECKLIST` (inside the text of 52.212-5, 52.213-4, 252.212-7001, or an agency checklist), `FULL_TEXT_CLAUSE` (a clause heading followed by its body), `INSTRUCTIONS` (Section L / 52.212-1 addenda), `EVALUATION` (Section M / 52.212-2), `SOW`, `OTHER`. Heading regexes plus state machine. Used by the rules baseline and as an optional auxiliary label.

### 8.3 Rules baseline (B1)

A deterministic classifier using section + box marker + line patterns (for example: in `CHECKLIST` with `⟦X⟧` → selected; in `CLAUSE_LIST_IBR` → incorporated by reference; in `TOC` → index entry; phrases "does not apply", "is deleted", "is not applicable" → excluded). Make it **as strong as you reasonably can**. A weak baseline makes the paper worthless.

### 8.4 VETR status-quo baseline (B0)

Every candidate that matches a registry number is "binding". This is exactly how VETR behaves today. It's the number the product improvement is measured against.

**Checkpoint 4:** rules baseline output on 5 documents as an HTML table (candidate, line, predicted role) for Raihan to eyeball.

---

## 9. Phase 5 — Label schema, guidelines, and the pilot (go/no-go) (~3 days + ~8 hours of Raihan's time)

### 9.1 Mention-level label: `role` (one per candidate)

| role | meaning | binds? |
|---|---|---|
| `INCORPORATED_BY_REFERENCE` | listed as incorporated by reference (52.252-2 lists, "the following clauses are incorporated by reference") | yes |
| `FULL_TEXT` | the clause's heading where its full text is included | yes |
| `CHECKLIST_SELECTED` | selected in a checklist clause (52.212-5, 52.213-4, 252.212-7001, agency checklists) | yes |
| `CHECKLIST_NOT_SELECTED` | listed in a checklist but not selected | no |
| `EXPLICITLY_EXCLUDED` | stated not to apply, deleted, or replaced | no (overrides) |
| `INTERNAL_REFERENCE` | cited inside the text of another clause or prescription ("as defined in 52.204-7") | no, on its own |
| `NARRATIVE_MENTION` | cited in instructions, evaluation, SOW or other narrative | no, on its own |
| `INDEX_ENTRY` | table of contents, index, header/footer repeat | no |
| `NOT_A_CLAUSE` | the candidate is not a clause/provision reference | no |
| `UNCLEAR` | the annotator cannot decide from the document (annotators must write a note) | excluded from scoring, counted |

**Attributes** (rules extract, annotators correct): `cited_date`, `alternate`, `deviation`.

### 9.2 Document-level labels

- **Ledger:** the set of `(number, alternate)` that bind = union of mentions in {IBR, FULL_TEXT, CHECKLIST_SELECTED} minus any {EXPLICITLY_EXCLUDED}. The annotation tool computes it, shows it, and lets the annotator **override** with a note (overrides are counted and reported).
- `is_commercial`: yes / no / unclear (with evidence: SF 1449 present, 52.212-4 incorporated, explicit statement).
- `form_type`: SF 1449 / SF 33 / SF 18 / other / none.
- `set_aside_from_clauses`: derived, then confirmed.

### 9.3 Annotation guidelines (`docs/annotation_guidelines.md`)

Write them **from the current text of 52.212-5 and 52.252-2 fetched from eCFR**, not from memory. The paragraph structure of 52.212-5 matters (for example, which paragraphs list clauses incorporated without checkboxes, which are checkbox lists, and which are subcontract flow-downs). Check whether RFO deviations changed that structure and handle both versions. Include 2–3 real examples per role, edge cases, and a decision tree.

**Raihan should ask Dr. Lori Smith** (VETR founder, retired federal contracting officer) to review the guidelines and to second-annotate part of the gold set. A retired contracting officer validating the labels is a major credibility point for the paper. Ask Raihan to get her written OK to be acknowledged (or listed as an author if she contributes substantially).

### 9.4 Annotation tool (`fl annotate`, Streamlit)

- Shows one document at a time: page image on the left with the candidate's bounding box highlighted; `text_layout` context (±6 lines) on the right; pre-label from the rules baseline.
- Keyboard: `1`–`9` and `0` pick the role, `Enter` accepts the pre-label, `n` adds a note, `j`/`k` next/previous candidate, `b` bulk-applies a role to all remaining candidates in the same section (big time saver on 60-item checklists, but each bulk action is logged).
- Document-level panel: computed ledger, `is_commercial`, `form_type`, override box.
- Saves to `data/labels/{annotator}/gold_mentions.parquet` and `gold_docs.parquet` after every action. Records time spent per document.

### 9.5 Pilot and go/no-go gate (do this **before** the big annotation effort)

1. Raihan annotates **20 clause-bearing documents** (stratified: about 8 with a checklist clause, 6 with an IBR list, 6 others).
2. Compute on the pilot:
   - B0 (VETR status quo) binding-set precision and recall
   - B1 rules baseline mention macro-F1 and binding-set F1
   - share of mentions that do not bind
   - checklist box recovery by source
   - minutes per document
3. **Go** if B0 binding-set precision < 0.85 **or** B1 binding-set F1 < 0.90 (there is a real gap for a model to close).
4. **Pivot** if both are above those thresholds. The rules already solve it, so the paper's centre moves to the corpus findings (version currency, deviations, set-aside inconsistency) and the rules engine itself, with a smaller model study. Write the numbers in `docs/decisions.md` and **stop for Raihan's decision.**

**Checkpoint 5 (decision):** the pilot report, `results/pilot.json`, the time estimate for the full gold set, and a go/pivot recommendation.

---

## 10. Phase 6 — Gold annotation, splits, pre-registration (~2–3 weeks of evenings for Raihan)

### 10.1 Size

Target **150 gold documents** (about 8,000–10,000 mentions; measure from the pilot). The 20 pilot documents count if the guidelines didn't change; otherwise re-check them.

### 10.2 Splits (by `solicitation_number` group, so no solicitation appears in two splits)

| split | docs | purpose |
|---|---|---|
| `gold_train` | 45 | fine-tuning on human labels |
| `dev` | 25 | model selection, threshold tuning |
| `test_iid` | 50 | primary results |
| `test_ood_agency` | 15 | two departments never seen in training or dev (choose them **now**, before any modelling, and record them) |
| `test_recent` | 15 | posted in the most recent 3 months (RFO-era drift) |

The silver pool (Phase 7) must exclude every solicitation in dev and test splits.

### 10.3 Inter-annotator agreement

A second annotator (Dr. Lori Smith or another qualified person) labels **30 documents** (from `test_iid` and `dev`) independently. Report Cohen's κ on `role` and binding-set agreement (Jaccard). Disagreements are adjudicated by Raihan and recorded. If κ < 0.75, revise the guidelines and re-annotate the affected cases before training.

### 10.4 Pre-registration (`docs/preregistration.md`, committed before any test evaluation)

Write down: the primary metric (document-level binding-set F1 on `test_iid`), secondary metrics, the baselines, the main hypotheses (for example: H1 the model beats B1 on binding-set F1; H2 layout markers matter, measured by the drop in the text-only ablation; H3 the OOD-agency drop is under X points), and the statistical tests. Commit it and record the commit hash in `docs/decisions.md`. Reviewers trust pre-registered results more.

### 10.5 Freeze

Hash every split file (sha256) into `docs/decisions.md`. From now on, test files are read **only** by `fl evaluate --final`.

**Checkpoint 6:** IAA report, split sizes, frozen hashes, pre-registration commit.

---

## 11. Phase 7 — Silver labels for scale (~2 days, ~$20–60 of API, ask first)

Gold alone (45 training documents) is small. Add silver labels on the pool (excluding all dev/test solicitations):

1. Run B1 rules on every clause-bearing pool document.
2. Run an LLM labeler (Claude Haiku-class via API, model ID pinned in config; ; Qwen is excluded, D-021) on chunks with candidates listed by ID; JSON output validated against the schema; temperature 0.
3. **Keep** a candidate's silver label where rules and LLM agree. Send disagreements to a second LLM pass or drop them. Record agreement rates per role.
4. Measure silver accuracy on `dev` (silver labeler vs gold) and report it.
5. State in the paper that silver labels come partly from an LLM that is also a baseline. Gold test labels are purely human, so the comparison stays fair.

Output: `data/labels/silver_mentions.parquet` with `source` (`rules`, `llm`, `agree`).

---

## 12. Phase 8 — The model (~5 days, multi-day GPU allowed)

### 12.1 Architecture: span classification over a long window

- Encoder: `answerdotai/ModernBERT-base` (8,192-token context, efficient on long documents). Also `ModernBERT-large` as a size ablation (fits a 12GB GPU with bf16, gradient checkpointing, window 1,024–2,048, batch 1 with accumulation).
- Input: `text_layout` of a document, split into windows of `W` tokens (default 2,048) with stride `W/2`. Add the box markers `⟦X⟧ ⟦ ⟧ ⟦?⟧` as **new special tokens** (resize embeddings) so the tokenizer doesn't fragment them.
- Each candidate is classified in the window where it is closest to the centre.
- Candidate representation: mean of its token embeddings, concatenated with the mean of its line's token embeddings, then a 2-layer MLP → 10 roles (`UNCLEAR` is not a training target; drop those mentions).
- Optional auxiliary head: token-level section tag (from the rules section detector on silver, human-corrected section boundaries on gold if cheap). Ablate it.
- Loss: cross-entropy with class weights (inverse sqrt frequency). Label smoothing 0.05.
- Attributes (`cited_date`, `alternate`, `deviation`) stay rule-extracted in v1. Evaluate them separately; if their error rate is above 2%, add a small head in v1.1.

**The model never outputs a clause number.** Identity comes from the text via the candidate generator and is validated by the registry. Say this clearly in the paper: hallucinated clause numbers are impossible by construction, unlike generative approaches (connect to FedProc-Bench v0 and the constrained-decoding results in `raihan-js/fedproc-constrained-results`).

### 12.2 Training recipe (starting point; tune on `dev` only)

- Stage A: silver, 3 epochs, lr 3e-5, warmup 10%, cosine decay, weight decay 0.01, bf16, effective batch 16 windows.
- Stage B: `gold_train`, 5–10 epochs, lr 1e-5, early stopping on dev binding-set F1.
- Seeds: 3 per configuration; report mean ± sd.
- Log every run to MLflow (local) with config hash, data hashes and git SHA.

### 12.3 Ablations (each with 3 seeds, all evaluated on dev during development and on test once at the end)

| id | change | question |
|---|---|---|
| A1 | `text_plain` instead of `text_layout` | how much does recovered checkbox state matter? (the production-extractor scenario) |
| A2 | window 512 / 1,024 / 2,048 / 4,096 | how much context does status need? |
| A3 | gold only / silver only / silver→gold | value of silver labels |
| A4 | init from FedProc v0 encoder (load `raihan-js/fedproc-180m-v0` safetensors, keep keys of the ModernBERT encoder, drop the heads; record which keys loaded) vs plain ModernBERT-base | does v0's domain training transfer? |
| A5 | ModernBERT-large | does size help? |
| A6 | without the section auxiliary head | does structure supervision help? |
| A7 | learning curve: 10 / 25 / 45 gold training documents | data efficiency |

### 12.4 Baselines (all on the same candidates and windows)

- **B0** VETR status quo (Section 8.4)
- **B1** rules (Section 8.3)
- **B2** LLM zero-shot, few-shot with 5 guideline examples: one strong API model and one fast API model (Claude family, IDs pinned; optional GPT-4o-class), and one local open model (not Qwen, D-021; for example a US-origin open model, AWQ, via vLLM). Same chunking and JSON schema as the silver labeler. Record cost and latency per document. **Ask Raihan before running** (expected total under $40 for 150 documents).
- **B3** a fine-tuned small baseline without layout or long context (DeBERTa-v3-base, window 512) to show what ModernBERT's context buys.

### 12.5 Export

- `optimum` ONNX export plus dynamic int8 quantisation.
- Parity check: predicted role agreement with PyTorch ≥ 99% on dev, and binding-set F1 difference ≤ 0.5 points.
- CPU latency per document (p50/p95) on 2 and 4 threads, plus peak RAM. These numbers decide the Fargate task size later.

---

## 13. Phase 9 — Evaluation and findings (~4 days)

### 13.1 Metrics

- **Primary:** document-level binding-set F1 (micro over documents) on `test_iid`. A predicted ledger entry is correct if `(number)` matches; **strict** variant also requires `alternate` and `cited_date` to match.
- Mention-level role macro-F1 and per-role F1, and a confusion matrix.
- Whole-ledger exact match rate (share of documents whose ledger is perfect).
- Provision vs clause split of the ledger (using registry `kind`).
- Candidate generator recall.
- All with **cluster bootstrap over documents** (10,000 resamples) 95% CIs; **paired** bootstrap for model-vs-baseline differences. Mentions inside one document are correlated, so never bootstrap mentions independently.
- Report `test_ood_agency` and `test_recent` separately, with the drop from `test_iid`.

### 13.2 Version currency check (`fl currency`)

For every binding ledger entry with a `cited_date`:
- Find the eCFR version in force on the notice's `posted_date`.
- Categories: `CURRENT` (cited date equals the clause date then in force), `SUPERSEDED` (cited date older), `NEWER_THAN_ECFR` (cited date not yet in eCFR on that day; often a deviation), `UNKNOWN_DATE` (date not found in any version), `DEVIATION_MARKED` (citation carries a deviation marker; checked against `deviations.parquet`).
- Validate on gold: annotators confirm the cited date in 9.1, so the check's input is verified.
- **Wording rule:** call these "date mismatches", not "errors". Agencies may legitimately use deviation text during the RFO transition.

### 13.3 Downstream impact on VETR's applicability engine

Port `app/Support/FarClauseApplicability.php` to Python (`eval/applicability.py`). It is pure, about 425 lines.
- **Parity test:** write a tiny PHP script in the VETR repo (run locally with `php`, not committed to VETR) that evaluates 200 generated `(applicability, context)` fixtures and writes JSON. The Python port must match 100%.
- Use VETR's clause library rules (`database/seeders/FarClauseSeeder.php`, 69 clauses, exported to JSON) as the clause set.
- For each `test_iid` document, compute verdicts with (a) today's context (`is_commercial = null`, other fields from SAM metadata) and (b) context enriched by the ledger's derived facts (`is_commercial` from 52.212-4/52.212-5/SF 1449; set-aside cross-check).
- Report: share of `UNDETERMINED` verdicts resolved, and **correctness of the resolved verdicts against gold document labels**. The target is many resolved verdicts with zero wrong ones; any wrong one is listed in the error analysis.

### 13.4 Corpus findings (run the final model on the whole clause-bearing pool, calibrated against gold)

| id | finding | how |
|---|---|---|
| F1 | Regex over-count: mentions per solicitation vs binding entries per solicitation | model on pool; gold-based estimate with CI |
| F2 | Checkbox state recoverability: share of checklist items whose state comes from widgets / glyphs / drawings / is lost | Phase 3 signals on gold checklists |
| F3 | Version currency: share of binding clauses `SUPERSEDED`, `DEVIATION_MARKED`, by department and by month (RFO trend) | 13.2 |
| F4 | Set-aside consistency: SAM `set_aside_type` vs set-aside clauses actually incorporated (build the clause→set-aside map from current FAR Part 19 text and deviations; Raihan/Dr. Smith confirm the map) | ledger vs metadata |
| F5 | Commercial-status coverage: share of solicitations where `is_commercial` becomes decidable from the ledger | 13.3 |

For every pool-level number, also report the model's error rate on the gold set for that quantity, so readers can judge how much of the estimate is noise.

### 13.5 Error analysis

Hand-review 100 test errors (or all, if fewer). Categorise them (lost checkbox, section boundary, cross-reference vs incorporation, exclusion missed, alternate/date, extraction artefact, guideline ambiguity) with counts and 2 real examples each.

**Checkpoint 9:** `results/final/*.json`, generated tables and figures, the error analysis, and a one-page summary of what the results actually support. Raihan approves the claims before the paper is written.

---

## 14. Phase 10 — Paper, releases, article (~1–2 weeks)

### 14.1 Paper (`paper/`, LaTeX, ACL style, 8 pages + appendix)

Working title (pick after results): **"Mentioned Is Not Binding: Clause Incorporation Status Extraction from U.S. Federal Solicitations"**.

Structure:
1. **Introduction:** the obligation problem; regex finds numbers, not obligations; RFO makes versions matter now. Contributions (only those the results support):
   (1) the task and label schema;
   (2) FedProc-Ledger-Bench: gold documents with a contracting-officer-validated subset, IAA, IID/OOD-agency/recent splits;
   (3) a layout-aware neuro-symbolic pipeline (symbolic identity + registry + version history, neural status) with strong rules and LLM baselines;
   (4) corpus findings F1–F5;
   (5) deployment evidence (CPU latency, downstream verdict resolution in a production compliance engine).
2. **Related work** (search and verify each): contract clause datasets (CUAD, LEDGAR, MAUD, ContractNLI, LexGLUE), legal citation extraction, form and checkbox understanding (FUNSD, Kleister and related), long-document encoders (ModernBERT), constrained decoding and grounding, procurement NLP, FedProc-Bench v0. State precisely what's new relative to each.
3. **Task and data:** sources, sampling, legal filter, extraction, the label schema, guidelines summary, IAA, statistics.
4. **Method:** candidates, registry and versions, layout markers, model, training.
5. **Experiments:** baselines, main results, ablations A1–A7, OOD and recent splits.
6. **Downstream and corpus findings:** 13.3 and F1–F5.
7. **Error analysis.**
8. **Limitations:** public solicitations only; amendments not modelled; scanned PDFs excluded; US federal only; deviation table hand-curated; date-mismatch is not legal error; silver labels partly LLM-made; small gold set.
9. **Ethics and data statement:** not legal advice; government works plus exclusions; PII redaction; no CUI; annotator compensation/consent; the authors' affiliation with a company that sells proposal software (conflict-of-interest statement).

Figures: pipeline diagram; example page with markers and predictions; binding-set F1 by method with CIs; A1 layout ablation; OOD drop; currency/deviation trend by month (F3). Tables: data stats, IAA, main results, ablations, downstream verdicts, costs/latency.

### 14.2 arXiv submission checklist (why the last one may have been rejected, and how to avoid it now)

- arXiv moderation is not peer review. The usual reasons for a hold or rejection are: **first-time submitters in a category need an endorsement**, the wrong primary category, or the submission reads like a project report instead of a research paper. Ask Raihan for the exact reason in the rejection email and record it in `docs/decisions.md`.
- Primary category **cs.CL**; cross-list cs.IR and cs.AI.
- If an endorsement is needed: find someone who has published in cs.CL (a co-author, a former collaborator, a researcher in legal NLP) and request it through arXiv's endorsement system. Never pay for or trade endorsements.
- Submit LaTeX source, not only a PDF. Licence CC BY 4.0. Self-contained figures, no broken references, a proper abstract (≤ 1,920 characters).
- **Company permission:** this work uses VETR context and names the product. Get written permission from Acu-Elligent LLC (Dr. Lori Smith) to publish the paper, the model and the dataset, and agree on the affiliation line.

### 14.3 Hugging Face

- Dataset card (datasheet format): motivation, composition, collection, preprocessing and redaction, labelling, splits with frozen hashes, IAA, licence and exclusions, intended and out-of-scope uses (not legal advice, not a compliance determination), maintenance.
- Model card: task, label set, training data, metrics with CIs on every split, ablation summary, ONNX usage, CPU latency, limitations, the "model never generates clause numbers" design note, citation.
- Optional: a CPU Gradio Space where you upload a public solicitation PDF and get its ledger with highlighted evidence.

### 14.4 GitHub release

README with: a 3-line summary, a ledger screenshot, quick start (`fl ledger path/to/rfp.pdf`), reproduction commands per table, a links section (paper, dataset, model, article), and a citation block. Tag `v1.0.0`. Optional Zenodo DOI.

### 14.5 Article (`docs/article/`)

dev.to: "Mentioned is not binding: why your RFP clause list is wrong." Lead with one real checklist example and the regex over-count, then results, then limitations. Zenn: a short Japanese summary linking to the English article and paper (have a fluent reader check it, and say who did).

---

## 15. Phase 11 — VETR integration contract (design now, deploy later)

**Deployment to AWS GovCloud is a separate instruction Raihan will request after v1.** In this phase, only write `docs/INTEGRATION.md` and implement `fl serve` locally, so the model is built to fit VETR from day one.

### 15.1 Service shape

A Python FastAPI sidecar (`src/fedproc_ledger/serve/`), CPU-only, ONNX int8, packaged as a container. It **receives the original file bytes** and does its own extraction (VETR's Smalot-based text loses checkbox state, as ablation A1 quantifies).

`POST /v1/ledger` (multipart file, plus optional JSON `{"posted_date": "...", "agency": "...", "set_aside_type": "..."}`) returns:

```json
{
  "model_version": "fedproc-ledger-v1.0.0",
  "registry_version": "ecfr-2026-10-xx",
  "document": {"pages": 42, "scanned": false, "form_type": "SF1449"},
  "entries": [
    {
      "number": "52.219-14",
      "regulation": "FAR",
      "kind": "clause",
      "title": "Limitations on Subcontracting",
      "status": "CHECKLIST_SELECTED",
      "binding": true,
      "alternate": null,
      "cited_date": "2022-10",
      "date_status": "CURRENT",
      "deviation": null,
      "confidence": 0.97,
      "evidence": [{"page": 31, "bbox": [72.0, 410.2, 540.1, 422.8], "snippet": "⟦X⟧ (17)(i) 52.219-14, Limitations on Subcontracting (OCT 2022)"}]
    }
  ],
  "not_binding": [{"number": "52.219-9", "status": "CHECKLIST_NOT_SELECTED", "evidence": [...]}],
  "derived_facts": {
    "is_commercial": {"value": true, "evidence": ["52.212-4 incorporated", "SF1449 on page 1"]},
    "set_aside_clauses": ["52.219-27"]
  },
  "warnings": ["3 checklist items had undetermined box state (⟦?⟧)"]
}
```

Rule carried over from VETR's own design: **low confidence never becomes a verdict.** Below a threshold tuned on dev, `binding` is `null` ("not determined") and the item is listed in `warnings`.

`GET /health` returns model and registry versions.

### 15.2 Where it plugs into VETR (for the later deployment instruction)

Record these in `docs/INTEGRATION.md`; do **not** edit the VETR repo in this project.
- **New job** after `app/Jobs/ParseRfpDocument.php` succeeds: `BuildClauseLedger` sends the stored document bytes to the sidecar and stores the result in new tables (for example `rfp_clause_ledgers` and `rfp_clause_entries`), behind a per-organization feature flag.
- `app/Services/FarClauseDetectionService.php`: when a ledger exists for the RFP, use ledger entries (binding only) for `matched`, expose `not_binding` separately, and keep regex as the fallback when the sidecar is down or the flag is off.
- `app/Http/Controllers/FarClauseController.php::solicitationContext()`: set `is_commercial` from `derived_facts.is_commercial` only when present with evidence; otherwise keep `null`.
- The far-compliance page: show status, cited date, date status and the evidence snippet (page link) per clause; separate "Provisions (answer in your offer)" from "Clauses (comply after award)".
- Infrastructure: a separate ECS Fargate service in the existing VPC (`infrastructure/aws/cloudformation.yml` defines the cluster). Size it from the Phase 8 CPU latency numbers; the current worker task (0.25 vCPU / 512 MB) is too small to host it.
- Data handling: customer documents stay in-boundary; the sidecar stores nothing and logs no document text.

---

## 16. Timeline (realistic for a full-time job plus evenings)

| week | phases | Raihan's hands-on time |
|---|---|---|
| 1 | 0, 1, 2 | ~2 h (keys, checkpoints) |
| 2 | 3, 4, 5 pilot | ~10 h (pilot annotation, go/no-go) |
| 3–5 | 6 gold annotation (+ Dr. Smith's 30 docs) | ~35–45 h |
| 5 | 7 silver | ~1 h |
| 6–7 | 8 training (multi-day GPU OK), baselines | ~3 h |
| 7–8 | 9 evaluation, findings, error analysis | ~6 h |
| 8–10 | 10 paper, releases, article | ~15 h |
| after | 11 deployment (separate instruction) | — |

---

## 17. Risks and how this plan handles them

| risk | handling |
|---|---|
| The rules baseline already solves it | Pilot go/no-go gate (9.5) before heavy annotation; pivot plan defined |
| Checkbox state unrecoverable in many PDFs | Measured as Finding F2; `⟦?⟧` markers; the model can still use context; v2 adds a vision model |
| Small gold set | Silver pretraining, learning curve (A7), cluster-bootstrap CIs, honest framing |
| LLM-generated silver biases the comparison | Gold test is human-only; silver accuracy reported; stated in the paper |
| Regulation facts drift (RFO) | Registry and deviations fetched with dates; `test_recent` split; "date mismatch" wording |
| GovCon API limits or plan gating | Token-bucket budget, monthly paging, `content=` used only if available |
| Legal or privacy issues in released data | Marking filter, PII redaction, release limited to `government_work` documents, datasheet |
| Company IP and permission | Written permission from Acu-Elligent before any public release |
| Over-claiming novelty | Verified literature search; claims approved at Checkpoint 9 |
| arXiv hold again | Section 14.2 checklist, endorsement planned early |

---

## 18. Definition of done for v1

- [ ] All checkpoints passed with Raihan's OK recorded in `docs/decisions.md`
- [ ] `uv run pytest -q` green; CI green
- [ ] Every number in README, cards, paper and article traceable to `results/final/*.json`
- [ ] Test splits evaluated exactly once with `--final`, after the pre-registration commit
- [ ] Dataset and model on Hugging Face with full cards; repo tagged `v1.0.0`
- [ ] Paper PDF builds from source; refs verified; company permission on file
- [ ] `docs/INTEGRATION.md` complete; `fl serve` runs locally and returns the schema in 15.1