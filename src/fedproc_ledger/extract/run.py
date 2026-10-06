"""Batch extraction: one parquet shard per document under data/processed/pages/, one summary line per document."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pandas as pd

from fedproc_ledger.extract.docx import extract_docx
from fedproc_ledger.extract.pdf import PageText, _line_from_chars, extract_pdf, page_row
from fedproc_ledger.extract.privacy import find_banner_markings, find_markings


def _extract_txt(path: Path) -> list[PageText]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = []
    for raw in text.splitlines():
        if raw.strip():
            lines.append(_line_from_chars([{"c": c, "bbox": (0, 0, 0, 0)} for c in raw], (0.0, 0.0, 0.0, 0.0)))
    from collections import Counter

    counts = Counter(f"{b.source}:{b.state}" for ln in lines for b in ln.boxes)
    return [PageText(1, text, "\n".join(ln.text_layout for ln in lines), lines, dict(counts), False, {})]


def _doc_to_docx(path: Path, work: Path) -> Path | None:
    """LibreOffice headless .doc -> .docx; None if LibreOffice is missing or fails (the file is then counted)."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    work.mkdir(parents=True, exist_ok=True)
    profile = work / "profile"
    cmd = [
        soffice,
        f"-env:UserInstallation=file://{profile}",
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(work),
        str(path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=180, check=True)
    except (subprocess.SubprocessError, OSError):
        return None
    out = work / (path.stem + ".docx")
    return out if out.exists() else None


def extract_file(path: Path, ext: str, work: Path) -> list[PageText]:
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    if ext == ".txt":
        return _extract_txt(path)
    if ext == ".doc":
        converted = _doc_to_docx(path, work)
        if converted is None:
            raise RuntimeError("doc conversion unavailable or failed")
        return extract_docx(converted)
    raise ValueError(f"unsupported type {ext}")


def process_document(doc_id: str, path: str, ext: str, out_dir: str, work_dir: str) -> dict[str, Any]:
    """Extract one document, write its shard, return its summary row (never raises)."""
    t0 = time.perf_counter()
    summary: dict[str, Any] = {"doc_id": doc_id, "ext": ext, "error": None}
    try:
        pages = extract_file(Path(path), ext, Path(work_dir) / doc_id)
        rows = [page_row(doc_id, p) for p in pages]
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        tmp = out / f".{doc_id}.tmp"
        pd.DataFrame(rows).to_parquet(tmp, index=False)
        tmp.replace(out / f"{doc_id}.parquet")
        counts: dict[str, int] = {}
        pua: dict[str, int] = {}
        for p in pages:
            for k, v in p.box_counts.items():
                counts[k] = counts.get(k, 0) + v
            for k, v in p.pua_codepoints.items():
                pua[k] = pua.get(k, 0) + v
        text = "\n".join(p.text_plain for p in pages)
        summary.update(
            n_pages=len(pages),
            n_chars=len(text),
            scanned=bool(pages) and sum(p.scanned for p in pages) / len(pages) >= 0.8,
            scanned_pages=sum(p.scanned for p in pages),
            box_counts=counts,
            pua=pua,
            unattached_widgets=sum(p.unattached_widgets for p in pages),
            markings=find_banner_markings(ln.text_plain for p in pages for ln in p.lines),
            marking_mentions=find_markings(text),
        )
    except Exception as e:  # noqa: BLE001  (one bad file must not stop the batch)
        summary["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    shutil.rmtree(Path(work_dir) / doc_id, ignore_errors=True)
    summary["seconds"] = round(time.perf_counter() - t0, 2)
    return summary


def read_summaries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
