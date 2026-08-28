"""Consultes del servidor MCP: funcions pures + lectures de la base de dades.

Les funcions que reben `conn` fan SQL; la resta són pures i tenen test.
Tot retorna dicts serialitzables a JSON (dates en ISO, Decimals a float).
"""

from datetime import date, timedelta


def week_bounds(day: date, offset_weeks: int = 0) -> tuple[date, date]:
    """(dilluns, diumenge) de la setmana de `day`, desplaçada offset_weeks."""
    monday = day - timedelta(days=day.weekday()) + timedelta(weeks=offset_weeks)
    return monday, monday + timedelta(days=6)


def summarize_by_sport(rows: list[dict]) -> dict:
    """Totals per esport: sessions, hores, km i càrrega."""
    totals: dict[str, dict] = {}
    for r in rows:
        t = totals.setdefault(r["sport"],
                              {"sessions": 0, "hours": 0.0, "distance_km": 0.0, "load": 0.0})
        t["sessions"] += 1
        t["hours"] = round(t["hours"] + (r.get("duration_sec") or 0) / 3600, 2)
        t["distance_km"] = round(t["distance_km"] + (r.get("distance_m") or 0) / 1000, 1)
        t["load"] = round(t["load"] + float(r.get("load") or 0), 1)
    return totals


ACTIVITY_COLS = """
    local_date, sport, sub_sport, raw->>'activityName' as name,
    duration_sec, distance_m, avg_hr, avg_pace_sec_km, avg_pace_sec_100m,
    load, load_estimated, perceived_effort, feeling, athlete_notes
"""


def _rows_to_dicts(cur) -> list[dict]:
    cols = [c.name for c in cur.description]
    out = []
    for row in cur.fetchall():
        d = {}
        for col, val in zip(cols, row):
            if isinstance(val, date):
                val = val.isoformat()
            elif hasattr(val, "is_finite"):  # Decimal
                val = float(val)
            d[col] = val
        out.append(d)
    return out


def recent_activities(conn, days: int) -> list[dict]:
    cur = conn.execute(f"""
        select {ACTIVITY_COLS} from activity
        where local_date >= current_date - %s::int
        order by local_date desc, start_time desc""", (days,))
    return _rows_to_dicts(cur)


def form_curve(conn, days: int) -> list[dict]:
    # arrodonit a 1 decimal: la precisió interna és de càlcul, no de lectura
    cur = conn.execute("""
        select local_date, round(load, 1) as load, round(ctl, 1) as ctl,
               round(atl, 1) as atl, round(tsb, 1) as tsb, monotony
        from load_daily
        where local_date >= current_date - %s::int
        order by local_date""", (days,))
    return _rows_to_dicts(cur)


def week(conn, offset_weeks: int) -> dict:
    monday, sunday = week_bounds(date.today(), offset_weeks)
    cur = conn.execute(f"""
        select {ACTIVITY_COLS} from activity
        where local_date between %s and %s
        order by local_date""", (monday, sunday))
    activities = _rows_to_dicts(cur)
    return {
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "totals_by_sport": summarize_by_sport(activities),
        "activities": activities,
    }


def summarize_compliance(due_rows: list[dict]) -> dict:
    """Totals sobre les sessions vençudes (dies ja acabats)."""
    totals = {"completed": 0, "partial": 0, "missed": 0, "planned": 0,
              "moved": 0, "cancelled": 0}
    for r in due_rows:
        if r["status"] in totals:
            totals[r["status"]] += 1
    resolved = totals["completed"] + totals["partial"] + totals["missed"]
    adherence = (round((totals["completed"] + 0.5 * totals["partial"])
                       / resolved * 100) if resolved else None)
    return {"totals": totals, "adherence_pct": adherence}


def compliance(conn, weeks: int = 3) -> dict:
    """Planificat vs real: sessions de les últimes N setmanes i la propera."""
    rows = conn.execute("""
        select s.local_date, s.sport, s.title, s.priority, s.status,
               s.duration_sec_target,
               coalesce(sum(a.duration_sec), 0) as actual_sec,
               count(a.id) as n_activities
        from plan_session s
        left join activity a on a.plan_session_id = s.id
        where s.superseded_by is null
          and s.local_date between current_date - %s::int and current_date + 7
        group by s.id
        order by s.local_date""", (weeks * 7,))
    sessions = _rows_to_dicts(rows)
    if not sessions:
        return {"status": "no_plan",
                "detail": "Cap sessió planificada a la finestra: o el pla encara no "
                          "està carregat, o és fora de rang."}
    today = date.today().isoformat()
    due = [s for s in sessions if s["local_date"] < today]
    return {"status": "ok",
            "window_weeks_back": weeks,
            **summarize_compliance(due),
            "sessions": sessions}
