"""Regla determinista auto vs proposta (docs/post-cursa-design.md, aprovació híbrida).

Automàtic NOMÉS si tot es compleix: cap bloqueig del validador, com a molt 2
sessions, horitzó de 3 dies, accions modificar / moure dins la mateixa setmana
cap endavant / cancel·lar una no-clau, i sense afegir càrrega total ni dura.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.classify import classify
from coach.models import Block, Session, Violation

MON = date(2026, 10, 5)   # dilluns
B = Block(id=1, phase="build", start_date=MON, end_date=MON + timedelta(days=6))


def easy(id, day, sport, minutes, rpe=3, priority="support"):
    sec = minutes * 60
    return Session(id=id, local_date=MON + timedelta(days=day), sport=sport,
                   session_type="easy", title=f"{sport}-{id}", block=B,
                   structure={"steps": [{"phase": "main", "duration_sec": sec,
                                         "target": {"type": "rpe", "value": rpe}}]},
                   duration_sec_target=sec, priority=priority)


PLAN = {s.id: s for s in [
    easy(1, 0, "run", 50),                 # dilluns
    easy(2, 1, "swim", 40, priority="key"),  # dimarts
    easy(3, 2, "bike", 60),                # dimecres
    easy(4, 5, "run", 45),                 # dissabte
]}


def modify(id, minutes, rpe=3):
    sec = minutes * 60
    return {"plan_session_id": id, "action": "modify", "reason": "x",
            "new_session": {"sport": PLAN[id].sport, "session_type": "easy",
                            "title": "canviada", "duration_sec_target": sec,
                            "structure": {"steps": [{"phase": "main", "duration_sec": sec,
                                                     "target": {"type": "rpe", "value": rpe}}]}}}


def test_no_changes_is_trivially_auto():
    c = classify([{"plan_session_id": 1, "action": "keep", "reason": ""}], PLAN, MON, [])
    assert c.auto and c.n_sessions == 0


def test_shortening_todays_session_is_auto():
    c = classify([modify(1, 30)], PLAN, MON, [])
    assert c.auto
    assert c.load_before_sec == 3000 and c.load_after_sec == 1800


def test_lengthening_or_hardening_is_a_proposal():
    assert not classify([modify(1, 60)], PLAN, MON, []).auto
    harder = classify([modify(1, 50, rpe=8)], PLAN, MON, [])
    assert not harder.auto and any("dura" in r for r in harder.reasons)


def test_move_inside_the_week_forward_is_auto_but_next_week_is_not():
    same_week = [{"plan_session_id": 3, "action": "move", "reason": "x",
                  "new_date": (MON + timedelta(days=3)).isoformat()}]
    assert classify(same_week, PLAN, MON, []).auto
    next_week = [{"plan_session_id": 3, "action": "move", "reason": "x",
                  "new_date": (MON + timedelta(days=8)).isoformat()}]
    c = classify(next_week, PLAN, MON, [])
    assert not c.auto and any("setmana" in r for r in c.reasons)


def test_cancel_support_is_auto_cancel_key_is_not():
    assert classify([{"plan_session_id": 1, "action": "cancel", "reason": "x"}], PLAN, MON, []).auto
    c = classify([{"plan_session_id": 2, "action": "cancel", "reason": "x"}], PLAN, MON, [])
    assert not c.auto and any("clau" in r for r in c.reasons)


def test_more_than_two_sessions_or_beyond_three_days_is_a_proposal():
    three = [modify(1, 30), modify(2, 30), modify(3, 30)]
    c = classify(three, PLAN, MON, [])
    assert not c.auto and c.n_sessions == 3
    far = classify([modify(4, 30)], PLAN, MON, [])   # dissabte = +5 dies
    assert not far.auto and far.horizon_days == 5


def test_any_blocking_violation_is_a_proposal():
    v = [Violation("R5", "blocking", "sense descans")]
    c = classify([modify(1, 30)], PLAN, MON, v)
    assert not c.auto and any("R5" in r for r in c.reasons)


def test_to_dict_is_json_friendly():
    d = classify([modify(1, 30)], PLAN, MON, []).to_dict()
    assert d["auto"] is True and d["reasons"] == [] and isinstance(d["horizon_days"], int)


def test_add_is_never_auto_and_does_not_crash():
    # S4a: una sessió nova no té sessió d'origen (plan_session_id): la regla
    # ha de comptar-la (càrrega, horitzó) i marcar-la sempre com a proposta.
    sec = 45 * 60
    add = {"action": "add", "reason": "volum", "new_session": {
        "local_date": (MON + timedelta(days=1)).isoformat(), "sport": "run",
        "session_type": "easy", "title": "Rodatge extra", "duration_sec_target": sec,
        "structure": {"steps": [{"phase": "main", "duration_sec": sec,
                                 "target": {"type": "rpe", "value": 3}}]}}}
    c = classify([add], PLAN, MON, blocking=[], blocks=[B])
    assert c.auto is False
    assert any("afegeix" in r for r in c.reasons)
    assert c.n_sessions == 1 and c.horizon_days == 1
    assert c.load_before_sec == 0 and c.load_after_sec == sec
