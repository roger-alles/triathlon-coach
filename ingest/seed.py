"""Loader idempotent del pla seed (spec §10 F3).

Carrega seeds/fornells-2026.yaml a goal, plan_block, plan_session i
logistics_task. Idempotent per claus naturals: executar-lo dues vegades
actualitza en lloc de duplicar.

  goal          -> name
  plan_block    -> (goal_id, start_date)
  plan_session  -> (goal_id, local_date, sport)  # una sessió per esport i dia; el títol pot canviar
  logistics_task-> (goal_id, local_date, title)

Ús:
    .venv/bin/python -m ingest.seed [seeds/fornells-2026.yaml] [--force]

Quan el coach ja ha versionat el pla (files amb version > 1 o informes
aplicats), el yaml deixa de ser la veritat: tornar a executar el seed
sobreescriuria les versions del coach. Es nega, tret de --force.
"""

import json
import os
import sys
from pathlib import Path

import psycopg
import yaml
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


def _jsonb(obj) -> Jsonb:
    """Jsonb que serialitza dates (el YAML les parseja com a datetime.date)."""
    return Jsonb(obj, dumps=lambda o: json.dumps(o, default=str))

ROOT = Path(__file__).parent.parent

# claus del YAML que passen tal qual a columnes de plan_session
SESSION_COLS_PASSTHROUGH = [
    "sport", "session_type", "title", "priority", "duration_sec_target",
    "distance_m_target", "rationale", "is_test", "rehearses_goal",
    "is_goal_event", "structure",
]


