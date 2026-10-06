"""Which attachments of a notice to download, and what a downloaded file really is. Pure functions, no network."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

# Name hints: a solicitation's clause lists are usually in the main solicitation document, a clauses/provisions file,
# or a form (SF 1449, SF 33, SF 18). Drawings, maps and wage-determination lists essentially never carry clauses.
STRONG = (
    "solicitation",
    "rfp",
    "rfq",
    "ifb",
    "combined",
    "synopsis",
    "1449",
    "sf33",
    "sf-33",
    "sf 33",
    "sf18",
    "sf-18",
    "clauses",
    "provisions",
    "section",
    "terms",
    "52.2",
    "252.2",
    "far",
    "dfars",
)
WEAK = ("sow", "pws", "statement of work", "performance work", "attachment", "addendum", "instructions")
NEGATIVE = (
    "drawing",
    "dwg",
    "map",
    "photo",
    "wage",
    "determination",
    "price",
    "pricing",
    "bid schedule",
    "q&a",
    "questions",
    "past performance",
    "sign in",
    "sign-in",
)


def extension(filename: str) -> str:
    return PurePosixPath((filename or "").lower()).suffix


def hint_score(filename: str) -> int:
    name = (filename or "").lower()
    return 3 * sum(h in name for h in STRONG) + sum(h in name for h in WEAK) - 2 * sum(h in name for h in NEGATIVE)


def select_files(
    files: list[dict[str, Any]], keep_ext: list[str], max_files: int, max_file_bytes: int, max_notice_bytes: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (selected, skipped). Each skipped entry has a `reason`. A file with no extension is kept for sniffing."""
    candidates, skipped = [], []
    for f in files:
        ext = extension(f.get("filename", ""))
        size = f.get("size_bytes")
        if ext and ext not in keep_ext:
            skipped.append({**f, "reason": "extension"})
        elif isinstance(size, int) and size > max_file_bytes:
            skipped.append({**f, "reason": "too_large"})
        elif isinstance(size, int) and size == 0:
            skipped.append({**f, "reason": "empty"})
        elif not f.get("url"):
            skipped.append({**f, "reason": "no_url"})
        else:
            candidates.append(f)
    candidates.sort(key=lambda f: (-hint_score(f.get("filename", "")), -(f.get("size_bytes") or 0)))
    selected: list[dict[str, Any]] = []
    total = 0
    for f in candidates:
        size = f.get("size_bytes") or 0
        if len(selected) >= max_files:
            skipped.append({**f, "reason": "over_file_cap"})
        elif total + size > max_notice_bytes:
            skipped.append({**f, "reason": "over_notice_bytes"})
        else:
            selected.append(f)
            total += size
    return selected, skipped


def sniff_kind(head: bytes) -> str | None:
    """pdf | zip (docx and friends) | doc (OLE2) | txt | None, from the first bytes."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return "doc"
    if head and b"\x00" not in head[:2048]:
        try:
            text = head[:2048].decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = head[:2048].decode("latin-1")
            except UnicodeDecodeError:
                return None
        if text and sum(c.isprintable() or c in "\r\n\t" for c in text) / len(text) > 0.95:
            return "txt"
    return None


def final_extension(filename: str, sniffed: str | None, zip_has_word: bool = False) -> str | None:
    """The extension to store under, or None if the bytes are not a kept type (so the file is discarded)."""
    if sniffed == "pdf":
        return ".pdf"
    if sniffed == "zip":
        return ".docx" if zip_has_word else None
    if sniffed == "doc":
        return ".doc"  # OLE2 container: .doc (an .xls would also be OLE2; the name decides below)
    if sniffed == "txt":
        return ".txt"
    return None


def looks_like_xls(filename: str) -> bool:
    return bool(re.search(r"\.xls[xm]?$", (filename or "").lower()))
