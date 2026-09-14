"""Blocs del pla (macro, S3): validació, aplicació en memòria i a la BD, desfer.

El macro proposa blocs (fase, dates, hores/setmana, intenció, fallback) fins a
l'objectiu A més proper i la recuperació posterior. Mai sessions. Aquí es
comprova que la proposta és coherent (dates, solapaments, taper i recovery al
voltant de la cursa, rampa entre blocs i contra les hores reals) i s'escriu a
plan_block amb efectes reversibles (coach_report_effect) com les sessions.
"""

from __future__ import annotations

import dataclasses
import json
import statistics
from datetime import date, timedelta

from coach.models import Athlete, Block, Goal, History, Session
from coach.rules import primary_goal

PHASES = ("base", "build", "peak", "taper", "race", "recovery", "transition")
ADD_REQUIRED = ("phase", "name", "start_date", "end_date", "target_weekly_hours")
MAX_BLOCK_RAMP = 1.15          # hores d'un bloc vs l'anterior (i vs realitat)
LOWERING_PHASES = ("taper", "recovery")
EDITABLE = ("phase", "name", "start_date", "end_date", "target_weekly_hours",
            "intent", "fallback")
EFFECT_COLS = ("report_id", "kind", "block_id", "prev_status", "prev_values")


def _date(v) -> date | None:
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def _taper_window(goal: Goal) -> tuple[int, int]:
    total = ((goal.profile or {}).get("target_times_sec") or {}).get("total")
    is_short = (total[1] <= 3 * 3600) if total else True
    return (7, 10) if is_short else (12, 21)


