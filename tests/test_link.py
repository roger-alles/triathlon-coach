"""Tests del vinculador planificat<->real (spec §9), part pura."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.link import match_day, session_status

TODAY = date(2026, 8, 28)
D_PAST = date(2026, 8, 26)


def sess(id=1, sport="swim", target=2100, load=None, local_date=D_PAST, distance_target=None):
    return {"id": id, "sport": sport, "local_date": local_date,
            "duration_sec_target": target, "distance_m_target": distance_target,
            "planned_load": load}


def act(id=100, sport="swim", dur=1500, load=20.8, distance_m=None):
    return {"id": id, "sport": sport, "duration_sec": dur, "load": load,
            "distance_m": distance_m}


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


def test_brick_completed_bike_and_run_by_run_duration():
    s = sess(sport="brick", target=1800)  # 1800s: durada objectiu del tram a peu
    day = [act(id=1, sport="bike", dur=5400), act(id=2, sport="run", dur=1600)]
    assert session_status(s, day, TODAY) == "completed"  # 1600/1800 = 89%


def test_brick_partial_when_run_too_short():
    s = sess(sport="brick", target=1800)
    day = [act(id=1, sport="bike", dur=5400), act(id=2, sport="run", dur=1200)]
    assert session_status(s, day, TODAY) == "partial"  # 1200/1800 = 67%


def test_brick_only_bike_is_partial_when_day_over_not_missed():
    s = sess(sport="brick", target=1800, local_date=D_PAST)
    day = [act(id=1, sport="bike", dur=5400)]
    assert session_status(s, day, TODAY) == "partial"


def test_brick_only_bike_stays_open_while_day_not_over():
    s = sess(sport="brick", target=1800, local_date=TODAY)
    day = [act(id=1, sport="bike", dur=5400)]
    assert session_status(s, day, TODAY) is None


def test_brick_missed_without_any_activity():
    s = sess(sport="brick", target=1800, local_date=D_PAST)
    assert session_status(s, [], TODAY) == "missed"


def test_multisport_three_sports_completed():
    s = sess(sport="multisport", target=10800)
    day = [act(id=1, sport="swim", dur=1800), act(id=2, sport="bike", dur=5400),
           act(id=3, sport="run", dur=2400)]
    assert session_status(s, day, TODAY) == "completed"  # 9600/10800 = 89%


def test_multisport_one_sport_is_partial_when_day_over():
    s = sess(sport="multisport", target=10800, local_date=D_PAST)
    day = [act(id=1, sport="bike", dur=5400)]
    assert session_status(s, day, TODAY) == "partial"


def test_multisport_missed_without_any_activity():
    s = sess(sport="multisport", target=10800, local_date=D_PAST)
    assert session_status(s, [], TODAY) == "missed"


def test_status_by_distance_when_no_duration_target():
    s = sess(target=None, distance_target=3000)
    assert session_status(s, [act(dur=1500, distance_m=2600)], TODAY) == "completed"  # 87%
    assert session_status(s, [act(dur=1500, distance_m=2000)], TODAY) == "partial"    # 67%


def test_status_completed_when_no_duration_and_no_distance_target():
    s = sess(target=None, distance_target=None)
    assert session_status(s, [act()], TODAY) == "completed"


def test_status_is_idempotent_given_same_inputs():
    s = sess(target=2100)
    linked = [act(dur=1700)]
    first = session_status(s, linked, TODAY)
    second = session_status(s, linked, TODAY)
    assert first == second == "completed"
