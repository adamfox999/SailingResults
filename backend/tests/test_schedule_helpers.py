from swsc_core.loader import DataStore


def test_schedule_record_from_payload_creates_consistent_iso_values():
    store = DataStore()
    payload = {
        "series": "Autumn Series",
        "race": "Race 1",
        "raceNumber": 3,
        "date": "2025-10-04",
        "startTime": "09:30",
        "raceOfficer": "Jane Doe",
        "notes": "Practice start",
    }

    record = store._schedule_record_from_payload(payload)

    assert record["series_code"] == "AUTUMNSERIES"
    assert record["date"] == "2025-10-04"
    assert record["start_time"] == "2025-10-04T09:30"
    assert record["race_number"] == 3
    assert record["race_officer"] == "Jane Doe"
    assert record["notes"] == "Practice start"
    assert record["metadata"]["startTime"] == "2025-10-04T09:30"


def test_normalise_schedule_row_handles_missing_fields():
    store = DataStore()
    row = {
        "id": "abc-123",
        "series_code": "SPRING",
        "metadata": {
            "series": "Spring Sprint",
            "race": "Race 2",
            "raceNumber": 2,
            "raceOfficer": "Alex",
            "date": "2025-03-16",
            "startTime": "2025-03-16T11:15",
            "notes": "Includes rescue boat drill",
        },
    }

    normalised = store._normalise_schedule_row(row)

    assert normalised["id"] == "abc-123"
    assert normalised["series"] == "Spring Sprint"
    assert normalised["race"] == "Race 2"
    assert normalised["raceNumber"] == 2
    assert normalised["raceOfficer"] == "Alex"
    assert normalised["date"] == "2025-03-16"
    assert normalised["startTime"] == "2025-03-16T11:15"
    assert normalised["notes"] == "Includes rescue boat drill"
