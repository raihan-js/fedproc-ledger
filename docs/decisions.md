# Decisions log

One entry per decision: what, why, alternatives. Newest at the bottom. Checkpoint approvals by Raihan are recorded here with the date.

## D-001 (2026-10-06): repo location and name
`research-learn/fedproc-ledger/`, its own git repo (`main`). The plan asks for a location outside the VETR repo and outside the interview-prep app; this satisfies that and matches the other projects in this workspace (and `pipeline/clear_finished_projects.py`, which requires a project to be its own repo). Alternative `~/code/fedproc-ledger` rejected only for consistency. GitHub name when released: `raihan-js/fedproc-ledger`.

## D-002 (2026-10-06): Python and environment
The machine's system Python is 3.12.3; the plan says 3.11, so `uv python install 3.11` provided 3.11.15 and `pyproject.toml` pins `>=3.11,<3.12`. Installed with `uv sync --extra ml --group dev`: torch 2.14.1+cu130 (venv about 6 GB). Extras not yet installed: `export`, `annotate`, `llm`, `serve`.

## D-003 (2026-10-06): hardware (Phase 0 GPU check)
`fedproc-ledger 0.1.0 | python 3.11.15 | torch 2.14.1+cu130: CUDA available, NVIDIA GeForce RTX 3060, 11.6 GB` (driver 580, Ubuntu-based Linux, native, so vLLM can run without WSL2). RAM 31 GB. Disk 197 GB free on `/home` after the housekeeping in D-011. The second GPU mentioned in the plan (4060) is not in this machine.

## D-004 (2026-10-06): dependencies beyond the Section 3 list (flagged for Raihan at Checkpoint 0)
Derived from other parts of the plan, declared as extras, all optional: `mlflow` (required by 12.2, in `ml`); `fastapi`, `uvicorn`, `python-multipart` (section 15.1 names a FastAPI sidecar, in `serve`, not installed); `hatchling` (build backend); `pandas-stubs`, `types-requests` (mypy, dev). Tests mock HTTP with `httpx.MockTransport` (no extra library). Configs are TOML read with stdlib `tomllib` (no YAML library). No other dependency was added.

## D-005 (2026-10-06): GovCon API, verified from the documentation
Source: https://govconapi.com/api-guide/search-endpoint and /attachments, fetched 2026-10-06.
- Search `GET https://govconapi.com/api/v1/opportunities/search`, `Authorization: Bearer <key>`. Parameters as in plan 5.1 plus `posted_after`, `active_only`, `sort_order`. All filters combine with AND. `notice_id` is unique per amendment; dedupe on `solicitation_number`.
- `limit`: default 100, **max 100 on the free trial and 1,000 on paid plans; exceeding returns 402**. On the free trial the response `window` shows a **90-day window** and a clamp status; paid plans show null. So reaching back to 2024-01 needs a paid plan.
- `pagination.total` is capped at 10,000 on broad searches and then `total_is_estimate` is true; use `has_next`. Month windows must stay under that cap or be split (week, agency).
- `content=` (full-text inside attachments) is **Pro only** (402 otherwise). One documentation line mentions "Pro plan ($39/mo), no per-query limits, 1,000 requests/hour"; rate limits are otherwise not documented numerically.
- 59 fields per record, including `contact_name`, `contact_email`, `contact_phone`, `contact_fax`: **personal contact data. Keep it out of anything released** (plan 5.4 redaction applies to text; this applies to the notices table).
- Attachments: `GET /opportunities/{notice_id}/attachments` returns `files[]` (`url`, `resource_id`, `filename`, `size_bytes`, `file_type`; `file_type` may be an extension, a label such as "Category Attachment", or empty). `url` is a SAM.gov front-door link that **303-redirects to a short-lived signed S3 URL**: use GET with redirects (HEAD returns 403), never cache the resolved URL, no API key needed for the download itself, 429 means rate limit.

## D-006 (2026-10-06): eCFR versioner API, verified by probing (the documentation page redirects to a bot check)
`GET https://www.ecfr.gov/api/versioner/v1/...` needs no key. `titles.json` returned Title 48 `up_to_date_as_of 2026-10-02`. `versions/title-48.json?section=52.219-14` returned 10 versions, first `2017-01-01`, last `2022-10-28` (fields: `date`, `amendment_date`, `issue_date`, `identifier`, `part`, `substantive`, `removed`, `type`), so the plan's "more than one clause date since 2017" test is satisfiable and the point-in-time history starts 2017-01-01. `full/{date}/title-48.xml?section=...` answers **406 unless the request allows compression** (`Accept-Encoding`; httpx sends it by default). Send the research `User-Agent` and cache every response by (endpoint, section, date).

## D-007 (2026-10-06): the FedProc v0 model is not safetensors
The plan (A4) says to load `raihan-js/fedproc-180m-v0` safetensors. The repo contains `model.pt` (596 MB), `labels.py`, `metadata.json`, `task3_thresholds.json` and a tokenizer, **no `config.json` and no safetensors**. `metadata.json`: encoder `answerdotai/ModernBERT-base`, `max_length` 512, multi-task heads (notice type, three other tasks), 6 epochs. A4 therefore needs a state-dict key mapping (`torch.load(..., weights_only=True)`, keep the encoder keys, drop the heads, log which keys loaded) rather than `from_pretrained`. v0 was trained on 512-token windows, which also matters for A2.

## D-008 (2026-10-06): VETR code, read-only
Found at `/home/raihan/Desktop/APPS/VETR-Framework` (vendor/ is present, so VETR's PHP can run locally for parity tests): `app/Services/FarClauseDetectionService.php` (193 lines; 16 regex entries (FAR, DFARS and 14 supplements), longest prefix first, including `FAR`, `DFARS`, `GSAM` and 14 supplements), `app/Support/FarClauseApplicability.php` (425 lines), `database/seeders/FarClauseSeeder.php` (193 lines), `app/Jobs/ParseRfpDocument.php` (1,370), `app/Jobs/ImportRfpFromUrl.php` (241), `app/Support/GovConCallBudget.php` (130), `app/Http/Controllers/FarClauseController.php` (193). This project never edits VETR. Parity scripts live here under `scripts/php/` and take the VETR path from an environment variable.

## D-009 (2026-10-06): the production GovCon quota is shared if the key is shared
`config/services.php` reads `GOVCON_API_KEY` for production, and `GovConCallBudget` guards that quota with a reserve, a local ceiling and "unknown quota stops the run". If this project uses the same key, a 3,000-solicitation acquisition (thousands of calls) draws on the same hourly quota as the live application. Decision pending Raihan: a separate key (preferred), or the same key with the same safeguards (reserve, hard ceiling, off-peak runs). The Python client will implement the same design either way.

## D-010 (2026-10-06): spec issues to resolve
Listed in `docs/EXECUTION_PLAN.md` section 3 (role count versus head size, legal filter needs text, free-trial window, and others).

## D-011 (2026-10-06): housekeeping before starting
Finished projects were already cleared (each folder is under 30 MB). The Hugging Face cache held 14 GB of unreferenced blobs and 1.1 GB of models/datasets from finished projects; the unreferenced blobs (no symlink or hardlink from any snapshot) and those entries were deleted, plus the pip cache (3.7 GB). Kept: ModernBERT-base (needed here), the Ollama models (the owner's), small ORCH and benchmark caches. `/home` went from 180 GB to 197 GB free.
