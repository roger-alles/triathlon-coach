"""Decisions de l'atleta sobre propostes del coach: Aplica, Descarta, Desfés.

    .venv/bin/python -m coach.decisions      # processa les pendents (cron cada 5 min)

L'app insereix files a coach_decision; aquí es reclamen una per una
(idempotent: status pending → processing) i cada una s'executa dins la seva
transacció:

  apply    només sobre un informe 'proposed'. Es torna a validar contra el pla
           VIU (semàntica + 15 regles): la proposta pot haver caducat si un
           diari ha tocat el pla entremig. Si passa, apply_to_db amb l'id de
           la decisió als efectes; l'informe passa a 'applied'.
  discard  només sobre 'proposed' → 'discarded'.
  undo     només sobre 'auto_applied' o 'applied'. Es nega si alguna fila que
           l'informe va crear ja té una versió posterior, ja està feta o a
           mitges, o té una activitat enllaçada. Si no: primer s'amaguen les
           files creades (superseded_by cap a la vella: desapareixen de tots
           els lectors), després es restauren les velles amb l'estat previ i
           els bricks tornen a penjar-ne. L'informe passa a 'undone'.

Una decisió que falla queda 'failed' amb el motiu; l'informe no canvia
d'estat, així l'atleta pot tornar-ho a intentar o descartar.

Peticions (athlete_request), després de les decisions:

  regenerate_macro          un macro nou (Opus), MACRO_DAILY_LIMIT al dia.
  free_text, scope 'week'   redisseny de la setmana `week_start` amb el text
                            de l'atleta (pestanya Setmana): coach.run replan,
                            s'aplica sol. REPLAN_DAILY_LIMIT al dia (3).
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from coach.blocks import apply_blocks_to_db, block_errors, undo_block_effects
from coach.plan_loader import plan_from_db
from coach.rules import primary_goal, validate_plan
from coach.run import (StaleProposal, apply_changes, apply_to_db, blocking_signatures,
                       replan_window, run_replan, run_report, semantic_errors)

ROOT = Path(__file__).parent.parent
MAX_REQUEST_CHARS = 1000
EFFECT_COLS = ("report_id", "kind", "session_id", "new_session_id",
               "prev_status", "prev_superseded_by", "block_id", "prev_values")


def _fail(conn, decision_id: int, reason: str) -> str:
    conn.execute("update coach_decision set status='failed', error=%s where id=%s",
                 (reason, decision_id))
    return "failed"


def _done(conn, decision_id: int) -> str:
    conn.execute("update coach_decision set status='done' where id=%s", (decision_id,))
    return "done"


def _report(conn, report_id: int) -> tuple[str, dict] | None:
    row = conn.execute("select proposal_status, output from coach_report where id=%s",
                       (report_id,)).fetchone()
    if row is None:
        return None
    output = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
    return row[0], output


def undo_blockers(conn, effects: list[dict]) -> list[str]:
    """Motius pels quals NO es pot desfer (llista buida = endavant)."""
    reasons = []
    for e in effects:
        if e["kind"] == "block_created":
            n = conn.execute("""select count(*) from plan_session where block_id=%s
                                and status='planned' and superseded_by is null""",
                             (e["block_id"],)).fetchone()
            if n and n[0]:
                reasons.append(f"el bloc {e['block_id']} ja té {n[0]} sessions planificades")
            continue
        if e["kind"] != "created":
            continue
        new_id = e["new_session_id"]
        row = conn.execute("select status, superseded_by from plan_session where id=%s",
                           (new_id,)).fetchone()
        if row is None:
            reasons.append(f"la sessió {new_id} ja no existeix")
            continue
        status, superseded_by = row
        if superseded_by is not None:
            reasons.append(f"la sessió {new_id} ja té una versió posterior")
        if status in ("completed", "partial"):
            reasons.append(f"la sessió {new_id} ja està {status}")
        if conn.execute("select 1 from activity where plan_session_id=%s limit 1",
                        (new_id,)).fetchone():
            reasons.append(f"la sessió {new_id} ja té una activitat enllaçada")
    return reasons


def _undo(conn, report_id: int) -> list[str]:
    rows = conn.execute(f"""select {", ".join(EFFECT_COLS)} from coach_report_effect
                            where report_id=%s order by id""", (report_id,)).fetchall()
    effects = [dict(zip(EFFECT_COLS, r)) for r in rows]
    blockers = undo_blockers(conn, effects)
    if blockers:
        return blockers
    # 1) amagar les files noves: apunten enrere a la vella (l'índex únic de
    #    clau/dia no admet la vella i la nova vives alhora)
    for e in effects:
        if e["kind"] == "created":
            if e["session_id"] == e["new_session_id"]:
                # un add: no hi ha fila vella; desfer-lo és cancel·lar la nova
                conn.execute("update plan_session set status='cancelled' where id=%s",
                             (e["new_session_id"],))
            else:
                conn.execute("update plan_session set superseded_by=%s where id=%s",
                             (e["session_id"], e["new_session_id"]))
    # 2) restaurar les velles amb l'estat que tenien, i els fills cap a elles
    for e in effects:
        if e["kind"] in ("moved", "superseded", "cancelled"):
            conn.execute("update plan_session set status=%s, superseded_by=%s where id=%s",
                         (e["prev_status"], e["prev_superseded_by"], e["session_id"]))
        if e["kind"] in ("moved", "superseded"):
            conn.execute("""update plan_session set chained_after=%s
                            where chained_after=%s and superseded_by is null""",
                         (e["session_id"], e["new_session_id"]))
    # 3) els blocs (macro), en ordre invers
    undo_block_effects(conn, [e for e in effects if e["kind"].startswith("block_")])
    return []


def process_decision(conn, decision: tuple, plan_loader=plan_from_db) -> str:
    """Una decisió: 'skipped' (ja reclamada), 'done' o 'failed'."""
    decision_id, report_id, kind = decision
    claimed = conn.execute("""update coach_decision set status='processing'
                              where id=%s and status='pending' returning id""",
                           (decision_id,)).fetchone()
    if claimed is None:
        return "skipped"
    report = _report(conn, report_id)
    if report is None:
        return _fail(conn, decision_id, f"l'informe {report_id} no existeix")
    status, output = report

    if kind == "discard":
        if status != "proposed":
            return _fail(conn, decision_id, f"només es pot descartar una proposta pendent ('proposed'; aquest informe és '{status}')")
        conn.execute("update coach_report set proposal_status='discarded' where id=%s", (report_id,))
        return _done(conn, decision_id)

    if kind == "apply":
        if status != "proposed":
            return _fail(conn, decision_id, f"només es pot aplicar una proposta pendent ('proposed'; aquest informe és '{status}')")
        changes = output.get("session_changes", [])
        block_changes = output.get("block_changes") or []
        plan, goals, history, athlete, blocks = plan_loader(conn)
        active = [s for s in plan if s.status not in ("cancelled", "moved")]
        plan_by_id = {s.id: s for s in active}
        today = date.today()
        errors = semantic_errors(changes, plan_by_id, athlete, blocks)
        if not errors and block_changes:
            errors += block_errors(block_changes, blocks, goals, history, today, plan=active,
                                   athlete=athlete)
        if not errors and active:
            preexisting = blocking_signatures(active, athlete, history, goals, today)
            candidate = apply_changes(active, changes, blocks)
            violations = validate_plan(candidate, athlete, history, goals,
                                       reference_date=today,
                                       plan_start=min(s.local_date for s in active))
            errors = [f"{v.rule}: {v.message}" for v in violations
                      if v.blocking and (v.rule, v.message) not in preexisting]
        if errors:
            return _fail(conn, decision_id, "la proposta ja no encaixa amb el pla viu: "
                         + "; ".join(errors))
        goal = primary_goal(goals)
        try:
            with conn.transaction():
                apply_to_db(conn, report_id, changes, decision_id=decision_id)
                if block_changes:
                    apply_blocks_to_db(conn, report_id, block_changes,
                                       goal_id=goal.id if goal else None,
                                       decision_id=decision_id)
        except StaleProposal as e:
            return _fail(conn, decision_id, f"proposta caducada: {e}")
        conn.execute("update coach_report set proposal_status='applied' where id=%s", (report_id,))
        return _done(conn, decision_id)

    if kind == "undo":
        if status not in ("auto_applied", "applied"):
            return _fail(conn, decision_id, f"només es pot desfer un informe aplicat (és {status})")
        blockers = _undo(conn, report_id)
        if blockers:
            return _fail(conn, decision_id, "no es pot desfer: " + "; ".join(blockers))
        conn.execute("update coach_report set proposal_status='undone' where id=%s", (report_id,))
        return _done(conn, decision_id)

    return _fail(conn, decision_id, f"decisió desconeguda: {kind}")


def _request_fail(conn, request_id: int, reason: str, report_id: int | None = None) -> str:
    conn.execute("update athlete_request set status='failed', error=%s, report_id=%s "
                 "where id=%s", (reason, report_id, request_id))
    return "failed"


def week_request(payload: dict, today: date) -> tuple[date, str] | str:
    """(dilluns, text) d'una petició de redisseny, o el motiu per rebutjar-la."""
    text = (payload.get("text") or "").strip()
    if not text:
        return "la petició no diu què vols canviar"
    if len(text) > MAX_REQUEST_CHARS:
        return f"la petició és massa llarga (màxim {MAX_REQUEST_CHARS} caràcters)"
    try:
        monday = date.fromisoformat(payload.get("week_start") or "")
    except ValueError:
        return "la petició no diu de quina setmana parla"
    if monday.weekday() != 0:
        return f"{monday} no és dilluns"
    if replan_window(monday, today) is None:
        return "aquesta setmana ja ha passat"
    return monday, text


