"""El mode d'aplicació del coach viu a la BD (app_setting), no al script del cron."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.settings import apply_mode


class _Conn:
    def __init__(self, row):
        self.row = row
        self.sql = None

    def execute(self, sql, params=None):
        self.sql = sql
        conn = self
        class R:
            def fetchone(self_inner):
                return conn.row
        return R()


def test_hybrid_when_the_setting_says_so():
    conn = _Conn(("hybrid",))
    assert apply_mode(conn) == "hybrid"
    assert "coach_apply_mode" in conn.sql


def test_anything_else_is_dry_run():
    assert apply_mode(_Conn(("dry_run",))) == "dry_run"
    assert apply_mode(_Conn(("banana",))) == "dry_run"
    assert apply_mode(_Conn(None)) == "dry_run"
