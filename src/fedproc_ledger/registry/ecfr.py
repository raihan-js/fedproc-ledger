"""eCFR versioner API client with an on-disk cache (https://www.ecfr.gov/api/versioner/v1, no key needed).

Every response is cached under data/raw/ecfr/cache/ by (endpoint, sorted parameters), gzipped, with an index line, so a
re-run costs no requests. The research User-Agent is sent; httpx allows compression (the full-text endpoint answers 406
without it, decisions.md D-006).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from fedproc_ledger.acquire.ratelimit import TokenBucket

BASE = "https://www.ecfr.gov/api/versioner/v1"
UA = "fedproc-ledger-research/1.0 (contact: araihansikder@gmail.com)"


class EcfrError(RuntimeError):
    pass


class _Transient(Exception):
    pass


def cache_key(endpoint: str, params: dict[str, Any]) -> str:
    canon = endpoint + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha256(canon.encode()).hexdigest()[:24]


class EcfrClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        transport: httpx.BaseTransport | None = None,
        rate_per_s: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 180.0,
    ) -> None:
        self.cache_dir = cache_dir
        self._http = httpx.Client(
            transport=transport, timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}
        )
        self._bucket = TokenBucket(rate_per_s, capacity=1.0)
        self._sleep = sleep
        self.requests = 0
        self.cache_hits = 0

    def close(self) -> None:
        self._http.close()

    def get(self, endpoint: str, params: dict[str, Any] | None = None, *, accept: str = "application/json") -> bytes:
        params = dict(params or {})
        key = cache_key(endpoint, params)
        path = self.cache_dir / f"{key}.gz"
        if path.exists():
            self.cache_hits += 1
            with gzip.open(path, "rb") as f:
                return f.read()

        def once() -> bytes:
            self._bucket.acquire()
            self.requests += 1
            r = self._http.get(f"{BASE}{endpoint}", params=params, headers={"Accept": accept})
            if r.status_code == 429 or r.status_code >= 500:
                raise _Transient(str(r.status_code))
            if r.status_code != 200:
                raise EcfrError(f"eCFR {endpoint} {params}: HTTP {r.status_code}")
            return r.content

        retrying = Retrying(
            retry=retry_if_exception(lambda e: isinstance(e, _Transient | httpx.TransportError)),
            wait=wait_exponential(multiplier=3, max=90),
            stop=stop_after_attempt(6),
            sleep=self._sleep,
            reraise=True,
        )
        try:
            body = retrying(once)
        except _Transient as e:
            raise EcfrError(f"eCFR {endpoint} {params}: still failing after retries ({e})") from None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wb") as gz:
            gz.write(body)
        os.replace(tmp, path)
        entry = {
            "key": key,
            "endpoint": endpoint,
            "params": params,
            "bytes": len(body),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        with open(self.cache_dir / "index.jsonl", "a", encoding="utf-8") as idx:
            idx.write(json.dumps(entry) + "\n")
        return body

    # -- endpoints used by the registry --------------------------------------------------------------------------------
    def titles(self) -> dict[str, Any]:
        return json.loads(self.get("/titles.json"))  # type: ignore[no-any-return]

    def structure(self, date: str) -> dict[str, Any]:
        return json.loads(self.get(f"/structure/{date}/title-48.json"))  # type: ignore[no-any-return]

    def versions(self, **params: Any) -> list[dict[str, Any]]:
        return json.loads(self.get("/versions/title-48.json", params))["content_versions"]  # type: ignore[no-any-return]

    def full_xml(self, date: str, **params: Any) -> bytes:
        return self.get(f"/full/{date}/title-48.xml", params, accept="application/xml")
