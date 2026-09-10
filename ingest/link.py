"""Vinculació planificat <-> real (spec §9).

Després de cada sync: cada activitat normal (swim/bike/run/strength/other)
s'associa a la seva plan_session (mateix dia i esport; si hi ha més d'una
candidata, la de durada més propera), i l'estat de la sessió es deriva del
que s'ha fet:

  completed  real >= 80% del planificat (planned_load si n'hi ha; si no,
             duration_sec_target; si no n'hi ha, distance_m_target; si no hi
             ha cap target, es dona per completed amb qualsevol activitat)
  partial    hi ha activitat però < 80%
  missed     el dia s'ha acabat sense cap activitat
  (les sessions de descans es completen soles quan passa el dia)

El rellotge mai registra l'esport 'brick': un brick real arriba com una
activitat 'bike' + una activitat 'run' el mateix dia. Les sessions 'brick' i
'multisport' (sport que no existeix a `activity`) no encaixen mai per
`match_day` — es resolen per composició d'esports del dia sencer, sense
escriure `activity.plan_session_id` (ja apunten a la sessió de bici/cursa del
dia, si n'hi ha):

  brick       cal bike + run el mateix dia; estat per la durada del run més
              curt (el tram a peu del brick) contra duration_sec_target.
              Només bike o només run -> partial (no missed) un cop passat el dia.
  multisport  cal >=2 esports diferents entre swim/bike/run el mateix dia;
              estat per la suma de durades d'aquests esports. Un sol esport
              -> partial un cop passat el dia.

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


def _brick_status(session: dict, day_acts: list[dict], day_over: bool) -> str | None:
    """Estat d'una sessió 'brick': cal bike + run el mateix dia."""
    bikes = [a for a in day_acts if a["sport"] == "bike"]
    runs = [a for a in day_acts if a["sport"] == "run"]
    if bikes and runs:
        target = session.get("duration_sec_target")
        if not target:
            return "completed"
        shortest_run = min(runs, key=lambda a: a.get("duration_sec") or 0)
        real = shortest_run.get("duration_sec") or 0
        return "completed" if real >= COMPLETED_RATIO * target else "partial"
    if bikes or runs:
        return "partial" if day_over else None
    return "missed" if day_over else None


def _multisport_status(session: dict, day_acts: list[dict], day_over: bool) -> str | None:
    """Estat d'una sessió 'multisport': cal >=2 esports (swim/bike/run) el mateix dia."""
    tri_acts = [a for a in day_acts if a["sport"] in ("swim", "bike", "run")]
    sports = {a["sport"] for a in tri_acts}
    if len(sports) >= 2:
        target = session.get("duration_sec_target")
        if not target:
            return "completed"
        real = sum(a.get("duration_sec") or 0 for a in tri_acts)
        return "completed" if real >= COMPLETED_RATIO * target else "partial"
    if sports:
        return "partial" if day_over else None
    return "missed" if day_over else None


def session_status(session: dict, linked: list[dict], today: date) -> str | None:
    """Nou estat de la sessió, o None per deixar-la com està (dia en curs).

    `linked` és, per a sessions normals i 'rest', les activitats ja
    aparellades per `match_day`; per a 'brick' i 'multisport', totes les
    activitats del dia sense filtrar (la vinculació és per composició
    d'esports, no 1-a-1).
    """
    day_over = session["local_date"] < today
    if session["sport"] == "rest":
        return "completed" if day_over else None
    if session["sport"] == "brick":
        return _brick_status(session, linked, day_over)
    if session["sport"] == "multisport":
        return _multisport_status(session, linked, day_over)
    if linked:
        if session.get("planned_load"):
            target = float(session["planned_load"])
            real = sum(float(a.get("load") or 0) for a in linked)
        elif session.get("duration_sec_target"):
            target = session["duration_sec_target"]
            real = sum(a.get("duration_sec") or 0 for a in linked)
        elif session.get("distance_m_target"):
            target = float(session["distance_m_target"])
            real = sum(float(a.get("distance_m") or 0) for a in linked)
        else:
            return "completed"
        return "completed" if real >= COMPLETED_RATIO * target else "partial"
    return "missed" if day_over else None


def run_linking(conn, today: date | None = None) -> dict:
    today = today or date.today()
    sessions = [dict(zip(("id", "local_date", "sport", "duration_sec_target",
                          "distance_m_target", "planned_load", "status"), r))
                for r in conn.execute("""
                    select id, local_date, sport, duration_sec_target,
                           distance_m_target, planned_load, status
                    from plan_session
                    where superseded_by is null and status = any(%s)""",
                    (list(MANAGED_STATUSES),))]
    activities = [dict(zip(("id", "local_date", "sport", "duration_sec",
                            "distance_m", "load"), r))
                  for r in conn.execute("""
                    select id, local_date, sport, duration_sec, distance_m, load
                    from activity""")]

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
        for s in day_sessions:
            if s["sport"] in ("brick", "multisport"):
                linked_by_session[s["id"]] = day_acts

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
