"""El bucle de l'entrenador (spec §7): context → model → validació → aplicar.

    1. Context determinista (coach/context.py)
    2. Crida amb sortida estructurada (coach/llm.py)
    3. Validació: semàntica (ids, new_session, contracte §6) + regles §8
    4. Infraccions → es tornen al model. MAX_ATTEMPTS intents en total.
    5. Si falla: es descarta, el pla queda intacte, tot registrat.
    6. Si s'accepta: canvis amb versionat (superseded_by) — res s'esborra mai.

Ús:
    .venv/bin/python -m coach.run daily [--dry-run]
    .venv/bin/python -m coach.run weekly [--dry-run]

El mode d'aplicació es llegeix de la BD (app_setting.coach_apply_mode, que
l'app pot canviar): 'dry_run' fa el cicle sencer (amb crida real a l'API)
però no escriu res al pla; 'hybrid' aplica sol els canvis petits (coach/
classify.py) i deixa la resta com a proposta pendent per a l'app. --dry-run
força dry_run sigui quin sigui el valor de la BD. Fins a la cursa del 27S el
valor és dry_run: la spec mana no tocar el pla de Fornells.

--tomorrow és el preview del vespre: build_context() rep sempre el dia real
com a `today` i, a més, `report_for=demà` — el snapshot porta totes dues
dates (i "mode": "evening_preview") en lloc de fingir que avui és demà.
S'ha triat un únic prompt (coach/prompts/daily-v1.md) que explica tots dos
camps i com parlar-ne segons el mode, en lloc de duplicar-lo en un fitxer
evening-v1.md: el contingut (regles de periodització, to, format) és el
mateix; només canvia de quin dia es parla i en quin temps verbal.
`report_type='daily'` es manté a la BD en tots dos casos.
"""

import argparse
import dataclasses
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from coach.classify import classify
from coach.context import build_context
from coach.llm import CoachLLM, OutputCutOff, load_prompt
from coach.plan_loader import plan_from_db
from coach.models import Athlete, History, Session, Violation
from coach.rules import validate_plan
from coach.settings import apply_mode
from coach.structure import validate_structure

ROOT = Path(__file__).parent.parent
MAX_ATTEMPTS = 3  # 1 proposta + 2 correccions (spec §7 pas 4)

NEW_SESSION_REQUIRED = ("sport", "session_type", "title", "structure_json")

# Columnes que una versió nova hereta de la vella. Fins al 10/09 modify/move
# n'ometien chained_after, test_spec, transition_practice (i modify,
# distance_m_target): el brick perdia la bici pare i R14/R3 fallaven després.
INHERITED = ("goal_id", "block_id", "is_test", "test_spec", "rehearses_goal",
             "is_goal_event", "chained_after", "transition_practice")


class StaleProposal(Exception):
    """La proposta parla d'una sessió que ja no és la viva (o ja no és pendent)."""


def semantic_errors(changes: list[dict], plan_by_id: dict[int, Session],
                    athlete: Athlete) -> list[str]:
    """Errors de forma que no cal cap regla per detectar.

    Efecte lateral volgut: si structure_json parseja bé, es deixa parsejada a
    new_session["structure"] perquè apply_changes i apply_to_db la reutilitzin.
    """
    errors = []
    for i, change in enumerate(changes):
        where = f"session_changes[{i}]"
        session = plan_by_id.get(change["plan_session_id"])
        if session is None:
            errors.append(f"{where}: plan_session_id {change['plan_session_id']} "
                          f"no existeix al pla")
            continue
        action = change["action"]
        if action in ("modify", "replace"):
            new_session = change.get("new_session")
            if not new_session:
                errors.append(f"{where}: action '{action}' sense new_session")
                continue
            missing = [f for f in NEW_SESSION_REQUIRED if not new_session.get(f)]
            if missing:
                errors.append(f"{where}: new_session sense {missing}")
                continue
            try:
                new_session["structure"] = json.loads(new_session["structure_json"])
            except json.JSONDecodeError as e:
                errors.append(f"{where}.new_session.structure_json: JSON invàlid ({e})")
                continue
            for e in validate_structure(new_session["structure"],
                                        new_session["sport"], athlete):
                errors.append(f"{where}.new_session: {e}")
        if action == "move" and not change.get("new_date"):
            errors.append(f"{where}: action 'move' sense new_date")
    return errors


