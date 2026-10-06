"""A live, local budget of API calls for a long unattended run.

Same design as VETR's `GovConCallBudget` (read-only reference, see docs/decisions.md D-008/D-009): the vendor's
remaining-calls figure is read from a free response header, calls are decremented locally in between, an UNKNOWN quota
stops the run after a small allowance instead of continuing, and a hard local ceiling bounds the run whatever the
vendor reports. The reserve is what is left for other users of the same key (the live VETR application).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CallBudget:
    reserve: int = 0  # stop while this many vendor calls remain
    max_calls: int = 0  # hard local ceiling (0 = none)
    blind_allowance: int = 25  # calls allowed while the vendor has reported no quota at all
    remaining: int | None = None  # last vendor figure
    spent_since_reading: int = 0
    spent_total: int = 0

    def record(self, remaining_header: int | None = None) -> None:
        """Call after every request (including retries). A header reading replaces the local estimate."""
        self.spent_total += 1
        if remaining_header is not None:
            self.remaining, self.spent_since_reading = remaining_header, 0
        else:
            self.spent_since_reading += 1

    @property
    def estimated_remaining(self) -> int | None:
        return None if self.remaining is None else self.remaining - self.spent_since_reading

    def stop_reason(self) -> str | None:
        """Why the run must stop now, or None to continue."""
        if self.max_calls > 0 and self.spent_total >= self.max_calls:
            return f"local call ceiling reached ({self.spent_total} of {self.max_calls})"
        if self.reserve <= 0:
            return None
        est = self.estimated_remaining
        if est is None:
            if self.spent_total >= self.blind_allowance:
                return f"quota unknown after {self.spent_total} calls (stopping rather than guessing)"
            return None
        if est <= self.reserve:
            return f"remaining calls ({est}) at or below the reserve ({self.reserve})"
        return None
