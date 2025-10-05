from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable


@dataclass
class QE:
    """Quick entry details for a helm/crew pairing."""

    code: str
    helm: str
    crew: str
    dinghy: str
    py: int
    personal: int = 0
    sail_number: str = ""
    age_group: str = "S"
    fleet: str = "S"
    message: str = ""

    @classmethod
    def from_csv(cls, line: str, classes: Dict[str, int]) -> "QE":
        """Factory that mirrors the legacy flat-file format."""

        line = line.replace("\r", "").strip()
        if not line:
            raise ValueError("empty QE line")

        tokens = [token.strip() for token in line.split(",")]
        if len(tokens) != 8:
            raise ValueError(
                "QE rows must contain 8 comma separated values: "
                "QE, helm, crew, class, sailno, personal, age group, fleet"
            )

        code, helm, crew, dinghy, sailno, personal, age_group, fleet = tokens

        if dinghy not in classes:
            raise ValueError(f"unknown class '{dinghy}' for QE {code}")

        py = classes[dinghy]
        try:
            personal_val = int(personal) if personal else 0
        except ValueError as exc:
            raise ValueError(f"invalid personal handicap '{personal}' for QE {code}") from exc

        age_group = age_group or "S"
        fleet = fleet or "S"

        return cls(
            code=code,
            helm=helm,
            crew=crew,
            dinghy=dinghy,
            py=py,
            personal=personal_val,
            sail_number=sailno,
            age_group=age_group,
            fleet=fleet,
        )

    @staticmethod
    def codes(qes: Iterable["QE"]) -> Dict[str, "QE"]:
        return {qe.code.upper(): qe for qe in qes}