def apply_changes(plan: list[Session], changes: list[dict]) -> list[Session]:
    """Pla candidat amb els canvis aplicats (en memòria; l'original no es toca)."""
    candidate = {s.id: s for s in plan}
    for change in changes:
        session = candidate[change["plan_session_id"]]
        action = change["action"]
        if action == "keep":
            continue
        if action == "cancel":
            del candidate[session.id]
        elif action == "move":
            candidate[session.id] = dataclasses.replace(
                session, local_date=date.fromisoformat(change["new_date"]))
        elif action in ("modify", "replace"):
            ns = change["new_session"]
            candidate[session.id] = Session(
                id=None, local_date=session.local_date, sport=ns["sport"],
                session_type=ns["session_type"], title=ns["title"],
                structure=ns["structure"], block=session.block,
                duration_sec_target=ns.get("duration_sec_target"),
                priority=ns.get("priority", session.priority),
                is_test=session.is_test, rehearses_goal=session.rehearses_goal,
                is_goal_event=session.is_goal_event, chained=session.chained)
    return list(candidate.values())


def _feedback_message(errors: list[str]) -> str:
    lines = "\n".join(f"- {e}" for e in errors)
    return (f"El validador ha rebutjat la teva proposta per aquestes "
            f"infraccions:\n{lines}\n\nCorregeix-les i torna a enviar "
            f"l'informe COMPLET (no només els canvis).")


def coach_cycle(llm, system: str, context_json: str, plan: list[Session],
                athlete: Athlete, history: History, goals: list,
                today: date, report_type: str) -> dict:
    """Passos 2-5 del bucle. Pur respecte de la DB: tot entra per paràmetre."""
    active = [s for s in plan if s.status not in ("cancelled", "moved")]
    plan_by_id = {s.id: s for s in active}
    messages = [{"role": "user", "content": context_json}]
    total_usage = {"model": None, "input_tokens": 0, "output_tokens": 0}
    validation_history: list[list[str]] = []
    output = None
    warnings: list[Violation] = []

    for _ in range(MAX_ATTEMPTS):
        try:
            output, usage = llm.generate(system, messages, report_type)
        except OutputCutOff as e:
            # sense JSON de fiar: una tanda d'infraccions més, i que sigui breu
            validation_history.append([f"resposta tallada per longitud ({e}): "
                                       f"sigues més compacte, keep sense comentaris"])
            messages += [{"role": "user", "content": _feedback_message(validation_history[-1])}]
            continue
        total_usage["model"] = usage["model"]
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]

        errors = semantic_errors(output["session_changes"], plan_by_id, athlete)
        if not errors:
            candidate = apply_changes(active, output["session_changes"])
            violations = validate_plan(candidate, athlete, history, goals,
                                       reference_date=today,
                                       plan_start=min(s.local_date for s in active))
            warnings = [v for v in violations if not v.blocking]
            errors = [f"{v.rule} [blocking]: {v.message}"
                      for v in violations if v.blocking]

        if not errors:
            return {"accepted": True, "output": output, "usage": total_usage,
                    "validation_errors": validation_history,
                    "warnings": [f"{v.rule}: {v.message}" for v in warnings]}

        validation_history.append(errors)
        messages += [{"role": "assistant", "content": json.dumps(output)},
                     {"role": "user", "content": _feedback_message(errors)}]

    # cap intent vàlid: es descarta la proposta, el pla existent mana (spec §7.5)
    return {"accepted": False, "output": output, "usage": total_usage,
            "validation_errors": validation_history, "warnings": []}


# ─── costat DB ───────────────────────────────────────────────────────

def _guard(conn, sid: int) -> str:
    row = conn.execute("select status, superseded_by from plan_session where id=%s",
                       (sid,)).fetchone()
    if row is None:
        raise StaleProposal(f"la sessió {sid} no existeix")
    status, superseded_by = row
    if superseded_by is not None:
        raise StaleProposal(f"la sessió {sid} ja té una versió posterior ({superseded_by})")
    if status != "planned":
        raise StaleProposal(f"la sessió {sid} ja no és pendent ({status})")
    return status


def _effect(conn, report_id: int, kind: str, session_id: int, new_session_id=None,
            prev_status=None, prev_superseded_by=None, decision_id=None) -> dict:
    conn.execute("""insert into coach_report_effect (report_id, kind, session_id,
                    new_session_id, prev_status, prev_superseded_by, decision_id)
                    values (%s, %s, %s, %s, %s, %s, %s)""",
                 (report_id, kind, session_id, new_session_id, prev_status,
                  prev_superseded_by, decision_id))
    return {"report_id": report_id, "kind": kind, "session_id": session_id,
            "new_session_id": new_session_id, "prev_status": prev_status,
            "prev_superseded_by": prev_superseded_by}


