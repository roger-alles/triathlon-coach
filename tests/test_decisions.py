"""Decisions de l'atleta sobre propostes del coach (Aplica / Descarta / Desfés).

Sense BD: una connexió falsa que respon per fragment de SQL i registra tot el
que s'executa. Els efectes (coach_report_effect) són el rastre que fa possible
desfer; sense ells no hi hauria manera de saber què va tocar un informe.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.decisions import process_decision, undo_blockers


class Conn:
    def __init__(self, *, decision, report=None, effects=(), sessions=None,
                 linked_activity_ids=(), claimable=True):
        self.decision = decision          # (id, report_id, decision)
        self.report = report              # (proposal_status, output_json)
        self.effects = list(effects)      # rows of coach_report_effect
        self.sessions = dict(sessions or {})   # id -> (status, superseded_by)
        self.linked = set(linked_activity_ids)
        self.claimable = claimable
        self.calls = []
        self.next_id = 200

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        self.calls.append((s, params))
        rows = []
        if "update coach_decision set status='processing'" in s:
            rows = [(self.decision[0],)] if self.claimable else []
        elif "select proposal_status, output from coach_report" in s:
            rows = [self.report] if self.report else []
        elif "from coach_report_effect" in s:
            rows = self.effects
        elif s.startswith("select status, superseded_by from plan_session"):
            r = self.sessions.get(params[0])
            rows = [r] if r else []
        elif "from activity where plan_session_id" in s:
            rows = [(1,)] if params[0] in self.linked else []
        elif s.startswith("insert into plan_session") or s.startswith("insert into plan_block"):
            self.next_id += 1
            rows = [(self.next_id,)]
        elif "update athlete_request set status='processing'" in s:
            rows = [(params[0],)] if getattr(self, "request_claimable", True) else []
        elif "from coach_report where report_type='macro'" in s:
            rows = [(getattr(self, "macro_today", 0),)]
        conn = self
        class R:
            def fetchone(self_inner):
                return rows[0] if rows else None
            def fetchall(self_inner):
                return rows
            def __iter__(self_inner):
                return iter(rows)
        return R()

    def sql(self, needle):
        return [c for c in self.calls if needle in c[0]]


def proposal(changes):
    return ("proposed", json.dumps({"session_changes": changes}))


def test_claim_is_idempotent_a_decision_already_taken_is_skipped():
    conn = Conn(decision=(1, 7, "discard"), report=proposal([]), claimable=False)
    assert process_decision(conn, (1, 7, "discard"), plan_loader=None) == "skipped"
    assert not conn.sql("update coach_report")


def test_discard_marks_the_proposal_and_the_decision():
    conn = Conn(decision=(1, 7, "discard"), report=proposal([]))
    assert process_decision(conn, (1, 7, "discard"), plan_loader=None) == "done"
    assert conn.sql("set proposal_status='discarded'")[0][1] == (7,)
    assert conn.sql("update coach_decision set status='done'")[0][1] == (1,)


def test_apply_refuses_a_report_that_is_not_a_pending_proposal():
    conn = Conn(decision=(1, 7, "apply"), report=("none", "{}"))
    assert process_decision(conn, (1, 7, "apply"), plan_loader=None) == "failed"
    failed = conn.sql("update coach_decision set status='failed'")[0]
    assert "proposed" in failed[1][0]
    assert not conn.sql("update plan_session")


def test_apply_revalidates_against_the_live_plan_and_applies_with_the_decision_id(monkeypatch):
    from coach.models import Athlete, Block, History, Session
    from datetime import timedelta
    MON = date(2026, 10, 5)
    b = Block(id=1, phase="build", start_date=MON, end_date=MON + timedelta(days=6))
    live = [Session(id=3, local_date=MON + timedelta(days=2), sport="bike", session_type="easy",
                    title="bici", block=b, duration_sec_target=3600,
                    structure={"steps": [{"phase": "main", "duration_sec": 3600,
                                          "target": {"type": "rpe", "value": 3}}]}),
            Session(id=1, local_date=MON, sport="rest", session_type="full", title="Descans",
                    priority="key", structure={"steps": []}, block=b)]
    changes = [{"plan_session_id": 3, "action": "cancel", "reason": "pluja"}]
    conn = Conn(decision=(1, 7, "apply"), report=proposal(changes),
                sessions={3: ("planned", None)})
    loader = lambda c: (live, [], History(), Athlete(name="R", max_hr=211), [b])
    assert process_decision(conn, (1, 7, "apply"), plan_loader=loader) == "done"
    assert conn.sql("set status='cancelled'")[0][1] == (3,)
    effect = conn.sql("insert into coach_report_effect")[0][1]
    assert effect[0] == 7 and effect[-1] == 1          # report_id, decision_id
    assert conn.sql("set proposal_status='applied'")[0][1] == (7,)


def test_apply_fails_cleanly_when_the_proposal_went_stale():
    from coach.models import Athlete, History
    changes = [{"plan_session_id": 3, "action": "cancel", "reason": "x"}]
    conn = Conn(decision=(1, 7, "apply"), report=proposal(changes),
                sessions={3: ("planned", None)})
    # el pla viu ja no té la sessió 3: semantic_errors la rebutja
    loader = lambda c: ([], [], History(), Athlete(name="R", max_hr=211), [])
    assert process_decision(conn, (1, 7, "apply"), plan_loader=loader) == "failed"
    assert not conn.sql("set status='cancelled'")
    assert not conn.sql("set proposal_status='applied'")   # segueix proposed


def test_undo_blockers_name_why_it_cannot_be_undone():
    effects = [{"kind": "created", "session_id": 3, "new_session_id": 101,
                "prev_status": None, "prev_superseded_by": None}]
    assert undo_blockers(Conn(decision=None, sessions={101: ("completed", None)}), effects)
    assert undo_blockers(Conn(decision=None, sessions={101: ("planned", 150)}), effects)
    assert undo_blockers(Conn(decision=None, sessions={101: ("planned", None)},
                              linked_activity_ids=[101]), effects)
    assert undo_blockers(Conn(decision=None, sessions={101: ("planned", None)}), effects) == []


def test_undo_reverses_effects_in_order_hiding_new_rows_before_restoring_old():
    effects = [(7, "created", 3, 101, None, None),
               (7, "moved", 3, 101, "planned", None),
               (7, "cancelled", 5, None, "planned", None)]
    conn = Conn(decision=(2, 7, "undo"), report=("auto_applied", "{}"), effects=effects,
                sessions={101: ("planned", None), 3: ("moved", 101), 5: ("cancelled", None)})
    assert process_decision(conn, (2, 7, "undo"), plan_loader=None) == "done"
    updates = [c for c in conn.calls if c[0].startswith("update plan_session")]
    # 1) amaga la fila nova (apunta enrere a la vella), 2) restaura la vella,
    # 3) els fills tornen a penjar de la vella, 4) la cancel·lada torna a pendent
    assert "set superseded_by=%s where id=%s" in updates[0][0] and updates[0][1] == (3, 101)
    assert updates[1][1] == ("planned", None, 3)
    assert "set chained_after=%s where chained_after=%s" in updates[2][0] and updates[2][1] == (3, 101)
    assert updates[3][1] == ("planned", None, 5)
    assert conn.sql("set proposal_status='undone'")[0][1] == (7,)


def test_undo_refuses_when_something_already_happened_on_a_created_row():
    effects = [(7, "created", 3, 101, None, None), (7, "moved", 3, 101, "planned", None)]
    conn = Conn(decision=(2, 7, "undo"), report=("applied", "{}"), effects=effects,
                sessions={101: ("completed", None)})
    assert process_decision(conn, (2, 7, "undo"), plan_loader=None) == "failed"
    assert not [c for c in conn.calls if c[0].startswith("update plan_session")]


def test_undo_only_applies_to_applied_reports():
    conn = Conn(decision=(2, 7, "undo"), report=("proposed", "{}"))
    assert process_decision(conn, (2, 7, "undo"), plan_loader=None) == "failed"


def test_undo_of_an_added_session_cancels_it_instead_of_pointing_back():
    # S4a: un add no té fila vella a què apuntar (session_id == new_session_id):
    # desfer-lo és cancel·lar la fila nova. La resta d'efectes no canvien.
    conn = Conn(decision=(1, 7, "undo"), report=("applied", "{}"),
                effects=[(7, "created", 300, 300, None, None)],
                sessions={300: ("planned", None)})
    assert process_decision(conn, (1, 7, "undo"), plan_loader=None) == "done"
    cancel = conn.sql("set status='cancelled'")
    assert cancel and cancel[0][1] == (300,)
    assert not conn.sql("set superseded_by=")
    assert conn.sql("set proposal_status='undone'")[0][1] == (7,)


# ─── S3: blocs i peticions ───────────────────────────────────────────

def test_apply_a_macro_proposal_writes_the_blocks_in_the_same_transaction():
    from coach.models import Athlete, Block, Goal, History
    race = date(2026, 9, 27)
    goal = Goal(name="Fornells", discipline="triathlon", event_date=race, priority="A", id=2,
                profile={"target_times_sec": {"total": [8110, 7470, 6895]}})
    taper = Block(id=8, phase="taper", start_date=date(2026, 9, 21), end_date=race, target_weekly_hours=3.5, goal_id=2)
    output = json.dumps({"session_changes": [], "block_changes": [
        {"action": "add", "reason": "x", "new_block": {"phase": "recovery", "name": "Rec",
         "start_date": "2026-09-28", "end_date": "2026-10-18", "target_weekly_hours": 3.0}}]})
    conn = Conn(decision=(1, 7, "apply"), report=("proposed", output))
    conn.blocks = {}
    loader = lambda c: ([], [goal], History(), Athlete(name="R", max_hr=211), [taper])
    assert process_decision(conn, (1, 7, "apply"), plan_loader=loader) == "done"
    ins = conn.sql("insert into plan_block")
    assert len(ins) == 1 and ins[0][1][0] == 2          # goal_id de l'A més proper
    assert conn.sql("insert into coach_report_effect")[0][1][1] == "block_created"
    assert conn.sql("set proposal_status='applied'")[0][1] == (7,)


def test_undo_reverts_block_effects_too():
    conn = Conn(decision=(1, 7, "undo"), report=("applied", "{}"),
                effects=[(7, "block_created", None, None, None, None, 101, None)])
    assert process_decision(conn, (1, 7, "undo"), plan_loader=None) == "done"
    assert conn.sql("update plan_block set status='cancelled'")[0][1] == (101,)


def test_regenerate_macro_request_runs_the_macro_once_a_day():
    from coach.decisions import process_request
    runs = []
    conn = Conn(decision=(0, 0, ""))
    conn.macro_today = 0
    conn.request_claimable = True
    outcome = process_request(conn, (5, "regenerate_macro", {}), run_macro=lambda: runs.append(1) or 99)
    assert outcome == "answered" and runs == [1]
    assert conn.sql("set status='answered', report_id=%s")[0][1] == (99, 5)
    # segona petició el mateix dia: no es gasta un altre macro
    conn2 = Conn(decision=(0, 0, ""))
    conn2.macro_today = 1
    conn2.request_claimable = True
    outcome = process_request(conn2, (6, "regenerate_macro", {}), run_macro=lambda: runs.append(2))
    assert outcome == "failed" and runs == [1]
    assert "avui" in conn2.sql("set status='failed'")[0][1][0]
