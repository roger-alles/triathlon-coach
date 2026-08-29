"""Tests del validador del contracte de sessió (spec §6)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.models import Athlete
from coach.structure import validate_structure

ATHLETE = Athlete(name="Roger", max_hr=211)  # sense FTP, CSS ni ritme llindar


def ok(structure, sport="run"):
    return validate_structure(structure, sport, ATHLETE)


def test_valid_steps_session():
    s = {"steps": [
        {"phase": "warmup", "duration_sec": 900, "target": {"type": "rpe", "value": 4}},
        {"phase": "main", "repeats": 4,
         "work": {"distance_m": 1000, "target": {"type": "pace_sec_km", "value": 222}},
         "recovery": {"duration_sec": 90}},
        {"phase": "cooldown", "duration_sec": 600, "target": {"type": "hr_zone", "value": 1}},
    ]}
    assert ok(s) == []


def test_step_needs_exactly_one_of_duration_or_distance():
    both = {"steps": [{"duration_sec": 600, "distance_m": 200,
                       "target": {"type": "rpe", "value": 3}}]}
    neither = {"steps": [{"target": {"type": "rpe", "value": 3}}]}
    assert len(ok(both)) == 1 and "exactament un" in ok(both)[0]
    assert len(ok(neither)) == 1


def test_unknown_target_type_rejected():
    s = {"steps": [{"duration_sec": 600, "target": {"type": "watts", "value": 200}}]}
    assert any("no admès" in e for e in ok(s))


def test_threshold_target_without_threshold_rejected():
    # l'atleta no té FTP: ftp_pct prohibit (spec §6, "Quan no hi ha llindars")
    s = {"steps": [{"duration_sec": 600, "target": {"type": "ftp_pct", "value": 0.9}}]}
    errors = ok(s, sport="bike")
    assert any("ftp_watts" in e for e in errors)


def test_rpe_and_hr_zone_ranges():
    bad_rpe = {"steps": [{"duration_sec": 60, "target": {"type": "rpe", "value": 11}}]}
    bad_zone = {"steps": [{"duration_sec": 60, "target": {"type": "hr_zone", "value": 6}}]}
    assert ok(bad_rpe) and ok(bad_zone)


def test_rest_session_allows_empty_steps():
    assert ok({"steps": []}, sport="rest") == []


def test_multisport_needs_segments_and_validates_them():
    assert ok({"steps": []}, sport="multisport")  # error: falta segments
    good = {"segments": [
        {"sport": "swim", "distance_m": 800, "target": {"type": "rpe", "value": 7}},
        {"sport": "transition", "transition": "t1"},
        {"sport": "bike", "distance_m": 34000},
    ]}
    assert ok(good, sport="multisport") == []
    bad = {"segments": [{"sport": "swim"}]}  # sense distància ni durada
    assert ok(bad, sport="multisport")


def test_structure_that_is_not_a_dict_is_an_error_not_a_crash():
    # 29/08 nit: el model va enviar structure_json com a llista de steps
    # directament i el cicle va petar amb AttributeError en lloc de donar
    # feedback al retry. Qualsevol cosa que no sigui un objecte és un error
    # semàntic més, amb missatge que expliqui al model com corregir-ho.
    for bad in ([{"phase": "main"}], "steps", 42, None):
        errors = ok(bad)
        assert len(errors) == 1
        assert "objecte" in errors[0] and "steps" in errors[0]
