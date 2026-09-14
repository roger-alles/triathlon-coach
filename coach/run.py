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

from coach.blocks import apply_block_changes, block_errors
from coach.classify import classify
from coach.context import build_context
from coach.llm import CoachLLM, OutputCutOff, load_prompt
from coach.plan_loader import plan_from_db
from coach.models import Athlete, Block, History, Session, Violation
from coach.rules import primary_goal, validate_plan
from coach.settings import apply_mode
from coach.structure import validate_structure

ROOT = Path(__file__).parent.parent
MAX_ATTEMPTS = 3  # 1 proposta + 2 correccions (spec §7 pas 4)
MACRO_MODEL = "claude-opus-5"  # el macro és car i poc freqüent: el millor model

NEW_SESSION_REQUIRED = ("sport", "session_type", "title", "structure_json")
ADD_REQUIRED = NEW_SESSION_REQUIRED + ("local_date",)


def _next_monday(d: date) -> date:
    return d + timedelta(days=7 - d.weekday())


def block_for(blocks: list[Block], d: date) -> Block | None:
    return next((b for b in blocks if b.covers(d)), None)


def _blocks_of(plan: list[Session]) -> list[Block]:
    seen: dict[int, Block] = {}
    for s in plan:
        if s.block is not None:
            seen.setdefault(s.block.id, s.block)
    return list(seen.values())

# Columnes que una versió nova hereta de la vella. Fins al 10/09 modify/move
# n'ometien chained_after, test_spec, transition_practice (i modify,
# distance_m_target): el brick perdia la bici pare i R14/R3 fallaven després.
INHERITED = ("goal_id", "block_id", "is_test", "test_spec", "rehearses_goal",
             "is_goal_event", "chained_after", "transition_practice")


class StaleProposal(Exception):
    """La proposta parla d'una sessió que ja no és la viva (o ja no és pendent)."""


def _parse_new_session(new_session: dict, where: str, required: tuple,
                       athlete: Athlete) -> list[str]:
    """Comprova els camps i deixa new_session["structure"] parsejada."""
    missing = [f for f in required if not new_session.get(f)]
    if missing:
        return [f"{where}: new_session sense {missing}"]
    try:
        new_session["structure"] = json.loads(new_session["structure_json"])
    except json.JSONDecodeError as e:
        return [f"{where}.new_session.structure_json: JSON invàlid ({e})"]
    return [f"{where}.new_session: {e}"
            for e in validate_structure(new_session["structure"], new_session["sport"], athlete)]


def semantic_errors(changes: list[dict], plan_by_id: dict[int, Session],
                    athlete: Athlete, blocks: list[Block] | None = None) -> list[str]:
    """Errors de forma que no cal cap regla per detectar.

    Efecte lateral volgut: si structure_json parseja bé, es deixa parsejada a
    new_session["structure"] perquè apply_changes i apply_to_db la reutilitzin.

    `add` (sessió nova): new_session amb local_date dins d'un bloc (si es
    passen `blocks`), i parent_of_day només si aquell dia hi ha (al pla viu o
    en un altre add del mateix informe) una sessió d'aquell esport.
    """
    errors = []
    added: set[tuple[date, str]] = set()
    for change in changes:
        if change.get("action") == "add":
            ns = change.get("new_session") or {}
            try:
                added.add((date.fromisoformat(ns.get("local_date", "")), ns.get("sport")))
            except ValueError:
                pass
    live_day_sport = {(s.local_date, s.sport) for s in plan_by_id.values()}
    for i, change in enumerate(changes):
        where = f"session_changes[{i}]"
        action = change["action"]
        if action == "add":
            new_session = change.get("new_session")
            if not new_session:
                errors.append(f"{where}: action 'add' sense new_session")
                continue
            errs = _parse_new_session(new_session, where, ADD_REQUIRED, athlete)
            if errs:
                errors += errs
                continue
            try:
                day = date.fromisoformat(new_session["local_date"])
            except ValueError:
                errors.append(f"{where}.new_session.local_date: data invàlida "
                              f"({new_session['local_date']!r}, cal YYYY-MM-DD)")
                continue
            if blocks is not None and block_for(blocks, day) is None:
                errors.append(f"{where}: cap bloc cobreix {day}; cal un macro "
                              f"que creï el bloc abans d'afegir-hi sessions")
            parent = new_session.get("parent_of_day")
            if parent and (day, parent) not in live_day_sport | added:
                errors.append(f"{where}: parent_of_day '{parent}' però el {day} no hi ha "
                              f"cap sessió de {parent} al pla ni en aquest informe")
            continue
        if change.get("plan_session_id") is None:
            errors.append(f"{where}: action '{action}' sense plan_session_id")
            continue
        session = plan_by_id.get(change["plan_session_id"])
        if session is None:
            errors.append(f"{where}: plan_session_id {change['plan_session_id']} "
                          f"no existeix al pla")
            continue
        if action in ("modify", "replace"):
            new_session = change.get("new_session")
            if not new_session:
                errors.append(f"{where}: action '{action}' sense new_session")
                continue
            errors += _parse_new_session(new_session, where, NEW_SESSION_REQUIRED, athlete)
        if action == "move" and not change.get("new_date"):
            errors.append(f"{where}: action 'move' sense new_date")
    return errors


