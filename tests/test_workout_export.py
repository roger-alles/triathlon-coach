"""Tests del conversor sessió del pla → workout de Garmin Connect (spec §F6).

Sense xarxa: només es comprova el JSON que s'enviaria. Format = el que Garmin
retorna a get_workout_by_id (stepType ids: warmup 1, cooldown 2, interval 3,
recovery 4, repeat 6; endCondition time 2 / distance 3; targetType no.target 1).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.workout_export import expand_contains, session_to_garmin_workout


def _steps(w):
    return w["workoutSegments"][0]["workoutSteps"]


def test_bici_blocs_amb_repunts():
    session = {
        "id": 67, "sport": "bike", "title": "Blocs amb repunts", "local_date": "2026-09-10",
        "duration_sec_target": 4800,
        "structure": {"steps": [
            {"phase": "warmup", "duration_sec": 900, "target": {"type": "rpe", "value": 4}},
            {"phase": "main", "repeats": 3,
             "work": {"duration_sec": 720, "target": {"type": "rpe", "value": 7, "label": "esforç de cursa"},
                      "contains": {"repeats": 2, "duration_sec": 40, "target": {"type": "rpe", "value": 9}, "note": "dempeus"}},
             "recovery": {"duration_sec": 300, "target": {"type": "rpe", "value": 3}}},
            {"phase": "cooldown", "duration_sec": 600, "target": {"type": "rpe", "value": 3}},
        ]},
    }
    w = session_to_garmin_workout(session)
    assert w["workoutName"] == "Blocs amb repunts"
    assert w["sportType"]["sportTypeKey"] == "cycling"
    assert w["estimatedDurationInSecs"] == 4800
    steps = _steps(w)
    assert [s["stepType"]["stepTypeKey"] for s in steps] == ["warmup", "repeat", "cooldown"]
    warm = steps[0]
    assert warm["endCondition"]["conditionTypeKey"] == "time" and warm["endConditionValue"] == 900.0
    assert warm["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert "RPE 4" in warm["description"]
    rep = steps[1]
    assert rep["type"] == "RepeatGroupDTO" and rep["numberOfIterations"] == 3
    kinds = [(s["stepType"]["stepTypeKey"], s["endConditionValue"]) for s in rep["workoutSteps"]]
    # 720 s amb 2 repunts de 40 s: 3 trams a RPE 7 (640 s repartits) + 2 repunts + recuperació
    assert kinds == [("interval", 213.0), ("interval", 40.0), ("interval", 213.0),
                     ("interval", 40.0), ("interval", 214.0), ("recovery", 300.0)]
    assert "RPE 9" in rep["workoutSteps"][1]["description"]
    assert "dempeus" in rep["workoutSteps"][1]["description"]
    # stepOrder consecutiu a tot l'arbre i childStepId al grup
    orders = [steps[0]["stepOrder"], rep["stepOrder"]] + [s["stepOrder"] for s in rep["workoutSteps"]] + [steps[2]["stepOrder"]]
    assert orders == list(range(1, len(orders) + 1))
    assert all(s["childStepId"] == rep["childStepId"] for s in rep["workoutSteps"])


def test_expand_contains_reparteix_la_resta():
    work = {"duration_sec": 720, "target": {"type": "rpe", "value": 7},
            "contains": {"repeats": 2, "duration_sec": 40, "target": {"type": "rpe", "value": 9}}}
    parts = expand_contains(work)
    assert sum(p["duration_sec"] for p in parts) == 720
    assert [p["target"]["value"] for p in parts] == [7, 9, 7, 9, 7]


def test_natacio_amb_distancia_i_ritme():
    session = {"id": 43, "sport": "swim", "title": "Ritme de cursa amb orientació",
               "local_date": "2026-09-10", "duration_sec_target": 2400,
               "structure": {"steps": [
                   {"phase": "warmup", "distance_m": 200, "target": {"type": "rpe", "value": 3}},
                   {"phase": "main", "repeats": 3,
                    "work": {"distance_m": 400, "target": {"type": "pace_sec_100m", "value": 135, "label": "ritme de cursa (2:15/100)"},
                             "note": "aixecar el cap cada 8-10 braçades"},
                    "recovery": {"duration_sec": 60}},
                   {"phase": "cooldown", "distance_m": 200, "target": {"type": "rpe", "value": 2}}]}}
    w = session_to_garmin_workout(session)
    assert w["sportType"]["sportTypeKey"] == "swimming"
    warm = _steps(w)[0]
    assert warm["endCondition"]["conditionTypeKey"] == "distance" and warm["endConditionValue"] == 200.0
    work = _steps(w)[1]["workoutSteps"][0]
    assert "2:15/100" in work["description"] and "aixecar el cap" in work["description"]
    rec = _steps(w)[1]["workoutSteps"][1]
    assert rec["stepType"]["stepTypeKey"] == "recovery" and rec["endConditionValue"] == 60.0
