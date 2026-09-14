"""Tests del bucle del coach (spec §7 passos 2-5 i §12.4) — SENSE cridar l'API.

Un LLM fals serveix respostes desades a tests/fixtures/coach/ i es comprova
que el bucle reacciona bé a cadascuna: la vàlida s'accepta, la semànticament
invàlida provoca correcció, la que viola regles es rebutja i, si no es
corregeix, es descarta.
"""

import json
import sys

import pytest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.models import Athlete, Block, History, Session
from coach.llm import OutputCutOff
from coach.run import (MAX_ATTEMPTS, StaleProposal, apply_changes, apply_to_db,
                       coach_cycle, semantic_errors, write_report)

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

    def generate(self, system, messages, report_type="daily"):
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
    monkeypatch.setattr(run, "plan_from_db", lambda conn, today=None: ([], [], None, None, []))
    monkeypatch.setattr(run, "coach_cycle", fake_cycle)
    monkeypatch.setattr(run, "CoachLLM", lambda: None)
    monkeypatch.setattr(run, "load_prompt", lambda name: "prompt")
    monkeypatch.setattr(run, "apply_mode", lambda conn: "dry_run")
    monkeypatch.setattr(run, "write_report", lambda *a, **kw: written.append((a, kw)) or 1)
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setattr(sys, "argv", ["run.py", "daily", "--dry-run"])

    run.main()

    assert len(connect_calls) == 2   # una per llegir, una per escriure
    assert len(written) == 1         # l'informe s'ha persistit


# ─── el model es queda sense tokens: una tanda més, no un crash ──────

class CutOffThenValid:
    def __init__(self):
        self.calls = 0

    def generate(self, system, messages, report_type="daily"):
        self.calls += 1
        if self.calls == 1:
            raise OutputCutOff("tallada")
        return fixture("valid_daily"), {"model": "fake", "input_tokens": 1, "output_tokens": 1}


def test_cut_off_output_becomes_feedback_not_a_crash():
    llm = CutOffThenValid()
    result = coach_cycle(llm=llm, system="s", context_json="{}", plan=make_plan(),
                         athlete=ATHLETE, history=History(), goals=[], today=MON,
                         report_type="daily")
    assert result["accepted"] and llm.calls == 2
    assert any("tallada" in e for e in result["validation_errors"][0])


# ─── apply_to_db: guardes, columnes senceres, bricks, efectes ────────

class DbConn:
    """Conn falsa: estat de les sessions per id, ids nous creixents, SQL registrat."""

    def __init__(self, sessions):
        self.sessions = dict(sessions)   # id -> (status, superseded_by)
        self.calls = []
        self.next_id = 100

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))
        s = self.calls[-1][0].lower()
        row = None
        if s.startswith("select status, superseded_by"):
            row = self.sessions.get(params[0])
        elif s.startswith("insert into plan_session"):
            self.next_id += 1
            row = (self.next_id,)
        elif s.startswith("select id, goal_id from plan_block"):
            row = getattr(self, "blocks", {}).get(params[0])
        elif s.startswith("select id from plan_session where local_date"):
            row = None   # cap sessió viva amb aquell (dia, esport): només les del mateix informe
        elif s.startswith("insert into coach_report ("):
            row = (7,)
        class R:
            def fetchone(self_inner):
                return row
        return R()

    def sql(self, needle):
        return [c for c in self.calls if needle in c[0].lower()]


def test_apply_cancel_records_previous_status():
    conn = DbConn({2: ("planned", None)})
    effects = apply_to_db(conn, 7, [{"plan_session_id": 2, "action": "cancel", "reason": "x"}])
    assert conn.sql("set status='cancelled'")[0][1] == (2,)
    assert effects == [{"report_id": 7, "kind": "cancelled", "session_id": 2,
                        "new_session_id": None, "prev_status": "planned",
                        "prev_superseded_by": None}]
    inserted = conn.sql("insert into coach_report_effect")
    assert len(inserted) == 1 and inserted[0][1][:3] == (7, "cancelled", 2)


