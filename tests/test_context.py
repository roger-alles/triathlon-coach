"""Tests de les parts pures del constructor de context del coach."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.context import compact, days_until


def test_compact_drops_nulls_and_empties_recursively():
    payload = {"a": 1, "b": None, "c": {"d": None, "e": 2, "f": {}}, "g": [], "h": 0}
    assert compact(payload) == {"a": 1, "c": {"e": 2}, "h": 0}  # el 0 es conserva


def test_compact_cleans_inside_lists():
    payload = {"rows": [{"x": 1, "y": None}, {"x": None}]}
    assert compact(payload) == {"rows": [{"x": 1}, {}]}


def test_days_until():
    assert days_until(date(2026, 9, 27), today=date(2026, 8, 28)) == 30
    assert days_until(None, today=date(2026, 8, 28)) is None


class _Cur:
    def __init__(self, cols, rows):
        class _C:  # imita cur.description de psycopg
            def __init__(self, name): self.name = name
        self.description = [_C(c) for c in cols]
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, cols, rows):
        self.sql = None
        self._cur = _Cur(cols, rows)

    def execute(self, sql, params=None):
        self.sql = sql
        return self._cur


def test_recent_answers_reads_the_athlete_answer_table():
    from datetime import datetime
    from coach.context import _recent_answers

    conn = _Conn(
        ["created_at", "question", "answer"],
        [(datetime(2026, 8, 29, 18, 0), "Com notes les cames?", "Bé, sense agulletes.")],
    )
    rows = _recent_answers(conn, date(2026, 8, 29))
    assert rows == [{"created_at": "2026-08-29T18:00:00",
                     "question": "Com notes les cames?",
                     "answer": "Bé, sense agulletes."}]
    assert "athlete_answer" in conn.sql


def test_build_context_includes_athlete_answers_key():
    import inspect
    from coach import context

    src = inspect.getsource(context.build_context)
    assert "athlete_answers_last_7d" in src


def test_test_results_arriba_al_snapshot_com_a_marques():
    from coach.context import _test_results

    conn = _Conn(
        ["local_date", "metric", "values", "session_title"],
        [(date(2026, 9, 3), "swim_continuous",
          {"distance_m": 1000, "duration_sec": 1350, "pace_sec_100m": 135,
           "environment": "open_water"},
          "Continuïtat")],
    )
    rows = _test_results(conn)
    assert rows == [{"local_date": "2026-09-03", "metric": "swim_continuous",
                     "distance_m": 1000, "duration_sec": 1350, "pace_sec_100m": 135,
                     "environment": "open_water", "session_title": "Continuïtat"}]
    assert "test_result" in conn.sql
