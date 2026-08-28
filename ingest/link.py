"""Vinculació planificat <-> real (spec §9).

Després de cada sync: cada activitat s'associa a la seva plan_session (mateix
dia i esport; si hi ha més d'una candidata, la de durada més propera), i
l'estat de la sessió es deriva del que s'ha fet:

  completed  real >= 80% del planificat (planned_load si n'hi ha; si no, durada)
  partial    hi ha activitat però < 80%
  missed     el dia s'ha acabat sense cap activitat
  (les sessions de descans es completen soles quan passa el dia)

Només es toquen estats gestionats per aquest procés (planned/completed/
partial/missed): 'moved' i 'cancelled' són decisions del coach o de l'atleta
i no s'sobreescriuen. Idempotent: recalcular no canvia res si no hi ha dades noves.

Ús:
    .venv/bin/python -m ingest.link
"""

import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent

MANAGED_STATUSES = ("planned", "completed", "partial", "missed")
COMPLETED_RATIO = 0.8


def match_day(sessions: list[dict], activities: list[dict]) -> list[tuple[int, int]]:
    """(activity_id, session_id) per a un dia: mateix esport, durada més propera."""
    links = []
    for a in activities:
        candidates = [s for s in sessions if s["sport"] == a["sport"]]
        if not candidates:
            continue
        best = min(candidates,
                   key=lambda s: abs((s.get("duration_sec_target") or 0)
                                     - (a.get("duration_sec") or 0)))
        links.append((a["id"], best["id"]))
    return links


def session_status(session: dict, linked: list[dict], today: date) -> str | None:
    """Nou estat de la sessió, o None per deixar-la com està (dia en curs)."""
    day_over = session["local_date"] < today
    if session["sport"] == "rest":
        return "completed" if day_over else None
    if linked:
        if session.get("planned_load"):
            target = float(session["planned_load"])
            real = sum(float(a.get("load") or 0) for a in linked)
        else:
            target = session.get("duration_sec_target") or 0
            real = sum(a.get("duration_sec") or 0 for a in linked)
        if not target:
            return "completed"
        return "completed" if real >= COMPLETED_RATIO * target else "partial"
    return "missed" if day_over else None


def run_linking(conn, today: date | None = None) -> dict:
    today = today or date.today()
    sessions = [dict(zip(("id", "local_date", "sport", "duration_sec_target",
                          "planned_load", "status"), r))
                for r in conn.execute("""
                    select id, local_date, sport, duration_sec_target,
                           planned_load, status
                    from plan_session
                    where superseded_by is null and status = any(%s)""",
                    (list(MANAGED_STATUSES),))]
    activities = [dict(zip(("id", "local_date", "sport", "duration_sec", "load"), r))
                  for r in conn.execute("""
                    select id, local_date, sport, duration_sec, load from activity""")]

    by_day_sessions: dict[date, list[dict]] = {}
    for s in sessions:
        by_day_sessions.setdefault(s["local_date"], []).append(s)
    by_day_activities: dict[date, list[dict]] = {}
    for a in activities:
        by_day_activities.setdefault(a["local_date"], []).append(a)

    linked_by_session: dict[int, list[dict]] = {}
    n_links = 0
    for day, day_sessions in by_day_sessions.items():
        day_acts = by_day_activities.get(day, [])
        for act_id, sess_id in match_day(day_sessions, day_acts):
            conn.execute("update activity set plan_session_id = %s where id = %s",
                         (sess_id, act_id))
            activity = next(a for a in day_acts if a["id"] == act_id)
            linked_by_session.setdefault(sess_id, []).append(activity)
            n_links += 1

    changes = {"completed": 0, "partial": 0, "missed": 0}
    for s in sessions:
        new_status = session_status(s, linked_by_session.get(s["id"], []), today)
        if new_status and new_status != s["status"]:
            conn.execute("update plan_session set status = %s where id = %s",
                         (new_status, s["id"]))
            changes[new_status] += 1
    return {"links": n_links, **changes}


def main() -> None:
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")
    with psycopg.connect(url) as conn:
        result = run_linking(conn)
    print(f"vinculació: {result['links']} activitats lligades | canvis d'estat: "
          f"{result['completed']} completed, {result['partial']} partial, "
          f"{result['missed']} missed")


if __name__ == "__main__":
    main()
