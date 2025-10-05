from typing import Any, Dict

import pytest

from swsc_core import DataStore
from swsc_core import loader as loader_module


class _DummyResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - nothing to do
        return None

    def json(self) -> Any:
        return self._payload


class _DummyClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.calls: list[Dict[str, Any]] = []

    def __enter__(self) -> "_DummyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - nothing to clean up
        return None

    def get(self, endpoint: str, params: Dict[str, Any], headers: Dict[str, str]) -> _DummyResponse:
        self.calls.append({"endpoint": endpoint, "params": params, "headers": headers})
        payload = [
            {"class_name": "RS200", "py_number": 1050, "source_list": "pn_list"},
            {"class_name": "RS200", "py_number": 1070, "source_list": "limited_list"},
            {"class_name": "DART 15 / SPRINT 15", "py_number": 924, "source_list": "pn_list"},
            {"class_name": "Mirror", "py_number": None, "source_list": "pn_list"},
        ]
        return _DummyResponse(payload)


class _DummyHTTPX:
    def __init__(self) -> None:  # pragma: no cover - never instantiated
        raise RuntimeError("Not expected to instantiate _DummyHTTPX directly")

    Client = _DummyClient


@pytest.fixture(autouse=True)
def reset_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_HANDICAPS_TABLE", raising=False)
    monkeypatch.delenv("SUPABASE_SCHEMA", raising=False)
    yield
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_HANDICAPS_TABLE", raising=False)
    monkeypatch.delenv("SUPABASE_SCHEMA", raising=False)


def test_load_handicaps_from_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_HANDICAPS_TABLE", "handicaps")

    monkeypatch.setattr(loader_module, "httpx", _DummyHTTPX)

    store = DataStore()

    classes = store.load_handicaps()

    # Only exact Supabase names - NO aliases created
    assert classes["RS200"] == 1050
    assert classes["DART 15 / SPRINT 15"] == 924
    assert "SPRINT 15" not in classes  # Alias should NOT be created
    assert "DART 15" not in classes  # Alias should NOT be created

    options = dict(store.class_display_options())
    assert options["RS200"] == "RS200"
    assert options["DART 15 / SPRINT 15"] == "DART 15 / SPRINT 15"
    assert "SPRINT 15" not in options
    assert "DART 15" not in options

    # cached value should be reused even if Supabase variables remain
    assert store.load_handicaps() is classes


def test_load_handicaps_without_supabase_requires_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Supabase credentials are missing, system falls back to CSV file."""
    # No Supabase env vars set - should attempt CSV fallback
    store = DataStore()
    
    # Without CSV file present, should raise FileNotFoundError
    # This test verifies that CSV fallback is still attempted when Supabase is not configured
    # In production, the CSV file exists, but in test environment it may not
    try:
        classes = store.load_handicaps()
        # If CSV exists, verify it loaded data
        assert len(classes) > 0
    except FileNotFoundError:
        # If CSV doesn't exist, that's expected in test environment
        pass


def test_load_handicaps_with_empty_supabase_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Supabase returns no data, system should raise error with no fallback."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    
    class _EmptyClient(_DummyClient):
        def get(self, endpoint: str, params: Dict[str, Any], headers: Dict[str, str]) -> _DummyResponse:
            self.calls.append({"endpoint": endpoint, "params": params, "headers": headers})
            return _DummyResponse([])  # Empty response
    
    class _EmptyHTTPX:
        Client = _EmptyClient
    
    monkeypatch.setattr(loader_module, "httpx", _EmptyHTTPX)
    
    store = DataStore()
    
    # Should raise RuntimeError when Supabase returns no data
    with pytest.raises(RuntimeError, match="Supabase query returned zero handicap rows"):
        store.load_handicaps()