def split_entries(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separa sessions d'entrenament de la logística inline (type: logistics)."""
    sessions = [e for e in entries if e.get("type") != "logistics"]
    logistics = [e for e in entries if e.get("type") == "logistics"]
    return sessions, logistics


def session_row(s: dict) -> dict:
    """D'una sessió del YAML a una fila de plan_session (+ marcador intern)."""
    row = {col: s.get(col) for col in SESSION_COLS_PASSTHROUGH}
    row["local_date"] = s["date"]
    row["priority"] = row["priority"] or "support"
    row["is_test"] = bool(row["is_test"])
    row["rehearses_goal"] = bool(row["rehearses_goal"])
    row["is_goal_event"] = bool(row["is_goal_event"])
    row["test_spec"] = s.get("test")
    row["transition_practice"] = s.get("includes_transition_practice")
    row["_parent_of_day"] = s.get("parent_of_day")
    return row


def resolve_chains(rows: list[dict]) -> list[tuple]:
    """Parelles (clau_brick, clau_pare) per omplir chained_after."""
    by_day_sport = {(r["local_date"], r["sport"]): r for r in rows}
    chains = []
    for r in rows:
        parent_sport = r.get("_parent_of_day")
        if parent_sport:
            parent = by_day_sport[(r["local_date"], parent_sport)]
            chains.append((
                (r["local_date"], r["sport"], r["title"]),
                (parent["local_date"], parent["sport"], parent["title"]),
            ))
    return chains


def upsert_goal(conn, g: dict, extra_profile: dict) -> int:
    profile = dict(g.get("profile") or {})
    profile.update(extra_profile)
    row = conn.execute("select id from goal where name = %s", (g["name"],)).fetchone()
    if row:
        conn.execute("""update goal set discipline=%s, event_date=%s, priority=%s,
                        profile=%s, status=%s where id=%s""",
                     (g["discipline"], g["event_date"], g["priority"],
                      _jsonb(profile), g["status"], row[0]))
        return row[0]
    return conn.execute("""insert into goal (name, discipline, event_date, priority,
                           profile, status) values (%s,%s,%s,%s,%s,%s) returning id""",
                        (g["name"], g["discipline"], g["event_date"], g["priority"],
                         _jsonb(profile), g["status"])).fetchone()[0]


def upsert_block(conn, goal_id: int, b: dict) -> int:
    key = (goal_id, b["start_date"])
    row = conn.execute("select id from plan_block where goal_id=%s and start_date=%s",
                       key).fetchone()
    values = (b["phase"], b.get("name"), b["end_date"], b.get("intent"),
              b.get("target_weekly_hours"), b.get("fallback"),
              bool(b.get("return_from_layoff")))
    if row:
        conn.execute("""update plan_block set phase=%s, name=%s, end_date=%s,
                        intent=%s, target_weekly_hours=%s, fallback=%s,
                        return_from_layoff=%s where id=%s""", values + (row[0],))
        return row[0]
    return conn.execute("""insert into plan_block (goal_id, start_date, phase, name,
                           end_date, intent, target_weekly_hours, fallback,
                           return_from_layoff)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                        key + values).fetchone()[0]


def upsert_session(conn, goal_id: int, block_id: int, row: dict) -> int:
    key = (goal_id, row["local_date"], row["sport"])
    found = conn.execute("""select id from plan_session where goal_id=%s
                            and local_date=%s and sport=%s
                            and superseded_by is null""", key).fetchone()
    params = {k: v for k, v in row.items() if not k.startswith("_")}
    params["structure"] = _jsonb(params["structure"])
    params["test_spec"] = _jsonb(params["test_spec"]) if params["test_spec"] else None
    params["goal_id"], params["block_id"] = goal_id, block_id
    if found:
        params["id"] = found[0]
        conn.execute("""update plan_session set block_id=%(block_id)s,
            title=%(title)s, session_type=%(session_type)s, structure=%(structure)s,
            duration_sec_target=%(duration_sec_target)s,
            distance_m_target=%(distance_m_target)s, priority=%(priority)s,
            rationale=%(rationale)s, is_test=%(is_test)s, test_spec=%(test_spec)s,
            rehearses_goal=%(rehearses_goal)s, is_goal_event=%(is_goal_event)s,
            transition_practice=%(transition_practice)s where id=%(id)s""", params)
        return found[0]
    return conn.execute("""insert into plan_session (goal_id, block_id, local_date,
        sport, session_type, title, structure, duration_sec_target,
        distance_m_target, priority, rationale, is_test, test_spec,
        rehearses_goal, is_goal_event, transition_practice)
        values (%(goal_id)s, %(block_id)s, %(local_date)s, %(sport)s,
        %(session_type)s, %(title)s, %(structure)s, %(duration_sec_target)s,
        %(distance_m_target)s, %(priority)s, %(rationale)s, %(is_test)s,
        %(test_spec)s, %(rehearses_goal)s, %(is_goal_event)s,
        %(transition_practice)s) returning id""", params).fetchone()[0]


def upsert_logistics(conn, goal_id: int, t: dict) -> None:
    detail = t.get("detail") or t.get("when")
    key = (goal_id, t["date"], t["title"])
    found = conn.execute("""select id from logistics_task where goal_id=%s
                            and local_date=%s and title=%s""", key).fetchone()
    if found:
        conn.execute("update logistics_task set detail=%s, blocking=%s where id=%s",
                     (detail, bool(t.get("blocking")), found[0]))
    else:
        conn.execute("""insert into logistics_task (goal_id, local_date, title,
                        detail, blocking) values (%s,%s,%s,%s,%s)""",
                     key + (detail, bool(t.get("blocking"))))


def coach_owns_plan(conn) -> bool:
    """El coach ha escrit versions al pla viu (S1a): el seed ja no mana."""
    versioned = conn.execute(
        "select 1 from plan_session where version > 1 limit 1").fetchone()
    applied = conn.execute("""select 1 from coach_report
                              where proposal_status in ('applied', 'auto_applied')
                              limit 1""").fetchone()
    return bool(versioned or applied)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    seed_path = ROOT / (args[0] if args else "seeds/fornells-2026.yaml")
    data = yaml.safe_load(seed_path.read_text())

    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")

    with psycopg.connect(url) as conn:
        if coach_owns_plan(conn) and not force:
            sys.exit("El pla viu ja té versions del coach: el seed ja no és la veritat "
                     "(docs/post-cursa-design.md). --force per sobreescriure-les.")

    extra_profile = {k: data[k] for k in
                     ("athlete_context", "race_day_protocol", "pacing_rules")
                     if k in data}
    extra_profile["source"] = data.get("source")

    with psycopg.connect(url) as conn, conn.transaction():
        goal_id = upsert_goal(conn, data["goal"], extra_profile)

        all_rows: list[dict] = []
        ids: dict[tuple, int] = {}
        n_logistics = 0
        for block in data["blocks"]:
            block_id = upsert_block(conn, goal_id, block)
            sessions, inline_logistics = split_entries(block.get("sessions", []))
            for s in sessions:
                row = session_row(s)
                sid = upsert_session(conn, goal_id, block_id, row)
                ids[(row["local_date"], row["sport"], row["title"])] = sid
                all_rows.append(row)
            for t in inline_logistics:
                upsert_logistics(conn, goal_id, t)
                n_logistics += 1

        for brick_key, parent_key in resolve_chains(all_rows):
            conn.execute("update plan_session set chained_after=%s where id=%s",
                         (ids[parent_key], ids[brick_key]))

        for t in data.get("logistics", []):
            upsert_logistics(conn, goal_id, t)
            n_logistics += 1

        n_blocks = len(data["blocks"])
        print(f"goal '{data['goal']['name']}' (id {goal_id}): "
              f"{n_blocks} blocs, {len(all_rows)} sessions, {n_logistics} logística")


if __name__ == "__main__":
    main()
