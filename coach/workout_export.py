"""Sessió del pla → workout de Garmin Connect (spec §F6: el pla al rellotge).

    .venv/bin/python -m coach.workout_export --session-id 67            # mostra el JSON
    .venv/bin/python -m coach.workout_export --session-id 67 --push     # puja + programa al calendari

Format: el mateix que Garmin retorna a get_workout_by_id (ids de la llibreria
garminconnect.workout). RPE no existeix a Garmin: cada pas va sense objectiu
("no.target") i amb el RPE i la nota a la descripció, que el rellotge mostra.
`contains` (repunts dins d'un bloc) s'aplana: trams al ritme base + repunts.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

SPORT = {"bike": (2, "cycling"), "run": (1, "running"), "swim": (4, "swimming")}
STEP = {"warmup": (1, "warmup"), "cooldown": (2, "cooldown"), "interval": (3, "interval"),
        "recovery": (4, "recovery"), "repeat": (6, "repeat")}
END_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
END_DIST = {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}


def describe(target: dict | None, note: str | None = None) -> str:
    parts = []
    if target:
        kind, value, label = target.get("type"), target.get("value"), target.get("label")
        if kind == "rpe":
            parts.append(f"RPE {value}")
        elif kind == "pace_sec_100m":
            parts.append(f"{int(value) // 60}:{int(value) % 60:02d}/100 m")
        elif kind == "pace_sec_km":
            parts.append(f"{int(value) // 60}:{int(value) % 60:02d}/km")
        elif kind == "open":
            parts.append("lliure")
        if label and label not in " ".join(parts):
            parts.append(label)
    if note:
        parts.append(note)
    return " · ".join(parts)


def expand_contains(work: dict) -> list[dict]:
    """Bloc de N s amb K repunts de M s → [tram, repunt, tram, ..., tram] que sumen N."""
    inner = work.get("contains")
    if not inner:
        return [work]
    k, m = int(inner.get("repeats", 1)), int(inner["duration_sec"])
    base_total = int(work["duration_sec"]) - k * m
    n_base = k + 1
    base = [base_total // n_base] * n_base
    base[-1] += base_total - sum(base)
    base_step = {k2: v for k2, v in work.items() if k2 != "contains"}
    surge = {"duration_sec": m, "target": inner.get("target"), "note": inner.get("note")}
    out = []
    for i in range(k):
        out.append({**base_step, "duration_sec": base[i]})
        out.append(surge)
    out.append({**base_step, "duration_sec": base[-1]})
    return out


def _end(step: dict) -> tuple[dict, float]:
    if step.get("duration_sec") is not None:
        return END_TIME, float(step["duration_sec"])
    if step.get("distance_m") is not None:
        return END_DIST, float(step["distance_m"])
    raise ValueError(f"pas sense durada ni distància: {step}")


def _exec(step: dict, kind: str, order: int, child: int | None) -> dict:
    cond, value = _end(step)
    tid, tkey = STEP[kind]
    return {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": {"stepTypeId": tid, "stepTypeKey": tkey, "displayOrder": tid},
            "childStepId": child, "description": describe(step.get("target"), step.get("note")) or None,
            "endCondition": cond, "endConditionValue": value, "targetType": NO_TARGET}


def session_to_garmin_workout(session: dict) -> dict:
    sport_id, sport_key = SPORT[session["sport"]]
    sport = {"sportTypeId": sport_id, "sportTypeKey": sport_key, "displayOrder": sport_id}
    steps, order, group = [], 1, 0
    for s in session["structure"]["steps"]:
        phase = s.get("phase", "main")
        if s.get("repeats"):
            group += 1
            rep = {"type": "RepeatGroupDTO", "stepOrder": order,
                   "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
                   "childStepId": group, "numberOfIterations": int(s["repeats"]), "workoutSteps": []}
            order += 1
            for part in expand_contains(s["work"]):
                rep["workoutSteps"].append(_exec(part, "interval", order, group)); order += 1
            if s.get("recovery"):
                rep["workoutSteps"].append(_exec(s["recovery"], "recovery", order, group)); order += 1
            steps.append(rep)
        else:
            kind = phase if phase in ("warmup", "cooldown") else "interval"
            steps.append(_exec(s, kind, order, None)); order += 1
    return {"workoutName": session["title"], "description": f"Pla Fornells · sessió {session['id']} · {session['local_date']}",
            "sportType": sport, "estimatedDurationInSecs": int(session.get("duration_sec_target") or 0) or None,
            "workoutSegments": [{"segmentOrder": 1, "sportType": sport, "workoutSteps": steps}]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", type=int, required=True)
    parser.add_argument("--push", action="store_true", help="puja a Garmin Connect i programa-la al dia de la sessió")
    args = parser.parse_args()
    import psycopg
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute("""select id, sport, title, local_date, duration_sec_target, structure
                              from plan_session where id = %s""", (args.session_id,)).fetchone()
    if not row:
        sys.exit(f"sessió {args.session_id} no trobada")
    session = dict(zip(["id", "sport", "title", "local_date", "duration_sec_target", "structure"], row))
    session["local_date"] = session["local_date"].isoformat()
    workout = session_to_garmin_workout(session)
    if not args.push:
        print(json.dumps(workout, ensure_ascii=False, indent=1)); return
    from ingest.providers.garmin import _login
    g = _login()
    created = g.upload_workout(workout)
    wid = created["workoutId"]
    g.schedule_workout(wid, session["local_date"])
    print(f"pujada: workout {wid} '{workout['workoutName']}' programada el {session['local_date']}")
    try:
        g.push_workout_to_device(wid)
        print("enviada al rellotge (sincronitza'l)")
    except Exception as e:  # el calendari ja la porta; el push directe és opcional
        print(f"push directe no disponible ({e}); arribarà pel calendari en sincronitzar")


if __name__ == "__main__":
    main()
