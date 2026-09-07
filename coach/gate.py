"""Porta del matí: decideix si toca generar l'informe diari.

    .venv/bin/python -m coach.gate morning        # exit 0 = genera, 3 = espera

L'informe del matí sense el son de la nit no diu res útil (el coach acaba
preguntant "quantes hores has dormit?"). Garmin només publica el son quan el
rellotge sincronitza amb el mòbil, sovint hores després de l'hora fixa de la
feina. Per això la feina del matí s'executa cada 20 min i passa per aquí:
genera només quan hi ha son d'avui i encara no s'ha generat cap informe del
matí avui. COACH_FORCE=1 salta la comprovació (decisió humana explícita).

Independent d'on corri: "avui" és el dia a la zona horària de l'atleta
(ATHLETE_TZ, per defecte Europe/Madrid), no la del servidor.
"""

import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
EXIT_WAIT = 3


def local_today(tz: ZoneInfo, now: datetime | None = None) -> date:
    now = now or datetime.now(tz)
    return now.astimezone(tz).date()


def morning_decision(today: date, sleep_sec: int | None,
                     last_report_at: datetime | None, tz: ZoneInfo,
                     force: bool = False) -> tuple[bool, str]:
    """(genera?, motiu). last_report_at: darrer informe diari amb window_start=avui."""
    if force:
        return True, "forçat (COACH_FORCE=1)"
    if not sleep_sec:
        return False, "esperant: Garmin encara no té el son d'avui"
    midnight = datetime.combine(today, time.min, tzinfo=tz)
    if last_report_at is not None and last_report_at.astimezone(tz) >= midnight:
        hhmm = last_report_at.astimezone(tz).strftime("%H:%M")
        return False, f"ja generat avui a les {hhmm}"
    return True, f"son d'avui: {sleep_sec / 3600:.1f} h; cap informe del matí encara"


def read_state(conn, today: date) -> tuple[int | None, datetime | None]:
    sleep = conn.execute(
        "select sleep_duration_sec from daily_metric where local_date = %s",
        (today,)).fetchone()
    report = conn.execute(
        """select max(created_at) from coach_report
           where report_type = 'daily' and window_start = %s""",
        (today,)).fetchone()
    return (sleep[0] if sleep else None), (report[0] if report else None)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] != "morning":
        sys.exit("ús: python -m coach.gate morning")
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")
    tz = ZoneInfo(os.getenv("ATHLETE_TZ", "Europe/Madrid"))
    today = local_today(tz)
    with psycopg.connect(url) as conn:
        sleep_sec, last_report_at = read_state(conn, today)
    run, reason = morning_decision(today, sleep_sec, last_report_at, tz,
                                   force=os.getenv("COACH_FORCE") == "1")
    print(f"porta matí {today}: {'GENERA' if run else 'ESPERA'} — {reason}")
    sys.exit(0 if run else EXIT_WAIT)


if __name__ == "__main__":
    main()
