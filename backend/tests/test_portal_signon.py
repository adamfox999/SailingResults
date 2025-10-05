from __future__ import annotations

import datetime as dt
from typing import Dict

import pytest

from swsc_core import DataStore


@pytest.fixture
def store(tmp_path) -> DataStore:
    return DataStore(data_dir=tmp_path)


def _create_series(store: DataStore, title: str, code: str) -> Dict[str, str]:
    return store.create_series({
        "title": title,
        "code": code,
        "startDate": dt.date.today().isoformat(),
    })


def _schedule_race(store: DataStore, series_title: str, race_label: str, date_value: str, start_time: str) -> Dict[str, str]:
    return store.create_scheduled_race({
        "series": series_title,
        "race": race_label,
        "date": date_value,
        "startTime": start_time,
    })


def test_create_series_entries_local(store: DataStore) -> None:
    series = _create_series(store, "Spring Cup", "SCUP")
    user = {"id": "user-123"}

    entries = store.create_series_entries(user, [{
        "seriesId": series["id"],
        "helmName": "Alice",
        "crew": [{"name": "Bob"}, {"name": "Charlie"}],
        "boatClass": "RS200",
        "sailNumber": "123",
    }])

    assert len(entries) == 1
    created = entries[0]
    assert created["series"]["id"] == series["id"]
    assert created["series"]["code"].upper() == "SCUP"
    assert created["helmName"] == "Alice"
    crew_names = {member["name"] for member in created["crew"]}
    assert crew_names == {"Bob", "Charlie"}
    assert created["boatClass"] == "RS200"
    assert created["submittedBy"] == "user-123"


def test_create_race_signons_today_only(store: DataStore) -> None:
    series = _create_series(store, "Autumn Cup", "ACUP")
    today = dt.date.today()
    tomorrow = today + dt.timedelta(days=1)

    race_today = _schedule_race(store, series["title"], "Race 1", today.isoformat(), "10:00")
    race_tomorrow = _schedule_race(store, series["title"], "Race 2", tomorrow.isoformat(), "11:00")

    user = {"id": "user-456"}

    signons = store.create_race_signons(user, {
        "seriesId": series["id"],
        "scheduledRaceIds": [race_today["id"]],
        "helmName": "Dana",
        "crew": [{"name": "Eli"}],
        "boatClass": "LASER",
    })

    assert len(signons) == 1
    created = signons[0]
    assert created["series"]["id"] == series["id"]
    assert created["race"]["id"] == race_today["id"]
    assert created["race"]["date"] == today.isoformat()
    assert created["crew"][0]["name"] == "Eli"

    with pytest.raises(ValueError, match="Sign-on is only allowed on the race date"):
        store.create_race_signons(user, {
            "seriesId": series["id"],
            "scheduledRaceIds": [race_tomorrow["id"]],
            "helmName": "Dana",
        })


def test_create_race_signons_validates_series_match(store: DataStore) -> None:
    autumn = _create_series(store, "Autumn Cup", "AUTUMN")
    spring = _create_series(store, "Spring Cup", "SPRING")
    today = dt.date.today().isoformat()

    race = _schedule_race(store, autumn["title"], "Race 1", today, "09:30")

    user = {"id": "user-789"}

    with pytest.raises(ValueError, match="Selected races do not belong to the chosen series"):
        store.create_race_signons(user, {
            "seriesId": spring["id"],
            "scheduledRaceIds": [race["id"]],
            "helmName": "Frank",
        })
