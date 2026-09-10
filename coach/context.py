"""Constructor del context del coach (spec §7, pas 1 del bucle).

Determinista i en codi: el model NO consulta la base de dades sol — rep
exactament aquest snapshot, que es desa sencer a coach_report.input_snapshot
per poder reconstruir després què sabia quan va decidir.

Higiene de tokens: resums i agregats, mai dades crues (spec §13); els camps
NULL s'eliminen abans d'enviar (compact) — un dispositiu que no dona HRV no
ha de costar tokens dient-ho 28 vegades.
"""

from datetime import date, timedelta

from mcp_server import queries

RECENT_DAYS = 28
RECOVERY_DAYS = 14
PLAN_AHEAD_DAYS = 14
COMPLIANCE_WEEKS = 3


def compact(value):
    """Elimina None, dicts buits i llistes buides, recursivament."""
    if isinstance(value, dict):
        cleaned = {k: compact(v) for k, v in value.items()}
        return {k: v for k, v in cleaned.items()
                if v is not None and v != {} and v != []}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def days_until(event_date: date | None, today: date) -> int | None:
    return (event_date - today).days if event_date else None


def _athlete(conn) -> dict:
    row = conn.execute("""select name, birth_date, max_hr, resting_hr_baseline,
                          ftp_watts, css_sec_per_100m, threshold_pace_sec_km
                          from athlete where id = 1""").fetchone()
    cols = ("name", "birth_date", "max_hr", "resting_hr_baseline", "ftp_watts",
            "css_sec_per_100m", "threshold_pace_sec_km")
    athlete = dict(zip(cols, row))
    athlete["birth_date"] = str(athlete["birth_date"]) if athlete["birth_date"] else None
    missing = [c for c in ("max_hr", "ftp_watts", "css_sec_per_100m",
                           "threshold_pace_sec_km") if athlete[c] is None]
    if missing:
        athlete["thresholds_missing"] = missing  # el coach ha de saber què NO sap
    return athlete


def _goals(conn, today: date) -> list[dict]:
    out = []
    for r in conn.execute("""select name, discipline, event_date, priority, profile
                             from goal where status = 'active'
                             order by priority, event_date nulls last"""):
        profile = r[4] or {}
        out.append({
            "name": r[0], "discipline": r[1],
            "event_date": str(r[2]) if r[2] else None,
            "days_to_event": days_until(r[2], today),
            "priority": r[3],
            "segments": profile.get("segments"),
            "target_times_sec": profile.get("target_times_sec"),
            "emphasis": profile.get("emphasis"),
            "athlete_context": profile.get("athlete_context"),
            "pacing_rules": profile.get("pacing_rules"),
        })
    return out


def _current_block(conn, today: date) -> dict | None:
    r = conn.execute("""select phase, name, start_date, end_date,
                        target_weekly_hours, fallback, intent, return_from_layoff
                        from plan_block where %s between start_date and end_date
                        order by start_date limit 1""", (today,)).fetchone()
    if not r:
        return None
    return {"phase": r[0], "name": r[1], "start_date": str(r[2]), "end_date": str(r[3]),
            "target_weekly_hours": float(r[4]) if r[4] else None,
            "fallback": r[5], "intent": r[6], "return_from_layoff": r[7]}


def _recovery(conn, today: date) -> list[dict]:
    cur = conn.execute("""
        select local_date, resting_hr, round(sleep_duration_sec / 360.0) / 10 as sleep_h,
               deep_sleep_sec, body_battery_max, body_battery_min, stress_avg,
               hrv_status, training_readiness
        from daily_metric
        where local_date > %s order by local_date""",
        (today - timedelta(days=RECOVERY_DAYS),))
    return queries._rows_to_dicts(cur)


def _plan_ahead(conn, today: date) -> list[dict]:
    cur = conn.execute("""
        select id, local_date, sport, session_type, title, priority, status,
               duration_sec_target, distance_m_target, rationale, is_test,
               rehearses_goal, is_goal_event, structure
        from plan_session
        where superseded_by is null
          and local_date between %s and %s
        order by local_date, priority""",
        (today, today + timedelta(days=PLAN_AHEAD_DAYS)))
    rows = queries._rows_to_dicts(cur)
    # l'estructura detallada només dels 3 propers dies: és sobre el que el
    # coach decideix; de la resta en té prou amb tipus, títol i durada
    horizon = (today + timedelta(days=3)).isoformat()
    for row in rows:
        if row["local_date"] > horizon:
            row.pop("structure", None)
    return rows


def _recent_notes(conn, today: date) -> list[dict]:
    cur = conn.execute("""
        select local_date, sport, athlete_notes, perceived_effort, feeling
        from activity
        where athlete_notes is not null and local_date > %s
        order by local_date desc""", (today - timedelta(days=RECOVERY_DAYS),))
    return queries._rows_to_dicts(cur)


def _recent_answers(conn, today: date) -> list[dict]:
    """Respostes de l'atleta (des de l'app) a preguntes d'informes anteriors."""
    cur = conn.execute("""
        select created_at, question, answer
        from athlete_answer
        where created_at > %s
        order by created_at desc
        limit 10""", (today - timedelta(days=7),))
    return queries._rows_to_dicts(cur)


def _test_results(conn) -> list[dict]:
    """Marques de referència: tests fets (test_result), els valors aplanats.
    Sense finestra temporal: una marca val fins que n'hi ha una de més nova."""
    cur = conn.execute("""
        select t.local_date, t.metric, t.values, p.title as session_title
        from test_result t
        left join plan_session p on p.id = t.plan_session_id
        order by t.local_date""")
    rows = []
    for row in queries._rows_to_dicts(cur):
        values = row.pop("values") or {}
        rows.append({"local_date": row["local_date"], "metric": row["metric"],
                     **values, "session_title": row.get("session_title")})
    return rows


def _logistics(conn, today: date) -> list[dict]:
    """Tasques de logística pendents dels propers 10 dies (viatge, dorsal...):
    no fer-les costa la cursa, i el coach les ha de recordar."""
    cur = conn.execute("""
        select local_date, title, detail, blocking, done
        from logistics_task
        where done = false and local_date between %s and %s
        order by local_date, blocking desc""",
        (today, today + timedelta(days=10)))
    return queries._rows_to_dicts(cur)


def _past_compliance(conn, today: date) -> dict:
    """El compliment del coach mira enrere; el futur ja és a plan_next_14d."""
    result = queries.compliance(conn, COMPLIANCE_WEEKS)
    if result.get("sessions"):
        result["sessions"] = [s for s in result["sessions"]
                              if s["local_date"] < today.isoformat()]
    return result


def build_context(conn, today: date | None = None) -> dict:
    """El snapshot complet que rep el model (spec §7, pas 1)."""
    today = today or date.today()
    context = {
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "athlete": _athlete(conn),
        "goals": _goals(conn, today),
        "current_block": _current_block(conn, today),
        "activities_last_28d": queries.recent_activities(conn, RECENT_DAYS),
        "form_curve_28d": queries.form_curve(conn, RECENT_DAYS),
        "recovery_last_14d": _recovery(conn, today),
        "compliance": _past_compliance(conn, today),
        "test_results": _test_results(conn),
        "plan_next_14d": _plan_ahead(conn, today),
        "recent_athlete_notes": _recent_notes(conn, today),
        "athlete_answers_last_7d": _recent_answers(conn, today),
        "logistics_next_10d": _logistics(conn, today),
    }
    return compact(context)
