"""Tests del bucle del coach (spec §7 passos 2-5 i §12.4) — SENSE cridar l'API.

Un LLM fals serveix respostes desades a tests/fixtures/coach/ i es comprova
que el bucle reacciona bé a cadascuna: la vàlida s'accepta, la semànticament
invàlida provoca correcció, la que viola regles es rebutja i, si no es
corregeix, es descarta.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.models import Athlete, Block, History, Session
from coach.run import MAX_ATTEMPTS, apply_changes, coach_cycle, semantic_errors

FIXTURES = Path(__file__).parent / "fixtures" / "coach"
ATHLETE = Athlete(name="Roger", max_hr=211)
MON = date(2026, 10, 5)


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def make_plan():
    b = Block(id=1, phase="build", start_date=MON, end_date=MON + timedelta(days=6),
              target_weekly_hours=4)
    def easy(id, day_offset, sport, hours):
        sec = int(hours * 3600)
        return Session(id=id, local_date=MON + timedelta(days=day_offset),
                       sport=sport, session_type="easy", title=f"{sport}-{id}",
                       structure={"steps": [{"phase": "main", "duration_sec": sec,
                                             "target": {"type": "rpe", "value": 3}}]},
                       duration_sec_target=sec, block=b)
    return [
        Session(id=1, local_date=MON, sport="rest", session_type="full",
                title="Descans", priority="key", structure={"steps": []}, block=b),
        easy(2, 1, "swim", 1.0),
        easy(3, 3, "run", 1.2),
        easy(4, 5, "bike", 1.5),
    ]


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def generate(self, system, messages):
        self.calls += 1
        return self.outputs.pop(0), {"model": "fake", "input_tokens": 100,
                                     "output_tokens": 50}


def run_cycle(outputs):
    llm = FakeLLM(outputs)
    result = coach_cycle(llm=llm, system="ets el coach", context_json="{}",
                         plan=make_plan(), athlete=ATHLETE, history=History(),
                         goals=[], today=MON, report_type="daily")
    return result, llm


# ─── semàntica i aplicació (parts pures) ────────────────────────────

def test_semantic_errors_catch_missing_new_session_and_ghost_id():
    plan_by_id = {s.id: s for s in make_plan()}
    errors = semantic_errors(fixture("semantic_invalid")["session_changes"],
                             plan_by_id, ATHLETE)
    assert len(errors) == 2
    assert any("new_session" in e for e in errors)
    assert any("999" in e for e in errors)


def test_apply_changes_cancel_removes_and_move_redates():
    plan = make_plan()
    changes = [{"plan_session_id": 2, "action": "cancel", "reason": "x"},
               {"plan_session_id": 3, "action": "move",
                "new_date": (MON + timedelta(days=4)).isoformat(), "reason": "x"}]
    candidate = apply_changes(plan, changes)
    ids = [s.id for s in candidate]
    assert 2 not in ids                       # cancel·lada: fora del pla candidat
    moved = next(s for s in candidate if s.id == 3)
    assert moved.local_date == MON + timedelta(days=4)
    assert len(plan) == 4                     # el pla original no es toca


def test_apply_changes_replace_builds_new_session_with_old_block():
    plan = make_plan()
    structure = {"steps": [{"phase": "main", "duration_sec": 1800,
                            "target": {"type": "rpe", "value": 2}}]}
    changes = [{"plan_session_id": 4, "action": "replace", "reason": "x",
                "new_session": {"sport": "bike", "session_type": "recovery",
                                "title": "Rodatge regeneratiu",
                                "duration_sec_target": 1800,
                                "structure_json": json.dumps(structure)}}]
    # el bucle real hidrata "structure" via semantic_errors; aquí ho simulem
    changes[0]["new_session"]["structure"] = structure
    candidate = apply_changes(plan, changes)
    new = next(s for s in candidate if s.title == "Rodatge regeneratiu")
    assert new.block is plan[3].block and new.local_date == plan[3].local_date
    assert 4 not in [s.id for s in candidate]


# ─── el bucle sencer (spec §12.4) ───────────────────────────────────

def test_valid_response_accepted_first_attempt():
    result, llm = run_cycle([fixture("valid_daily")])
    assert result["accepted"] and llm.calls == 1
    assert result["validation_errors"] == []
    assert result["usage"]["input_tokens"] == 100


def test_semantic_failure_then_valid_is_corrected():
    result, llm = run_cycle([fixture("semantic_invalid"), fixture("valid_daily")])
    assert result["accepted"] and llm.calls == 2
    assert len(result["validation_errors"]) == 1   # una tanda d'infraccions registrada
    assert any("999" in e for e in result["validation_errors"][0])


def test_rule_violation_rejected_and_discarded_after_max_attempts():
    result, llm = run_cycle([fixture("rule_violating")] * MAX_ATTEMPTS)
    assert not result["accepted"]
    assert llm.calls == MAX_ATTEMPTS
    # el motiu és concret: cancel·lar el descans viola R5
    assert any("R5" in e for errors in result["validation_errors"] for e in errors)


def test_main_holds_no_db_connection_while_the_model_thinks(monkeypatch):
    # 30-31/08: el pooler de Supabase va matar la connexió durant la crida al
    # model (1-3 min) i write_report va fallar: informe generat, pagat i perdut.
    # Contracte: llegir amb una connexió, tancar-la, cridar el model, i obrir-ne
    # una de nova per persistir.
    import coach.run as run

    open_conns = []
    connect_calls = []

    class FakeConn:
        def __enter__(self):
            open_conns.append(self)
            return self
        def __exit__(self, *a):
            open_conns.remove(self)
        def transaction(self):
            return self

    def fake_connect(url):
        connect_calls.append(url)
        return FakeConn()

    def fake_cycle(**kw):
        assert open_conns == [], "coach_cycle s'ha cridat amb una connexió oberta"
        return {"accepted": True, "output": {"session_changes": [], "readiness":
                {"verdict": "green", "drivers": []}, "summary": "s", "rationale": "r"},
                "usage": {"model": "m", "input_tokens": 1, "output_tokens": 1},
                "validation_errors": []}

    written = []
    monkeypatch.setattr(run.psycopg, "connect", fake_connect)
    monkeypatch.setattr(run, "build_context",
                        lambda conn, today, report_for=None: {"today": str(today)})
    monkeypatch.setattr(run, "plan_from_db", lambda conn: ([], None, None, None))
    monkeypatch.setattr(run, "coach_cycle", fake_cycle)
    monkeypatch.setattr(run, "CoachLLM", lambda: None)
    monkeypatch.setattr(run, "load_prompt", lambda name: "prompt")
    monkeypatch.setattr(run, "write_report", lambda *a: written.append(a))
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setattr(sys, "argv", ["run.py", "daily", "--dry-run"])

    run.main()

    assert len(connect_calls) == 2   # una per llegir, una per escriure
    assert len(written) == 1         # l'informe s'ha persistit
