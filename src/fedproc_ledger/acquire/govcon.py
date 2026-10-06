"""GovCon API client (https://govconapi.com/api-guide): Bearer auth, retries, a call budget, a call log.

The key lives only in the Authorization header of outgoing requests. It is never logged and never put in an exception.
Every attempt (including retries) is counted against the budget and appended to a JSONL call log.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import RetryCallState, Retrying, retry_if_exception, stop_after_attempt

from fedproc_ledger.acquire.budget import CallBudget
from fedproc_ledger.acquire.ratelimit import TokenBucket

DEFAULT_BASE_URL = "https://govconapi.com/api/v1"
DEFAULT_UA = "fedproc-ledger-research/1.0 (contact: araihansikder@gmail.com)"


class GovConError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GovCon API HTTP {status}: {message}")
        self.status = status


class PlanLimitError(GovConError):
    """HTTP 402: a limit of the plan (page size above the plan maximum, or `content=` on a plan without it)."""


class BudgetStop(RuntimeError):
    """The call budget says to stop (reserve reached, local ceiling reached, or quota unknown)."""


class _Retryable(Exception):
    def __init__(self, status: int | None, retry_after: float | None = None) -> None:
        super().__init__(f"retryable (status {status})")
        self.status, self.retry_after = status, retry_after


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, _Retryable | httpx.TransportError)


class GovConClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        budget: CallBudget | None = None,
        bucket: TokenBucket | None = None,
        log_path: Path | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
        user_agent: str = DEFAULT_UA,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 6,
    ) -> None:
        self._key = api_key
        self.base_url = base_url.rstrip("/")
        self.budget = budget or CallBudget()
        self.bucket = bucket
        self.log_path = log_path
        self._sleep = sleep
        self._max_attempts = max_attempts
        self._http = httpx.Client(
            transport=transport, timeout=timeout, headers={"User-Agent": user_agent, "Accept": "application/json"}
        )
        self.last_rate_headers: dict[str, str] = {}

    def close(self) -> None:
        self._http.close()

    # -- plumbing ---------------------------------------------------------------------------------------------------
    def _log(self, entry: dict[str, Any]) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _wait(self, state: RetryCallState) -> float:
        exc = state.outcome.exception() if state.outcome else None
        if isinstance(exc, _Retryable) and exc.retry_after is not None:
            return min(exc.retry_after, 300.0)
        return min(2.0 * 2.0 ** (state.attempt_number - 1), 60.0) * (0.75 + 0.5 * random.random())

    def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        url = f"{self.base_url}{path}"
        attempt = {"n": 0}

        def once() -> httpx.Response:
            attempt["n"] += 1
            reason = self.budget.stop_reason()
            if reason:
                raise BudgetStop(reason)
            if self.bucket:
                self.bucket.acquire()
            t0 = time.perf_counter()
            status: int | None = None
            remaining: int | None = None
            try:
                resp = self._http.get(url, params=params, headers={"Authorization": f"Bearer {self._key}"})
                status = resp.status_code
                hdr = resp.headers.get("X-RateLimit-Remaining", "")
                remaining = int(hdr) if hdr.isdigit() else None
                self.last_rate_headers = {
                    k: v
                    for k, v in resp.headers.items()
                    if k.lower().startswith("x-ratelimit") or k.lower() == "retry-after"
                }
            except httpx.TransportError as e:
                self.budget.record(None)
                self._log(
                    {
                        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                        "path": path,
                        "params": params,
                        "status": None,
                        "error": type(e).__name__,
                        "attempt": attempt["n"],
                    }
                )
                raise
            self.budget.record(remaining)
            self._log(
                {
                    "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                    "path": path,
                    "params": params,
                    "status": status,
                    "ms": round(1000 * (time.perf_counter() - t0)),
                    "attempt": attempt["n"],
                    "remaining": remaining,
                    "bytes": len(resp.content),
                }
            )
            if status == 402:
                raise PlanLimitError(402, _short(resp))
            if status == 429 or status >= 500:
                ra = resp.headers.get("Retry-After", "")
                raise _Retryable(status, float(ra) if ra.replace(".", "", 1).isdigit() else None)
            if status >= 400:
                raise GovConError(status, _short(resp))
            return resp

        retrying = Retrying(
            retry=retry_if_exception(_is_retryable),
            wait=self._wait,
            stop=stop_after_attempt(self._max_attempts),
            sleep=self._sleep,
            reraise=True,
        )
        try:
            return retrying(once)
        except _Retryable as e:
            raise GovConError(e.status or 0, "still failing after retries") from None

    # -- endpoints ----------------------------------------------------------------------------------------------------
    def me(self) -> dict[str, Any]:
        return self._get("/me").json()  # type: ignore[no-any-return]

    def search(self, **params: Any) -> dict[str, Any]:
        clean = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in params.items() if v is not None}
        return self._get("/opportunities/search", clean).json()  # type: ignore[no-any-return]

    def iter_search_pages(self, limit: int, **params: Any) -> Iterator[tuple[int, dict[str, Any]]]:
        """Yield (offset, payload) until the API reports no next page."""
        offset = 0
        while True:
            payload = self.search(limit=limit, offset=offset, **params)
            yield offset, payload
            pg = payload.get("pagination", {})
            if not pg.get("has_next") or not payload.get("data"):
                return
            offset += limit

    def attachments(self, notice_id: str) -> dict[str, Any]:
        return self._get(f"/opportunities/{notice_id}/attachments").json()  # type: ignore[no-any-return]


def _short(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        msg = body.get("error") or body.get("message") or body.get("detail") or body
    except ValueError:
        msg = resp.text
    return str(msg)[:200]
