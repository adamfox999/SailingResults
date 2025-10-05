from __future__ import annotations

import json
from typing import Any, Dict, List

import typing as t

try:  # pragma: no cover - import guard for type checkers
    import pytest  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - pytest always available at runtime
    pytest = t.cast(t.Any, None)

from swsc_core import loader as loader_module
from swsc_core.loader import DataStore


class _SuccessClient:
    requests: List[Dict[str, Any]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_SuccessClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - nothing to clean
        return None

    def post(self, endpoint: str, params: Dict[str, Any], json: Any, headers: Dict[str, str]):
        _SuccessClient.requests.append(
            {
                "endpoint": endpoint,
                "params": params,
                "json": json,
                "headers": headers,
            }
        )
        request = loader_module.httpx.Request("POST", endpoint)
        return loader_module.httpx.Response(201, request=request, json=json)


class _FailingClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_FailingClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - nothing to clean
        return None

    def post(self, endpoint: str, params: Dict[str, Any], json: Any, headers: Dict[str, str]):
        request = loader_module.httpx.Request("POST", endpoint)
        response = loader_module.httpx.Response(
            400,
            request=request,
            json={"message": "invalid payload"},
        )
        raise loader_module.httpx.HTTPStatusError("Bad Request", request=request, response=response)


def _write_json(path, payload):
    path.write_text(json.dumps(payload))


def test_sync_local_backlog_success(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    store = DataStore(data_dir=tmp_path)

    series_entry = {
        "id": "local-series-1",
        "code": "AUT25",
        "title": "Autumn 2025",
        "start_date": "2025-09-07",
        "metadata": {
            "code": "AUT25",
            "title": "Autumn 2025",
            "startDate": "2025-09-07",
        },
    }
    schedule_entry = {
        "id": "sched-1",
        "series_code": "AUT25",
        "date": "2025-09-21",
        "start_time": "2025-09-21T10:30",
        "race_number": 1,
        "race_officer": "Jane",
        "metadata": {
            "series": "Autumn 2025",
            "race": "Race 1",
            "raceNumber": 1,
            "raceOfficer": "Jane",
            "date": "2025-09-21",
            "startTime": "2025-09-21T10:30",
            "notes": "",
        },
    }

    _write_json(store.local_series_path, [series_entry])
    _write_json(store.local_schedule_path, [schedule_entry])

    _SuccessClient.requests = []
    monkeypatch.setattr(loader_module.httpx, "Client", _SuccessClient)

    summary = store.sync_local_backlog()

    assert summary["series"] == {"synced": 1, "remaining": 0, "errors": []}
    assert summary["schedule"] == {"synced": 1, "remaining": 0, "errors": []}
    assert not store.local_series_path.exists()
    assert not store.local_schedule_path.exists()

    assert len(_SuccessClient.requests) == 2
    series_request = _SuccessClient.requests[0]
    assert series_request["params"].get("on_conflict") == "code"
    assert series_request["json"][0]["code"] == "AUT25"

    schedule_request = _SuccessClient.requests[1]
    assert schedule_request["params"].get("on_conflict") == "id"
    assert schedule_request["json"][0]["id"] == "sched-1"


def test_sync_local_backlog_schedule_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    store = DataStore(data_dir=tmp_path)

    schedule_entry = {
        "id": "sched-2",
        "series_code": "AUT25",
        "date": "2025-09-28",
        "start_time": "2025-09-28T10:30",
        "race_number": 2,
        "race_officer": "Sam",
        "metadata": {
            "series": "Autumn 2025",
            "race": "Race 2",
            "raceNumber": 2,
            "raceOfficer": "Sam",
            "date": "2025-09-28",
            "startTime": "2025-09-28T10:30",
            "notes": "",
        },
    }

    _write_json(store.local_schedule_path, [schedule_entry])

    monkeypatch.setattr(loader_module.httpx, "Client", _FailingClient)

    summary = store.sync_local_backlog()

    assert summary["schedule"]["synced"] == 0
    assert summary["schedule"]["remaining"] == 1
    assert summary["schedule"]["errors"]
    assert store.local_schedule_path.exists()


def test_sync_local_backlog_requires_supabase(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    store = DataStore(data_dir=tmp_path)
    _write_json(store.local_series_path, [])

    with pytest.raises(RuntimeError):
        store.sync_local_backlog()
