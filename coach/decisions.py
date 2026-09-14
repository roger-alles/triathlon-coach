"""Decisions de l'atleta sobre propostes del coach: Aplica, Descarta, Desfés.

    .venv/bin/python -m coach.decisions      # processa les pendents (cron cada 5 min)

L'app insereix files a coach_decision; aquí es reclamen una per una
(idempotent: status pending → processing) i cada una s'executa dins la seva
transacció:

  apply    només sobre un informe 'proposed'. Es torna a validar contra el pla
           VIU (semàntica + 14 regles): la proposta pot haver caducat si un
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
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from coach.plan_loader import plan_from_db
from coach.rules import validate_plan
from coach.run import (StaleProposal, apply_changes, apply_to_db, blocking_signatures,
                       semantic_errors)

ROOT = Path(__file__).parent.parent
EFFECT_COLS = ("report_id", "kind", "session_id", "new_session_id",
               "prev_status", "prev_superseded_by")


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
        plan, goals, history, athlete, blocks = plan_loader(conn)
        active = [s for s in plan if s.status not in ("cancelled", "moved")]
        plan_by_id = {s.id: s for s in active}
        errors = semantic_errors(changes, plan_by_id, athlete, blocks)
        if not errors and active:
            today = date.today()
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
        try:
            with conn.transaction():
                apply_to_db(conn, report_id, changes, decision_id=decision_id)
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
        if not pending:
            print("cap decisió pendent")


if __name__ == "__main__":
    main()
