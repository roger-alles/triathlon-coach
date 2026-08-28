"""Sincronització Garmin -> base de dades (spec §9).

Incremental per defecte: reprèn des de l'última dada coneguda menys 3 dies de
marge (Garmin de vegades reprocessa). Idempotent: upserts — executar-la dues
vegades no duplica res. Per a la càrrega inicial: --since YYYY-MM-DD.

Ús:
    .venv/bin/python -m ingest.sync                    # incremental
    .venv/bin/python -m ingest.sync --since 2026-05-29 # càrrega inicial
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from ingest.mapping import map_activity, map_daily
from ingest.providers.garmin import GarminProvider

ROOT = Path(__file__).parent.parent
MARGIN_DAYS = 3

UPSERT_ACTIVITY = """
insert into activity (id, start_time, local_date, sport, sub_sport,
    duration_sec, moving_duration_sec, distance_m, elevation_gain_m,
    avg_hr, max_hr, avg_power_w, normalized_power_w,
    avg_pace_sec_km, avg_pace_sec_100m, avg_cadence, calories,
    garmin_training_load, aerobic_te, anaerobic_te, raw)
values (%(id)s, %(start_time)s, %(local_date)s, %(sport)s, %(sub_sport)s,
    %(duration_sec)s, %(moving_duration_sec)s, %(distance_m)s, %(elevation_gain_m)s,
    %(avg_hr)s, %(max_hr)s, %(avg_power_w)s, %(normalized_power_w)s,
    %(avg_pace_sec_km)s, %(avg_pace_sec_100m)s, %(avg_cadence)s, %(calories)s,
    %(garmin_training_load)s, %(aerobic_te)s, %(anaerobic_te)s, %(raw)s)
on conflict (id) do update set
    start_time = excluded.start_time,
    local_date = excluded.local_date,
    sport = excluded.sport,
    sub_sport = excluded.sub_sport,
    duration_sec = excluded.duration_sec,
    moving_duration_sec = excluded.moving_duration_sec,
    distance_m = excluded.distance_m,
    elevation_gain_m = excluded.elevation_gain_m,
    avg_hr = excluded.avg_hr,
    max_hr = excluded.max_hr,
    avg_power_w = excluded.avg_power_w,
    normalized_power_w = excluded.normalized_power_w,
    avg_pace_sec_km = excluded.avg_pace_sec_km,
    avg_pace_sec_100m = excluded.avg_pace_sec_100m,
    avg_cadence = excluded.avg_cadence,
    calories = excluded.calories,
    garmin_training_load = excluded.garmin_training_load,
    aerobic_te = excluded.aerobic_te,
    anaerobic_te = excluded.anaerobic_te,
    raw = excluded.raw,
    ingested_at = now()
"""
# Nota: load, load_estimated, perceived_effort, feeling, athlete_notes i
# plan_session_id NO es toquen al conflict: són nostres (calculats o manuals),
# i una re-sincronització no els ha d'esborrar mai.

UPSERT_DAILY = """
insert into daily_metric (local_date, resting_hr, hrv_last_night_ms, hrv_status,
    sleep_duration_sec, sleep_score, deep_sleep_sec,
    body_battery_max, body_battery_min, training_readiness, stress_avg,
    garmin_training_status, raw)
values (%(local_date)s, %(resting_hr)s, %(hrv_last_night_ms)s, %(hrv_status)s,
    %(sleep_duration_sec)s, %(sleep_score)s, %(deep_sleep_sec)s,
    %(body_battery_max)s, %(body_battery_min)s, %(training_readiness)s, %(stress_avg)s,
    %(garmin_training_status)s, %(raw)s)
on conflict (local_date) do update set
    resting_hr = excluded.resting_hr,
    hrv_last_night_ms = excluded.hrv_last_night_ms,
    hrv_status = excluded.hrv_status,
    sleep_duration_sec = excluded.sleep_duration_sec,
    sleep_score = excluded.sleep_score,
    deep_sleep_sec = excluded.deep_sleep_sec,
    body_battery_max = excluded.body_battery_max,
    body_battery_min = excluded.body_battery_min,
    training_readiness = excluded.training_readiness,
    stress_avg = excluded.stress_avg,
    garmin_training_status = excluded.garmin_training_status,
    raw = excluded.raw,
    ingested_at = now()
"""


def compute_start_date(last_known: date | None, since_arg: date | None) -> date:
    """Inici de la finestra de sync: --since mana; si no, incremental amb marge."""
    if since_arg:
        return since_arg
    if last_known is None:
        sys.exit("Base de dades buida: cal --since YYYY-MM-DD per a la càrrega inicial.")
    return last_known - timedelta(days=MARGIN_DAYS)


def last_date(conn, table: str) -> date | None:
    return conn.execute(f"select max(local_date) from {table}").fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=date.fromisoformat,
                        help="inici explícit de la finestra (càrrega inicial)")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")

    provider = GarminProvider()
    today = date.today()

    with psycopg.connect(url) as conn:
        # Activitats
        start = compute_start_date(last_date(conn, "activity"), args.since)
        activities = provider.fetch_activities(start, today)
        for a in activities:
            row = map_activity(a)
            row["raw"] = Jsonb(row["raw"])
            conn.execute(UPSERT_ACTIVITY, row)
        print(f"activitats: {len(activities)} upserts ({start} -> {today})")

        # Mètriques diàries
        start = compute_start_date(last_date(conn, "daily_metric"), args.since)
        n_days = (today - start).days + 1
        for i in range(n_days):
            day = start + timedelta(days=i)
            row = map_daily(day, provider.fetch_daily(day))
            row["raw"] = Jsonb(row["raw"])
            conn.execute(UPSERT_DAILY, row)
        print(f"mètriques diàries: {n_days} upserts ({start} -> {today})")


if __name__ == "__main__":
    main()