def apply_changes(plan: list[Session], changes: list[dict],
                  blocks: list[Block] | None = None) -> list[Session]:
    """Pla candidat amb els canvis aplicats (en memòria; l'original no es toca).

    Els `add` reben un id sintètic negatiu (-1, -2, …) i el bloc que cobreix
    la seva data (dels `blocks` donats o, si no, dels que ja té el pla).
    """
    candidate = {s.id: s for s in plan}
    known_blocks = blocks if blocks is not None else _blocks_of(plan)
    n_added = 0
    for change in changes:
        action = change["action"]
        if action == "keep":
            continue
        if action == "add":
            ns = change["new_session"]
            n_added += 1
            day = date.fromisoformat(ns["local_date"])
            candidate[-n_added] = Session(
                id=-n_added, local_date=day, sport=ns["sport"],
                session_type=ns["session_type"], title=ns["title"],
                structure=ns["structure"], block=block_for(known_blocks, day),
                duration_sec_target=ns.get("duration_sec_target"),
                priority=ns.get("priority", "support"),
                chained=bool(ns.get("parent_of_day")))
            continue
        session = candidate[change["plan_session_id"]]
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


NO_BLOCK_CHANGES = "Cap canvi de blocs"


def _macro_shape_errors(output: dict) -> list[str]:
    """Un macro parla de blocs i només de blocs. Sense block_changes, la proposta
    seria buida (res a aprovar) mentre el rationale diu que afegeix coses: el
    model ho ha de posar al JSON o dir explícitament que no cal tocar res."""
    errors = []
    if any(c.get("action") != "keep" for c in output.get("session_changes") or []):
        errors.append("el macro no toca sessions: session_changes ha de ser []")
    if not output.get("block_changes") and not (output.get("summary") or "").startswith(NO_BLOCK_CHANGES):
        errors.append("informe macro sense block_changes: si afegeixes, modifiques o cancel·les "
                      "blocs (com diu el rationale), han d'anar a block_changes amb new_block "
                      f"complet; si cap bloc ha de canviar, block_changes: [] i un summary que "
                      f"comenci per '{NO_BLOCK_CHANGES}'")
    return errors


def blocking_signatures(plan: list[Session], athlete: Athlete, history: History,
                        goals: list, today: date) -> set[tuple[str, str]]:
    """(regla, missatge) de les violacions bloquejants que el pla JA té."""
    if not plan:
        return set()
    return {(v.rule, v.message)
            for v in validate_plan(plan, athlete, history, goals, reference_date=today,
                                   plan_start=min(s.local_date for s in plan))
            if v.blocking}