def _relink_children(conn, old_id: int, new_id: int) -> None:
    conn.execute("""update plan_session set chained_after=%s
                    where chained_after=%s and superseded_by is null""", (new_id, old_id))


def apply_to_db(conn, report_id: int, changes: list[dict], decision_id=None) -> list[dict]:
    """Aplica els canvis d'un informe al pla viu, dins la transacció del caller.

    Cada mutació queda a coach_report_effect (per poder desfer-la) i cada fila
    tocada ha de ser la viva i pendent: si no, StaleProposal i el caller fa
    rollback. Res s'esborra mai: versionat amb superseded_by.
    """
    effects: list[dict] = []
    inherited = ", ".join(INHERITED)
    for change in changes:
        action = change["action"]
        if action == "keep":
            continue
        sid = change["plan_session_id"]
        prev_status = _guard(conn, sid)
        if action == "cancel":
            conn.execute("update plan_session set status='cancelled' where id=%s", (sid,))
            effects.append(_effect(conn, report_id, "cancelled", sid,
                                   prev_status=prev_status, decision_id=decision_id))
        elif action == "move":
            new_id = conn.execute(f"""
                insert into plan_session ({inherited}, local_date, sport,
                    session_type, title, structure, duration_sec_target,
                    distance_m_target, priority, rationale, created_by, version)
                select {inherited}, %s, sport, session_type, title, structure,
                    duration_sec_target, distance_m_target, priority, %s,
                    'coach', version + 1
                from plan_session where id = %s returning id""",
                (change["new_date"], change["reason"], sid)).fetchone()[0]
            _relink_children(conn, sid, new_id)
            conn.execute("""update plan_session set status='moved',
                            superseded_by=%s where id=%s""", (new_id, sid))
            effects.append(_effect(conn, report_id, "created", sid, new_id,
                                   decision_id=decision_id))
            effects.append(_effect(conn, report_id, "moved", sid, new_id,
                                   prev_status=prev_status, decision_id=decision_id))
        elif action in ("modify", "replace"):
            ns = change["new_session"]
            new_id = conn.execute(f"""
                insert into plan_session ({inherited}, local_date, sport,
                    session_type, title, structure, duration_sec_target,
                    distance_m_target, priority, rationale, created_by, version)
                select {inherited}, local_date, %s, %s, %s, %s, %s,
                    coalesce(%s, distance_m_target), coalesce(%s, priority), %s,
                    'coach', version + 1
                from plan_session where id = %s returning id""",
                (ns["sport"], ns["session_type"], ns["title"],
                 json.dumps(ns["structure"]), ns.get("duration_sec_target"),
                 ns.get("distance_m_target"), ns.get("priority"),
                 change["reason"], sid)).fetchone()[0]
            _relink_children(conn, sid, new_id)
            conn.execute("update plan_session set superseded_by=%s where id=%s",
                         (new_id, sid))
            effects.append(_effect(conn, report_id, "created", sid, new_id,
                                   decision_id=decision_id))
            effects.append(_effect(conn, report_id, "superseded", sid, new_id,
                                   prev_status=prev_status, decision_id=decision_id))
    return effects


SUMMARY_PREFIX = {
    "none": "*(dry-run: canvis NO aplicats al pla)*",
    "proposed": "*(proposta pendent: cap canvi fins que l'aprovis a l'app)*",
    "auto_applied": "*(aplicat automàticament: canvis petits, es poden desfer des de l'app)*",
    "applied": "*(aplicat)*",
    "failed": "*(no aplicat: el pla havia canviat entre la proposta i l'aplicació)*",
}


