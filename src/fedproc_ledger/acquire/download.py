"""Download the selected attachments of each notice (SAM.gov front-door links, redirects followed, no API key).

Resumable through a JSONL journal; politeness through a shared token bucket; a hard cap on disk use; every skipped or
failed file is recorded with a reason, nothing is silently dropped.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from fedproc_ledger.acquire.files import extension, final_extension, looks_like_xls, select_files, sniff_kind
from fedproc_ledger.acquire.govcon import BudgetStop, GovConClient, GovConError
from fedproc_ledger.acquire.ratelimit import TokenBucket
from fedproc_ledger.acquire.search import with_quota_wait


class DiskCapReached(RuntimeError):
    pass


class _Transient(Exception):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.glob("*") if p.is_file()) if path.exists() else 0


class Journal:
    """Append-only JSONL; `done_notices` is what a resumed run skips."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.done_notices: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    e = json.loads(line)
                    if e.get("event") == "notice_done":
                        self.done_notices.add(e["notice_id"])

    def write(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": now(), **entry}, ensure_ascii=False) + "\n")


def _filename_from(resp: httpx.Response, fallback: str) -> str:
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd, re.I)
    return m.group(1) if m else fallback


def fetch_to_store(
    http: httpx.Client,
    url: str,
    files_dir: Path,
    *,
    filename: str,
    max_bytes: int,
    bucket: TokenBucket | None,
    sleep: Callable[[float], None] = lambda s: None,
    attempts: int = 4,
) -> dict[str, Any]:
    """GET (never HEAD) with redirects, stream to a temp file, hash, sniff, store as {sha256}{ext}.

    Returns a record with `status` ok | skipped | failed and a `reason`; never raises for an expected failure.
    """
    files_dir.mkdir(parents=True, exist_ok=True)

    def once() -> dict[str, Any]:
        if bucket:
            bucket.acquire()
        tmp = files_dir / f".tmp-{threading.get_ident()}-{os.getpid()}"
        h, size, head = hashlib.sha256(), 0, b""
        try:
            with http.stream("GET", url) as resp:
                if resp.status_code in (404, 410):
                    return {"status": "failed", "reason": f"gone_{resp.status_code}"}
                if resp.status_code in (401, 403):
                    return {"status": "failed", "reason": f"denied_{resp.status_code}"}
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise _Transient(str(resp.status_code))
                if resp.status_code >= 400:
                    return {"status": "failed", "reason": f"http_{resp.status_code}"}
                cl = resp.headers.get("content-length", "")
                if cl.isdigit() and int(cl) > max_bytes:
                    return {"status": "skipped", "reason": "too_large"}
                name = _filename_from(resp, filename)
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(1 << 16):
                        if not head:
                            head = chunk[:4096]
                        size += len(chunk)
                        if size > max_bytes:
                            return {"status": "skipped", "reason": "too_large"}
                        h.update(chunk)
                        f.write(chunk)
            if size == 0:
                return {"status": "skipped", "reason": "empty"}
            kind = sniff_kind(head)
            zip_has_word = False
            if kind == "zip":
                try:
                    with zipfile.ZipFile(tmp) as z:
                        zip_has_word = any(n.startswith("word/") for n in z.namelist())
                except zipfile.BadZipFile:
                    return {"status": "skipped", "reason": "bad_zip"}
            ext = final_extension(name, kind, zip_has_word)
            if ext == ".doc" and looks_like_xls(name):
                ext = None
            if ext is None:
                return {"status": "skipped", "reason": f"not_a_kept_type_{kind}"}
            sha = h.hexdigest()
            dest = files_dir / f"{sha}{ext}"
            dup = dest.exists()
            if not dup:
                os.replace(tmp, dest)
            return {"status": "ok", "sha256": sha, "ext": ext, "bytes": size, "name": name, "duplicate": dup}
        finally:
            if tmp.exists():
                tmp.unlink()

    retrying = Retrying(
        retry=retry_if_exception(lambda e: isinstance(e, _Transient | httpx.TransportError)),
        wait=wait_exponential(multiplier=2, max=60),
        stop=stop_after_attempt(attempts),
        sleep=sleep,
        reraise=True,
    )
    try:
        return retrying(once)
    except (_Transient, httpx.TransportError) as e:
        return {"status": "failed", "reason": f"transient_{type(e).__name__}"}