def test_apply_move_copies_every_column_relinks_children_and_records_effects():
    conn = DbConn({3: ("planned", None)})
    effects = apply_to_db(conn, 7, [{"plan_session_id": 3, "action": "move",
                                     "new_date": "2026-10-09", "reason": "pluja"}])
    insert = conn.sql("insert into plan_session")[0][0]
    for col in ("chained_after", "test_spec", "transition_practice", "distance_m_target"):
        assert col in insert, col
    # el brick que penjava de la sessió vella ara penja de la nova
    relink = conn.sql("set chained_after=")[0]
    assert relink[1] == (101, 3)
    assert conn.sql("set status='moved'")[0][1] == (101, 3)
    kinds = [(e["kind"], e["session_id"], e["new_session_id"]) for e in effects]
    assert kinds == [("created", 3, 101), ("moved", 3, 101)]
    assert effects[1]["prev_status"] == "planned"


def test_apply_modify_keeps_distance_and_supersedes():
    conn = DbConn({4: ("planned", None)})
    ns = {"sport": "bike", "session_type": "recovery", "title": "Suau",
          "structure": {"steps": []}, "duration_sec_target": 1800}
    effects = apply_to_db(conn, 7, [{"plan_session_id": 4, "action": "modify",
                                     "reason": "x", "new_session": ns}])
    insert = conn.sql("insert into plan_session")[0][0]
    assert "chained_after" in insert and "distance_m_target" in insert
    assert conn.sql("set superseded_by=")[0][1] == (101, 4)
    assert [e["kind"] for e in effects] == ["created", "superseded"]


def test_apply_refuses_stale_or_non_planned_sessions():
    with pytest.raises(StaleProposal):
        apply_to_db(DbConn({5: ("planned", 77)}), 7,
                    [{"plan_session_id": 5, "action": "cancel", "reason": "x"}])
    with pytest.raises(StaleProposal):
        apply_to_db(DbConn({5: ("completed", None)}), 7,
                    [{"plan_session_id": 5, "action": "cancel", "reason": "x"}])
    conn = DbConn({})
    with pytest.raises(StaleProposal):
        apply_to_db(conn, 7, [{"plan_session_id": 9, "action": "cancel", "reason": "x"}])
    assert not conn.sql("update")   # res tocat


def test_keep_touches_nothing():
    conn = DbConn({2: ("planned", None)})
    assert apply_to_db(conn, 7, [{"plan_session_id": 2, "action": "keep", "reason": ""}]) == []
    assert not conn.sql("update") and not conn.sql("insert")


# ─── write_report: retorna id, estat de proposta i classificació ─────

def _result():
    return {"accepted": True, "usage": {"model": "m", "input_tokens": 1, "output_tokens": 1},
            "validation_errors": [], "warnings": [],
            "output": {"summary": "S", "rationale": "R", "session_changes": [],
                       "questions_for_athlete": []}}


def test_write_report_returns_id_and_persists_proposal_state():
    conn = DbConn({})
    rid = write_report(conn, "daily", {"today": "x"}, _result(), MON,
                       proposal_status="proposed", scope="sessions",
                       classification={"auto": False, "reasons": ["horitzó"]})
    assert rid == 7
    sql, params = conn.sql("insert into coach_report (")[0]
    assert "proposal_status" in sql and "classification" in sql
    assert "proposed" in params
    assert any(isinstance(p, str) and "horitzó" in p for p in params)


def test_write_report_summary_prefix_follows_the_state():
    def summary(status):
        conn = DbConn({})
        write_report(conn, "daily", {}, _result(), MON, proposal_status=status,
                     scope="sessions", classification=None)
        return next(p for p in conn.sql("insert into coach_report (")[0][1]
                    if isinstance(p, str) and p.startswith("*(") or
                    (isinstance(p, str) and p.startswith("## ")))
    assert summary("none").startswith("*(dry-run")
    assert summary("proposed").startswith("*(proposta")
    assert summary("auto_applied").startswith("*(aplicat")
    assert summary("failed").startswith("*(no aplicat")


