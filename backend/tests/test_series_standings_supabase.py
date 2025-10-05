from __future__ import annotations

from typing import Any, Dict, Generator

import pytest  # type: ignore

from swsc_core import DataStore
from swsc_core import loader as loader_module


class _Response:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - simple stub
        return None

    def json(self) -> Any:
        return self._payload


def _build_series_row(metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "id": "series-1",
        "code": "SPR",
        "title": "Spring Series",
        "start_date": "2025-03-01",
        "end_date": "2025-05-01",
        "metadata": metadata or {
            "code": "SPR",
            "title": "Spring Series",
            "startDate": "2025-03-01",
            "endDate": "2025-05-01",
        },
    }


def _build_race_row(
    race_id: str,
    race_label: str,
    py_rows: list[dict[str, Any]],
    personal_rows: list[dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "id": race_id,
        "start_time": "2025-03-01T10:00:00Z",
        "created_at": "2025-03-01T11:00:00Z",
        "payload": {
            "response": {
                "metadata": {
                    "race": race_label,
                    "raceNumber": int(race_id.split("-")[-1]),
                    "date": "2025-03-01",
                    "startTime": "10:00",
                },
                "pyResults": py_rows,
                "personalResults": personal_rows,
            }
        },
    }


@pytest.fixture(autouse=True)
def reset_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERIES_TABLE", raising=False)
    monkeypatch.delenv("SUPABASE_RACES_TABLE", raising=False)
    yield
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERIES_TABLE", raising=False)
    monkeypatch.delenv("SUPABASE_RACES_TABLE", raising=False)


def test_fetch_series_standings_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERIES_TABLE", "series")
    monkeypatch.setenv("SUPABASE_RACES_TABLE", "races")

    series_row = _build_series_row()

    race_one = _build_race_row(
        "race-1",
        "Race 1",
        [
            {
                "entryId": "alice-r1",
                "helm": "Alice",
                "crew": "",
                "dinghy": "Laser",
                "rank": 1,
            },
            {
                "entryId": "bob-r1",
                "helm": "Bob",
                "crew": "Charlie",
                "dinghy": "RS200",
                "rank": 2,
            },
        ],
        [
            {"entryId": "alice-r1", "rank": 1},
            {"entryId": "bob-r1", "rank": 2},
        ],
    )

    race_two = _build_race_row(
        "race-2",
        "Race 2",
        [
            {
                "entryId": "bob-r2",
                "helm": "Bob",
                "crew": "Charlie",
                "dinghy": "RS200",
                "rank": 1,
            },
            {
                "entryId": "eve-r2",
                "helm": "Eve",
                "crew": "",
                "dinghy": "Solo",
                "rank": 2,
            },
        ],
        [
            {"entryId": "bob-r2", "rank": 1},
            {"entryId": "eve-r2", "rank": 2},
        ],
    )

    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - nothing to clean up
            return None

        def get(self, endpoint: str, params: Dict[str, Any], headers: Dict[str, str]) -> _Response:
            if endpoint.endswith("/rest/v1/series"):
                return _Response([series_row])
            if endpoint.endswith("/rest/v1/races"):
                return _Response([race_one, race_two])
            raise AssertionError(f"Unexpected endpoint: {endpoint}")

    monkeypatch.setattr(loader_module.httpx, "Client", _Client)

    store = DataStore()
    standings = store.fetch_series_standings("series-1")

    assert standings["series"]["raceCount"] == 2
    assert standings["series"]["competitorCount"] == 3
    assert standings["series"]["dncValue"] == 4
    assert standings["series"]["toCount"] == 2

    py_results = standings["pyResults"]
    assert [item["helm"] for item in py_results] == ["Bob", "Alice", "Eve"]

    alice = next(item for item in py_results if item["helm"] == "Alice")
    assert alice["scores"]["perRace"][0] == {"value": 1.0, "isDnc": False, "counted": True}
    assert alice["scores"]["perRace"][1]["isDnc"] is True
    assert alice["scores"]["total"] == pytest.approx(5.0)

    bob = next(item for item in py_results if item["helm"] == "Bob")
    assert bob["scores"]["total"] == pytest.approx(3.0)
    assert bob["rank"] == 1

    personal_results = standings["personalResults"]
    assert [item["helm"] for item in personal_results] == ["Bob", "Alice", "Eve"]


def test_fetch_series_standings_honours_metadata_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERIES_TABLE", "series")
    monkeypatch.setenv("SUPABASE_RACES_TABLE", "races")

    series_row = _build_series_row(
        {
            "code": "SPR",
            "title": "Spring Series",
            "startDate": "2025-03-01",
            "endDate": "2025-05-01",
            "toCount": 1,
        }
    )

    race_one = _build_race_row(
        "race-1",
        "Race 1",
        [
            {
                "entryId": "alice-r1",
                "helm": "Alice",
                "crew": "",
                "dinghy": "Laser",
                "rank": 1,
            }
        ],
        [{"entryId": "alice-r1", "rank": 1}],
    )

    race_two = _build_race_row(
        "race-2",
        "Race 2",
        [
            {
                "entryId": "alice-r2",
                "helm": "Alice",
                "crew": "",
                "dinghy": "Laser",
                "rank": 2,
            }
        ],
        [{"entryId": "alice-r2", "rank": 2}],
    )

    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - nothing to clean up
            return None

        def get(self, endpoint: str, params: Dict[str, Any], headers: Dict[str, str]) -> _Response:
            if endpoint.endswith("/rest/v1/series"):
                return _Response([series_row])
            if endpoint.endswith("/rest/v1/races"):
                return _Response([race_one, race_two])
            raise AssertionError(f"Unexpected endpoint: {endpoint}")

    monkeypatch.setattr(loader_module.httpx, "Client", _Client)

    store = DataStore()
    standings = store.fetch_series_standings("series-1")

    assert standings["series"]["toCount"] == 1

    alice_scores = standings["pyResults"][0]["scores"]
    counted_flags = [cell["counted"] for cell in alice_scores["perRace"]]
    assert counted_flags.count(True) == 1
    assert alice_scores["total"] == pytest.approx(1.0)
