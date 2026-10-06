# Where we are (update after every step; read this first when resuming)

- **Phases 1 to 3 built; Checkpoints 1, 2 and 3 are waiting on the long jobs and on the owner.** Owner approved Checkpoint 0 and the plan inputs (D-012).
- **Running jobs (detached, resumable; logs in `data/logs/`):**
  - `fl acquire download` (journal `data/interim/download_journal.jsonl`, log `download.log`). If dead: check the log tail, then re-run `uv run fl acquire download`. ~4,800 notices, about 13 per minute, quota 1,000/hour with a 250 reserve (D-014, D-016).
  - `fl registry build` (log `registry_build.log`). If dead: re-run `uv run fl registry build` (cached requests make it resume fast).
- **Done and committed:** GovCon client/budget/search/pool/downloader/stats (Phase 1); eCFR client, parser, versions, build, RFO deviations table (Phase 2); PDF/DOCX extraction with checkbox markers, privacy filter, batch runner, HTML report (Phase 3). 137 tests, ruff and mypy clean.
- **Next steps:** (a) when the registry build ends: `fl registry deviations` is already done; run the registry data tests, show Checkpoint 2; (b) when the download ends: `fl acquire stats`, `fl extract run`, `fl extract stats`, `fl extract report`, show Checkpoints 1 and 3; (c) Phase 4 (candidates, section detector, B0, B1) is being built meanwhile; Phase 5 (annotation) starts only after the owner's OK.
- **Data facts to remember:** GovCon index starts 2024-10 (D-015); per-connection download speed 30 KB/s (D-016); glyph semantics verified (D-017); RFO model deviation reserves 259 Part 52 sections including 52.212-5 and 52.204-21 (see `data/processed/rfo_part52_sections.parquet`).
- **Needs from the owner:** DoD DPAP deviations page (not reachable from here); Part 52 deviation files for DoD, DOE, GSA, VA, NASA, USDA (not on the guide); review at the checkpoints. Nothing pushed anywhere.
