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
