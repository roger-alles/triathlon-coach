"""Blocs del pla (macro, S3): validació, aplicació en memòria i a la BD, desfer."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.blocks import (apply_block_changes, apply_blocks_to_db, block_errors,
                          undo_block_effects)
from coach.models import Block, Goal, History, Session

TODAY = date(2026, 9, 14)
RACE = date(2026, 9, 27)
FORNELLS = Goal(name="Fornells", discipline="triathlon", event_date=RACE, priority="A", id=2,
                profile={"target_times_sec": {"total": [8110, 7470, 6895]}})
BLOCKS = [
    Block(id=7, phase="peak", start_date=date(2026, 9, 14), end_date=date(2026, 9, 20),
          target_weekly_hours=7.0, goal_id=2, name="Setmana 3"),
    Block(id=8, phase="taper", start_date=date(2026, 9, 21), end_date=RACE,
          target_weekly_hours=3.5, goal_id=2, name="Setmana 4 · afinada i cursa"),
]
REAL = History(weekly_hours={TODAY - timedelta(weeks=i): h for i, h in
                             zip(range(1, 5), [5.3, 4.3, 6.1, 4.6])})   # mitjana 5.08


def add(phase, start, end, hours, name="Bloc", **kw):
    nb = {"phase": phase, "name": name, "start_date": start.isoformat(),
          "end_date": end.isoformat(), "target_weekly_hours": hours,
          "intent": "x", "fallback": "y"}
    nb.update(kw)
    return {"action": "add", "reason": "cal", "new_block": nb}


def recovery():
    return add("recovery", RACE + timedelta(days=1), RACE + timedelta(days=21), 3.0, "Recuperació")


def test_recovery_after_the_race_is_valid_and_gets_a_synthetic_id():
    changes = [recovery()]
    assert block_errors(changes, BLOCKS, [FORNELLS], REAL, TODAY) == []
    cand = apply_block_changes(BLOCKS, changes)
    new = [b for b in cand if b.id < 0]
    assert len(new) == 1 and new[0].phase == "recovery" and new[0].status == "active"
    assert new[0].start_date == RACE + timedelta(days=1)


def test_add_in_the_past_bad_dates_or_unknown_phase_are_errors():
    past = add("base", TODAY, TODAY + timedelta(days=13), 4.0)
    assert any("demà" in e for e in block_errors([past], BLOCKS, [FORNELLS], REAL, TODAY))
    inverted = add("base", date(2026, 10, 10), date(2026, 10, 5), 4.0)
    assert any("end_date" in e for e in block_errors([inverted], BLOCKS, [FORNELLS], REAL, TODAY))
    phase = add("magic", date(2026, 10, 5), date(2026, 10, 10), 4.0)
    assert any("phase" in e for e in block_errors([phase], BLOCKS, [FORNELLS], REAL, TODAY))
    missing = {"action": "add", "reason": "x", "new_block": {"phase": "base"}}
    assert any("sense" in e for e in block_errors([missing], BLOCKS, [FORNELLS], REAL, TODAY))


def test_cancel_or_modify_a_block_with_planned_sessions_is_refused():
    plan = [Session(local_date=date(2026, 9, 23), sport="run", session_type="easy", title="x",
                    structure={}, block=BLOCKS[1], status="planned")]
    cancel = {"action": "cancel", "block_id": 8, "reason": "x"}
    errs = block_errors([cancel], BLOCKS, [FORNELLS], REAL, TODAY, plan=plan)
    assert any("sessions planificades" in e for e in errs)
    # sense sessions, cancel·lar el taper deixa la cursa sense taper: error de coherència
    errs = block_errors([cancel], BLOCKS, [FORNELLS], REAL, TODAY)
    assert any("taper" in e for e in errs)
    # un bloc inexistent
    assert any("no existeix" in e for e in block_errors(
        [{"action": "cancel", "block_id": 99, "reason": "x"}], BLOCKS, [FORNELLS], REAL, TODAY))


def test_overlapping_blocks_are_an_error():
    overlap = add("base", date(2026, 9, 25), date(2026, 10, 10), 4.0)
    assert any("solap" in e for e in block_errors([overlap], BLOCKS, [FORNELLS], REAL, TODAY))


def test_taper_and_recovery_around_the_A_race_are_checked():
    # sense taper (cancel·lat) i recovery: error de taper
    no_taper = [{"action": "cancel", "block_id": 8, "reason": "x"},
                add("peak", date(2026, 9, 21), RACE, 6.0), recovery()]
    errs = block_errors(no_taper, BLOCKS, [FORNELLS], REAL, TODAY)
    assert any("taper" in e for e in errs)
    # taper massa llarg per a una cursa curta (2h04 objectiu): 7-10 dies
    long_taper = [{"action": "modify", "block_id": 8, "reason": "x",
                   "new_block": {"start_date": date(2026, 9, 15).isoformat()}},
                  {"action": "modify", "block_id": 7, "reason": "x",
                   "new_block": {"end_date": date(2026, 9, 14).isoformat()}}, recovery()]
    errs = block_errors(long_taper, BLOCKS, [FORNELLS], REAL, TODAY)
    assert any("taper de 13 dies" in e for e in errs)
    # recovery que no comença l'endemà, o massa llarg
    late = add("recovery", RACE + timedelta(days=3), RACE + timedelta(days=14), 3.0)
    assert any("recovery" in e for e in block_errors([late], BLOCKS, [FORNELLS], REAL, TODAY))
    # cap recovery quan el pla arriba a la cursa
    assert any("recovery" in e for e in block_errors([], BLOCKS, [FORNELLS], REAL, TODAY))


def test_ramp_between_blocks_and_against_real_hours():
    # després de la recuperació (3 h), un base a 6 h és +100%: error
    steep = [recovery(), add("base", RACE + timedelta(days=22), RACE + timedelta(days=42), 6.0)]
    errs = block_errors(steep, BLOCKS, [FORNELLS], REAL, TODAY)
    assert any("+" in e and "15%" in e for e in errs)
    # una recuperació més dura que el taper que la precedeix: error
    hard_recovery = [add("recovery", RACE + timedelta(days=1), RACE + timedelta(days=14), 5.0)]
    assert any("baixar" in e for e in block_errors(hard_recovery, BLOCKS, [FORNELLS], REAL, TODAY))
    # el primer bloc nou d'un pla sense blocs es compara amb les hores reals (5,08 h)
    fresh = [add("base", date(2026, 9, 21), date(2026, 10, 11), 7.0)]
    errs = block_errors(fresh, [], [], REAL, TODAY)
    assert any("hores reals" in e for e in errs)
    ok = [add("base", date(2026, 9, 21), date(2026, 10, 11), 5.5)]
    assert block_errors(ok, [], [], REAL, TODAY) == []


class DbConn:
    def __init__(self, blocks):
        self.blocks = blocks   # id -> dict(status, phase, name, start_date, end_date, target_weekly_hours, intent, fallback)
        self.calls = []
        self.next_id = 100

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        self.calls.append((s, params))
        row = None
        if s.startswith("insert into plan_block"):
            self.next_id += 1
            row = (self.next_id,)
        elif s.startswith("select status, phase, name, start_date, end_date, target_weekly_hours, intent, fallback from plan_block"):
            b = self.blocks.get(params[0])
            row = (b["status"], b["phase"], b["name"], b["start_date"], b["end_date"],
                   b["target_weekly_hours"], b["intent"], b["fallback"]) if b else None
        class R:
            def fetchone(self_inner):
                return row
        return R()

    def sql(self, needle):
        return [c for c in self.calls if needle in c[0]]


def test_apply_blocks_to_db_add_cancel_modify_record_reversible_effects():
    conn = DbConn({8: dict(status="active", phase="taper", name="Setmana 4", start_date=date(2026, 9, 21),
                           end_date=RACE, target_weekly_hours=3.5, intent="i", fallback="f")})
    changes = [recovery(),
               {"action": "modify", "block_id": 8, "reason": "x",
                "new_block": {"name": "Afinada", "target_weekly_hours": 3.0}}]
    effects = apply_blocks_to_db(conn, 7, changes, goal_id=2, decision_id=3)
    ins = conn.sql("insert into plan_block")
    assert len(ins) == 1 and ins[0][1][0] == 2 and "'coach'" in ins[0][0]
    upd = conn.sql("update plan_block set")
    assert upd and "name" in upd[0][0] and "target_weekly_hours" in upd[0][0]
    kinds = [(e["kind"], e["block_id"]) for e in effects]
    assert kinds == [("block_created", 101), ("block_modified", 8)]
    assert json.loads(effects[1]["prev_values"]) == {"name": "Setmana 4", "target_weekly_hours": 3.5}
    eff = conn.sql("insert into coach_report_effect")
    assert len(eff) == 2 and eff[0][1][-1] == 3   # decision_id

    # desfer: la creada es cancel·la; la modificada recupera els valors previs
    conn2 = DbConn({})
    undo_block_effects(conn2, effects)
    assert conn2.sql("set status='cancelled'")[0][1] == (101,)
    restore = conn2.sql("update plan_block set")
    assert any(c[1] and "Setmana 4" in c[1] for c in restore)


def test_cancel_records_previous_status_and_undo_restores_it():
    conn = DbConn({8: dict(status="active", phase="taper", name="x", start_date=date(2026, 9, 21),
                           end_date=RACE, target_weekly_hours=3.5, intent=None, fallback=None)})
    effects = apply_blocks_to_db(conn, 7, [{"action": "cancel", "block_id": 8, "reason": "x"}], goal_id=2)
    assert effects[0]["kind"] == "block_cancelled" and effects[0]["prev_status"] == "active"
    conn2 = DbConn({})
    undo_block_effects(conn2, effects)
    assert conn2.sql("set status=%s")[0][1] == ("active", 8)


def test_a_block_above_the_athletes_declared_ceiling_is_an_error():
    from coach.models import Athlete
    athlete = Athlete(name="Roger", profile={"constraints": {"weekly_hours_ceiling": 8}})
    base = add("base", RACE + timedelta(days=22), RACE + timedelta(days=49), 9.0, "Base")
    errs = block_errors([recovery(), base], BLOCKS, [FORNELLS], REAL, TODAY, athlete=athlete)
    assert any("sostre de 8" in e for e in errs)
    ok = add("base", RACE + timedelta(days=22), RACE + timedelta(days=49), 3.4, "Base")
    assert block_errors([recovery(), ok], BLOCKS, [FORNELLS], REAL, TODAY, athlete=athlete) == []
    # sense perfil, res no canvia
    assert not any("sostre" in e for e in block_errors([recovery(), base], BLOCKS, [FORNELLS], REAL, TODAY))