def process_week_request(conn, request_id: int, payload: dict, run_week,
                         today: date | None = None, daily_limit: int | None = None) -> str:
    """Redisseny de la setmana. run_week(monday, text) -> run_cycle(...) dict."""
    today = today or date.today()
    if daily_limit is None:
        daily_limit = int(os.getenv("REPLAN_DAILY_LIMIT", "3"))
    parsed = week_request(payload, today)
    if isinstance(parsed, str):
        return _request_fail(conn, request_id, parsed)
    n = conn.execute("""select count(*) from coach_report where report_type='replan'
                        and created_at::date = current_date""").fetchone()
    if n and n[0] >= daily_limit:
        return _request_fail(conn, request_id, f"avui ja s'han fet {n[0]} redissenys (límit "
                                                f"{daily_limit}); demà en pots demanar més")
    out = run_week(*parsed)
    if not out["accepted"]:
        return _request_fail(conn, request_id, "el coach no ha trobat cap setmana que compleixi "
                                               "les regles; el pla no ha canviat",
                             out["report_id"])
    if out["proposal_status"] == "failed":
        return _request_fail(conn, request_id, "el pla ha canviat mentre el coach hi pensava; "
                                               "torna-ho a demanar", out["report_id"])
    conn.execute("update athlete_request set status='answered', report_id=%s where id=%s",
                 (out["report_id"], request_id))
    return "answered"