def block_errors(changes: list[dict], blocks: list[Block], goals: list[Goal],
                 history: History, today: date, plan: list[Session] = (),
                 athlete: Athlete | None = None) -> list[str]:
    """Errors de forma i de coherència d'una proposta de blocs. Buida = endavant."""
    errors: list[str] = []
    tomorrow = today + timedelta(days=1)
    ceiling = (((athlete.profile if athlete else None) or {}).get("constraints") or {}
               ).get("weekly_hours_ceiling")
    by_id = {b.id: b for b in blocks}
    planned_after = {}
    for s in plan:
        if s.block is not None and s.status == "planned" and s.local_date >= tomorrow:
            planned_after[s.block.id] = planned_after.get(s.block.id, 0) + 1

    for i, ch in enumerate(changes):
        where = f"block_changes[{i}]"
        action = ch.get("action")
        nb = ch.get("new_block") or {}
        if action in ("modify", "cancel"):
            bid = ch.get("block_id")
            if bid not in by_id:
                errors.append(f"{where}: block_id {bid} no existeix")
                continue
            if planned_after.get(bid):
                errors.append(f"{where}: el bloc {bid} té {planned_after[bid]} sessions "
                              f"planificades a partir de demà; el macro no toca sessions "
                              f"(cancel·la-les o mou-les primer)")
                continue
        if action == "add":
            missing = [f for f in ADD_REQUIRED if nb.get(f) in (None, "")]
            if missing:
                errors.append(f"{where}: new_block sense {missing}")
                continue
        if action in ("add", "modify"):
            if "phase" in nb and nb["phase"] not in PHASES:
                errors.append(f"{where}: phase '{nb['phase']}' desconeguda ({', '.join(PHASES)})")
            start = _date(nb.get("start_date")) if "start_date" in nb else None
            end = _date(nb.get("end_date")) if "end_date" in nb else None
            if "start_date" in nb and start is None:
                errors.append(f"{where}: start_date invàlida ({nb.get('start_date')!r})")
            if "end_date" in nb and end is None:
                errors.append(f"{where}: end_date invàlida ({nb.get('end_date')!r})")
            original = by_id.get(ch.get("block_id")) if action == "modify" else None
            eff_start = start or (original.start_date if original else None)
            eff_end = end or (original.end_date if original else None)
            if eff_start and eff_end and eff_end < eff_start:
                errors.append(f"{where}: end_date {eff_end} anterior a start_date {eff_start}")
            if start and start < tomorrow and (original is None or start != original.start_date):
                errors.append(f"{where}: el bloc no pot començar abans de demà ({tomorrow})")
            if end and end < today:
                errors.append(f"{where}: end_date {end} ja és passat")
            hours = nb.get("target_weekly_hours")
            if ceiling and hours and float(hours) > float(ceiling):
                errors.append(f"{where}: {hours} h/setmana supera el sostre de {ceiling} h "
                              f"que l'atleta ha declarat")
        elif action not in ("cancel",):
            errors.append(f"{where}: action '{action}' desconeguda")
    if errors:
        return errors

    candidate = [b for b in apply_block_changes(blocks, changes) if b.status != "cancelled"]
    candidate.sort(key=lambda b: b.start_date)
    for a, b in zip(candidate, candidate[1:]):
        if b.start_date <= a.end_date:
            errors.append(f"els blocs '{a.name}' ({a.start_date}–{a.end_date}) i '{b.name}' "
                          f"({b.start_date}–{b.end_date}) se solapen")

    goal = primary_goal(goals)
    if goal and goal.event_date and goal.event_date > today:
        race = goal.event_date
        covers_race = any(b.covers(race) for b in candidate)
        was_covered = any(b.covers(race) for b in blocks if b.status != "cancelled")
        if was_covered and not covers_race:
            errors.append(f"la proposta deixa la cursa A '{goal.name}' ({race}) sense cap bloc "
                          f"(abans en tenia); el taper no es pot cancel·lar sense substituir-lo")
        if covers_race:
            tapers = [b for b in candidate if b.phase == "taper"
                      and race - timedelta(days=1) <= b.end_date <= race]
            lo, hi = _taper_window(goal)
            if not tapers:
                errors.append(f"la cursa A '{goal.name}' ({race}) no té cap bloc taper que hi acabi")
            else:
                days = (race - tapers[0].start_date).days + 1
                if not lo <= days <= hi:
                    errors.append(f"taper de {days} dies per a '{goal.name}'; ha de ser {lo}-{hi}")
            rec = [b for b in candidate if b.phase == "recovery" and b.start_date > race]
            if not rec:
                errors.append(f"cal un bloc recovery que comenci l'endemà de la cursa ({race + timedelta(days=1)})")
            else:
                r = min(rec, key=lambda b: b.start_date)
                length = (r.end_date - r.start_date).days + 1
                if r.start_date != race + timedelta(days=1):
                    errors.append(f"el recovery ha de començar l'endemà de la cursa "
                                  f"({race + timedelta(days=1)}), no el {r.start_date}")
                if not 7 <= length <= 21:
                    errors.append(f"recovery de {length} dies; ha de ser 7-21")

    # rampa entre blocs consecutius, i del primer bloc nou contra la realitat
    new_ids = {b.id for b in candidate if b.id is not None and b.id < 0} | {
        ch.get("block_id") for ch in changes if ch.get("action") == "modify"}
    real = [h for _, h in sorted(history.weekly_hours.items())][-4:]
    first_new_checked = False
    for i, b in enumerate(candidate):
        if b.id not in new_ids or not b.target_weekly_hours:
            continue
        prev = candidate[i - 1] if i > 0 else None
        if prev and prev.target_weekly_hours:
            if b.phase in LOWERING_PHASES:
                # taper/recovery baixen respecte a un bloc de càrrega; després
                # d'un altre bloc baix, com a molt s'hi queden
                strict = prev.phase not in LOWERING_PHASES
                too_high = (b.target_weekly_hours >= prev.target_weekly_hours if strict
                            else b.target_weekly_hours > prev.target_weekly_hours)
                if too_high:
                    errors.append(f"'{b.name}' ({b.phase}) ha de baixar hores respecte a "
                                  f"'{prev.name}' ({prev.target_weekly_hours} h)")
            else:
                ramp = b.target_weekly_hours / prev.target_weekly_hours - 1
                if ramp > MAX_BLOCK_RAMP - 1:
                    errors.append(f"'{b.name}': {b.target_weekly_hours} h és +{round(ramp*100)}% "
                                  f"sobre '{prev.name}' ({prev.target_weekly_hours} h); màxim +15%")
        elif not first_new_checked and real and b.phase not in LOWERING_PHASES:
            mean = statistics.mean(real)
            if b.target_weekly_hours > MAX_BLOCK_RAMP * mean:
                errors.append(f"'{b.name}': {b.target_weekly_hours} h/setmana és més d'un 15% sobre "
                              f"les hores reals de les últimes setmanes ({round(mean, 1)} h)")
        first_new_checked = True
    return errors