def download_notice(
    http: httpx.Client,
    notice: dict[str, Any],
    selected: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    files_dir: Path,
    journal: Journal,
    bucket: TokenBucket | None,
    max_file_bytes: int,
    cap_bytes: int,
    sleep: Callable[[float], None] = lambda s: None,
) -> None:
    nid = notice["notice_id"]
    for s in skipped:
        journal.write(
            {
                "event": "file",
                "notice_id": nid,
                "resource_id": s.get("resource_id"),
                "filename": s.get("filename"),
                "status": "skipped",
                "reason": s["reason"],
            }
        )
    stored = 0
    for f in selected:
        if dir_bytes(files_dir) >= cap_bytes:
            raise DiskCapReached(f"data/raw/files reached {cap_bytes / 1e9:.1f} GB")
        res = fetch_to_store(
            http,
            f["url"],
            files_dir,
            filename=f.get("filename") or "",
            max_bytes=max_file_bytes,
            bucket=bucket,
            sleep=sleep,
        )
        journal.write(
            {
                "event": "file",
                "notice_id": nid,
                "resource_id": f.get("resource_id"),
                "filename": f.get("filename"),
                "file_type": f.get("file_type"),
                "listed_bytes": f.get("size_bytes"),
                "source_url": f.get("url"),
                **res,
            }
        )
        stored += res["status"] == "ok"
    journal.write(
        {
            "event": "notice_done",
            "notice_id": nid,
            "solicitation_number": notice.get("solicitation_number"),
            "n_selected": len(selected),
            "n_skipped": len(skipped),
            "n_stored": stored,
        }
    )


def ext_of(name: str) -> str:
    return extension(name)


def run_download(
    client: GovConClient,
    http: httpx.Client,
    notices: list[dict[str, Any]],
    cfg: dict[str, Any],
    journal: Journal,
    files_dir: Path,
    *,
    workers: int = 4,
    bucket: TokenBucket | None = None,
    log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = lambda s: None,
    quota_wait_s: float = 600.0,
) -> dict[str, Any]:
    """Attachment list per notice (main thread, budgeted), downloads in `workers` threads sharing one rate limit.

    Stops cleanly on the disk cap, a local call ceiling or an unknown quota; waits out a reached reserve.
    """
    f = cfg["files"]
    keep_ext = cfg["download"]["keep_extensions"]
    max_file = cfg["download"]["max_file_mb"] * 1_000_000
    max_notice = f["max_bytes_per_notice_mb"] * 1_000_000
    cap = int(f["max_total_gb"] * 1e9)
    stop = threading.Event()
    reason: list[str] = []
    gate = threading.BoundedSemaphore(workers * 2)
    totals = {"notices": 0, "stored": 0, "attachments_failed": 0}

    def work(n: dict[str, Any], sel: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> None:
        try:
            download_notice(http, n, sel, skipped, files_dir, journal, bucket, max_file, cap, sleep)
        except DiskCapReached as e:
            reason.append(str(e))
            stop.set()
        finally:
            gate.release()

    with ThreadPoolExecutor(workers) as pool:
        for n in notices:
            if stop.is_set() or n["notice_id"] in journal.done_notices:
                continue
            gate.acquire()
            try:
                att = with_quota_wait(
                    client, partial(client.attachments, n["notice_id"]), wait_s=quota_wait_s, sleep=sleep, log=log
                )
            except BudgetStop as e:
                gate.release()
                reason.append(str(e))
                break
            except GovConError as e:
                gate.release()
                journal.write({"event": "notice_failed", "notice_id": n["notice_id"], "reason": str(e)[:200]})
                totals["attachments_failed"] += 1
                continue
            sel, skipped = select_files(att.get("files") or [], keep_ext, f["max_per_notice"], max_file, max_notice)
            totals["notices"] += 1
            pool.submit(work, n, sel, skipped)
            if totals["notices"] % 25 == 0:
                spent, left = client.budget.spent_total, client.budget.remaining
                disk = dir_bytes(files_dir) / 1e9
                log(f"[download] {totals['notices']} notices, calls {spent}, remaining {left}, disk {disk:.2f} GB")
    return {**totals, "stopped": reason[0] if reason else None}
