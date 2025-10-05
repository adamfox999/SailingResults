from swsc_core import Entry, Race


def test_score_assigns_places_and_html() -> None:
    entries = [
        Entry(
            entry_id="TEST001",
            helm="Alice",
            crew="Bob",
            dinghy="DART 15 / SPRINT 15",
            py=924,
            laps=4,
            time_seconds=3600,
            personal=0,
            sail_number="1234",
        ),
        Entry(
            entry_id="TEST002",
            helm="Cara",
            crew="",
            dinghy="DART 15 / SPRINT 15",
            py=924,
            laps=4,
            time_seconds=3720,
            personal=0,
            sail_number="5678",
        ),
        Entry(
            entry_id="TEST003",
            helm="Eve",
            crew="",
            dinghy="DART 15 / SPRINT 15",
            py=924,
            laps=4,
            time_seconds=3800,
            fin_code="DNF",
            sail_number="9999",
        ),
    ]

    race = Race(entries=entries)
    results = race.score()

    py_ranks = [row.rank for row in results.py_rows]
    assert py_ranks[:2] == [1.0, 2.0]
    assert results.py_rows[2].fin_code == "DNF"
    assert "<html" in results.html
    assert "TEST001" in results.summary_text
    assert "Entry ID" in results.html