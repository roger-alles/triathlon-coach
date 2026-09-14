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

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _Conn:
    """Connexió falsa. Amb `cols`/`rows` totes les consultes retornen el
    mateix (comportament original); amb `by_table` (dict substring_sql ->
    (cols, rows)) cada consulta que conté aquella substring retorna les
    seves pròpies files, i la resta retornen buit per defecte — necessari
    per cridar build_context() de veritat, que fa moltes consultes diferents."""
    def __init__(self, cols=None, rows=None, by_table=None):
        self.sql = None
        self.queries = []
        self._default = _Cur(cols or [], rows or [])
        self._by_table = by_table or {}

    def execute(self, sql, params=None):
        self.sql = sql
        self.queries.append(sql)
        for key, (cols, rows) in self._by_table.items():
            if key in sql:
                return _Cur(cols, rows)
        return self._default


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


ATHLETE_COLS = ("name", "birth_date", "max_hr", "resting_hr_baseline",
                "ftp_watts", "css_sec_per_100m", "threshold_pace_sec_km")
ATHLETE_ROW = ("Roger", date(2005, 12, 13), 211, 50, None, None, None)


def _full_conn(**extra_by_table):
    by_table = {"from athlete where": (ATHLETE_COLS, [ATHLETE_ROW])}
    by_table.update(extra_by_table)
    return _Conn(by_table=by_table)


def test_build_context_includes_athlete_answers_key():
    from datetime import datetime
    from coach.context import build_context

    conn = _full_conn(**{"from athlete_answer": (
        ["created_at", "question", "answer"],
        [(datetime(2026, 9, 6, 21, 0), "Com notes les cames?", "Bé.")])})
    snapshot = build_context(conn, date(2026, 9, 7))
    assert snapshot["athlete_answers_last_7d"] == [
        {"created_at": "2026-09-06T21:00:00",
         "question": "Com notes les cames?", "answer": "Bé."}]
    assert snapshot["athlete"]["name"] == "Roger"


def test_build_context_today_is_always_real_even_with_report_for():
    from coach.context import build_context

    today = date(2026, 9, 7)  # dilluns
    tomorrow = date(2026, 9, 8)  # dimarts
    snapshot = build_context(_full_conn(), today, report_for=tomorrow)
    assert snapshot["today"] == "2026-09-07"
    assert snapshot["weekday"] == "dilluns"
    assert snapshot["report_for"] == "2026-09-08"
    assert snapshot["report_for_weekday"] == "dimarts"
    assert snapshot["mode"] == "evening_preview"


def test_build_context_defaults_report_for_to_today_in_morning_mode():
    from coach.context import build_context

    today = date(2026, 9, 7)
    snapshot = build_context(_full_conn(), today)
    assert snapshot["today"] == snapshot["report_for"] == "2026-09-07"
    assert snapshot["mode"] == "morning"


def test_weekday_name_catalan_sunday_and_monday():
    from coach.context import weekday_name

    assert weekday_name(date(2026, 9, 6)) == "diumenge"
    assert weekday_name(date(2026, 9, 7)) == "dilluns"


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


def test_logistics_next_days_reads_logistics_task_with_detail_and_blocking():
    from coach.context import _logistics

    conn = _Conn(
        ["local_date", "title", "detail", "blocking", "done"],
        [(date(2026, 9, 26), "Recollida de dorsal · Fira del Participant",
          "Dissabte 16-20 h. Sense dorsal no hi ha cursa.", True, False)],
    )
    rows = _logistics(conn, date(2026, 9, 20))
    assert rows == [{"local_date": "2026-09-26",
                     "title": "Recollida de dorsal · Fira del Participant",
                     "detail": "Dissabte 16-20 h. Sense dorsal no hi ha cursa.",
                     "blocking": True, "done": False}]
    assert "logistics_task" in conn.sql
    assert "done = false" in conn.sql  # les fetes ja no cal recordar-les


def test_block_for_uses_the_report_day_not_today():
    # S4a: el setmanal corre diumenge però parla de la setmana que comença
    # demà: el bloc que rep és el del dilluns vinent, no el que acaba avui.
    from coach.context import block_for
    conn = _Conn(["phase", "name", "start_date", "end_date", "target_weekly_hours",
                  "fallback", "intent", "return_from_layoff"],
                 [("recovery", "Recuperació", date(2026, 9, 28), date(2026, 10, 18), 4.0, None, "descans actiu", False)])
    block = block_for(conn, date(2026, 9, 28))
    assert block["phase"] == "recovery" and block["start_date"] == "2026-09-28"
    assert "between start_date and end_date" in conn.sql


def test_build_context_weekly_takes_the_block_and_plan_of_next_monday():
    from coach.context import build_context
    today = date(2026, 9, 27)          # diumenge
    next_monday = date(2026, 9, 28)
    conn = _full_conn()
    build_context(conn, today, report_for=next_monday)
    block_query = next(q for q in conn.queries if "from plan_block" in q)
    assert "between start_date and end_date" in block_query
    plan_query = next(q for q in conn.queries if "from plan_session" in q and "between" in q)
    assert plan_query


def test_build_context_carries_the_macro_blocks_and_real_weekly_hours():
    from coach.context import build_context
    conn = _full_conn(**{
        "from plan_block where status": (
            ["id", "phase", "name", "start_date", "end_date", "target_weekly_hours", "intent",
             "fallback", "status", "sessions_planned"],
            [(8, "taper", "Afinada", date(2026, 9, 21), date(2026, 9, 27), 3.5, "i", "f", "active", 6)]),
        "sum(duration_sec)": (["monday", "hours"], [(date(2026, 9, 7), 5.26)]),
    })
    snapshot = build_context(conn, date(2026, 9, 14))
    assert snapshot["macro"] == [{"id": 8, "phase": "taper", "name": "Afinada", "start_date": "2026-09-21",
                                 "end_date": "2026-09-27", "target_weekly_hours": 3.5, "intent": "i",
                                 "fallback": "f", "status": "active", "sessions_planned": 6}]
    assert snapshot["history_weekly_hours"] == [{"monday": "2026-09-07", "hours": 5.26}]
