"""Tests del mapeig Garmin -> model propi, contra fixtures REALS de F0."""

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.mapping import map_activity, map_daily, map_sport

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_map_sport_known_and_unknown_keys():
    assert map_sport("running") == "run"
    assert map_sport("trail_running") == "run"
    assert map_sport("cycling") == "bike"
    assert map_sport("indoor_cycling") == "bike"
    assert map_sport("lap_swimming") == "swim"
    assert map_sport("open_water_swimming") == "swim"
    assert map_sport("strength_training") == "strength"
    assert map_sport("multi_sport") == "brick"
    assert map_sport("walking") == "other"
    assert map_sport("un_esport_que_no_existeix") == "other"


def test_map_activity_running_fixture():
    row = map_activity(fixture("activity_running.json"))
    assert row["sport"] == "run"
    assert row["sub_sport"] == "running"
    assert row["id"] > 0
    # startTimeGMT és UTC: 13:45:14 GMT amb local 15:45:14 (CEST)
    assert row["start_time"] == datetime(2026, 8, 20, 13, 45, 14, tzinfo=timezone.utc)
    assert row["local_date"] == date(2026, 8, 20)
    # ritme de cursa en s/km derivat de la velocitat en m/s
    assert row["avg_pace_sec_km"] == round(1000 / 3.34500002861023, 1)
    assert row["avg_pace_sec_100m"] is None
    assert row["avg_hr"] is not None
    assert row["raw"]  # sempre es guarda la resposta sencera


def test_map_activity_swim_uses_pace_per_100m():
    row = map_activity(fixture("activity_lap_swimming.json"))
    assert row["sport"] == "swim"
    assert row["avg_pace_sec_100m"] == round(100 / 0.7390000224113464, 1)
    assert row["avg_pace_sec_km"] is None


def test_map_activity_cycling_without_power_meter():
    row = map_activity(fixture("activity_cycling.json"))
    assert row["sport"] == "bike"
    # sense potenciòmetre ni training load: NULL, mai inventat (spec §0)
    assert row["avg_power_w"] is None
    assert row["garmin_training_load"] is None


def test_map_daily_fixture():
    row = map_daily(date(2026, 8, 26), fixture("daily_2026-08-26.json"))
    assert row["local_date"] == date(2026, 8, 26)
    assert row["resting_hr"] == 50
    assert row["body_battery_max"] == 83
    assert row["body_battery_min"] == 5
    assert row["stress_avg"] == 28
    assert row["sleep_duration_sec"] == 29100
    assert row["deep_sleep_sec"] == 1320
    # el dispositiu no ho dona: NULL, no zero
    assert row["sleep_score"] is None
    assert row["hrv_last_night_ms"] is None


def test_map_daily_survives_empty_payloads():
    row = map_daily(date(2026, 8, 26), {"stats": None, "sleep": {}})
    assert row["resting_hr"] is None
    assert row["sleep_duration_sec"] is None


def test_body_battery_of_the_morning_comes_from_the_night_when_the_summary_lags():
    # 09/10/2026, informe de les 07:11: el resum només tenia el valor de mitjanit
    lagging = {"stats": {"bodyBatteryHighestValue": 25, "bodyBatteryLowestValue": 20},
               "sleep": {"sleepBodyBattery": [{"value": 20, "startGMT": 1}, {"value": 64, "startGMT": 2},
                                              {"value": 99, "startGMT": 3}]}}
    row = map_daily(date(2026, 10, 9), lagging)
    assert row["body_battery_max"] == 99
    assert row["body_battery_min"] == 20


def test_body_battery_at_wake_time_counts_when_present():
    row = map_daily(date(2026, 10, 9), {"stats": {"bodyBatteryHighestValue": 25,
                                                  "bodyBatteryAtWakeTime": 99}, "sleep": {}})
    assert row["body_battery_max"] == 99


def test_body_battery_missing_everywhere_stays_null():
    row = map_daily(date(2026, 10, 9), {"stats": None, "sleep": {"sleepBodyBattery": None}})
    assert row["body_battery_max"] is None
