"""Càrrega per activitat i corba de forma CTL/ATL/TSB (spec §5).

Càrrega d'una activitat, per ordre de preferència segons les dades:
  1. garmin_training_load (aquest dispositiu no la dona — docs/garmin-api.md)
  2. potència: (NP/FTP)² · hores · 100 — inaplicable: sense potenciòmetre ni FTP
  3. TRIMP per zones de FC: sum(minuts_zona_i · factor_i), factors [1,1.5,2.5,4,6].
     Les zones són les hrTimeInZone_* que calcula Garmin amb la seva pròpia
     configuració de zones — no les d'athlete.zones, que necessiten un max_hr
     que encara no existeix.
  4. durada_hores · 50, marcada load_estimated = true.

La sèrie CTL/ATL/TSB es recalcula SENCERA des de zero a cada execució (spec §5):
és barat i evita divergències quan arriba una activitat endarrerida.

Ús:
    .venv/bin/python -m ingest.load
"""

import os
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent

TRIMP_FACTORS = {1: 1.0, 2: 1.5, 3: 2.5, 4: 4.0, 5: 6.0}
CTL_DAYS = 42
ATL_DAYS = 7


def trimp_load(sec_by_zone: dict[int, float]) -> float | None:
    if sum(sec_by_zone.values()) <= 0:
        return None
    return round(sum(sec / 60 * TRIMP_FACTORS[z]
                     for z, sec in sec_by_zone.items() if z in TRIMP_FACTORS), 1)


def activity_load(raw: dict, duration_sec: int) -> tuple[float, bool]:
    """(càrrega, és_estimada) d'una activitat a partir del seu JSON cru."""
    garmin_load = raw.get("activityTrainingLoad")
    if garmin_load:
        return round(garmin_load, 1), False

    zones = {i: raw.get(f"hrTimeInZone_{i}") or 0 for i in range(1, 6)}
    trimp = trimp_load(zones)
    if trimp is not None:
        return trimp, False

    return round(duration_sec / 3600 * 50, 1), True


def form_series(daily_load: dict[date, float], start: date, end: date) -> list[dict]:
    """Corba de forma dia a dia. TSB del dia usa el CTL/ATL d'AHIR (spec §5)."""
    rows = []
    ctl = atl = 0.0
    for i in range((end - start).days + 1):
        day = start + timedelta(days=i)
        load = daily_load.get(day, 0.0)
        tsb = ctl - atl
        ctl += (load - ctl) / CTL_DAYS
        atl += (load - atl) / ATL_DAYS

        week = [daily_load.get(day - timedelta(days=n), 0.0) for n in range(7)]
        monotony = strain = None
        if i >= 6:
            std = statistics.stdev(week)
            if std > 0:
                monotony = round(statistics.mean(week) / std, 2)
                strain = round(monotony * sum(week), 1)

        # 4 decimals: prou per no acumular error; l'app ja arrodonirà per pintar
        rows.append({"local_date": day, "load": round(load, 1),
                     "ctl": round(ctl, 4), "atl": round(atl, 4),
                     "tsb": round(tsb, 4), "monotony": monotony, "strain": strain})
    return rows


def main() -> None:
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")

    with psycopg.connect(url) as conn:
        activities = conn.execute(
            "select id, local_date, duration_sec, raw from activity").fetchall()
        if not activities:
            sys.exit("Cap activitat a la base de dades: executa primer el sync.")

        daily: dict[date, float] = {}
        n_estimated = 0
        for act_id, local_date, duration_sec, raw in activities:
            load, estimated = activity_load(raw, duration_sec)
            n_estimated += estimated
            conn.execute(
                "update activity set load = %s, load_estimated = %s where id = %s",
                (load, estimated, act_id))
            daily[local_date] = daily.get(local_date, 0.0) + load

        series = form_series(daily, start=min(daily), end=date.today())
        with conn.transaction():
            conn.execute("delete from load_daily")
            for r in series:
                conn.execute("""
                    insert into load_daily (local_date, load, ctl, atl, tsb,
                                            monotony, strain)
                    values (%(local_date)s, %(load)s, %(ctl)s, %(atl)s, %(tsb)s,
                            %(monotony)s, %(strain)s)""", r)

        last = series[-1]
        print(f"càrrega: {len(activities)} activitats ({n_estimated} estimades per durada)")
        print(f"forma:   {len(series)} dies recalculats | avui "
              f"CTL {last['ctl']} · ATL {last['atl']} · TSB {last['tsb']}")


if __name__ == "__main__":
    main()
