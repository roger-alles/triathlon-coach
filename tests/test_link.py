"""Tests del vinculador planificat<->real (spec §9), part pura."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.link import match_day, session_status

TODAY = date(2026, 8, 28)
D_PAST = date(2026, 8, 26)


def sess(id=1, sport="swim", target=2100, load=None, local_date=D_PAST):
    return {"id": id, "sport": sport, "local_date": local_date,
            "duration_sec_target": target, "planned_load": load}


def act(id=100, sport="swim", dur=1500, load=20.8):
    return {"id": id, "sport": sport, "duration_sec": dur, "load": load}


def test_match_same_day_same_sport():
    links = match_day([sess()], [act()])
    assert links == [(100, 1)]


def test_match_picks_closest_duration_among_candidates():
    short = sess(id=1, target=1800)
    long = sess(id=2, target=5400)
    links = match_day([short, long], [act(dur=5100)])
    assert links == [(100, 2)]


def test_match_ignores_other_sports():
    assert match_day([sess(sport="bike")], [act(sport="swim")]) == []


def test_status_completed_at_80pct_duration():
    s = sess(target=2100)
    assert session_status(s, [act(dur=1700)], TODAY) == "completed"  # 81%
    assert session_status(s, [act(dur=1500)], TODAY) == "partial"    # 71%


def test_status_uses_planned_load_when_present():
    s = sess(target=2100, load=100.0)
    assert session_status(s, [act(load=85.0)], TODAY) == "completed"
    assert session_status(s, [act(load=50.0)], TODAY) == "partial"


def test_status_missed_only_after_the_day_ends():
    assert session_status(sess(local_date=D_PAST), [], TODAY) == "missed"
    assert session_status(sess(local_date=TODAY), [], TODAY) is None  # el dia no s'ha acabat


def test_status_multiple_activities_sum():
    s = sess(target=3600)
    linked = [act(id=1, dur=1500), act(id=2, dur=1500)]
    assert session_status(s, linked, TODAY) == "completed"  # 83%


def test_rest_day_completes_itself_when_past():
    s = sess(sport="rest", target=None, local_date=D_PAST)
    assert session_status(s, [], TODAY) == "completed"
    assert session_status(sess(sport="rest", target=None, local_date=TODAY), [], TODAY) is None
