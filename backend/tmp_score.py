import json

import httpx

PAYLOAD = {
    "metadata": {
        "series": "Test",
        "race": "Race 1",
        "date": "2025-10-04",
        "raceOfficer": "RO",
    },
    "entries": [
        {
            "entryId": None,
            "helm": "Alice",
            "crew": "Bob",
            "dinghy": "DART 15 / SPRINT 15",
            "personal": 0,
            "laps": 2,
            "timeSeconds": 3600,
            "finCode": None,
        }
    ],
}

response = httpx.post("http://127.0.0.1:8000/score", json=PAYLOAD)
print(response.status_code)
print(json.dumps(response.json(), indent=2))
