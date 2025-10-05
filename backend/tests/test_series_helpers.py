from __future__ import annotations

import typing as t

try:  # pragma: no cover - import guard for type checkers
    import pytest  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - pytest always available at runtime
    pytest = t.cast(t.Any, None)

from swsc_core.loader import DataStore
from swsc_core import loader as loader_module


@pytest.fixture
def store() -> DataStore:
    return DataStore()


class _SeriesDummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):  # pragma: no cover - satisfies DataStore contract
        return None

    def json(self):
        return self._payload


def test_series_record_for_create_requires_title(store: DataStore):
    with pytest.raises(ValueError):
        store._series_record_for_create({})


def test_series_record_for_create_builds_metadata(store: DataStore):
    record = store._series_record_for_create(
        {
            "title": "Autumn Series",
            "code": "autumn",
            "startDate": "2025-09-07",
        }
    )

    assert record["code"] == "AUTUMN"
    assert record["title"] == "Autumn Series"
    assert record["start_date"] == "2025-09-07"
    assert record["end_date"] is None
    assert record["metadata"] == {
        "code": "AUTUMN",
        "title": "Autumn Series",
        "startDate": "2025-09-07",
        "endDate": None,
    }


def test_series_record_for_update_validates_title(store: DataStore):
    existing = {"code": "AUT", "title": "Autumn", "startDate": "2025-09-07"}
    with pytest.raises(ValueError):
        store._series_record_for_update({"title": "   "}, existing)


def test_series_record_for_update_returns_none_when_no_changes(store: DataStore):
    existing = {"code": "AUT", "title": "Autumn", "startDate": "2025-09-07"}
    assert store._series_record_for_update({}, existing) is None


def test_series_record_for_update_merges_fields(store: DataStore):
    existing = {
        "code": "AUT",
        "title": "Autumn",
        "startDate": "2025-09-07",
        "endDate": "2025-12-07",
    }
    record = store._series_record_for_update(
        {"title": "Autumn 2025", "startDate": "2025-09-14", "endDate": "2025-12-14"},
        existing,
    )

    assert record == {
        "title": "Autumn 2025",
        "start_date": "2025-09-14",
        "end_date": "2025-12-14",
        "metadata": {
            "code": "AUT",
            "title": "Autumn 2025",
            "startDate": "2025-09-14",
            "endDate": "2025-12-14",
        },
    }


def test_normalise_series_row_prefers_metadata(store: DataStore):
    row = {
        "id": "123",
        "code": "SPR",
        "title": "Spring",
        "start_date": "2025-03-01",
        "end_date": "2025-06-01",
        "metadata": {
            "code": "SPRING",
            "title": "Spring Sprint",
            "startDate": "2025-03-02",
            "endDate": "2025-05-31",
        },
    }

    normalised = store._normalise_series_row(row)

    assert normalised == {
        "id": "123",
        "code": "SPRING",
        "title": "Spring Sprint",
        "startDate": "2025-03-02",
        "endDate": "2025-05-31",
    }


def test_fetch_series_handles_missing_metadata_column(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    store = DataStore(data_dir=tmp_path)

    class MetadataClient:
        call_count = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # pragma: no cover - nothing to clean up
            return None

        def get(self, endpoint, params, headers):
            MetadataClient.call_count += 1
            request = loader_module.httpx.Request("GET", endpoint)
            if MetadataClient.call_count == 1:
                response = loader_module.httpx.Response(
                    400,
                    request=request,
                    json={"message": "Could not find the 'metadata' column of 'series' in the schema cache"},
                )
                raise loader_module.httpx.HTTPStatusError("Bad Request", request=request, response=response)
            return _SeriesDummyResponse([
                {
                    "id": "series-1",
                    "code": "AUT",
                    "title": "Autumn",
                    "start_date": "2025-09-07",
                }
            ])

    MetadataClient.call_count = 0
    monkeypatch.setattr(loader_module.httpx, "Client", MetadataClient)

    series = store.fetch_series()

    assert store._series_supports_metadata is False
    assert series == [
        {
            "id": "series-1",
            "code": "AUT",
            "title": "Autumn",
            "startDate": "2025-09-07",
            "endDate": None,
        }
    ]


def test_create_series_handles_missing_metadata_column(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    store = DataStore(data_dir=tmp_path)

    class MetadataClient:
        call_count = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # pragma: no cover - nothing to clean up
            return None

        def post(self, endpoint, params, json, headers):
            MetadataClient.call_count += 1
            request = loader_module.httpx.Request("POST", endpoint)
            if MetadataClient.call_count == 1:
                response = loader_module.httpx.Response(
                    400,
                    request=request,
                    json={"message": "Could not find the 'metadata' column of 'series' in the schema cache"},
                )
                raise loader_module.httpx.HTTPStatusError("Bad Request", request=request, response=response)

            assert "metadata" not in json
            response_payload = dict(json)
            response_payload.setdefault("id", "series-2")
            return loader_module.httpx.Response(201, request=request, json=response_payload)

    MetadataClient.call_count = 0
    monkeypatch.setattr(loader_module.httpx, "Client", MetadataClient)

    created = store.create_series({
        "title": "Autumn Series",
        "code": "AUT25",
        "startDate": "2025-09-07",
    })

    assert store._series_supports_metadata is False
    assert created["code"] == "AUT25"
    assert created["title"] == "Autumn Series"
    assert created["startDate"] == "2025-09-07"
    assert created["endDate"] is None


def test_create_series_conflict_from_supabase(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    store = DataStore(data_dir=tmp_path)

    class ConflictClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # pragma: no cover - no cleanup needed
            return None

        def post(self, endpoint, params, json, headers):
            request = loader_module.httpx.Request("POST", endpoint)
            response = loader_module.httpx.Response(
                409,
                request=request,
                json={
                    "message": "duplicate key value violates unique constraint \"series_code_key\""
                },
            )
            raise loader_module.httpx.HTTPStatusError("Conflict", request=request, response=response)

    monkeypatch.setattr(loader_module.httpx, "Client", ConflictClient)

    with pytest.raises(ValueError, match="Series code already exists"):
        store.create_series({
            "title": "Autumn Series",
            "startDate": "2025-09-07",
        })

    assert not store.local_series_path.exists()


def test_update_series_conflict_from_supabase(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    store = DataStore(data_dir=tmp_path)

    sample_row = {
        "id": "abc-123",
        "code": "AUTUMN",
        "title": "Autumn Series",
        "start_date": "2025-09-07",
        "metadata": {
            "code": "AUTUMN",
            "title": "Autumn Series",
            "startDate": "2025-09-07",
        },
    }

    class ConflictClient:
        def __init__(self, *args, **kwargs):
            self._call_count = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # pragma: no cover - no cleanup needed
            return None

        def get(self, endpoint, params, headers):
            self._call_count += 1
            return _SeriesDummyResponse([sample_row])

        def patch(self, endpoint, params, json, headers):
            request = loader_module.httpx.Request("PATCH", endpoint)
            response = loader_module.httpx.Response(
                409,
                request=request,
                json={
                    "message": "duplicate key value violates unique constraint \"series_code_key\""
                },
            )
            raise loader_module.httpx.HTTPStatusError("Conflict", request=request, response=response)

    monkeypatch.setattr(loader_module.httpx, "Client", ConflictClient)

    with pytest.raises(ValueError, match="Series code already exists"):
        store.update_series("abc-123", {"title": "Autumn 2025"})

    assert not store.local_series_path.exists()
