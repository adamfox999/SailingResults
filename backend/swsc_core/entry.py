from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Entry:
    """An individual race result entry.

    Each entry represents a competitor in a race with their boat details,
    times, and calculated results. Entry IDs are unique within a series.
    """

    entry_id: str  # Unique ID for this competitor within the series
    helm: str
    crew: str
    dinghy: str  # Boat class name
    py: int  # Portsmouth Yardstick number for the boat class
    laps: int
    time_seconds: int
    fin_code: str = ""
    sail_number: str = ""
    personal: int = 0  # Personal handicap (0 = no personal handicap)
    
    # Calculated fields
    max_laps: int = 0
    corrected_py: int = 0
    corrected_personal: int = 0
    py_place: float = 0
    personal_place: float = 0

    def calculate_corrected(self, max_laps: int) -> None:
        """Recalculate corrected times for PY and personal handicaps."""

        self.max_laps = max_laps
        if self.fin_code:
            # Retired/DNF style codes are not scored; leave metrics at zero.
            self.corrected_py = 0
            self.corrected_personal = 0
            return

        if not self.laps or not self.time_seconds or not self.py:
            self.corrected_py = 0
            self.corrected_personal = 0
            return

        self.corrected_py = int(self.time_seconds * max_laps * 1000 / self.laps / self.py)
        if self.personal:
            self.corrected_personal = int(self.corrected_py * 1000 / self.personal)
        else:
            self.corrected_personal = 0

    def audit_delta(self, datum: float) -> int:
        if not datum:
            raise ValueError("datum must be non-zero")
        if not self.corrected_py:
            return 0
        return int(self.corrected_py / datum * 1000)
