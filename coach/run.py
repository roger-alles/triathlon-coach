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

--dry-run fa el cicle sencer (amb crida real a l'API) però no escriu res al
pla; desa igualment el coach_report marcant-ho al summary. És el mode d'ús
fins a la cursa del 27S: la spec mana no tocar el pla de Fornells.
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

from coach.context import build_context
from coach.llm import CoachLLM, load_prompt
from coach.plan_loader import plan_from_db
from coach.models import Athlete, History, Session, Violation
from coach.rules import validate_plan
from coach.structure import validate_structure

ROOT = Path(__file__).parent.parent
MAX_ATTEMPTS = 3  # 1 proposta + 2 correccions (spec §7 pas 4)

NEW_SESSION_REQUIRED = ("sport", "session_type", "title", "structure_json")


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
        output, usage = llm.generate(system, messages)
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

def apply_to_db(conn, changes: list[dict]) -> int:
    n_applied = 0
    for change in changes:
        action = change["action"]
        if action == "keep":
            continue
        sid = change["plan_session_id"]
        if action == "cancel":
            conn.execute("update plan_session set status='cancelled' where id=%s",
                         (sid,))
        elif action == "move":
            new_id = conn.execute("""
                insert into plan_session (goal_id, block_id, local_date, sport,
                    session_type, title, structure, duration_sec_target,
                    distance_m_target, priority, rationale, is_test,
                    rehearses_goal, is_goal_event, created_by, version)
                select goal_id, block_id, %s, sport, session_type, title,
                    structure, duration_sec_target, distance_m_target, priority,
                    %s, is_test, rehearses_goal, is_goal_event, 'coach', version + 1
                from plan_session where id = %s returning id""",
                (change["new_date"], change["reason"], sid)).fetchone()[0]
            conn.execute("""update plan_session set status='moved',
                            superseded_by=%s where id=%s""", (new_id, sid))
        elif action in ("modify", "replace"):
            ns = change["new_session"]
            new_id = conn.execute("""
                insert into plan_session (goal_id, block_id, local_date, sport,
                    session_type, title, structure, duration_sec_target,
                    priority, rationale, is_test, rehearses_goal, is_goal_event,
                    created_by, version)
                select goal_id, block_id, local_date, %s, %s, %s, %s, %s,
                    coalesce(%s, priority), %s, is_test, rehearses_goal,
                    is_goal_event, 'coach', version + 1
                from plan_session where id = %s returning id""",
                (ns["sport"], ns["session_type"], ns["title"],
                 json.dumps(ns["structure"]), ns.get("duration_sec_target"),
                 ns.get("priority"), change["reason"], sid)).fetchone()[0]
            conn.execute("update plan_session set superseded_by=%s where id=%s",
                         (new_id, sid))
        n_applied += 1
    return n_applied


def write_report(conn, report_type: str, snapshot: dict, result: dict,
                 today: date, dry_run: bool) -> None:
    output = result["output"]
    summary_md = f"## {output['summary']}\n\n{output['rationale']}"
    if output.get("questions_for_athlete"):
        summary_md += "\n\n**Preguntes:** " + " · ".join(output["questions_for_athlete"])
    if not result["accepted"]:
        summary_md = "## PROPOSTA DESCARTADA PEL VALIDADOR\n\n" + summary_md
    elif dry_run:
        summary_md = "*(dry-run: canvis NO aplicats al pla)*\n\n" + summary_md
    window = (today, today + timedelta(days=3 if report_type == "daily" else 7))
    conn.execute("""
        insert into coach_report (report_type, window_start, window_end,
            input_snapshot, output, summary_md, model, input_tokens,
            output_tokens, validation_errors)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (report_type, window[0], window[1], json.dumps(snapshot),
         json.dumps(output), summary_md, result["usage"]["model"],
         result["usage"]["input_tokens"], result["usage"]["output_tokens"],
         json.dumps(result["validation_errors"] + [result["warnings"]])
         if (result["validation_errors"] or result["warnings"]) else None))


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
        snapshot = build_context(conn, target)
        if args.tomorrow:
            snapshot["mode"] = "evening_preview"
        plan, goal, history, athlete = plan_from_db(conn)

    result = coach_cycle(
        llm=CoachLLM(), system=load_prompt(f"{args.report_type}-v1"),
        context_json=json.dumps(snapshot, ensure_ascii=False),
        plan=plan, athlete=athlete, history=history, goals=[goal],
        today=today, report_type=args.report_type)

    # Segona connexió curta per persistir.
    applied = 0
    with psycopg.connect(url) as conn:
        if result["accepted"] and not args.dry_run:
            with conn.transaction():
                applied = apply_to_db(conn, result["output"]["session_changes"])
        write_report(conn, args.report_type, snapshot, result, target, args.dry_run)

    output = result["output"]
    status = "ACCEPTAT" if result["accepted"] else "DESCARTAT"
    print(f"[{status}] {args.report_type} · model {result['usage']['model']} · "
          f"{result['usage']['input_tokens']} in / {result['usage']['output_tokens']} out "
          f"· {len(result['validation_errors'])} tandes d'infraccions · "
          f"{applied} canvis aplicats{' (dry-run)' if args.dry_run else ''}")
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