def coach_cycle(llm, system: str, context_json: str, plan: list[Session],
                athlete: Athlete, history: History, goals: list,
                today: date, report_type: str,
                blocks: list[Block] | None = None) -> dict:
    """Passos 2-5 del bucle. Pur respecte de la DB: tot entra per paràmetre."""
    active = [s for s in plan if s.status not in ("cancelled", "moved")]
    if blocks is None:
        blocks = _blocks_of(active)
    plan_by_id = {s.id: s for s in active}
    # El coach no pot empitjorar el pla, però no se'l castiga per una violació
    # que ja hi era (p. ex. R1 amb hores reals sobre una setmana escrita a mà):
    # les que ja existeixen, idèntiques, passen a avís.
    preexisting = blocking_signatures(active, athlete, history, goals, today)
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
            hint = ("un macro porta session_changes: [] i NOMÉS block_changes; "
                    "rationale de 2500 caràcters com a molt"
                    if report_type == "macro" else "sigues més compacte, keep sense comentaris")
            validation_history.append([f"resposta tallada per longitud ({e}): {hint}"])
            messages += [{"role": "user", "content": _feedback_message(validation_history[-1])}]
            continue
        total_usage["model"] = usage["model"]
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]

        block_changes = output.get("block_changes") or []
        errors = _macro_shape_errors(output) if report_type == "macro" else []
        errors += semantic_errors(output["session_changes"], plan_by_id, athlete, blocks)
        cycle_blocks = blocks
        if block_changes:
            errors += block_errors(block_changes, blocks, goals, history, today, plan=active,
                                   athlete=athlete)
            if not errors:
                cycle_blocks = [b for b in apply_block_changes(blocks, block_changes)
                                if b.status != "cancelled"]
        if not errors:
            candidate = apply_changes(active, output["session_changes"], cycle_blocks)
            violations = validate_plan(candidate, athlete, history, goals,
                                       reference_date=today,
                                       plan_start=min(s.local_date for s in active))
            warnings = [v for v in violations
                        if not v.blocking or (v.rule, v.message) in preexisting]
            errors = [f"{v.rule} [blocking]: {v.message}"
                      for v in violations
                      if v.blocking and (v.rule, v.message) not in preexisting]

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

    # Passada 1: sessions noves (add). Neixen al bloc que cobreix la data
    # (i a l'objectiu del bloc); sense bloc, la proposta ha caducat.
    created_by_day_sport: dict[tuple[date, str], int] = {}
    pending_chains: list[tuple[int, date, str]] = []
    for change in changes:
        if change["action"] != "add":
            continue
        ns = change["new_session"]
        day = date.fromisoformat(ns["local_date"])
        block = conn.execute("""select id, goal_id from plan_block
                                where %s between start_date and end_date
                                order by start_date limit 1""", (day,)).fetchone()
        if block is None:
            raise StaleProposal(f"cap bloc cobreix {day} (cal macro)")
        new_id = conn.execute("""
            insert into plan_session (goal_id, block_id, local_date, sport,
                session_type, title, structure, duration_sec_target,
                distance_m_target, priority, rationale, created_by, version)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'coach', 1)
            returning id""",
            (block[1], block[0], day, ns["sport"], ns["session_type"], ns["title"],
             json.dumps(ns["structure"]), ns.get("duration_sec_target"),
             ns.get("distance_m_target"), ns.get("priority", "support"),
             change["reason"])).fetchone()[0]
        created_by_day_sport[(day, ns["sport"])] = new_id
        if ns.get("parent_of_day"):
            pending_chains.append((new_id, day, ns["parent_of_day"]))
        effects.append(_effect(conn, report_id, "created", new_id, new_id,
                               decision_id=decision_id))
    # Passada 2: els bricks pengen del pare (creat en aquest informe o ja viu).
    for new_id, day, parent_sport in pending_chains:
        parent_id = created_by_day_sport.get((day, parent_sport))
        if parent_id is None:
            row = conn.execute("""select id from plan_session where local_date=%s
                                  and sport=%s and superseded_by is null
                                  and status='planned' limit 1""",
                               (day, parent_sport)).fetchone()
            if row is None:
                raise StaleProposal(f"el {day} ja no hi ha cap sessió de {parent_sport} "
                                    f"de què pugui penjar el brick")
            parent_id = row[0]
        conn.execute("update plan_session set chained_after=%s where id=%s",
                     (parent_id, new_id))

    for change in changes:
        action = change["action"]
        if action in ("keep", "add"):
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
                 classification: dict | None = None, window_end: date | None = None) -> int:
    """Desa l'informe i en retorna l'id (per lligar-hi efectes i decisions)."""
    output = result["output"]
    summary_md = f"## {output['summary']}\n\n{output['rationale']}"
    if output.get("questions_for_athlete"):
        summary_md += "\n\n**Preguntes:** " + " · ".join(output["questions_for_athlete"])
    if not result["accepted"]:
        summary_md = "## PROPOSTA DESCARTADA PEL VALIDADOR\n\n" + summary_md
    elif proposal_status in SUMMARY_PREFIX:
        summary_md = SUMMARY_PREFIX[proposal_status] + "\n\n" + summary_md
    if report_type == "weekly":
        monday = _next_monday(today)
        window = (monday, monday + timedelta(days=6))
    elif report_type == "macro":
        window = (today + timedelta(days=1), window_end or today + timedelta(weeks=12))
    else:
        window = (today, today + timedelta(days=3))
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


