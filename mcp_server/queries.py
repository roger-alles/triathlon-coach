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
    cur = conn.execute("""
        select local_date, load, ctl, atl, tsb, monotony, strain
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


def compliance(conn) -> dict:
    """Planificat vs real. Fins que la F3 no carregui el pla, ho diu clarament."""
    exists = conn.execute("""
        select 1 from information_schema.tables
        where table_schema = 'public' and table_name = 'plan_session'""").fetchone()
    if not exists:
        return {"status": "no_plan",
                "detail": "Encara no hi ha pla carregat: les taules del pla arriben a la F3. "
                          "De moment només hi ha activitats reals i corba de forma."}
    raise NotImplementedError("compliance real: F3")
