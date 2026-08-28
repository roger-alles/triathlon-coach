"""Tests mínims dels models del coach."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.models import Session, Violation


def test_violation_blocking_property():
    assert Violation("R1", "blocking", "x").blocking is True
    assert Violation("R4", "warning", "x").blocking is False


def test_session_defaults():
    s = Session(local_date=date(2026, 9, 1), sport="swim", session_type="technique",
                title="T", structure={"steps": []})
    assert s.priority == "support"
    assert s.is_goal_event is False