# ─── S4a: add (sessions noves dins d'un bloc) ────────────────────────

def _block():
    return Block(id=1, phase="build", start_date=MON, end_date=MON + timedelta(days=6),
                 target_weekly_hours=4, goal_id=2)


def add_change(day_offset=2, sport="bike", title="Bici nova", minutes=60, parent=None, **extra):
    sec = minutes * 60
    ns = {"local_date": (MON + timedelta(days=day_offset)).isoformat(), "sport": sport,
          "session_type": "easy", "title": title, "duration_sec_target": sec,
          "structure_json": json.dumps({"steps": [{"phase": "main", "duration_sec": sec,
                                                   "target": {"type": "rpe", "value": 3}}]})}
    if parent:
        ns["parent_of_day"] = parent
    ns.update(extra)
    return {"action": "add", "reason": "cal volum", "new_session": ns}


def test_semantic_add_requires_date_block_and_parent_that_exists():
    plan_by_id = {s.id: s for s in make_plan()}
    blocks = [_block()]
    ok = add_change()
    assert semantic_errors([ok], plan_by_id, ATHLETE, blocks=blocks) == []
    # sense local_date
    bad = add_change(); del bad["new_session"]["local_date"]
    assert any("local_date" in e for e in semantic_errors([bad], plan_by_id, ATHLETE, blocks=blocks))
    # fora de tot bloc: cal macro
    outside = add_change(day_offset=20)
    assert any("bloc" in e for e in semantic_errors([outside], plan_by_id, ATHLETE, blocks=blocks))
    # brick que penja d'una bici que no existeix aquell dia (dia 2 no té bici al pla)
    orphan = add_change(day_offset=2, sport="run", title="brick", minutes=10, parent="bike")
    assert any("parent_of_day" in e for e in semantic_errors([orphan], plan_by_id, ATHLETE, blocks=blocks))
    # però sí si la bici s'afegeix al mateix informe
    assert semantic_errors([ok, orphan], plan_by_id, ATHLETE, blocks=blocks) == []
    # o si ja és al pla (dia 5 té la bici 4)
    brick5 = add_change(day_offset=5, sport="run", title="brick", minutes=10, parent="bike")
    assert semantic_errors([brick5], plan_by_id, ATHLETE, blocks=blocks) == []


def test_semantic_non_add_actions_still_need_plan_session_id():
    plan_by_id = {s.id: s for s in make_plan()}
    errs = semantic_errors([{"action": "cancel", "reason": "x"}], plan_by_id, ATHLETE)
    assert errs and "plan_session_id" in errs[0]


def test_apply_changes_add_builds_a_session_in_its_block_and_chains_the_brick():
    plan = make_plan()
    blocks = [_block()]
    changes = [add_change(), add_change(day_offset=2, sport="run", title="brick", minutes=10, parent="bike")]
    semantic_errors(changes, {s.id: s for s in plan}, ATHLETE, blocks=blocks)  # parseja structure
    candidate = apply_changes(plan, changes, blocks=blocks)
    new = [s for s in candidate if s.id is not None and s.id < 0]
    assert len(new) == 2 and {s.title for s in new} == {"Bici nova", "brick"}
    bici = next(s for s in new if s.sport == "bike")
    brick = next(s for s in new if s.sport == "run")
    assert bici.block is blocks[0] and bici.local_date == MON + timedelta(days=2)
    assert bici.priority == "support" and bici.status == "planned"
    assert brick.chained is True and bici.chained is False
    assert len(candidate) == len(plan) + 2   # l'original no es toca