def process_request(conn, request: tuple, run_macro, daily_limit: int | None = None,
                    run_week=None) -> str:
    """Una petició de l'atleta: 'skipped' (ja reclamada), 'answered' o 'failed'.
    regenerate_macro i el redisseny de setmana (free_text amb scope 'week');
    la resta de tipus arriben amb la bústia (S5).
    MACRO_DAILY_LIMIT (per defecte 1) limita els macros per dia: és la crida cara."""
    request_id, kind, payload = request
    claimed = conn.execute("""update athlete_request set status='processing'
                              where id=%s and status='pending' returning id""",
                           (request_id,)).fetchone()
    if claimed is None:
        return "skipped"
    payload = payload or {}
    if kind == "free_text" and payload.get("scope") == "week" and run_week is not None:
        return process_week_request(conn, request_id, payload, run_week)
    if daily_limit is None:
        daily_limit = int(os.getenv("MACRO_DAILY_LIMIT", "1"))
    if kind != "regenerate_macro":
        return _request_fail(conn, request_id, f"petició '{kind}' encara no suportada")
    n = conn.execute("""select count(*) from coach_report where report_type='macro'
                        and created_at::date = current_date""").fetchone()
    if n and n[0] >= daily_limit:
        return _request_fail(conn, request_id, f"ja hi ha {n[0]} macro(s) d'avui (límit "
                                                f"{daily_limit}): descarta'l o aplica'l, i "
                                                f"demana'n un altre demà")
    report_id = run_macro()
    conn.execute("update athlete_request set status='answered', report_id=%s where id=%s",
                 (report_id, request_id))
    return "answered"


def main() -> None:
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")
    with psycopg.connect(url) as conn:
        pending = conn.execute("""select id, report_id, decision from coach_decision
                                  where status='pending' order by id""").fetchall()
        for decision in pending:
            try:
                with conn.transaction():
                    outcome = process_decision(conn, decision)
            except Exception as e:  # noqa: BLE001 — el motiu ha d'arribar a l'app
                with conn.transaction():
                    _fail(conn, decision[0], f"error inesperat: {e}")
                outcome = "failed"
            print(f"decisió {decision[0]} ({decision[2]} sobre informe {decision[1]}): {outcome}")
        requests = conn.execute("""select id, kind, payload from athlete_request
                                   where status='pending' order by id""").fetchall()
        if not pending and not requests:
            print("cap decisió pendent")

    # Les peticions criden el model (1-3 min amb Opus): mai amb una connexió
    # oberta al pooler. Cada petició obre la seva, i el macro les seves.
    for request in requests:
        try:
            with psycopg.connect(url) as conn:
                outcome = process_request(
                    conn, request,
                    run_macro=lambda: run_report("macro", url=url),
                    run_week=lambda monday, text: run_replan(url=url, week_start=monday,
                                                             request_text=text))
        except Exception as e:  # noqa: BLE001
            with psycopg.connect(url) as conn:
                _request_fail(conn, request[0], f"error inesperat: {e}")
            outcome = "failed"
        print(f"petició {request[0]} ({request[1]}): {outcome}")


if __name__ == "__main__":
    main()
