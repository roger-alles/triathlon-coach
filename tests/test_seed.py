"""Tests de la transformació YAML -> files del pla (part pura del loader)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.seed import resolve_chains, session_row, split_entries


def test_split_entries_routes_inline_logistics_out():
    entries = [
        {"date": date(2026, 9, 24), "sport": "bike", "session_type": "race_pace",
         "title": "Recordatori", "structure": {"steps": []}},
        {"date": date(2026, 9, 24), "type": "logistics",
         "title": "Revisió completa de material", "when": "vespre"},
    ]
    sessions, logistics = split_entries(entries)
    assert len(sessions) == 1 and len(logistics) == 1
    assert logistics[0]["title"] == "Revisió completa de material"


def test_session_row_maps_test_block_to_test_spec():
    s = {"date": date(2026, 8, 28), "sport": "swim", "session_type": "test",
         "title": "Test de referència", "priority": "key", "is_test": True,
         "test": {"metric": "swim_continuous", "records": ["distance_m"]},
         "duration_sec_target": 2400, "structure": {"steps": []}}
    row = session_row(s)
    assert row["is_test"] is True
    assert row["test_spec"]["metric"] == "swim_continuous"
    assert "test" not in row


def test_session_row_defaults_and_transition_rename():
    s = {"date": date(2026, 9, 19), "sport": "brick", "session_type": "bike_run",
         "title": "Brick + assaig de T2", "parent_of_day": "bike",
         "includes_transition_practice": ["t2"], "structure": {"steps": []}}
    row = session_row(s)
    assert row["priority"] == "support"          # default de la spec
    assert row["is_test"] is False
    assert row["transition_practice"] == ["t2"]
    assert row["_parent_of_day"] == "bike"       # marcador intern, no columna


def test_resolve_chains_links_brick_to_same_day_parent():
    rows = [
        {"local_date": date(2026, 9, 5), "sport": "bike", "title": "Llarga", "_parent_of_day": None},
        {"local_date": date(2026, 9, 5), "sport": "brick", "title": "Brick", "_parent_of_day": "bike"},
        {"local_date": date(2026, 9, 6), "sport": "run", "title": "Suau", "_parent_of_day": None},
    ]
    chains = resolve_chains(rows)
    assert chains == [((date(2026, 9, 5), "brick", "Brick"),
                       (date(2026, 9, 5), "bike", "Llarga"))]