def write_report(conn, report_type: str, snapshot: dict, result: dict, today: date,
                 *, proposal_status: str, scope: str = "sessions",
                 classification: dict | None = None) -> int:
    """Desa l'informe i en retorna l'id (per lligar-hi efectes i decisions)."""
    output = result["output"]
    summary_md = f"## {output['summary']}\n\n{output['rationale']}"
    if output.get("questions_for_athlete"):
        summary_md += "\n\n**Preguntes:** " + " · ".join(output["questions_for_athlete"])
    if not result["accepted"]:
        summary_md = "## PROPOSTA DESCARTADA PEL VALIDADOR\n\n" + summary_md
    elif proposal_status in SUMMARY_PREFIX:
        summary_md = SUMMARY_PREFIX[proposal_status] + "\n\n" + summary_md
    window = (today, today + timedelta(days=3 if report_type == "daily" else 7))
    return conn.execute("""
        insert into coach_report (report_type, window_start, window_end,
            input_snapshot, output, summary_md, model, input_tokens,
            output_tokens, validation_errors, proposal_status, scope, classification)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (report_type, window[0], window[1], json.dumps(snapshot),
         json.dumps(output), summary_md, result["usage"]["model"],
         result["usage"]["input_tokens"], result["usage"]["output_tokens"],
         json.dumps(result["validation_errors"] + [result["warnings"]])
         if (result["validation_errors"] or result["warnings"]) else None,
         proposal_status, scope,
         json.dumps(classification, ensure_ascii=False)
         if classification is not None else None)).fetchone()[0]


def main() -> None:

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_type", choices=["daily", "weekly"])
    parser.add_argument("--dry-run", action="store_true",
                        help="cicle complet però sense tocar el pla")
    parser.add_argument("--tomorrow", action="store_true",
                        help="preview del vespre: el context es construeix per a demà")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")
    today = date.today()
    # el preview mira demà, però la validació "res al passat" segueix ancorada
    # al dia real: les sessions d'avui encara no són passat a les 21:30
    target = today + timedelta(days=1) if args.tomorrow else today

    # Connexió curta només per llegir. El pooler de Supabase mata connexions
    # ocioses: mantenir-ne una oberta durant la crida al model (1-3 min) va
    # perdre dos informes ja generats el 30-31/08.
    with psycopg.connect(url) as conn:
        snapshot = build_context(conn, today, report_for=target)
        if args.tomorrow:
            snapshot["mode"] = "evening_preview"
        plan, goals, history, athlete = plan_from_db(conn)
        mode = "dry_run" if args.dry_run else apply_mode(conn)

    result = coach_cycle(
        llm=CoachLLM(), system=load_prompt(f"{args.report_type}-v1"),
        context_json=json.dumps(snapshot, ensure_ascii=False),
        plan=plan, athlete=athlete, history=history, goals=goals,
        today=today, report_type=args.report_type)

    # Auto o proposta? Es classifica sempre (també en dry_run: l'app ho ensenya
    # com a "mode prova"), però només s'aplica en mode hybrid.
    classification = None
    proposal_status = "none"
    if result["accepted"]:
        active = {s.id: s for s in plan if s.status not in ("cancelled", "moved")}
        classification = classify(result["output"]["session_changes"], active,
                                  today, blocking=[]).to_dict()
        if mode == "hybrid":
            proposal_status = "auto_applied" if classification["auto"] else "proposed"

    # Segona connexió curta per persistir: informe + canvis + efectes, tot o res.
    applied = 0
    with psycopg.connect(url) as conn:
        try:
            with conn.transaction():
                report_id = write_report(conn, args.report_type, snapshot, result, target,
                                         proposal_status=proposal_status,
                                         classification=classification)
                if proposal_status == "auto_applied":
                    applied = len(apply_to_db(conn, report_id,
                                              result["output"]["session_changes"]))
        except StaleProposal as e:
            result["validation_errors"].append([f"no aplicat: {e}"])
            with conn.transaction():
                write_report(conn, args.report_type, snapshot, result, target,
                             proposal_status="failed", classification=classification)
            proposal_status = "failed"

    output = result["output"]
    status = "ACCEPTAT" if result["accepted"] else "DESCARTAT"
    print(f"[{status}] {args.report_type} · model {result['usage']['model']} · "
          f"{result['usage']['input_tokens']} in / {result['usage']['output_tokens']} out "
          f"· {len(result['validation_errors'])} tandes d'infraccions · "
          f"mode {mode} · {proposal_status} · {applied} efectes")
    print(f"\nSemàfor: {output['readiness']['verdict'].upper()} "
          f"({', '.join(output['readiness']['drivers']) or 'sense drivers'})")
    print(f"\n{output['summary']}\n\n{output['rationale']}")
    if output.get("questions_for_athlete"):
        print("\nPreguntes per a tu:")
        for q in output["questions_for_athlete"]:
            print(f"  - {q}")
    if output.get("flags"):
        print(f"\nFlags: {output['flags']}")


if __name__ == "__main__":
    main()
