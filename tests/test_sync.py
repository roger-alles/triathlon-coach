"""Tests de la lògica pura de sync (finestra incremental)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.sync import compute_start_date


def test_incremental_goes_back_margin_days_from_last_known():
    # Garmin de vegades reprocessa: 3 dies de marge (spec §9)
    start = compute_start_date(last_known=date(2026, 8, 25), since_arg=None)
    assert start == date(2026, 8, 22)


def test_explicit_since_wins_over_incremental():
    start = compute_start_date(last_known=date(2026, 8, 25),
                               since_arg=date(2026, 5, 29))
    assert start == date(2026, 5, 29)


def test_empty_database_requires_since():
    try:
        compute_start_date(last_known=None, since_arg=None)
        assert False, "hauria d'haver petat"
    except SystemExit:
        pass


class _SpyProvider:
    """Registra QUAN es fa cada fetch respecte de les escriptures a la BD."""

    def __init__(self, log):
        self.log = log

    def fetch_activities(self, start, end):
        self.log.append("fetch_activities")
        return [{"activityId": 1, "startTimeLocal": "2026-08-29 10:00:00",
                 "startTimeGMT": "2026-08-29 08:00:00",
                 "activityType": {"typeKey": "running"}, "duration": 600}]

    def fetch_daily(self, day):
        self.log.append(f"fetch_daily:{day}")
        return {}


class _SpyConn:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append("db_execute")
        class R:
            def fetchone(self): return (None,)
        return R()


def test_no_db_writes_while_garmin_is_being_fetched():
    # 29-30/08: el pooler de Supabase mata connexions ocioses; el sync mantenia
    # la connexió oberta durant tots els fetch lents de Garmin. Contracte nou:
    # primer es recull TOT de Garmin, després s'escriu. Cap execute entremig.
    from ingest.sync import collect_rows

    log = []
    provider = _SpyProvider(log)
    activity_rows, daily_rows = collect_rows(
        provider, date(2026, 8, 28), date(2026, 8, 28), date(2026, 8, 29))

    assert all(not e.startswith("db_execute") for e in log)
    assert len(activity_rows) == 1
    assert len(daily_rows) == 2  # 28 i 29


def test_write_rows_only_touches_db():
    from ingest.sync import write_rows

    log = []
    conn = _SpyConn(log)
    write_rows(conn, [{"any": "activitat"}], [{"any": "dia"}])
    assert log == ["db_execute", "db_execute"]
