"""Porta del matí: decideix si toca generar l'informe diari.

    .venv/bin/python -m coach.gate morning        # exit 0 = genera, 3 = espera

L'informe del matí sense el son de la nit no diu res útil (el coach acaba
preguntant "quantes hores has dormit?"). Garmin només publica el son quan el
rellotge sincronitza amb el mòbil, sovint hores després de l'hora fixa de la
feina. Per això la feina del matí s'intenta cada 5 min i passa per aquí abans
de fer res car. Ordre, parant al primer "no":

  1. ¿Ja hi ha informe del matí avui?  → base de dades, zero peticions a Garmin
  2. ¿Garmin té el son d'avui?          → UNA petició (el bloc de son del dia)
  3. Genera: la feina fa el sync complet i crida el coach.

Un intent buit costa 1 petició a Garmin (o 0, un cop hi ha informe). El sync
complet (15-20 peticions) es fa un sol cop al dia, quan toca.
COACH_FORCE=1 salta la porta (decisió humana explícita, futur botó a l'app).

Independent d'on corri: "avui" és el dia a la zona horària de l'atleta
(ATHLETE_TZ, per defecte Europe/Madrid), no la del servidor.
"""

import os
import sys
from collections.abc import Callable
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


def morning_decision(today: date, last_report_at: datetime | None,
                     sleep: Callable[[], int | None], tz: ZoneInfo,
                     force: bool = False) -> tuple[bool, str]:
    """(genera?, motiu). `sleep` és una funció perquè només es cridi si cal:
    és la petició a Garmin. last_report_at: darrer informe diari amb window_start=avui."""
    if force:
        return True, "forçat (COACH_FORCE=1)"
    midnight = datetime.combine(today, time.min, tzinfo=tz)
    if last_report_at is not None and last_report_at.astimezone(tz) >= midnight:
        hhmm = last_report_at.astimezone(tz).strftime("%H:%M")
        return False, f"ja generat avui a les {hhmm}"
    sleep_sec = sleep()
    if not sleep_sec:
        return False, "esperant: Garmin encara no té el son d'avui"
    return True, f"son d'avui: {sleep_sec / 3600:.1f} h; cap informe del matí encara"


def last_morning_report(conn, today: date) -> datetime | None:
    row = conn.execute(
        """select max(created_at) from coach_report
           where report_type = 'daily' and window_start = %s""",
        (today,)).fetchone()
    return row[0] if row else None


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
        last_report_at = last_morning_report(conn, today)

    def sleep_from_garmin() -> int | None:
        from ingest.providers.garmin import GarminProvider  # login només si cal
        return GarminProvider().fetch_sleep_seconds(today)

    run, reason = morning_decision(today, last_report_at, sleep_from_garmin, tz,
                                   force=os.getenv("COACH_FORCE") == "1")
    print(f"porta matí {today}: {'GENERA' if run else 'ESPERA'} — {reason}")
    sys.exit(0 if run else EXIT_WAIT)


if __name__ == "__main__":
    main()
