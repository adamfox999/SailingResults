import os

os.environ.setdefault("SUPABASE_URL", "https://fazawdwokaahuslisksn.supabase.co")
os.environ.setdefault(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhemF3ZHdva2FhaHVzbGlza3NuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTk0OTI4MjcsImV4cCI6MjA3NTA2ODgyN30.BFcrU9g4_8RaerZG-JwnA7uA1fyneQjYya3RWWJJa28",
)

from app.main import ScoreRequest, score

payload = ScoreRequest(
    metadata={
        "series": "Test",
        "race": "Race 1",
        "date": "2025-10-04",
        "raceOfficer": "RO",
    },
    entries=[
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
)

result = score(payload)
print(result)
