# arXiv submission checklist (fedproc-ledger v1)

Owner actions are marked **[OWNER]**; everything else is done.

## The paper
- Source: `release/paper/main.tex` + `tab_fresh.tex` + `tab_ceiling.tex` + `fig_forest.pdf` (self-contained, no .bst needed). PDF: `release/paper/main.pdf` (8 pages, builds with tectonic).
- Abstract is 1,889 characters (limit 1,920). Title: "Mentioned Is Not Binding: A Rules-plus-Small-Model Clause Ledger and a Pre-registered Audit of Regex Extraction on US Federal Solicitations".
- References: every citation verified on arXiv / ACL Anthology / eCFR before use (see `paper/refs.bib`); no invented references, numbers, or regulation facts.
- Public artefacts (reviewers can click): model `https://huggingface.co/raihan-js/fedproc-ledger-v1`, data `https://huggingface.co/datasets/raihan-js/fedproc-ledger-bench`.

## Submission settings
- Primary category: **cs.CL**; cross-lists: **cs.IR**, **cs.AI**.
- Licence: **CC BY 4.0**. Upload: LaTeX source (the four files above as a tarball/zip), not PDF only.
- Conflict line in the paper: authors affiliated with Acu-Elligent LLC (VETR Proposal); only public solicitations used.

## Endorsement [OWNER]
- First-time submitters in cs.CL usually need an endorsement. Request it **before** submitting via arXiv's endorsement system: find someone who has published in cs.CL (a legal-NLP researcher, a former collaborator) and ask them to endorse the account for cs.CL. Never pay for endorsements. This can take days — start now.
- Alternative that also strengthens the paper: add a cs.CL-published co-author (e.g. whoever second-annotates the expert gold sample).

## Why the last submission may have stalled (inference from `paper/rejected-research.pdf`, D-013)
Dead repo links, a headline comparison that was not like-for-like, thin real data, single runs with no intervals. This submission fixes all four: working public links, pre-registered rounds with frozen artefacts and cluster-bootstrap intervals, 16,128 extracted documents, and every failure reported.

## After acceptance on arXiv
- Put the arXiv ID into the HF model/dataset cards and the README headline.
- Announce with the dev.to article + Zenn summary (`docs/article/`).

## Troubleshooting: arXiv ran plain `etex` instead of pdflatex (submit/8192309, 2026-10-07)
Symptom: log shows `/usr/local/texlive/.../etex ... main.tex` and `! Undefined control sequence. l.1 \documentclass`.
Cause: the Process step used the `tex` compiler, not a source defect (the source is pure ASCII, starts with a clean `\documentclass`, all figures are PDF, all `\input` files present).
Fix: at Add Files upload ONLY the four flat files (`main.tex`, `tab_fresh.tex`, `tab_ceiling.tex`, `fig_forest.pdf` — ready-made `release/paper/arxiv_bundle.zip`, no paper PDF, no subdirectories). At the Process step select **pdflatex** from the compiler dropdown, then Reprocess. Do not hand-craft a 00README file.