def run_report(report_type: str, *, url: str, today: date | None = None,
               dry_run: bool = False, tomorrow: bool = False) -> int:
    """Un cicle sencer (context → model → validació → persistir). Retorna l'id
    de l'informe. Cridat per main (CLI) i per coach.decisions (peticions)."""
    today = today or date.today()
    # el preview mira demà, però la validació "res al passat" segueix ancorada
    # al dia real: les sessions d'avui encara no són passat a les 21:30.
    # El setmanal (diumenge) parla de la setmana que comença demà: bloc i
    # finestra del dilluns vinent. El macro parla d'avui en endavant.
    if report_type == "weekly":
        target = _next_monday(today)
    else:
        target = today + timedelta(days=1) if tomorrow else today

    # Connexió curta només per llegir. El pooler de Supabase mata connexions
    # ocioses: mantenir-ne una oberta durant la crida al model (1-3 min) va
    # perdre dos informes ja generats el 30-31/08.
    with psycopg.connect(url) as conn:
        snapshot = build_context(conn, today, report_for=target)
        if report_type in ("weekly", "macro"):
            snapshot["mode"] = report_type
        elif tomorrow:
            snapshot["mode"] = "evening_preview"
        plan, goals, history, athlete, blocks = plan_from_db(conn, today)
        mode = "dry_run" if dry_run else apply_mode(conn)

    model = os.getenv("COACH_MODEL_MACRO", MACRO_MODEL) if report_type == "macro" else None
    result = coach_cycle(
        llm=CoachLLM(model=model), system=load_prompt(f"{report_type}-v1"),
        context_json=json.dumps(snapshot, ensure_ascii=False),
        plan=plan, athlete=athlete, history=history, goals=goals,
        today=today, report_type=report_type, blocks=blocks)

    # Auto o proposta? Es classifica sempre (també en dry_run: l'app ho ensenya
    # com a "mode prova"), però només s'aplica en mode hybrid. Un macro (blocs)
    # mai s'aplica sol.
    classification = None
    proposal_status = "none"
    scope = "macro" if report_type == "macro" else "sessions"
    if result["accepted"]:
        active = {s.id: s for s in plan if s.status not in ("cancelled", "moved")}
        classification = classify(result["output"]["session_changes"], active,
                                  today, blocking=[], blocks=blocks,
                                  block_changes=result["output"].get("block_changes") or []
                                  ).to_dict()
        if mode == "hybrid":
            proposal_status = "auto_applied" if classification["auto"] else "proposed"
        if report_type == "macro":
            # un macro mai s'aplica sol; i sense canvis de blocs no és cap
            # proposta (res a aprovar): informe informatiu
            has_blocks = bool(result["output"].get("block_changes"))
            proposal_status = "proposed" if has_blocks and mode == "hybrid" else "none"
    goal = primary_goal(goals)
    window_end = goal.event_date if (goal and goal.event_date and goal.event_date > today) else None

    # Segona connexió curta per persistir: informe + canvis + efectes, tot o res.
    applied = 0
    report_id = None
    with psycopg.connect(url) as conn:
        try:
            with conn.transaction():
                report_id = write_report(conn, report_type, snapshot, result, target,
                                         proposal_status=proposal_status, scope=scope,
                                         classification=classification, window_end=window_end)
                if proposal_status == "auto_applied":
                    applied = len(apply_to_db(conn, report_id,
                                              result["output"]["session_changes"]))
        except StaleProposal as e:
            result["validation_errors"].append([f"no aplicat: {e}"])
            with conn.transaction():
                report_id = write_report(conn, report_type, snapshot, result, target,
                                         proposal_status="failed", scope=scope,
                                         classification=classification, window_end=window_end)
            proposal_status = "failed"

    output = result["output"]
    status = "ACCEPTAT" if result["accepted"] else "DESCARTAT"
    print(f"[{status}] {report_type} · model {result['usage']['model']} · "
          f"{result['usage']['input_tokens']} in / {result['usage']['output_tokens']} out "
          f"· {len(result['validation_errors'])} tandes d'infraccions · "
          f"mode {mode} · {proposal_status} · {applied} efectes · informe {report_id}")
    print(f"\nSemàfor: {output['readiness']['verdict'].upper()} "
          f"({', '.join(output['readiness']['drivers']) or 'sense drivers'})")
    print(f"\n{output['summary']}\n\n{output['rationale']}")
    if output.get("block_changes"):
        print("\nBlocs:")
        for c in output["block_changes"]:
            nb = c.get("new_block") or {}
            print(f"  - {c['action']} {c.get('block_id') or ''} {nb.get('phase', '')} "
                  f"{nb.get('name', '')} {nb.get('start_date', '')}–{nb.get('end_date', '')} "
                  f"{nb.get('target_weekly_hours', '')} h · {c.get('reason', '')}")
    if output.get("questions_for_athlete"):
        print("\nPreguntes per a tu:")
        for q in output["questions_for_athlete"]:
            print(f"  - {q}")
    if output.get("flags"):
        print(f"\nFlags: {output['flags']}")
    return report_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_type", choices=["daily", "weekly", "macro"])
    parser.add_argument("--dry-run", action="store_true",
                        help="cicle complet però sense tocar el pla")
    parser.add_argument("--tomorrow", action="store_true",
                        help="preview del vespre: el context es construeix per a demà")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")
    run_report(args.report_type, url=url, dry_run=args.dry_run, tomorrow=args.tomorrow)


if __name__ == "__main__":
    main()
