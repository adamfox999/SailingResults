# Version 2.0.0 - Removed QE codes system, simplified to only load handicaps from Supabase
from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import math
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx


logger = logging.getLogger(__name__)


@dataclass
class DataSources:
    """Legacy structure - kept for backward compatibility."""
    handicap_file: Path


class DataStore:
    """Loads handicap data from Supabase or CSV fallback."""

    def __init__(self, data_dir: Path | None = None, config_path: Path | None = None) -> None:
        """Initialize the DataStore.
        
        Args:
            data_dir: Directory containing data files (for CSV fallback)
            config_path: Path to config.json (for CSV fallback)
        """
        self.data_dir = data_dir or (Path(__file__).parent.parent / "data")
        self.config_path = config_path or (self.data_dir / "config.json")
        self._sources: DataSources | None = None
        self._handicaps: Dict[str, int] | None = None
        self._display_options: List[Tuple[str, str]] | None = None
        
        # Supabase configuration
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_SERVICE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
            or ""
        )
        self.supabase_table = os.getenv("SUPABASE_HANDICAPS_TABLE", "handicaps")
        self.supabase_schema = os.getenv("SUPABASE_SCHEMA", "public")
        self.supabase_series_table = os.getenv("SUPABASE_SERIES_TABLE", "series")
        self.supabase_races_table = os.getenv("SUPABASE_RACES_TABLE", "races")
        self.supabase_entries_table = os.getenv("SUPABASE_ENTRIES_TABLE", "entries")
        self.supabase_schedule_table = os.getenv("SUPABASE_SCHEDULE_TABLE", "scheduled_races")
        self.supabase_profiles_table = os.getenv("SUPABASE_PROFILES_TABLE", "profiles")
        self.supabase_series_entries_table = os.getenv("SUPABASE_SERIES_ENTRIES_TABLE", "series_entries")
        self.supabase_series_signons_table = os.getenv("SUPABASE_SERIES_SIGNONS_TABLE", "series_signons")
        self.local_series_path = self.data_dir / "series_local.json"
        self.local_schedule_path = self.data_dir / "scheduled_races_local.json"
        self.local_series_entries_path = self.data_dir / "series_entries_local.json"
        self.local_series_signons_path = self.data_dir / "series_signons_local.json"
        self._series_supports_metadata = True
        self._schedule_warning_logged = False
        self._races_supports_number: bool | None = None
        self._entries_supports_entry_id: bool | None = None
        self._entries_excluded_fields: set[str] = set()
        self._entries_conflict_target: str | None = None

    def load_handicaps(self) -> Dict[str, int]:
        """Load handicap numbers from Supabase or CSV fallback."""
        if self._handicaps is not None:
            return self._handicaps

        if self.supabase_url and self.supabase_key:
            handicaps, display = self._handicaps_from_supabase()
        else:
            handicaps, display = self._handicaps_from_file()

        self._handicaps = handicaps
        self._display_options = [(key, label) for key, label in display.items()]
        self._display_options.sort(key=lambda item: item[1])

        return self._handicaps

    def class_display_options(self) -> List[Tuple[str, str]]:
        """Get list of (key, label) pairs for class dropdown options."""
        if self._display_options is None:
            self.load_handicaps()
        return self._display_options or []

    def fetch_profiles_roster(self) -> List[Dict[str, Any]]:
        """Fetch profile roster (names and boats) from Supabase."""
        if not (self.supabase_url and self.supabase_key and self.supabase_profiles_table):
            return []

        profile_rows = self._fetch_supabase_profile_rows()
        if not profile_rows:
            return []

        users = self._fetch_supabase_users()

        roster: List[Dict[str, Any]] = []
        profiles_seen: set[str] = set()
        for row in profile_rows:
            profile_id = str(row.get("id") or "").strip()
            if not profile_id:
                continue
            profiles_seen.add(profile_id)

            boats_raw = row.get("boats")
            boats: List[Dict[str, Any]] = []
            if isinstance(boats_raw, list):
                for boat in boats_raw:
                    if isinstance(boat, dict):
                        boats.append(
                            {
                                "className": str(boat.get("className") or "").strip(),
                                "sailNumber": str(boat.get("sailNumber") or "").strip(),
                            }
                        )

            user = users.get(profile_id)
            display_name = self._extract_user_display_name(user)

            helm_name = str(row.get("helm") or "").strip()
            crew_name = str(row.get("crew") or "").strip()

            if not helm_name:
                helm_name = display_name
            if not crew_name and display_name:
                crew_name = display_name

            if not helm_name and not crew_name:
                fallback = display_name or str(user.get("email", "")) if isinstance(user, dict) else ""
                if not fallback:
                    fallback = profile_id
                helm_name = crew_name = fallback

            roster.append(
                {
                    "id": profile_id,
                    "helm": helm_name,
                    "crew": crew_name,
                    "boats": boats,
                }
            )

        for user_id, user in users.items():
            if user_id in profiles_seen:
                continue
            display_name = self._extract_user_display_name(user)
            if not display_name:
                continue
            roster.append(
                {
                    "id": user_id,
                    "helm": display_name,
                    "crew": display_name,
                    "boats": [],
                }
            )

        roster.sort(key=lambda item: (item.get("helm") or item.get("crew") or "").lower())

        return roster

    def _fetch_supabase_profile_rows(self) -> List[Dict[str, Any]]:
        endpoint = self._supabase_endpoint(self.supabase_profiles_table)
        attempts = [
            {"select": "id,helm,crew,boats", "order": "helm.asc"},
            {"select": "id,boats", "order": "id.asc"},
        ]

        headers_primary = self._supabase_headers(include_content_profile=False)

        for attempt_index, attempt in enumerate(attempts):
            params = {
                "select": attempt["select"],
                "order": attempt["order"],
            }
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(endpoint, params=params, headers=headers_primary)
                    response.raise_for_status()
                    rows = response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (400, 406) and attempt_index < len(attempts) - 1:
                    continue
                logger.warning("Supabase profiles query failed (%s)", exc)
                return []
            except httpx.HTTPError as exc:
                logger.warning("Supabase profiles query failed (%s)", exc)
                return []

            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
            logger.warning("Supabase profiles query returned unexpected payload: %s", type(rows))
            return []

        return []

    def _fetch_supabase_users(self) -> Dict[str, Dict[str, Any]]:
        if not (self.supabase_url and self.supabase_key):
            return {}

        endpoint = f"{self.supabase_url.rstrip('/')}/auth/v1/admin/users"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Accept": "application/json",
        }
        params = {"per_page": 1000}

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(endpoint, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                logger.info(
                    "Supabase users query returned 403 (not_admin). Configure SUPABASE_SERVICE_ROLE_KEY to access display names.",
                )
                return {}
            logger.warning("Supabase users query failed (%s)", exc)
            return {}
        except httpx.HTTPError as exc:
            logger.warning("Supabase users query failed (%s)", exc)
            return {}

        records: List[Dict[str, Any]]
        if isinstance(payload, dict) and isinstance(payload.get("users"), list):
            records = [item for item in payload["users"] if isinstance(item, dict)]
        elif isinstance(payload, list):
            records = [item for item in payload if isinstance(item, dict)]
        else:
            logger.warning("Supabase users query returned unexpected payload: %s", type(payload))
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        for item in records:
            user_id = str(item.get("id") or "").strip()
            if not user_id:
                continue
            result[user_id] = item

        return result

    @staticmethod
    def _extract_user_display_name(user: Dict[str, Any] | None) -> str:
        if not user:
            return ""

        for key in ("display_name", "displayName", "Display Name", "name"):
            value = user.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        metadata_fields = (
            user.get("user_metadata"),
            user.get("raw_user_meta_data"),
            user.get("raw_user_metadata"),
            user.get("app_metadata"),
        )
        for metadata in metadata_fields:
            if not isinstance(metadata, dict):
                continue
            for key in ("full_name", "name", "display_name", "displayName", "Display Name"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        email = user.get("email")
        if isinstance(email, str) and email.strip():
            return email.strip()

        phone = user.get("phone")
        if isinstance(phone, str) and phone.strip():
            return phone.strip()

        return ""

    def _handicaps_from_supabase(self) -> Tuple[Dict[str, int], Dict[str, str]]:
        """Load handicaps from Supabase REST API."""
        endpoint = self.supabase_url.rstrip("/") + "/rest/v1/" + self.supabase_table
        params = {
            "select": "class_name,py_number,source_list",
        }
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Accept": "application/json",
        }
        if self.supabase_schema and self.supabase_schema != "public":
            headers["Accept-Profile"] = self.supabase_schema

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(endpoint, params=params, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Failed to load handicaps from Supabase: {exc}") from exc

        if not isinstance(rows, list):
            raise RuntimeError("Unexpected payload from Supabase handicaps endpoint")

        priority = {"pn_list": 2, "limited_list": 1}
        handicaps_with_priority: Dict[str, Tuple[int, int]] = {}
        display: Dict[str, str] = {}

        for row in rows:
            if not isinstance(row, dict):
                continue
            class_name = str(row.get("class_name") or "").strip()
            if not class_name:
                continue
            py_number = row.get("py_number")
            try:
                py_value = int(py_number)
            except (TypeError, ValueError):
                continue
            source_list = row.get("source_list") or ""
            priority_score = priority.get(str(source_list), 0)

            canonical_key = class_name.upper()
            existing = handicaps_with_priority.get(canonical_key)
            if not existing or priority_score > existing[1]:
                handicaps_with_priority[canonical_key] = (py_value, priority_score)
                display[canonical_key] = class_name

        final_handicaps = {cls: value for cls, (value, _) in handicaps_with_priority.items()}

        if not final_handicaps:
            raise RuntimeError("Supabase query returned zero handicap rows")

        return final_handicaps, display

    def _handicaps_from_file(self) -> Tuple[Dict[str, int], Dict[str, str]]:
        """Load handicaps from CSV file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        raw = json.loads(self.config_path.read_text())
        if not isinstance(raw, list) or len(raw) < 1:
            raise ValueError("config.json must contain at least handicaps file path")
        
        handicap_file = (self.data_dir / raw[0]).resolve()
        if not handicap_file.exists():
            raise FileNotFoundError(f"Handicap file not found: {handicap_file}")

        handicaps: Dict[str, int] = {}
        display: Dict[str, str] = {}
        
        with handicap_file.open(newline="") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if not row or not row[0].strip():
                    continue
                raw_name = row[0].strip()
                dinghy = raw_name.upper()
                try:
                    py_value = int(row[1])
                except (IndexError, ValueError):
                    continue
                handicaps[dinghy] = py_value
                display[dinghy] = raw_name
        
        if not handicaps:
            raise ValueError(f"No handicap rows found in {handicap_file}")
        
        return handicaps, display

    # ------------------------------------------------------------------
    # Race persistence helpers

    def persist_race(
        self,
        metadata: Dict[str, Any],
        request_payload: Dict[str, Any],
        response_payload: Dict[str, Any],
        entries: List[Dict[str, Any]],
    ) -> None:
        """Persist a scored race to Supabase tables.

        Best-effort operation; failures are logged but do not raise.
        """

        if not (self.supabase_url and self.supabase_key):
            return

        series_code = (metadata.get("series") or "").strip()
        if not series_code:
            logger.debug("Skipping race persistence: missing series code")
            return

        race_number_raw = metadata.get("raceNumber") or metadata.get("race_number")
        try:
            race_number = int(race_number_raw) if race_number_raw is not None else None
        except (TypeError, ValueError):
            race_number = None

        date_str = metadata.get("date")
        start_time_raw = metadata.get("startTime") or metadata.get("start_time")
        start_time_value = None
        if start_time_raw:
            if date_str and "T" not in str(start_time_raw):
                start_time_value = f"{date_str}T{start_time_raw}"
            else:
                start_time_value = str(start_time_raw)

        payload_wrapper = {
            "request": request_payload,
            "response": response_payload,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                series_id = self._persist_get_or_create_series(client, series_code, metadata)
                if not series_id:
                    return
                race_id = self._persist_upsert_race(
                    client,
                    series_id,
                    race_number,
                    start_time_value,
                    payload_wrapper,
                )
                if race_id and entries:
                    self._persist_upsert_entries(client, race_id, entries, response_payload)
        except Exception:  # pragma: no cover - logging side effect
            logger.exception("Failed to persist race data to Supabase")

    # ------------------------------------------------------------------
    # Series helpers

    def fetch_series(self) -> List[Dict[str, Any]]:
        if not (self.supabase_url and self.supabase_key and self.supabase_series_table):
            return self._load_local_series()

        endpoint = self._supabase_endpoint(self.supabase_series_table)
        headers = self._supabase_headers(include_content_profile=False)
        params = {
            "select": self._series_select_fields(),
            "order": "start_date.asc,title.asc",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(endpoint, params=params, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPStatusError as exc:
            if self._handle_series_metadata_error(exc.response):
                return self.fetch_series()
            raise RuntimeError(f"Failed to fetch series: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.warning("Supabase fetch_series failed (%s); using local fallback", exc)
            return self._load_local_series()

        if not isinstance(rows, list):
            return []

        return [self._normalise_series_row(row) for row in rows if isinstance(row, dict)]

    def create_series(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = self._series_record_for_create(payload)

        if not (self.supabase_url and self.supabase_key and self.supabase_series_table):
            return self._create_series_local(record)

        endpoint = self._supabase_endpoint(self.supabase_series_table)
        headers = self._supabase_headers("return=representation")
        headers["Content-Type"] = "application/json"
        while True:
            params = {"select": self._series_select_fields()}
            payload_for_supabase = self._prepare_series_payload(record)

            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(endpoint, params=params, json=payload_for_supabase, headers=headers)
                    response.raise_for_status()
                    rows = response.json()
            except httpx.HTTPStatusError as exc:
                if self._handle_series_metadata_error(exc.response):
                    continue

                status_code = exc.response.status_code if exc.response else None
                detail = self._extract_supabase_detail(exc.response)
                if status_code == 409:
                    existing = self._fetch_existing_series_by_code(record["code"])
                    if existing:
                        return existing

                    message = "Series code already exists"
                    if detail and detail.lower() not in message.lower():
                        message = f"{message}. Supabase: {detail}"
                    raise ValueError(message) from exc
                if status_code is not None and 400 <= status_code < 500:
                    raise ValueError(detail or f"Supabase rejected create_series ({status_code})") from exc
                logger.warning("Supabase create_series failed (%s); using local fallback", exc)
                return self._create_series_local(record)
            except httpx.RequestError as exc:
                logger.warning("Supabase create_series unavailable (%s); using local fallback", exc)
                return self._create_series_local(record)
            break

        if isinstance(rows, list) and rows:
            return self._normalise_series_row(rows[0])
        if isinstance(rows, dict):
            return self._normalise_series_row(rows)
        raise RuntimeError("Unexpected response when creating series")

    def update_series(self, series_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not (self.supabase_url and self.supabase_key and self.supabase_series_table):
            return self._update_series_local(series_id, payload)

        endpoint = self._supabase_endpoint(self.supabase_series_table)
        headers = self._supabase_headers(include_content_profile=False)
        params = {
            "select": self._series_select_fields(),
            "id": f"eq.{series_id}",
            "limit": 1,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(endpoint, params=params, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPStatusError as exc:
            if self._handle_series_metadata_error(exc.response):
                return self.update_series(series_id, payload)
            logger.warning("Supabase update_series fetch failed (%s); using local fallback", exc)
            return self._update_series_local(series_id, payload)
        except httpx.HTTPError as exc:
            logger.warning("Supabase update_series fetch failed (%s); using local fallback", exc)
            return self._update_series_local(series_id, payload)

        existing_row = rows[0] if isinstance(rows, list) and rows else None
        if not isinstance(existing_row, dict):
            raise ValueError("Series not found")

        existing = self._normalise_series_row(existing_row)
        record = self._series_record_for_update(payload, existing)
        if record is None:
            return existing

        headers = self._supabase_headers("return=representation")
        headers["Content-Type"] = "application/json"

        while True:
            patch_params = {"id": f"eq.{series_id}", "select": self._series_select_fields()}
            payload_for_supabase = self._prepare_series_payload(record)

            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.patch(
                        endpoint,
                        params=patch_params,
                        json=payload_for_supabase,
                        headers=headers,
                    )
                    response.raise_for_status()
                    rows = response.json()
            except httpx.HTTPStatusError as exc:
                if self._handle_series_metadata_error(exc.response):
                    continue

                status_code = exc.response.status_code if exc.response else None
                detail = self._extract_supabase_detail(exc.response)
                if status_code == 409:
                    message = "Series code already exists"
                    if detail and detail.lower() not in message.lower():
                        message = f"{message}. Supabase: {detail}"
                    raise ValueError(message) from exc
                if status_code == 404:
                    raise ValueError("Series not found") from exc
                if status_code is not None and 400 <= status_code < 500:
                    raise ValueError(detail or f"Supabase rejected update_series ({status_code})") from exc
                logger.warning("Supabase update_series patch failed (%s); using local fallback", exc)
                return self._update_series_local(series_id, payload, existing)
            except httpx.RequestError as exc:
                logger.warning("Supabase update_series unavailable (%s); using local fallback", exc)
                return self._update_series_local(series_id, payload, existing)
            break

        if isinstance(rows, list) and rows:
            return self._normalise_series_row(rows[0])
        if isinstance(rows, dict):
            return self._normalise_series_row(rows)
        return existing

    def _fetch_existing_series_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        if not (self.supabase_url and self.supabase_key and self.supabase_series_table):
            return None

        endpoint = self._supabase_endpoint(self.supabase_series_table)
        headers = self._supabase_headers(include_content_profile=False)
        params = {
            "select": self._series_select_fields(),
            "code": f"eq.{code}",
            "limit": 1,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                get_method = getattr(client, "get", None)
                if not callable(get_method):
                    return None
                response = get_method(endpoint, params=params, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except (httpx.HTTPError, AttributeError):
            return None

        if isinstance(rows, list) and rows:
            return self._normalise_series_row(rows[0])
        if isinstance(rows, dict) and rows:
            return self._normalise_series_row(rows)
        return None

    # ------------------------------------------------------------------
    # Scheduled race helpers

    def fetch_scheduled_races(self, include_past: bool = False) -> List[Dict[str, Any]]:
        if not (self.supabase_url and self.supabase_key and self.supabase_schedule_table):
            return self._load_local_schedule(include_past)

        endpoint = self._supabase_endpoint(self.supabase_schedule_table)
        headers = self._supabase_headers(include_content_profile=False)
        params = {
            "select": "id,series_code,metadata,date,start_time,notes,race_number,race_officer",
            "order": "date.asc,start_time.asc",
        }
        if not include_past:
            today = dt.date.today().isoformat()
            params["date"] = f"gte.{today}"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(endpoint, params=params, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                if not self._schedule_warning_logged:
                    logger.info(
                        "Supabase scheduled races table missing (HTTP 404). Falling back to local JSON. "
                        "Create table '%s' or set SUPABASE_SCHEDULE_TABLE to match your schema.",
                        self.supabase_schedule_table,
                    )
                    self._schedule_warning_logged = True
                return self._load_local_schedule(include_past)
            logger.warning("Supabase fetch_scheduled_races failed (%s); using local fallback", exc)
            return self._load_local_schedule(include_past)
        except httpx.HTTPError as exc:
            logger.warning("Supabase fetch_scheduled_races failed (%s); using local fallback", exc)
            return self._load_local_schedule(include_past)

        if not isinstance(rows, list):
            return []

        return [self._normalise_schedule_row(row) for row in rows if isinstance(row, dict)]

    def create_scheduled_race(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = self._schedule_record_from_payload(payload)

        if not (self.supabase_url and self.supabase_key and self.supabase_schedule_table):
            return self._create_scheduled_race_local(record)

        endpoint = self._supabase_endpoint(self.supabase_schedule_table)
        headers = self._supabase_headers("return=representation")
        headers["Content-Type"] = "application/json"
        params = {"select": "id,series_code,metadata,date,start_time,notes,race_number,race_officer"}

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(endpoint, params=params, json=record, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Supabase create_scheduled_race failed (%s); using local fallback", exc)
            return self._create_scheduled_race_local(record)

        if isinstance(rows, list) and rows:
            return self._normalise_schedule_row(rows[0])
        if isinstance(rows, dict):
            return self._normalise_schedule_row(rows)
        raise RuntimeError("Unexpected response when creating scheduled race")

    # ---- internal Supabase helpers -------------------------------------------------

    def _supabase_endpoint(self, table: str) -> str:
        return f"{self.supabase_url.rstrip('/')}/rest/v1/{table}"

    def _supabase_headers(self, prefer: str | None = None, include_content_profile: bool = True) -> Dict[str, str]:
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Accept": "application/json",
        }
        if include_content_profile and self.supabase_schema and self.supabase_schema != "public":
            headers["Content-Profile"] = self.supabase_schema
        if self.supabase_schema and self.supabase_schema != "public":
            headers["Accept-Profile"] = self.supabase_schema
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _persist_get_or_create_series(
        self,
        client: httpx.Client,
        series_code: str,
        metadata: Dict[str, Any],
    ) -> str | None:
        if not self.supabase_series_table:
            return None
        endpoint = self._supabase_endpoint(self.supabase_series_table)
        headers = self._supabase_headers(include_content_profile=False)
        params = {"select": "id", "code": f"eq.{series_code}", "limit": 1}
        response = client.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        rows = response.json()
        if isinstance(rows, list) and rows:
            return rows[0].get("id")

        payload = {
            "code": series_code,
            "title": metadata.get("series"),
            "start_date": metadata.get("date"),
        }
        headers = self._supabase_headers("resolution=merge-duplicates,return=representation")
        headers["Content-Type"] = "application/json"
        params = {"on_conflict": "code", "select": "id"}
        response = client.post(endpoint, params=params, json=payload, headers=headers)
        response.raise_for_status()
        rows = response.json()
        if isinstance(rows, list) and rows:
            return rows[0].get("id")
        return None

    def _persist_upsert_race(
        self,
        client: httpx.Client,
        series_id: str,
        race_number: int | None,
        start_time_value: str | None,
        payload_wrapper: Dict[str, Any],
    ) -> str | None:
        if not self.supabase_races_table:
            return None

        if self._races_supports_number is None:
            self._races_supports_number = True

        endpoint = self._supabase_endpoint(self.supabase_races_table)
        supports_number = bool(self._races_supports_number)

        while True:
            record = {
                "series_id": series_id,
                "start_time": start_time_value,
                "payload": payload_wrapper,
            }

            params: Dict[str, Any] = {"select": "id"}
            if supports_number and race_number is not None:
                record["race_number"] = race_number
                params["on_conflict"] = "series_id,race_number"

            headers = self._supabase_headers("resolution=merge-duplicates,return=representation")
            headers["Content-Type"] = "application/json"

            try:
                response = client.post(endpoint, params=params, json=record, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = self._extract_supabase_detail(exc.response)
                if (
                    supports_number
                    and exc.response
                    and exc.response.status_code == 400
                    and detail
                    and "race_number" in detail
                ):
                    self._races_supports_number = False
                    supports_number = False
                    logger.info("Supabase races table missing race_number column; retrying without it")
                    continue
                raise

            rows = response.json()
            if isinstance(rows, list) and rows:
                return rows[0].get("id")
            if isinstance(rows, dict):
                return rows.get("id")
            return None

    def _persist_upsert_entries(
        self,
        client: httpx.Client,
        race_id: str,
        entries: List[Dict[str, Any]],
        response_payload: Dict[str, Any],
    ) -> None:
        if not self.supabase_entries_table:
            return

        endpoint = self._supabase_endpoint(self.supabase_entries_table)
        py_results = {row.get("entryId"): row for row in response_payload.get("pyResults", []) if isinstance(row, dict)}
        personal_results = {
            row.get("entryId"): row for row in response_payload.get("personalResults", []) if isinstance(row, dict)
        }
        if self._entries_supports_entry_id is None:
            self._entries_supports_entry_id = True

        headers = self._supabase_headers("resolution=merge-duplicates,return=representation")
        headers["Content-Type"] = "application/json"

        raw_entries = entries
        conflict_target = self._entries_conflict_target

        while True:
            supports_entry_id = bool(self._entries_supports_entry_id)

            records: List[Dict[str, Any]] = []
            for entry in raw_entries:
                entry_id = entry.get("entry_id")
                if not entry_id:
                    continue
                py_row = py_results.get(entry_id) or {}
                personal_row = personal_results.get(entry_id) or {}
                competitor_key = "|".join(
                    [
                        (entry.get("helm") or "").strip(),
                        (entry.get("crew") or "").strip(),
                        (entry.get("dinghy") or "").strip(),
                    ]
                )
                record = {
                    "race_id": race_id,
                    "competitor_key": competitor_key,
                    "helm": entry.get("helm"),
                    "crew": entry.get("crew"),
                    "class_name": entry.get("dinghy"),
                    "py": entry.get("py"),
                    "personal": entry.get("personal"),
                    "sail_number": entry.get("sail_number") or None,
                    "result": {
                        "laps": entry.get("laps"),
                        "timeSeconds": entry.get("time_seconds"),
                        "finCode": entry.get("fin_code"),
                        "py": py_row,
                        "personal": personal_row,
                    },
                }
                if supports_entry_id:
                    record["entry_id"] = entry_id
                for excluded in self._entries_excluded_fields:
                    record.pop(excluded, None)
                records.append(record)

            if not records:
                return

            current_conflict = conflict_target
            if current_conflict is None:
                current_conflict = "entry_id" if supports_entry_id else None

            params: Dict[str, Any] = {"select": "race_id"}
            if current_conflict:
                params["on_conflict"] = current_conflict

            try:
                response = client.post(endpoint, params=params, json=records, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = self._extract_supabase_detail(exc.response)
                if detail:
                    lowered = detail.lower()
                    missing_column = self._extract_missing_column_name(detail)
                    if missing_column:
                        if missing_column == "entry_id":
                            self._entries_supports_entry_id = False
                            supports_entry_id = False
                        self._entries_excluded_fields.add(missing_column)
                        conflict_target = None if missing_column == "entry_id" else conflict_target
                        logger.info(
                            "Supabase entries table missing column '%s'; retrying without it",
                            missing_column,
                        )
                        continue
                    if "on conflict" in lowered and "constraint" in lowered:
                        logger.info(
                            "Supabase entries table lacks conflict target '%s'; retrying without upsert",
                            current_conflict,
                        )
                        conflict_target = None
                        self._entries_conflict_target = None
                        continue
                raise
            else:
                self._entries_conflict_target = current_conflict
                break

    def _fetch_series_record(self, series_id: str) -> Dict[str, Any] | None:
        if not (self.supabase_url and self.supabase_key and self.supabase_series_table):
            return None

        endpoint = self._supabase_endpoint(self.supabase_series_table)
        headers = self._supabase_headers(include_content_profile=False)
        params = {
            "select": self._series_select_fields(),
            "id": f"eq.{series_id}",
            "limit": 1,
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            rows = response.json()

        if isinstance(rows, list) and rows:
            row = rows[0]
            return row if isinstance(row, dict) else None
        if isinstance(rows, dict):
            return rows
        return None

    def _fetch_series_races(self, series_id: str) -> List[Dict[str, Any]]:
        if not (self.supabase_url and self.supabase_key and self.supabase_races_table):
            return []

        endpoint = self._supabase_endpoint(self.supabase_races_table)
        headers = self._supabase_headers(include_content_profile=False)
        params = {
            "select": "id,start_time,payload,created_at",
            "series_id": f"eq.{series_id}",
            "order": "start_time.asc,created_at.asc",
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            rows = response.json()

        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        if isinstance(rows, dict):
            return [rows]
        return []

    @staticmethod
    def _series_settings_from_metadata(metadata: Dict[str, Any]) -> Tuple[Optional[int], Optional[bool]]:
        to_count: Optional[int] = None
        count_all: Optional[bool] = None

        candidates: List[Dict[str, Any]] = []
        if isinstance(metadata, dict):
            candidates.append(metadata)
            for key in ("settings", "seriesSettings", "scoring", "results"):
                nested = metadata.get(key)
                if isinstance(nested, dict):
                    candidates.append(nested)

        for candidate in candidates:
            if to_count is None:
                raw_count = candidate.get("toCount")
                if isinstance(raw_count, int):
                    to_count = raw_count
                elif isinstance(raw_count, str) and raw_count.strip().isdigit():
                    to_count = int(raw_count.strip())
            if count_all is None:
                raw_all = candidate.get("countAll")
                if isinstance(raw_all, bool):
                    count_all = raw_all
                elif isinstance(raw_all, str):
                    lowered = raw_all.strip().lower()
                    if lowered in {"true", "1", "yes", "y"}:
                        count_all = True
                    elif lowered in {"false", "0", "no", "n"}:
                        count_all = False

        return to_count, count_all

    def fetch_series_standings(self, series_id: str) -> Dict[str, Any]:
        if not (self.supabase_url and self.supabase_key):
            raise RuntimeError("Supabase is not configured")

        series_record = self._fetch_series_record(series_id)
        if not series_record:
            raise ValueError("Series not found")

        series_normalised = self._normalise_series_row(series_record)
        metadata = series_record.get("metadata") if isinstance(series_record.get("metadata"), dict) else {}
        to_count_override, count_all_override = self._series_settings_from_metadata(metadata)

        races = self._fetch_series_races(series_id)

        race_items: List[Dict[str, Any]] = []
        competitors: Dict[str, Dict[str, Any]] = {}

        for race in races:
            race_id = str(race.get("id") or "").strip()
            if not race_id:
                continue
            payload = race.get("payload")
            if not isinstance(payload, dict):
                continue
            response_payload = payload.get("response")
            if not isinstance(response_payload, dict):
                continue

            race_metadata = response_payload.get("metadata") if isinstance(response_payload.get("metadata"), dict) else {}
            race_label = str(race_metadata.get("race") or race_metadata.get("filename") or "").strip()
            race_items.append(
                {
                    "id": race_id,
                    "label": race_label or f"Race {len(race_items) + 1}",
                    "raceNumber": race_metadata.get("raceNumber"),
                    "date": race_metadata.get("date"),
                    "startTime": race_metadata.get("startTime"),
                }
            )

            py_rows = [row for row in response_payload.get("pyResults", []) if isinstance(row, dict)]
            personal_rows = [row for row in response_payload.get("personalResults", []) if isinstance(row, dict)]
            personal_by_entry = {
                str(row.get("entryId")): row for row in personal_rows if row.get("entryId")
            }

            entry_to_helm: Dict[str, str] = {}

            for index, row in enumerate(py_rows):
                entry_id = str(row.get("entryId") or "").strip()
                helm = str(row.get("helm") or "").strip()
                if not helm:
                    continue
                entry_to_helm[entry_id] = helm

                competitor = competitors.setdefault(
                    helm,
                    {
                        "helm": helm,
                        "boats": [],
                        "boats_set": set(),
                        "crews": [],
                        "crews_set": set(),
                        "py_scores": {},
                        "personal_scores": {},
                    },
                )

                dinghy = str(row.get("dinghy") or "").strip()
                if dinghy and dinghy not in competitor["boats_set"]:
                    competitor["boats_set"].add(dinghy)
                    competitor["boats"].append(dinghy)

                crew = str(row.get("crew") or "").strip()
                if crew:
                    crew_label = f"{crew} ({dinghy})" if dinghy else crew
                    if crew_label not in competitor["crews_set"]:
                        competitor["crews_set"].add(crew_label)
                        competitor["crews"].append(crew_label)

                rank_value = row.get("rank")
                if rank_value is None:
                    rank_value = index + 1
                competitor["py_scores"][race_id] = float(rank_value)

                personal_row = personal_by_entry.get(entry_id)
                if personal_row is not None:
                    personal_rank = personal_row.get("rank")
                    competitor["personal_scores"][race_id] = float(personal_rank) if personal_rank is not None else None

            for entry_id, personal_row in personal_by_entry.items():
                helm = entry_to_helm.get(entry_id)
                if not helm:
                    continue
                competitor = competitors.get(helm)
                if competitor is None:
                    continue
                if race_id not in competitor["personal_scores"]:
                    personal_rank = personal_row.get("rank")
                    competitor["personal_scores"][race_id] = float(personal_rank) if personal_rank is not None else None

        race_count = len(race_items)
        competitor_count = len(competitors)
        dnc_value = competitor_count + 1 if competitor_count else 1

        if to_count_override is not None and to_count_override >= 0:
            to_count = to_count_override
        elif race_count:
            to_count = math.ceil(race_count / 3) + 1
        else:
            to_count = 0

        if count_all_override:
            to_count = race_count

        if to_count > race_count:
            to_count = race_count
        if to_count < 0:
            to_count = 0

        def _build_scores(score_map: Dict[str, Optional[float]]) -> Dict[str, Any]:
            per_race: List[Dict[str, Any]] = []
            numeric_scores: List[Tuple[float, int]] = []

            for idx, race in enumerate(race_items):
                value = score_map.get(race["id"])
                if value is None:
                    numeric_value = float(dnc_value)
                    per_race.append({"value": None, "isDnc": True, "counted": False})
                else:
                    numeric_value = float(value)
                    per_race.append({"value": numeric_value, "isDnc": False, "counted": False})
                numeric_scores.append((numeric_value, idx))

            counting_slots = min(to_count, len(race_items))
            if counting_slots > 0:
                numeric_scores.sort(key=lambda item: item[0])
                counted_indexes = {idx for _, idx in numeric_scores[:counting_slots]}
                for idx in counted_indexes:
                    per_race[idx]["counted"] = True
                total = sum(score for score, _ in numeric_scores[:counting_slots])
            else:
                counted_indexes = set()
                total = None

            if to_count == 0:
                # Ensure counted flags are cleared when no races count
                for item in per_race:
                    item["counted"] = False

            return {
                "perRace": per_race,
                "total": total,
            }

        py_competitors: List[Dict[str, Any]] = []
        personal_competitors: List[Dict[str, Any]] = []

        for data in competitors.values():
            py_scores = _build_scores(data["py_scores"])
            competitor_entry = {
                "helm": data["helm"],
                "boats": data["boats"],
                "crews": data["crews"],
                "scores": py_scores,
            }
            py_competitors.append(competitor_entry)

            personal_scores = _build_scores(data["personal_scores"])
            personal_entry = {
                "helm": data["helm"],
                "boats": data["boats"],
                "crews": data["crews"],
                "scores": personal_scores,
            }
            personal_competitors.append(personal_entry)

        def _assign_ranks(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            sorted_items = sorted(
                items,
                key=lambda item: (
                    float("inf") if item["scores"]["total"] is None else item["scores"]["total"],
                    item["helm"].lower(),
                ),
            )
            for index, item in enumerate(sorted_items, start=1):
                item["rank"] = index if item["scores"]["total"] is not None else None
            return sorted_items

        py_competitors = _assign_ranks(py_competitors)
        personal_competitors = _assign_ranks(personal_competitors)

        return {
            "series": {
                "id": series_normalised.get("id"),
                "code": series_normalised.get("code"),
                "title": series_normalised.get("title"),
                "startDate": series_normalised.get("startDate"),
                "endDate": series_normalised.get("endDate"),
                "toCount": to_count,
                "countAll": bool(count_all_override),
                "raceCount": race_count,
                "competitorCount": competitor_count,
                "dncValue": dnc_value,
            },
            "races": race_items,
            "pyResults": py_competitors,
            "personalResults": personal_competitors,
        }

    # ------------------------------------------------------------------
    # Series entry & race sign-on helpers

    def create_series_entries(
        self,
        user: Dict[str, Any],
        entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not entries:
            return []

        user_id = str(user.get("id") or "").strip()
        if not user_id:
            raise ValueError("Authenticated user id is required")

        prepared: List[Dict[str, Any]] = []
        for raw in entries:
            prepared.append(self._prepare_series_entry_payload(raw))

        series_ids = {item["series_id"] for item in prepared}
        series_summaries = {series_id: self._series_summary(series_id) for series_id in series_ids}

        records: List[Dict[str, Any]]
        if self.supabase_url and self.supabase_key and self.supabase_series_entries_table:
            records = self._create_series_entries_supabase(user_id, prepared)
        else:
            records = self._create_series_entries_local(user_id, prepared)

        result: List[Dict[str, Any]] = []
        for record in records:
            series_id = str(record.get("series_id") or "")
            summary = series_summaries.get(series_id) or {"id": series_id}
            result.append(self._normalise_series_entry_record(record, summary))
        return result

    def create_race_signons(
        self,
        user: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        user_id = str(user.get("id") or "").strip()
        if not user_id:
            raise ValueError("Authenticated user id is required")

        series_id = str(payload.get("seriesId") or payload.get("series_id") or "").strip()
        if not series_id:
            raise ValueError("Series ID is required for sign-on")

        scheduled_ids_raw = payload.get("scheduledRaceIds") or payload.get("scheduled_race_ids") or []
        if not isinstance(scheduled_ids_raw, list) or not scheduled_ids_raw:
            raise ValueError("At least one scheduled race must be selected")
        scheduled_race_ids = [str(item).strip() for item in scheduled_ids_raw if str(item).strip()]
        if not scheduled_race_ids:
            raise ValueError("At least one scheduled race must be selected")

        helm_name = str(payload.get("helmName") or payload.get("helm_name") or "").strip()
        if not helm_name:
            raise ValueError("Helm name is required")

        helm_profile_id_raw = payload.get("helmProfileId") or payload.get("helm_profile_id")
        helm_profile_id = str(helm_profile_id_raw).strip() if helm_profile_id_raw else None

        crew_list = self._coerce_crew_payload(payload.get("crew"))

        boat_class_raw = payload.get("boatClass") or payload.get("boat_class")
        boat_class = str(boat_class_raw).strip() if isinstance(boat_class_raw, str) else None
        if boat_class == "":
            boat_class = None

        sail_number_raw = payload.get("sailNumber") or payload.get("sail_number")
        sail_number = str(sail_number_raw).strip() if isinstance(sail_number_raw, str) else None
        if sail_number == "":
            sail_number = None

        notes_raw = payload.get("notes")
        notes = str(notes_raw).strip() if isinstance(notes_raw, str) else None
        if notes == "":
            notes = None

        today = dt.date.today().isoformat()

        signon_date_raw = payload.get("signonDate") or payload.get("signon_date")
        if signon_date_raw:
            try:
                signon_date = dt.date.fromisoformat(str(signon_date_raw)[:10]).isoformat()
            except ValueError as exc:
                raise ValueError("Invalid sign-on date") from exc
            if signon_date != today:
                raise ValueError("Sign-on is only allowed on the race date")

        schedule_map = {race["id"]: race for race in self.fetch_scheduled_races(include_past=True)}

        missing_ids = [race_id for race_id in scheduled_race_ids if race_id not in schedule_map]
        if missing_ids:
            raise ValueError(f"Scheduled race not found: {missing_ids[0]}")

        series_summary = self._series_summary(series_id)
        series_code = str(series_summary.get("code") or "").upper()

        race_records: List[Dict[str, Any]] = []
        for race_id in scheduled_race_ids:
            race = schedule_map[race_id]
            race_date = str(race.get("date") or "")
            if race_date != today:
                raise ValueError("Sign-on is only allowed on the race date")

            race_code = str(race.get("seriesCode") or "").upper()
            if series_code:
                candidate_codes = {code for code in [race_code, self._series_code(str(race.get("series") or ""))] if code}
                if candidate_codes:
                    title_code = self._series_code(str(series_summary.get("title") or ""))
                    acceptable_codes = {series_code}
                    if title_code:
                        acceptable_codes.add(title_code)
                    if acceptable_codes.isdisjoint(candidate_codes):
                        raise ValueError("Selected races do not belong to the chosen series")

            race_number = race.get("raceNumber")
            if race_number is not None:
                try:
                    race_number = int(race_number)
                except (TypeError, ValueError):
                    race_number = None

            snapshot = {
                "label": race.get("race") or (f"Race {race_number}" if race_number else "Race"),
                "date": race_date,
                "startTime": race.get("startTime"),
                "raceNumber": race_number,
                "seriesCode": race.get("seriesCode"),
            }
            race_records.append({"id": race_id, "snapshot": snapshot})

        records_signon: List[Dict[str, Any]]
        if self.supabase_url and self.supabase_key and self.supabase_series_signons_table:
            records_signon = self._create_race_signons_supabase(
                user_id,
                series_id,
                helm_name,
                helm_profile_id,
                crew_list,
                boat_class,
                sail_number,
                notes,
                race_records,
            )
        else:
            records_signon = self._create_race_signons_local(
                user_id,
                series_id,
                helm_name,
                helm_profile_id,
                crew_list,
                boat_class,
                sail_number,
                notes,
                race_records,
            )

        schedule_summary_map = {race_id: schedule_map.get(race_id, {}) for race_id in scheduled_race_ids}

        result = []
        for record in records_signon:
            race_id = str(record.get("scheduled_race_id") or "")
            race_summary = schedule_summary_map.get(race_id) or {}
            result.append(self._normalise_signon_record(record, series_summary, race_summary))

        return result

    def _prepare_series_entry_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        series_id = str(payload.get("seriesId") or payload.get("series_id") or "").strip()
        if not series_id:
            raise ValueError("Series ID is required")

        helm_name = str(payload.get("helmName") or payload.get("helm_name") or "").strip()
        if not helm_name:
            raise ValueError("Helm name is required")

        helm_profile_raw = payload.get("helmProfileId") or payload.get("helm_profile_id")
        helm_profile_id = str(helm_profile_raw).strip() if helm_profile_raw else None

        crew = self._coerce_crew_payload(payload.get("crew"))

        boat_class_raw = payload.get("boatClass") or payload.get("boat_class")
        boat_class = str(boat_class_raw).strip() if isinstance(boat_class_raw, str) else None
        if boat_class == "":
            boat_class = None

        sail_number_raw = payload.get("sailNumber") or payload.get("sail_number")
        sail_number = str(sail_number_raw).strip() if isinstance(sail_number_raw, str) else None
        if sail_number == "":
            sail_number = None

        notes_raw = payload.get("notes")
        notes = str(notes_raw).strip() if isinstance(notes_raw, str) else None
        if notes == "":
            notes = None

        return {
            "series_id": series_id,
            "helm_name": helm_name,
            "helm_profile_id": helm_profile_id,
            "crew": crew,
            "boat_class": boat_class,
            "sail_number": sail_number,
            "notes": notes,
        }

    def _coerce_crew_payload(self, raw: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        crew: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            profile_raw = item.get("profileId") or item.get("profile_id")
            profile_id = str(profile_raw).strip() if profile_raw else None
            crew.append({"profileId": profile_id, "name": name})
        return crew

    def _create_series_entries_supabase(
        self,
        user_id: str,
        entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        endpoint = self._supabase_endpoint(self.supabase_series_entries_table)
        headers = self._supabase_headers("return=representation")
        headers["Content-Type"] = "application/json"

        now_iso = self._utc_now_iso()
        payload = []
        for item in entries:
            payload.append(
                {
                    "id": str(uuid.uuid4()),
                    "series_id": item["series_id"],
                    "submitted_by": user_id,
                    "helm_profile_id": item["helm_profile_id"],
                    "helm_name": item["helm_name"],
                    "crew_json": item["crew"],
                    "boat_class": item["boat_class"],
                    "sail_number": item["sail_number"],
                    "notes": item["notes"],
                    "created_at": now_iso,
                }
            )

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(endpoint, params={"select": "*"}, json=payload, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else None
            if status_code == 404:
                logger.warning(
                    "Supabase series entries table missing (HTTP 404). Using local fallback for create_series_entries",
                )
                return self._create_series_entries_local(user_id, entries)
            if status_code is not None and 400 <= status_code < 500:
                detail = self._extract_supabase_detail(exc.response)
                raise ValueError(detail or "Supabase rejected series entry create") from exc
            logger.warning("Supabase create_series_entries failed (%s); using local fallback", exc)
            return self._create_series_entries_local(user_id, entries)
        except httpx.RequestError as exc:
            logger.warning("Supabase create_series_entries unavailable (%s); using local fallback", exc)
            return self._create_series_entries_local(user_id, entries)

        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        if isinstance(rows, dict):
            return [rows]
        return []

    def _create_series_entries_local(
        self,
        user_id: str,
        entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        data = self._read_json_file(self.local_series_entries_path, [])
        if not isinstance(data, list):
            data = []
        now_iso = self._utc_now_iso()
        created: List[Dict[str, Any]] = []
        for item in entries:
            record = {
                "id": str(uuid.uuid4()),
                "series_id": item["series_id"],
                "submitted_by": user_id,
                "helm_profile_id": item["helm_profile_id"],
                "helm_name": item["helm_name"],
                "crew_json": item["crew"],
                "boat_class": item["boat_class"],
                "sail_number": item["sail_number"],
                "notes": item["notes"],
                "created_at": now_iso,
            }
            data.append(record)
            created.append(record)
        self._write_json_file(self.local_series_entries_path, data)
        return created

    def _create_race_signons_supabase(
        self,
        user_id: str,
        series_id: str,
        helm_name: str,
        helm_profile_id: str | None,
        crew: List[Dict[str, Any]],
        boat_class: str | None,
        sail_number: str | None,
        notes: str | None,
        race_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        endpoint = self._supabase_endpoint(self.supabase_series_signons_table)
        headers = self._supabase_headers("return=representation")
        headers["Content-Type"] = "application/json"

        now_iso = self._utc_now_iso()
        payload = []
        for race in race_records:
            payload.append(
                {
                    "id": str(uuid.uuid4()),
                    "series_id": series_id,
                    "scheduled_race_id": race["id"],
                    "submitted_by": user_id,
                    "helm_profile_id": helm_profile_id,
                    "helm_name": helm_name,
                    "crew_json": crew,
                    "boat_class": boat_class,
                    "sail_number": sail_number,
                    "notes": notes,
                    "race_snapshot": race.get("snapshot"),
                    "created_at": now_iso,
                }
            )

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(endpoint, params={"select": "*"}, json=payload, headers=headers)
                response.raise_for_status()
                rows = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else None
            if status_code == 404:
                logger.warning(
                    "Supabase series sign-ons table missing (HTTP 404). Using local fallback for create_race_signons",
                )
                return self._create_race_signons_local(
                    user_id,
                    series_id,
                    helm_name,
                    helm_profile_id,
                    crew,
                    boat_class,
                    sail_number,
                    notes,
                    race_records,
                )
            if status_code is not None and 400 <= status_code < 500:
                detail = self._extract_supabase_detail(exc.response)
                raise ValueError(detail or "Supabase rejected race sign-on create") from exc
            logger.warning("Supabase create_race_signons failed (%s); using local fallback", exc)
            return self._create_race_signons_local(
                user_id,
                series_id,
                helm_name,
                helm_profile_id,
                crew,
                boat_class,
                sail_number,
                notes,
                race_records,
            )
        except httpx.RequestError as exc:
            logger.warning("Supabase create_race_signons unavailable (%s); using local fallback", exc)
            return self._create_race_signons_local(
                user_id,
                series_id,
                helm_name,
                helm_profile_id,
                crew,
                boat_class,
                sail_number,
                notes,
                race_records,
            )

        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        if isinstance(rows, dict):
            return [rows]
        return []

    def _create_race_signons_local(
        self,
        user_id: str,
        series_id: str,
        helm_name: str,
        helm_profile_id: str | None,
        crew: List[Dict[str, Any]],
        boat_class: str | None,
        sail_number: str | None,
        notes: str | None,
        race_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        data = self._read_json_file(self.local_series_signons_path, [])
        if not isinstance(data, list):
            data = []
        now_iso = self._utc_now_iso()
        created: List[Dict[str, Any]] = []
        for race in race_records:
            record = {
                "id": str(uuid.uuid4()),
                "series_id": series_id,
                "scheduled_race_id": race["id"],
                "submitted_by": user_id,
                "helm_profile_id": helm_profile_id,
                "helm_name": helm_name,
                "crew_json": crew,
                "boat_class": boat_class,
                "sail_number": sail_number,
                "notes": notes,
                "race_snapshot": race.get("snapshot"),
                "created_at": now_iso,
            }
            data.append(record)
            created.append(record)
        self._write_json_file(self.local_series_signons_path, data)
        return created

    def _series_summary(self, series_id: str) -> Dict[str, Any]:
        if not series_id:
            return {"id": ""}

        record = self._fetch_series_record(series_id)
        if record:
            return self._normalise_series_row(record)

        local_data = self._read_json_file(self.local_series_path, [])
        if isinstance(local_data, list):
            for row in local_data:
                if isinstance(row, dict) and str(row.get("id")) == series_id:
                    return self._normalise_series_row(row)

        return {"id": series_id, "code": "", "title": "", "startDate": None, "endDate": None}

    def _normalise_crew_list(self, raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = []
        if not isinstance(raw, list):
            return []
        crew: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            profile_raw = item.get("profileId") or item.get("profile_id")
            profile_id = str(profile_raw).strip() if profile_raw else None
            crew.append({"profileId": profile_id, "name": name})
        return crew

    def _normalise_series_entry_record(
        self,
        record: Dict[str, Any],
        series_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        crew = self._normalise_crew_list(record.get("crew_json") or record.get("crew"))
        return {
            "id": str(record.get("id")),
            "series": series_summary,
            "helmName": record.get("helm_name") or "",
            "helmProfileId": record.get("helm_profile_id"),
            "crew": crew,
            "boatClass": record.get("boat_class"),
            "sailNumber": record.get("sail_number"),
            "notes": record.get("notes"),
            "submittedBy": record.get("submitted_by"),
            "createdAt": record.get("created_at") or "",
        }

    def _normalise_signon_record(
        self,
        record: Dict[str, Any],
        series_summary: Dict[str, Any],
        race_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        crew = self._normalise_crew_list(record.get("crew_json") or record.get("crew"))

        race_snapshot = record.get("race_snapshot")
        if isinstance(race_snapshot, str):
            try:
                race_snapshot = json.loads(race_snapshot)
            except json.JSONDecodeError:
                race_snapshot = {}
        if not isinstance(race_snapshot, dict):
            race_snapshot = {}

        label = race_snapshot.get("label") or race_summary.get("race") or race_summary.get("label") or ""
        date_value = race_snapshot.get("date") or race_summary.get("date") or ""
        start_time = race_snapshot.get("startTime") or race_summary.get("startTime")
        race_number = race_snapshot.get("raceNumber") or race_summary.get("raceNumber")
        try:
            race_number = int(race_number) if race_number is not None else None
        except (TypeError, ValueError):
            race_number = None

        race_details = {
            "id": str(record.get("scheduled_race_id") or race_summary.get("id") or ""),
            "label": label,
            "date": date_value,
            "startTime": start_time,
            "raceNumber": race_number,
        }

        return {
            "id": str(record.get("id")),
            "series": series_summary,
            "race": race_details,
            "helmName": record.get("helm_name") or "",
            "helmProfileId": record.get("helm_profile_id"),
            "crew": crew,
            "boatClass": record.get("boat_class"),
            "sailNumber": record.get("sail_number"),
            "notes": record.get("notes"),
            "submittedBy": record.get("submitted_by"),
            "createdAt": record.get("created_at") or "",
        }

    def _series_code(self, series: str) -> str:
        canonical = re.sub(r"[^A-Z0-9]+", "", series.upper()) if series else ""
        return canonical[:12] if canonical else ""

    def _series_record_for_create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("Series title is required")

        code_value = str(payload.get("code") or title)
        code = self._series_code(code_value)
        if not code:
            raise ValueError("Series code is required")

        start_date_str = self._coerce_date(payload.get("startDate") or payload.get("start_date"))
        end_date_str = self._coerce_date(payload.get("endDate") or payload.get("end_date"))

        metadata = {
            "code": code,
            "title": title,
            "startDate": start_date_str,
            "endDate": end_date_str,
        }

        record: Dict[str, Any] = {
            "code": code,
            "title": title,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "metadata": metadata,
        }

        return record

    def _series_record_for_update(
        self,
        payload: Dict[str, Any],
        existing: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        record: Dict[str, Any] = {}
        metadata = {
            "code": existing.get("code"),
            "title": existing.get("title"),
            "startDate": existing.get("startDate"),
            "endDate": existing.get("endDate"),
        }

        if "title" in payload:
            title_value = str(payload.get("title") or "").strip()
            if not title_value:
                raise ValueError("Series title cannot be empty")
            record["title"] = title_value
            metadata["title"] = title_value

        if "startDate" in payload or "start_date" in payload:
            start_date_str = self._coerce_date(payload.get("startDate") or payload.get("start_date"))
            record["start_date"] = start_date_str
            metadata["startDate"] = start_date_str

        if "endDate" in payload or "end_date" in payload:
            end_date_str = self._coerce_date(payload.get("endDate") or payload.get("end_date"))
            record["end_date"] = end_date_str
            metadata["endDate"] = end_date_str

        if not record:
            return None

        record["metadata"] = metadata
        return record

    def _coerce_date(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, dt.date):
            return value.isoformat()
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return dt.date.fromisoformat(stripped[:10]).isoformat()
            except ValueError as exc:
                raise ValueError("Invalid date value") from exc
        raise ValueError("Invalid date value")

    def _normalise_series_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        code = metadata.get("code") or row.get("code") or ""
        title = metadata.get("title") or row.get("title") or ""

        start_raw = (
            metadata.get("startDate")
            or metadata.get("start_date")
            or row.get("start_date")
        )
        if isinstance(start_raw, dt.date):
            start_date = start_raw.isoformat()
        elif isinstance(start_raw, str) and start_raw:
            start_date = start_raw[:10]
        else:
            start_date = None

        end_raw = metadata.get("endDate") or metadata.get("end_date") or row.get("end_date")
        if isinstance(end_raw, dt.date):
            end_date = end_raw.isoformat()
        elif isinstance(end_raw, str) and end_raw:
            end_date = end_raw[:10]
        else:
            end_date = None

        return {
            "id": str(row.get("id")),
            "code": code,
            "title": title,
            "startDate": start_date,
            "endDate": end_date,
        }

    def _schedule_record_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        series = str(payload.get("series") or "").strip()
        race = str(payload.get("race") or "").strip()
        race_officer = str(payload.get("raceOfficer") or payload.get("race_officer") or "").strip()
        notes = str(payload.get("notes") or "").strip()

        race_number_raw = payload.get("raceNumber") or payload.get("race_number")
        try:
            race_number = int(race_number_raw) if race_number_raw is not None else None
        except (TypeError, ValueError):
            race_number = None

        date_value = payload.get("date")
        if isinstance(date_value, dt.date):
            date_str = date_value.isoformat()
        elif isinstance(date_value, str):
            date_str = date_value[:10]
        else:
            raise ValueError("Scheduled race requires a date value")

        start_time_value = payload.get("startTime") or payload.get("start_time")
        if isinstance(start_time_value, dt.datetime):
            start_time_str = start_time_value.isoformat()
        elif isinstance(start_time_value, dt.time):
            start_time_str = start_time_value.isoformat()
        elif isinstance(start_time_value, str) and start_time_value:
            start_time_str = start_time_value
        else:
            start_time_str = None

        if start_time_str and date_str and "T" not in start_time_str:
            start_time_str = f"{date_str}T{start_time_str}"

        metadata = {
            "series": series,
            "race": race,
            "raceNumber": race_number,
            "raceOfficer": race_officer or None,
            "date": date_str,
            "startTime": start_time_str,
            "notes": notes or None,
        }

        record = {
            "series_code": self._series_code(series),
            "date": date_str,
            "start_time": start_time_str,
            "race_number": race_number,
            "race_officer": race_officer or None,
            "metadata": metadata,
            "notes": notes or None,
        }
        return record

    def _normalise_schedule_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        series = metadata.get("series") or row.get("series") or row.get("series_title") or ""
        race = metadata.get("race") or row.get("race") or row.get("race_label") or ""

        race_officer = metadata.get("raceOfficer") or metadata.get("race_officer") or row.get("race_officer")

        date_value = metadata.get("date") or row.get("date")
        if isinstance(date_value, dt.date):
            date_str = date_value.isoformat()
        elif isinstance(date_value, str):
            date_str = date_value[:10]
        else:
            date_str = ""

        start_time_value = metadata.get("startTime") or metadata.get("start_time") or row.get("start_time")
        if isinstance(start_time_value, dt.datetime):
            start_time_str = start_time_value.isoformat()
        elif isinstance(start_time_value, dt.time):
            time_part = start_time_value.isoformat()
            start_time_str = f"{date_str}T{time_part}" if date_str and "T" not in time_part else time_part
        elif isinstance(start_time_value, str) and start_time_value:
            start_time_str = (
                f"{date_str}T{start_time_value}" if date_str and "T" not in start_time_value else start_time_value
            )
        else:
            start_time_str = None

        race_number_raw = metadata.get("raceNumber") or metadata.get("race_number") or row.get("race_number")
        try:
            race_number = int(race_number_raw) if race_number_raw is not None else None
        except (TypeError, ValueError):
            race_number = None

        notes_value = metadata.get("notes") or row.get("notes")
        notes = notes_value.strip() if isinstance(notes_value, str) else None

        return {
            "id": str(row.get("id")),
            "series": series,
            "race": race,
            "seriesCode": row.get("series_code") or metadata.get("seriesCode"),
            "raceNumber": race_number,
            "raceOfficer": race_officer or None,
            "date": date_str,
            "startTime": start_time_str,
            "notes": notes,
        }

    def _read_json_file(self, path: Path, default: Any) -> Any:
        try:
            if not path.exists():
                return default
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Falling back to default for %s due to read error: %s", path, exc)
            return default

    def _write_json_file(self, path: Path, data: Any) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
        except OSError as exc:
            raise RuntimeError(f"Failed to write local data store {path}") from exc

    @staticmethod
    def _utc_now_iso() -> str:
        return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _series_select_fields(self) -> str:
        fields = ["id", "code", "title", "start_date", "end_date"]
        if self._series_supports_metadata:
            fields.append("metadata")
        return ",".join(fields)

    def _prepare_series_payload(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if self._series_supports_metadata or "metadata" not in record:
            return record
        filtered = dict(record)
        filtered.pop("metadata", None)
        return filtered

    def _handle_series_metadata_error(self, response: httpx.Response | None) -> bool:
        if not self._series_supports_metadata:
            return False
        detail = self._extract_supabase_detail(response)
        if not detail:
            return False
        message = detail.lower()
        if "metadata" in message and "column" in message:
            self._series_supports_metadata = False
            logger.warning(
                "Supabase 'metadata' column missing for series table; disabling metadata payloads"
            )
            return True
        return False

    def _load_local_series(self) -> List[Dict[str, Any]]:
        data = self._read_json_file(self.local_series_path, [])
        return [self._normalise_series_row(row) for row in data if isinstance(row, dict)]

    def _create_series_local(self, record: Dict[str, Any]) -> Dict[str, Any]:
        data = self._read_json_file(self.local_series_path, [])
        for row in data:
            if not isinstance(row, dict):
                continue
            code_value = row.get("code") or row.get("metadata", {}).get("code")
            if code_value == record["code"]:
                raise ValueError("Series code already exists")

        entry = {"id": str(uuid.uuid4()), **record}
        data.append(entry)
        self._write_json_file(self.local_series_path, data)
        return self._normalise_series_row(entry)

    def _update_series_local(
        self,
        series_id: str,
        payload: Dict[str, Any],
        existing_series: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        data = self._read_json_file(self.local_series_path, [])
        target_index = None
        for index, row in enumerate(data):
            if isinstance(row, dict) and str(row.get("id")) == str(series_id):
                target_index = index
                break

        if target_index is None:
            if existing_series is None:
                raise ValueError("Series not found")
            entry = {
                "id": str(series_id),
                "code": existing_series.get("code"),
                "title": existing_series.get("title"),
                "start_date": existing_series.get("startDate"),
                "end_date": existing_series.get("endDate"),
                "metadata": {
                    "code": existing_series.get("code"),
                    "title": existing_series.get("title"),
                    "startDate": existing_series.get("startDate"),
                    "endDate": existing_series.get("endDate"),
                },
            }
            data.append(entry)
            target_index = len(data) - 1

        row = data[target_index]
        if not isinstance(row, dict):
            row = {}

        existing = self._normalise_series_row(row)
        record = self._series_record_for_update(payload, existing)
        if record is None:
            return existing

        updated_row = {**row}
        if "title" in record:
            updated_row["title"] = record["title"]
        if "start_date" in record:
            updated_row["start_date"] = record["start_date"]
        if "end_date" in record:
            updated_row["end_date"] = record["end_date"]
        if "metadata" in record:
            updated_row["metadata"] = record["metadata"]

        data[target_index] = updated_row
        self._write_json_file(self.local_series_path, data)
        return self._normalise_series_row(updated_row)

    def _load_local_schedule(self, include_past: bool) -> List[Dict[str, Any]]:
        data = self._read_json_file(self.local_schedule_path, [])
        rows = [self._normalise_schedule_row(row) for row in data if isinstance(row, dict)]
        if include_past:
            return rows

        today = dt.date.today().isoformat()
        return [row for row in rows if row.get("date") and str(row.get("date")) >= today]

    def _create_scheduled_race_local(self, record: Dict[str, Any]) -> Dict[str, Any]:
        data = self._read_json_file(self.local_schedule_path, [])
        entry = {"id": str(uuid.uuid4()), **record}
        data.append(entry)
        try:
            data.sort(key=lambda row: (
                row.get("date") or "",
                row.get("start_time") or "",
                str(row.get("id")),
            ))
        except Exception:  # pragma: no cover - sorting guard
            pass
        self._write_json_file(self.local_schedule_path, data)
        return self._normalise_schedule_row(entry)

    # ------------------------------------------------------------------
    # Local backlog synchronisation helpers

    def sync_local_backlog(self) -> Dict[str, Any]:
        """Push locally cached series and scheduled races to Supabase."""

        if not (self.supabase_url and self.supabase_key):
            raise RuntimeError("Supabase configuration is required to sync local backlog")

        summary = {
            "series": {"synced": 0, "remaining": 0, "errors": []},
            "schedule": {"synced": 0, "remaining": 0, "errors": []},
        }

        if self.supabase_series_table:
            summary["series"] = self._sync_series_backlog()
        elif self.local_series_path.exists():
            data = self._read_json_file(self.local_series_path, [])
            remaining = sum(1 for row in data if isinstance(row, dict))
            summary["series"]["remaining"] = remaining
            summary["series"]["errors"].append("Supabase series table is not configured")

        if self.supabase_schedule_table:
            summary["schedule"] = self._sync_schedule_backlog()
        elif self.local_schedule_path.exists():
            data = self._read_json_file(self.local_schedule_path, [])
            remaining = sum(1 for row in data if isinstance(row, dict))
            summary["schedule"]["remaining"] = remaining
            summary["schedule"]["errors"].append("Supabase scheduled races table is not configured")

        return summary

    def _sync_series_backlog(self) -> Dict[str, Any]:
        result = {"synced": 0, "remaining": 0, "errors": []}
        data = self._read_json_file(self.local_series_path, [])

        if not data:
            self._remove_local_file(self.local_series_path)
            return result

        rows: List[Dict[str, Any]] = []
        remaining: List[Any] = []

        for row in data:
            if isinstance(row, dict):
                rows.append(row)
            else:
                remaining.append(row)
                result["errors"].append("Skipping non-dict entry in series backlog")

        if not rows and not remaining:
            self._remove_local_file(self.local_series_path)
            return result

        if not rows:
            self._write_json_file(self.local_series_path, remaining)
            result["remaining"] = len(remaining)
            return result

        with httpx.Client(timeout=10.0) as client:
            for row in rows:
                try:
                    record = self._series_record_from_local(row)
                except ValueError as exc:
                    remaining.append(row)
                    result["errors"].append(str(exc))
                    continue

                try:
                    self._upsert_series_remote(client, record)
                except httpx.HTTPStatusError as exc:
                    detail = self._extract_supabase_detail(exc.response)
                    remaining.append(row)
                    result["errors"].append(detail or f"Supabase rejected series sync: {exc}")
                except httpx.HTTPError as exc:
                    remaining.append(row)
                    result["errors"].append(f"Series sync request failed: {exc}")
                else:
                    result["synced"] += 1

        if remaining:
            self._write_json_file(self.local_series_path, remaining)
            result["remaining"] = len(remaining)
        else:
            self._remove_local_file(self.local_series_path)

        return result

    def _series_record_from_local(self, row: Dict[str, Any]) -> Dict[str, Any]:
        code = row.get("code") or row.get("metadata", {}).get("code")
        if not code:
            raise ValueError("Series sync skipped: missing code")

        title = row.get("title") or row.get("metadata", {}).get("title")
        if not title:
            raise ValueError(f"Series sync skipped for {code}: missing title")

        metadata_raw = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}

        start_date = row.get("start_date") or metadata_raw.get("startDate")
        end_date = row.get("end_date") or metadata_raw.get("endDate")

        metadata = {
            "code": metadata_raw.get("code") or code,
            "title": metadata_raw.get("title") or title,
            "startDate": metadata_raw.get("startDate") or start_date,
            "endDate": metadata_raw.get("endDate") or end_date,
        }

        record: Dict[str, Any] = {
            "code": code,
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "metadata": metadata,
        }

        if row.get("id"):
            record["id"] = str(row["id"])

        return record

    def _upsert_series_remote(self, client: httpx.Client, record: Dict[str, Any]) -> None:
        endpoint = self._supabase_endpoint(self.supabase_series_table)
        headers = self._supabase_headers("resolution=merge-duplicates,return=representation")
        headers["Content-Type"] = "application/json"
        params = {"on_conflict": "code"}

        while True:
            payload_for_supabase = self._prepare_series_payload(record)
            try:
                response = client.post(endpoint, params=params, json=[payload_for_supabase], headers=headers)
                if response.status_code == 409:  # Already exists with same data
                    return
                response.raise_for_status()
                return
            except httpx.HTTPStatusError as exc:
                if self._handle_series_metadata_error(exc.response):
                    continue
                raise

    def _sync_schedule_backlog(self) -> Dict[str, Any]:
        result = {"synced": 0, "remaining": 0, "errors": []}
        data = self._read_json_file(self.local_schedule_path, [])

        if not data:
            self._remove_local_file(self.local_schedule_path)
            return result

        rows: List[Dict[str, Any]] = []
        remaining: List[Any] = []

        for row in data:
            if isinstance(row, dict):
                rows.append(row)
            else:
                remaining.append(row)
                result["errors"].append("Skipping non-dict entry in schedule backlog")

        if not rows and not remaining:
            self._remove_local_file(self.local_schedule_path)
            return result

        if not rows:
            self._write_json_file(self.local_schedule_path, remaining)
            result["remaining"] = len(remaining)
            return result

        with httpx.Client(timeout=10.0) as client:
            for row in rows:
                try:
                    record = self._schedule_record_from_local(row)
                except ValueError as exc:
                    remaining.append(row)
                    result["errors"].append(str(exc))
                    continue

                try:
                    self._upsert_schedule_remote(client, record)
                except httpx.HTTPStatusError as exc:
                    detail = self._extract_supabase_detail(exc.response)
                    remaining.append(row)
                    result["errors"].append(detail or f"Supabase rejected schedule sync: {exc}")
                except httpx.HTTPError as exc:
                    remaining.append(row)
                    result["errors"].append(f"Schedule sync request failed: {exc}")
                else:
                    result["synced"] += 1

        if remaining:
            self._write_json_file(self.local_schedule_path, remaining)
            result["remaining"] = len(remaining)
        else:
            self._remove_local_file(self.local_schedule_path)

        return result

    def _schedule_record_from_local(self, row: Dict[str, Any]) -> Dict[str, Any]:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}

        series_code = row.get("series_code") or metadata.get("seriesCode") or self._series_code(metadata.get("series"))
        if not series_code:
            raise ValueError("Scheduled race sync skipped: missing series code")

        date_value = row.get("date") or metadata.get("date")
        if not date_value:
            raise ValueError(f"Scheduled race sync skipped for {series_code}: missing date")

        start_time_value = row.get("start_time") or metadata.get("startTime")

        record: Dict[str, Any] = {
            "series_code": series_code,
            "date": date_value,
            "start_time": start_time_value,
            "race_number": row.get("race_number") or metadata.get("raceNumber"),
            "race_officer": row.get("race_officer") or metadata.get("raceOfficer"),
            "notes": row.get("notes") or metadata.get("notes"),
            "metadata": {
                "series": metadata.get("series"),
                "race": metadata.get("race"),
                "raceNumber": metadata.get("raceNumber"),
                "raceOfficer": metadata.get("raceOfficer"),
                "date": date_value,
                "startTime": start_time_value,
                "notes": metadata.get("notes"),
            },
        }

        record_id = row.get("id") or metadata.get("id")
        if record_id:
            record["id"] = str(record_id)
        else:
            generated = str(uuid.uuid4())
            record["id"] = generated

        return record

    def _upsert_schedule_remote(self, client: httpx.Client, record: Dict[str, Any]) -> None:
        endpoint = self._supabase_endpoint(self.supabase_schedule_table)
        headers = self._supabase_headers("resolution=merge-duplicates,return=representation")
        headers["Content-Type"] = "application/json"
        params = {"on_conflict": "id"}

        response = client.post(endpoint, params=params, json=[record], headers=headers)
        if response.status_code == 409:
            return
        response.raise_for_status()

    def _remove_local_file(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:  # pragma: no cover - unlikely but logged for diagnosis
            logger.warning("Failed to remove local data store %s: %s", path, exc)

    def _extract_supabase_detail(self, response: httpx.Response | None) -> str | None:
        if response is None:
            return None
        try:
            payload = response.json()
        except ValueError:
            text = (response.text or "").strip()
            return text or None

        if isinstance(payload, dict):
            for key in ("message", "detail", "error", "hint", "code"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict):
                for key in ("message", "detail", "error", "hint", "code"):
                    value = first.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return None

    @staticmethod
    def _extract_missing_column_name(detail: str) -> str | None:
        patterns = [
            r"could not find the '([^']+)' column",
            r"column\s+([\w\.]+)\s+does not exist",
        ]
        for pattern in patterns:
            match = re.search(pattern, detail, flags=re.IGNORECASE)
            if match:
                column = match.group(1)
                if column:
                    return column.split(".")[-1]
        return None
