"""Tests de les funcions pures del servidor MCP (les de DB no es testegen aquí)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.queries import summarize_by_sport, week_bounds


def test_week_bounds_monday_to_sunday():
    # el 28/08/2026 és divendres -> setmana del dilluns 24 al diumenge 30
    assert week_bounds(date(2026, 8, 28)) == (date(2026, 8, 24), date(2026, 8, 30))


def test_week_bounds_on_monday_and_sunday():
    assert week_bounds(date(2026, 8, 24)) == (date(2026, 8, 24), date(2026, 8, 30))
    assert week_bounds(date(2026, 8, 30)) == (date(2026, 8, 24), date(2026, 8, 30))


def test_week_bounds_offset_weeks_back():
    assert week_bounds(date(2026, 8, 28), offset_weeks=-1) == (date(2026, 8, 17),
                                                              date(2026, 8, 23))


def test_summarize_by_sport_totals():
    rows = [
        {"sport": "run", "duration_sec": 3600, "distance_m": 10000, "load": 80.0},
        {"sport": "run", "duration_sec": 1800, "distance_m": 5000, "load": 30.0},
        {"sport": "bike", "duration_sec": 7200, "distance_m": 60000, "load": 150.0},
        {"sport": "swim", "duration_sec": 1800, "distance_m": None, "load": None},
    ]
    totals = summarize_by_sport(rows)
    assert totals["run"] == {"sessions": 2, "hours": 1.5, "distance_km": 15.0, "load": 110.0}
    assert totals["bike"]["sessions"] == 1
    # None no ha de petar ni comptar com a zero fantasma
    assert totals["swim"] == {"sessions": 1, "hours": 0.5, "distance_km": 0.0, "load": 0.0}
