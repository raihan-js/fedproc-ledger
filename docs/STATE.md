# Where we are (update after every step; read this first when resuming)

- **Phase:** 1 (acquisition). Owner approved Checkpoint 0 and the plan inputs (D-012).
- **Done:** client, budget, search sweep (198 sampled weekdays, 44,446 notices), pool (4,800 selected, 24 months 2024-10..2026-09, 200 per month, max department share 14%), 20-notice download trial (59 files, 60 MB).
- **Running now:** `fl acquire download` (resumable via `data/interim/download_journal.jsonl`; log `data/logs/download.log`). If it died (power loss, crash): check the log tail, then re-run `uv run fl acquire download` (do not count failed attempts as results).
- **Next:** when the download finishes, `fl acquire stats`, then Checkpoint 1 (stats + 10 random documents + disk use).
- **Known data facts:** GovCon index is nearly empty before 2024-10 (D-015); quota is 1,000 requests per hour (reserve 250 kept); 429 bursts at ~1 call/s, call rate lowered to 0.8/s.
- **Nothing pushed:** no GitHub repo, no Hugging Face upload.
