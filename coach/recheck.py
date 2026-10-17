"""Xarxa de seguretat de l'informe del matí: el refà si el son ha canviat.

    .venv/bin/python -m coach.recheck        # després de cada sync horari

La porta del matí (coach.gate) espera una sincronització de les 06:00 o més
tard, però no pot saber si en Roger encara dormia: un dissabte que es lleva a
les 9 amb una sincronització a les 06:30, l'informe surt amb el son a mitges.
Aquí es compara el que l'informe va fer servir (input_snapshot) amb el que
la base de dades té ara, que el sync horari acaba d'actualitzar. Si el son o
la body battery han canviat prou, es refà l'informe UN cop (mai més d'una
correcció al dia) i se li posa una nota. Zero peticions a Garmin. Només al
matí: a la tarda, l'informe ja no es llegeix per decidir el dia.
"""

import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
SLEEP_DIFF_H = 1.0
BODY_BATTERY_DIFF = 15
UNTIL = time(12, 0)  # hora local


def _num(x) -> str:
    return f"{float(x):g}".replace(".", ",")  # coma decimal: el text va a l'app


def changed_inputs(used: dict | None, now: dict | None) -> str | None:
    """Què ha canviat entre les dades de l'informe i les d'ara, o None si res
    rellevant. `used`/`now`: {"sleep_h", "body_battery_max"} del dia."""
    if not now:
        return None
    used = used or {}
    changes = []
    for key, diff, unit in (("sleep_h", SLEEP_DIFF_H, " h"),
                            ("body_battery_max", BODY_BATTERY_DIFF, "")):
        before, after = used.get(key), now.get(key)
        if after is None:
            continue
        if before is None or abs(float(after) - float(before)) >= diff:
            shown = "?" if before is None else _num(before) + unit
            label = "son" if key == "sleep_h" else "body battery màxima"
            changes.append(f"{label} {shown} → {_num(after)}{unit}")
    return ", ".join(changes) or None


def recheck_decision(today: date, now: datetime, tz: ZoneInfo,
                     morning_reports: list[dict], metrics: dict | None) -> tuple[bool, str]:
    """(refer?, motiu). morning_reports: informes diaris d'avui fets avui
    (window_start=avui; el preview del vespre anterior no compta), per ordre."""
    if now.astimezone(tz).time() >= UNTIL:
        return False, f"passades les {UNTIL:%H:%M}, ja no es corregeix"
    if not morning_reports:
        return False, "encara no hi ha informe del matí"
    if len(morning_reports) > 1:
        return False, "l'informe d'avui ja s'ha corregit (o refet) un cop"
    used = next((d for d in morning_reports[0]["snapshot"].get("recovery_last_14d") or []
                 if d.get("local_date") == today.isoformat()), None)
    changes = changed_inputs(used, metrics)
    if changes is None:
        return False, "les dades del son no han canviat"
    return True, changes


def morning_reports(conn, today: date, tz: ZoneInfo) -> list[dict]:
    midnight = datetime.combine(today, time.min, tzinfo=tz)
    rows = conn.execute(
        """select id, created_at, input_snapshot from coach_report
           where report_type = 'daily' and window_start = %s and created_at >= %s
           order by created_at""", (today, midnight)).fetchall()
    return [{"id": r[0], "created_at": r[1], "snapshot": r[2] or {}} for r in rows]


def today_metrics(conn, today: date) -> dict | None:
    # mateix arrodoniment que coach.context (recovery_last_14d)
    row = conn.execute(
        """select round(sleep_duration_sec / 360.0) / 10, body_battery_max
           from daily_metric where local_date = %s""", (today,)).fetchone()
    if row is None:
        return None
    return {"sleep_h": row[0], "body_battery_max": row[1]}


def mark_corrected(conn, report_id: int, changes: str, first_at: datetime,
                   tz: ZoneInfo) -> None:
    note = (f"*(Informe corregit: el de les {first_at.astimezone(tz):%H:%M} es va fer "
            f"amb dades de son incompletes; ara Garmin té la nit sencera: {changes}.)*")
    conn.execute(
        """update coach_report
           set output = jsonb_set(output, '{rationale}',
                                  to_jsonb(%s || E'\\n\\n' || (output->>'rationale'))),
               summary_md = %s || E'\\n\\n' || summary_md
           where id = %s""", (note, note, report_id))


def main() -> None:
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")
    tz = ZoneInfo(os.getenv("ATHLETE_TZ", "Europe/Madrid"))
    now = datetime.now(tz)
    today = now.date()
    with psycopg.connect(url) as conn:
        reports = morning_reports(conn, today, tz)
        metrics = today_metrics(conn, today)
    redo, reason = recheck_decision(today, now, tz, reports, metrics)
    print(f"revisió del matí {today}: {'REFÀ' if redo else 'RES'} — {reason}")
    if not redo:
        return
    from coach.run import run_cycle  # crida al model només si cal
    result = run_cycle("daily", url=url, today=today)
    with psycopg.connect(url) as conn:
        mark_corrected(conn, result["report_id"], reason, reports[0]["created_at"], tz)
    print(f"informe {result['report_id']} marcat com a correcció de "
          f"l'informe {reports[0]['id']}")


if __name__ == "__main__":
    main()
