from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from .entry import Entry


@dataclass
class PyRow:
    entry_id: str
    helm: str
    crew: str
    dinghy: str
    py: int
    laps: int
    time_seconds: int
    corrected: int | None
    rank: float | None
    fin_code: str


@dataclass
class PersonalRow:
    entry_id: str
    helm: str
    crew: str
    personal_handicap: int
    corrected: int | None
    rank: float | None


@dataclass
class ScoreResults:
    py_rows: List[PyRow] = field(default_factory=list)
    personal_rows: List[PersonalRow] = field(default_factory=list)
    summary_text: str = ""
    html: str = ""


class Race:
    def __init__(self, entries: Iterable[Entry] | None = None) -> None:
        self.entries: List[Entry] = list(entries or [])

    def add_entry(self, entry: Entry) -> None:
        self.entries.append(entry)

    def score(self, dnc_position: float | None = None) -> ScoreResults:
        if not self.entries:
            return ScoreResults()

        dnc = dnc_position or (len(self.entries) + 1)

        max_laps = max((entry.laps for entry in self.entries if entry.laps), default=0)
        for entry in self.entries:
            entry.calculate_corrected(max_laps)
            if entry.fin_code:
                entry.py_place = dnc
                entry.personal_place = dnc

        self._award_places(
            [entry for entry in self.entries if not entry.fin_code and entry.corrected_py],
            key=lambda e: e.corrected_py,
            attr="py_place",
        )

        personal_candidates = [
            entry
            for entry in self.entries
            if not entry.fin_code and entry.corrected_personal and entry.personal
        ]
        self._award_places(personal_candidates, key=lambda e: e.corrected_personal, attr="personal_place")
        for entry in self.entries:
            if entry.personal_place == 0 and (entry.fin_code or not entry.personal):
                entry.personal_place = dnc

        summary_lines = ["ID    Helm                Class     Time  Laps  Corrected Place"]
        py_rows: List[PyRow] = []
        personal_rows: List[PersonalRow] = []

        for entry in sorted(self.entries, key=lambda e: e.py_place or dnc):
            summary_lines.append(
                f"{entry.entry_id.ljust(6)}{entry.helm.ljust(20)}{entry.dinghy.ljust(10)}"
                f"{str(entry.time_seconds).ljust(6)}{str(entry.laps).ljust(6)}"
                f"{str(entry.corrected_py).ljust(10)}{entry.py_place}"
            )
            py_rows.append(
                PyRow(
                    entry_id=entry.entry_id,
                    helm=entry.helm,
                    crew=entry.crew,
                    dinghy=entry.dinghy,
                    py=entry.py,
                    laps=entry.laps,
                    time_seconds=entry.time_seconds,
                    corrected=entry.corrected_py or None,
                    rank=entry.py_place or None,
                    fin_code=entry.fin_code,
                )
            )

        for entry in sorted(self.entries, key=lambda e: e.personal_place or dnc):
            if entry.personal:  # Only include entries with personal handicaps
                personal_rows.append(
                    PersonalRow(
                        entry_id=entry.entry_id,
                        helm=entry.helm,
                        crew=entry.crew,
                        personal_handicap=entry.personal,
                        corrected=entry.corrected_personal or None,
                        rank=entry.personal_place or None,
                    )
                )

        html = self._build_html(py_rows, personal_rows)
        summary_text = "\n".join(summary_lines)
        return ScoreResults(py_rows=py_rows, personal_rows=personal_rows, summary_text=summary_text, html=html)

    @staticmethod
    def _award_places(entries: List[Entry], key, attr: str) -> None:
        if not entries:
            return
        entries.sort(key=key)
        place = 1
        idx = 0
        while idx < len(entries):
            current = entries[idx]
            tie_group = [current]
            idx += 1
            while idx < len(entries) and key(entries[idx]) == key(current):
                tie_group.append(entries[idx])
                idx += 1
            tie_size = len(tie_group)
            place_value = float((place * tie_size + tie_size - 1) / tie_size)
            for entry in tie_group:
                setattr(entry, attr, place_value)
            place += tie_size

    @staticmethod
    def _build_html(py_rows: List[PyRow], personal_rows: List[PersonalRow]) -> str:
        def table_header(headers: List[str]) -> str:
            return "<tr>" + "".join(f"<th>{header}</th>" for header in headers) + "</tr>"

        def td(value) -> str:
            display = "" if value is None else value
            return f"<td>{display}</td>"

        py_table = [
            "<table id='PY'>",
            table_header(["Entry ID", "Helm/<br>Crew", "Class", "PY", "Laps", "Time", "Corrected", "Rank"]),
        ]
        for row in py_rows:
            corrected_value = row.fin_code if row.fin_code else row.corrected
            py_table.append(
                "<tr>"
                + td(row.entry_id)
                + td(f"{row.helm}<br>{row.crew}")
                + td(row.dinghy)
                + td(row.py)
                + td(row.laps)
                + td(row.time_seconds)
                + td(corrected_value)
                + td(row.rank or "")
                + "</tr>"
            )
        py_table.append("</table>")

        personal_table = [
            "<table id='personal'>",
            table_header(["Helm/<br>Crew", "Personal<br>Handicap", "Corrected", "Rank"]),
        ]
        for row in personal_rows:
            personal_table.append(
                "<tr>"
                + td(f"{row.helm}<br>{row.crew}")
                + td(row.personal_handicap)
                + td(row.corrected or "")
                + td(row.rank or "")
                + "</tr>"
            )
        personal_table.append("</table>")

        style = """<style>
            th{
                font-size: 12px;
                border: 1px solid black;
                text-align: center;
                padding: 2px;
            }
            table {border-collapse: collapse;}
            table#PY tr:nth-child(odd) td{background-color: #f2f2f2;}
            table#personal tr:nth-child(even) td{background-color: #a2a2a2;}
            table#personal {float: left; margin-left: 16px; }
            table#PY {float: left;}
            td {
                text-align: center;
                font-size: 12px;
                border: 1px solid black;
                padding: 2px;
            }
        </style>"""

        return "<html><head>" + style + "</head><body>" + "".join(py_table + personal_table) + "</body></html>"
