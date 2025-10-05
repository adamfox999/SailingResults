"""CLI helper for pushing locally cached series and schedule records to Supabase."""

from __future__ import annotations

import sys
from typing import Dict, List

from swsc_core.loader import DataStore


def _format_section(name: str, stats: Dict[str, object]) -> str:
    synced = stats.get("synced", 0)
    remaining = stats.get("remaining", 0)
    errors = stats.get("errors", [])
    lines = [f"{name}: {synced} synced, {remaining} remaining"]
    if isinstance(errors, list):
        for item in errors:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def main() -> int:
    store = DataStore()
    try:
        summary = store.sync_local_backlog()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_format_section("Series", summary.get("series", {})))
    print()
    print(_format_section("Scheduled races", summary.get("schedule", {})))

    errors: List[str] = []
    for stats in summary.values():
        if isinstance(stats, dict):
            for item in stats.get("errors", []) or []:
                errors.append(str(item))

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
