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


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    """Registra les queries; retorna `found` al select i id 99 a l'insert."""

    def __init__(self, found=None):
        self.calls = []
        self._found = found

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.strip().lower().startswith("select"):
            return _FakeResult(self._found)
        return _FakeResult((99,))


def test_upsert_session_matches_by_date_and_sport_when_title_changes():
    # Reprogramar una sessió canviant-li el títol ha d'ACTUALITZAR la fila
    # existent (la BD només permet una sessió per esport i dia), no inserir-ne una.
    from ingest.seed import upsert_session

    row = {"local_date": date(2026, 9, 1), "sport": "swim", "session_type": "test",
           "title": "Test de referència (reprogramat)", "priority": "key",
           "structure": {"steps": []}, "duration_sec_target": 2400,
           "distance_m_target": None, "rationale": None, "is_test": True,
           "test_spec": {"metric": "swim_continuous"}, "rehearses_goal": False,
           "is_goal_event": False, "transition_practice": None}
    conn = _FakeConn(found=(7,))
    assert upsert_session(conn, goal_id=1, block_id=2, row=row) == 7

    select_sql, select_params = conn.calls[0]
    assert "title" not in select_sql          # el match no depèn del títol
    assert select_params == (1, date(2026, 9, 1), "swim")

    update_sql = conn.calls[1][0]
    assert "title=%(title)s" in update_sql    # el títol nou es persisteix