def test_apply_to_db_add_inserts_in_two_passes_and_links_the_brick_to_its_parent():
    conn = DbConn({})
    conn.blocks = {(MON + timedelta(days=2)): (1, 2)}   # dia -> (block_id, goal_id)
    changes = [add_change(), add_change(day_offset=2, sport="run", title="brick", minutes=10, parent="bike")]
    for c in changes:
        c["new_session"]["structure"] = json.loads(c["new_session"]["structure_json"])
    effects = apply_to_db(conn, 7, changes)
    inserts = conn.sql("insert into plan_session")
    assert len(inserts) == 2
    # la fila nova neix amb bloc i objectiu del bloc, versió 1, creada pel coach
    assert "block_id" in inserts[0][0] and "'coach'" in inserts[0][0]
    # segona passada: el brick (id 102) penja de la bici (id 101) creada al mateix informe
    chain = conn.sql("set chained_after=")
    assert chain and chain[0][1] == (101, 102)
    kinds = [(e["kind"], e["session_id"], e["new_session_id"]) for e in effects]
    assert kinds == [("created", 101, 101), ("created", 102, 102)]


def test_apply_to_db_add_without_block_is_stale():
    conn = DbConn({})
    conn.blocks = {}
    c = add_change(); c["new_session"]["structure"] = {"steps": []}
    with pytest.raises(StaleProposal):
        apply_to_db(conn, 7, [c])


def test_write_report_weekly_window_is_next_monday_to_sunday():
    conn = DbConn({})
    result = {"output": {"summary": "s", "rationale": "r", "session_changes": []},
              "accepted": True, "usage": {"model": "m", "input_tokens": 1, "output_tokens": 1},
              "validation_errors": [], "warnings": []}
    sunday = date(2026, 9, 20)
    write_report(conn, "weekly", {}, result, sunday, proposal_status="none")
    params = conn.sql("insert into coach_report (")[0][1]
    assert params[1] == date(2026, 9, 21) and params[2] == date(2026, 9, 27)
    # el diari no canvia: avui + 3
    write_report(conn, "daily", {}, result, sunday, proposal_status="none")
    params = conn.sql("insert into coach_report (")[1][1]
    assert params[1] == sunday and params[2] == sunday + timedelta(days=3)


# ─── violacions preexistents: el coach no pot empitjorar, però no se'l castiga ──

def test_preexisting_blocking_violation_becomes_a_warning_not_a_rejection():
    # 14/09: amb hores reals, la setmana en curs ja viola R1 (+37%) abans que el
    # coach digui res. Un informe que ho manté tot (keep) s'ha d'acceptar amb
    # l'R1 com a avís; un que empitjora la setmana sí que es bloqueja.
    plan = make_plan()   # 3,7 h aquesta setmana
    # per sobre del sòl de volum de R1: dupliquem cada sessió d'entrenament
    for s in plan:
        if s.sport != "rest":
            s.duration_sec_target *= 2
            s.structure["steps"][0]["duration_sec"] *= 2
    real = History(weekly_hours={MON - timedelta(weeks=i): 3.0 for i in range(1, 5)})
    keep_all = {"session_changes": [{"plan_session_id": s.id, "action": "keep", "reason": ""} for s in plan],
                "readiness": {"verdict": "green", "drivers": []}, "summary": "s", "rationale": "r",
                "flags": [], "questions_for_athlete": []}
    result = coach_cycle(llm=FakeLLM([keep_all]), system="", context_json="{}", plan=plan,
                         athlete=ATHLETE, history=real, goals=[], today=MON, report_type="daily")
    assert result["accepted"] is True
    assert any(w.startswith("R1") for w in result["warnings"])

    # allargar la bici del dissabte de 3 h a 5 h empitjora la rampa: bloqueig nou
    sec = 5 * 3600
    worse = dict(keep_all, session_changes=[
        {"plan_session_id": 4, "action": "modify", "reason": "més volum",
         "new_session": {"sport": "bike", "session_type": "long", "title": "Llarga",
                         "duration_sec_target": sec,
                         "structure_json": json.dumps({"steps": [{"phase": "main", "duration_sec": sec,
                                                                  "target": {"type": "rpe", "value": 3}}]})}}])
    result = coach_cycle(llm=FakeLLM([worse] * MAX_ATTEMPTS), system="", context_json="{}", plan=plan,
                         athlete=ATHLETE, history=real, goals=[], today=MON, report_type="daily")
    assert result["accepted"] is False
    assert any("R1" in e for e in result["validation_errors"][0])
