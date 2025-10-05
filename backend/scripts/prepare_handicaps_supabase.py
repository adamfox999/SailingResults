"""Build a normalized handicaps CSV ready for Supabase import.

This script consolidates the RYA "Portsmouth Number List" and "Limited data" CSV
exports into a single flat file with consistent columns. The resulting
`handicaps_supabase.csv` can be bulk-imported into Supabase using the SQL editor
or CLI `storage/object` upload + `copy` command.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_source(filename: str) -> Path:
    """Return the location of an input CSV, supporting both repo and parent dirs."""

    candidates = [
        REPO_ROOT / filename,
        REPO_ROOT.parent / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Could not locate '{filename}'. Checked: "
        + ", ".join(str(candidate) for candidate in candidates)
    )


PN_LIST_PATH = _resolve_source("PY_List_2025.csv")
LIMITED_LIST_PATH = _resolve_source("Limited data_PN_List_2025.csv")
OUTPUT_PATH = REPO_ROOT / "web" / "backend" / "data" / "handicaps_supabase.csv"

FIELDNAMES = [
    "source_list",
    "class_id",
    "class_name",
    "crew_count",
    "rig",
    "spinnaker",
    "py_number",
    "change",
    "notes",
    "remark",
    "last_published_year",
    "years_published",
]


@dataclass
class HandicapRecord:
    source_list: str
    class_id: str | None
    class_name: str
    crew_count: int | None
    rig: str | None
    spinnaker: str | None
    py_number: int | None
    change: int | None
    notes: str | None
    remark: str | None
    last_published_year: int | None
    years_published: int | None

    def as_dict(self) -> dict[str, str]:
        def to_str(value: int | str | None) -> str:
            if value is None:
                return ""
            return str(value)

        return {
            "source_list": self.source_list,
            "class_id": self.class_id or "",
            "class_name": self.class_name,
            "crew_count": to_str(self.crew_count),
            "rig": self.rig or "",
            "spinnaker": self.spinnaker or "",
            "py_number": to_str(self.py_number),
            "change": to_str(self.change),
            "notes": self.notes or "",
            "remark": self.remark or "",
            "last_published_year": to_str(self.last_published_year),
            "years_published": to_str(self.years_published),
        }


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().strip("\ufeff")


def _parse_int(value: str | None) -> int | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _iter_rows(path: Path) -> Iterator[list[str]]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with path.open(newline="", encoding=encoding) as handle:
                reader = csv.reader(handle)
                for row in reader:
                    yield row
            return
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("", b"", 0, 0, f"Unable to decode {path}")


def _is_header_row(row: list[str]) -> bool:
    first = _clean(row[0]) if row else ""
    if not any(_clean(cell) for cell in row):
        return True
    header_tokens = {
        "RYA Class ID",
        "RYA PN LIST - Dinghy",
        "RYA PN List - Multi",
        "EXPERIMENTAL NUMBERS",
    }
    if first in header_tokens:
        return True
    if first.startswith("Portsmouth") or first.startswith("The RYA"):
        return True
    if first.startswith("\""):
        # Narrative paragraph wrapped in quotes
        return True
    if first.startswith("Users of the PY scheme"):
        return True
    if first.startswith("For any catamaran classes"):
        return True
    if first.startswith("RYA Class"):
        return True
    if first.lower().startswith("experimental numbers"):
        return True
    if first.upper().startswith("RYA PN LIST"):
        return True
    if len(row) > 1 and _clean(row[1]).lower() == "class name":
        return True
    return False


def parse_pn_list() -> Iterable[HandicapRecord]:
    for row in _iter_rows(PN_LIST_PATH):
        if not row or _is_header_row(row):
            continue
        class_name = _clean(row[1])
        if class_name.lower() == "class name":
            continue
        if not class_name:
            continue
        py_number = _parse_int(row[5] if len(row) > 5 else None)
        if py_number is None:
            # Skip rows without a published number
            continue
        notes_value = _clean(row[7]) if len(row) > 7 else ""
        yield HandicapRecord(
            source_list="pn_list",
            class_id=_clean(row[0]) or None,
            class_name=class_name,
            crew_count=_parse_int(row[2]) if len(row) > 2 else None,
            rig=_clean(row[3]) or None,
            spinnaker=_clean(row[4]) or None,
            py_number=py_number,
            change=_parse_int(row[6]) if len(row) > 6 else None,
            notes=notes_value or None,
            remark=None,
            last_published_year=None,
            years_published=None,
        )


def parse_limited_list() -> Iterable[HandicapRecord]:
    for row in _iter_rows(LIMITED_LIST_PATH):
        if not row or _is_header_row(row):
            continue
        class_name = _clean(row[1])
        if class_name.lower() == "class name":
            continue
        if not class_name:
            continue
        py_number = _parse_int(row[6] if len(row) > 6 else None)
        if py_number is None:
            # Skip rows without an historical PN
            continue
        remark_value = _clean(row[5]) if len(row) > 5 else ""
        yield HandicapRecord(
            source_list="limited_list",
            class_id=_clean(row[0]) or None,
            class_name=class_name,
            crew_count=_parse_int(row[2]) if len(row) > 2 else None,
            rig=_clean(row[3]) or None,
            spinnaker=_clean(row[4]) or None,
            py_number=py_number,
            change=None,
            notes=None,
            remark=remark_value or None,
            last_published_year=_parse_int(row[7]) if len(row) > 7 else None,
            years_published=_parse_int(row[8]) if len(row) > 8 else None,
        )


def build_csv() -> None:
    records = list(parse_pn_list()) + list(parse_limited_list())
    # Sort deterministically for diff-friendly output.
    records.sort(key=lambda r: (r.source_list, r.class_name.lower()))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow(record.as_dict())

    print(f"Wrote {len(records)} rows to {OUTPUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    build_csv()
