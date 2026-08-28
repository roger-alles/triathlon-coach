"""Tests del càlcul de càrrega i forma (spec §5 i §12.3).

La sèrie CTL/ATL/TSB del test està calculada a mà:
  dia 1: load=100 -> tsb = 0-0 = 0
          ctl = 0 + (100-0)/42 = 2.380952   atl = 0 + (100-0)/7 = 14.285714
  dia 2: load=0   -> tsb = 2.380952 - 14.285714 = -11.904762
          ctl = 2.380952·(41/42) = 2.324263  atl = 14.285714·(6/7) = 12.244898
  dia 3: load=50  -> tsb = 2.324263 - 12.244898 = -9.920635
          ctl = 2.324263 + (50-2.324263)/42 = 3.459495
          atl = 12.244898 + (50-12.244898)/7 = 17.638484
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.load import activity_load, form_series, trimp_load

D1, D2, D3 = date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)


def test_trimp_weights_minutes_by_zone():
    # 10' Z1 + 20' Z2 + 10' Z3 = 10·1 + 20·1.5 + 10·2.5 = 65
    zones = {1: 600, 2: 1200, 3: 600, 4: 0, 5: 0}
    assert trimp_load(zones) == 65.0


def test_trimp_none_without_hr_data():
    assert trimp_load({1: 0, 2: 0, 3: 0, 4: 0, 5: 0}) is None


def test_activity_load_prefers_garmin_load():
    load, estimated = activity_load({"activityTrainingLoad": 87.3}, duration_sec=3600)
    assert (load, estimated) == (87.3, False)


def test_activity_load_falls_back_to_trimp():
    raw = {"hrTimeInZone_1": 600, "hrTimeInZone_2": 1200, "hrTimeInZone_3": 600}
    load, estimated = activity_load(raw, duration_sec=2400)
    assert (load, estimated) == (65.0, False)


def test_activity_load_last_resort_duration_based():
    # sense FC ni res: durada_hores × 50, i marcat com a estimat (spec §5.4)
    load, estimated = activity_load({}, duration_sec=5400)
    assert (load, estimated) == (75.0, True)


def test_form_series_hand_computed():
    series = form_series({D1: 100.0, D3: 50.0}, start=D1, end=D3)
    assert [r["local_date"] for r in series] == [D1, D2, D3]

    r1, r2, r3 = series
    assert r1["tsb"] == pytest.approx(0.0)
    assert r1["ctl"] == pytest.approx(2.380952, abs=1e-4)
    assert r1["atl"] == pytest.approx(14.285714, abs=1e-4)
    assert r2["load"] == 0
    assert r2["tsb"] == pytest.approx(-11.904762, abs=1e-4)
    assert r3["ctl"] == pytest.approx(3.459495, abs=1e-4)
    assert r3["atl"] == pytest.approx(17.638484, abs=1e-4)
    assert r3["tsb"] == pytest.approx(-9.920635, abs=1e-4)


def test_form_series_monotony_needs_variation():
    # 7 dies idèntics: desviació 0 -> monotonia indefinida (None), no infinit
    loads = {date(2026, 8, d): 50.0 for d in range(1, 8)}
    series = form_series(loads, start=date(2026, 8, 1), end=date(2026, 8, 7))
    assert series[-1]["monotony"] is None
    assert series[-1]["strain"] is None