def apply_block_changes(blocks: list[Block], changes: list[dict]) -> list[Block]:
    """Blocs candidats (en memòria). Els add reben ids sintètics negatius."""
    out = {b.id: b for b in blocks}
    n = 0
    for ch in changes:
        action = ch["action"]
        nb = ch.get("new_block") or {}
        if action == "add":
            n += 1
            out[-n] = Block(id=-n, phase=nb["phase"], start_date=_date(nb["start_date"]),
                            end_date=_date(nb["end_date"]),
                            target_weekly_hours=float(nb["target_weekly_hours"]),
                            goal_id=None, status="active", name=nb.get("name"),
                            intent=nb.get("intent"), fallback=nb.get("fallback"))
        elif action == "cancel":
            out[ch["block_id"]] = dataclasses.replace(out[ch["block_id"]], status="cancelled")
        elif action == "modify":
            b = out[ch["block_id"]]
            fields = {}
            for f in EDITABLE:
                if f in nb:
                    v = nb[f]
                    if f in ("start_date", "end_date"):
                        v = _date(v)
                    elif f == "target_weekly_hours":
                        v = float(v)
                    fields[f] = v
            out[ch["block_id"]] = dataclasses.replace(b, **fields)
    return list(out.values())


def _effect(conn, report_id: int, kind: str, block_id: int, prev_status=None,
            prev_values=None, decision_id=None) -> dict:
    conn.execute("""insert into coach_report_effect (report_id, kind, block_id,
                    prev_status, prev_values, decision_id)
                    values (%s, %s, %s, %s, %s, %s)""",
                 (report_id, kind, block_id, prev_status, prev_values, decision_id))
    return {"report_id": report_id, "kind": kind, "block_id": block_id,
            "prev_status": prev_status, "prev_values": prev_values}


def apply_blocks_to_db(conn, report_id: int, changes: list[dict], goal_id: int | None,
                       decision_id=None) -> list[dict]:
    """Escriu els canvis de blocs al pla viu, dins la transacció del caller."""
    effects: list[dict] = []
    for ch in changes:
        action = ch["action"]
        nb = ch.get("new_block") or {}
        if action == "add":
            new_id = conn.execute("""
                insert into plan_block (goal_id, phase, name, start_date, end_date,
                    intent, target_weekly_hours, fallback, status, created_by)
                values (%s, %s, %s, %s, %s, %s, %s, %s, 'active', 'coach')
                returning id""",
                (goal_id, nb["phase"], nb.get("name"), nb["start_date"], nb["end_date"],
                 nb.get("intent"), nb["target_weekly_hours"], nb.get("fallback"))).fetchone()[0]
            effects.append(_effect(conn, report_id, "block_created", new_id,
                                   decision_id=decision_id))
            continue
        bid = ch["block_id"]
        row = conn.execute("""select status, phase, name, start_date, end_date,
                              target_weekly_hours, intent, fallback
                              from plan_block where id=%s""", (bid,)).fetchone()
        if row is None:
            raise ValueError(f"el bloc {bid} no existeix")
        current = dict(zip(("status",) + EDITABLE, row))
        if action == "cancel":
            conn.execute("update plan_block set status='cancelled' where id=%s", (bid,))
            effects.append(_effect(conn, report_id, "block_cancelled", bid,
                                   prev_status=current["status"], decision_id=decision_id))
        elif action == "modify":
            fields = {f: nb[f] for f in EDITABLE if f in nb}
            prev = {f: current[f] for f in fields}
            sets = ", ".join(f"{f}=%s" for f in fields)
            conn.execute(f"update plan_block set {sets} where id=%s",
                         tuple(fields.values()) + (bid,))
            effects.append(_effect(conn, report_id, "block_modified", bid,
                                   prev_values=json.dumps(prev, default=str),
                                   decision_id=decision_id))
    return effects


def undo_block_effects(conn, effects: list[dict]) -> None:
    """Reverteix els efectes de bloc d'un informe (en ordre invers)."""
    for e in reversed(effects):
        kind = e["kind"]
        if kind == "block_created":
            conn.execute("update plan_block set status='cancelled' where id=%s", (e["block_id"],))
        elif kind == "block_cancelled":
            conn.execute("update plan_block set status=%s where id=%s",
                         (e["prev_status"] or "active", e["block_id"]))
        elif kind == "block_modified":
            prev = e["prev_values"]
            if isinstance(prev, str):
                prev = json.loads(prev)
            if prev:
                sets = ", ".join(f"{f}=%s" for f in prev)
                conn.execute(f"update plan_block set {sets} where id=%s",
                             tuple(prev.values()) + (e["block_id"],))
