"""Mapeig de les respostes de Garmin al nostre model (spec §3).

Funcions pures: dict de Garmin a dins, dict de columnes a fora. Cap accés a
xarxa ni a base de dades — per això es poden testejar amb fixtures reals.
Regla d'or (spec §0): si una dada no hi és, NULL. Mai inventada ni a zero.
"""

from datetime import date, datetime, timezone

# typeKey de Garmin -> sport del nostre model. Tot el que no és a la taula cau
# a 'other'; el typeKey original es conserva sempre a sub_sport.
SPORT_MAP = {
    "running": "run",
    "trail_running": "run",
    "treadmill_running": "run",
    "track_running": "run",
    "cycling": "bike",
    "road_biking": "bike",
    "mountain_biking": "bike",
    "gravel_cycling": "bike",
    "indoor_cycling": "bike",
    "virtual_ride": "bike",
    "lap_swimming": "swim",
    "open_water_swimming": "swim",
    "strength_training": "strength",
    "multi_sport": "brick",
}


def map_sport(type_key: str) -> str:
    return SPORT_MAP.get(type_key, "other")


def _pace(avg_speed_m_s, meters: int):
    """Segons per recórrer `meters` a la velocitat donada (None si no n'hi ha)."""
    if not avg_speed_m_s or avg_speed_m_s <= 0:
        return None
    return round(meters / avg_speed_m_s, 1)


def map_activity(a: dict) -> dict:
    """D'un resum d'activitat de get_activities_by_date a una fila d'`activity`."""
    sport = map_sport(a["activityType"]["typeKey"])
    avg_speed = a.get("averageSpeed")
    return {
        "id": a["activityId"],
        "start_time": datetime.strptime(a["startTimeGMT"], "%Y-%m-%d %H:%M:%S")
                              .replace(tzinfo=timezone.utc),
        "local_date": date.fromisoformat(a["startTimeLocal"][:10]),
        "sport": sport,
        "sub_sport": a["activityType"]["typeKey"],
        "duration_sec": round(a["duration"]),
        "moving_duration_sec": round(a["movingDuration"]) if a.get("movingDuration") else None,
        "distance_m": a.get("distance"),
        "elevation_gain_m": a.get("elevationGain"),
        "avg_hr": round(a["averageHR"]) if a.get("averageHR") else None,
        "max_hr": round(a["maxHR"]) if a.get("maxHR") else None,
        "avg_power_w": a.get("avgPower"),
        "normalized_power_w": a.get("normPower"),
        "avg_pace_sec_km": _pace(avg_speed, 1000) if sport == "run" else None,
        "avg_pace_sec_100m": _pace(avg_speed, 100) if sport == "swim" else None,
        "avg_cadence": a.get("averageRunningCadenceInStepsPerMinute")
                       or a.get("averageBikingCadenceInRevPerMinute"),
        "calories": round(a["calories"]) if a.get("calories") else None,
        "garmin_training_load": a.get("activityTrainingLoad"),
        "aerobic_te": a.get("aerobicTrainingEffect"),
        "anaerobic_te": a.get("anaerobicTrainingEffect"),
        "raw": a,
    }


def _body_battery_max(stats: dict, sleep: dict) -> int | None:
    """La càrrega del dia (el valor en despertar), encara que el resum diari
    vagi endarrerit. Garmin té el son abans que el resum (`get_stats`): els
    matins del 06, 08 i 09/10/2026 el coach va llegir 64, 8 i 25 quan en
    despertar era 87, 53 i 99 (només hi havia el valor de mitjanit). La sèrie
    de la nit (`sleep.sleepBodyBattery`) arriba amb el son."""
    night = [p.get("value") for p in (sleep.get("sleepBodyBattery") or [])
             if isinstance(p, dict)]
    values = [v for v in (stats.get("bodyBatteryHighestValue"),
                          stats.get("bodyBatteryAtWakeTime"), *night)
              if isinstance(v, (int, float))]
    return max(values) if values else None


def map_daily(day: date, payload: dict) -> dict:
    """De {stats, sleep} d'un dia a una fila de `daily_metric`."""
    stats = payload.get("stats") or {}
    sleep = payload.get("sleep") or {}
    sleep_dto = sleep.get("dailySleepDTO") or {}
    sleep_scores = sleep_dto.get("sleepScores") or {}
    return {
        "local_date": day,
        "resting_hr": stats.get("restingHeartRate"),
        "hrv_last_night_ms": None,      # el dispositiu no dona HRV (docs/garmin-api.md)
        "hrv_status": None,
        "sleep_duration_sec": sleep_dto.get("sleepTimeSeconds"),
        "sleep_score": (sleep_scores.get("overall") or {}).get("value"),
        "deep_sleep_sec": sleep_dto.get("deepSleepSeconds"),
        "body_battery_max": _body_battery_max(stats, sleep),
        "body_battery_min": stats.get("bodyBatteryLowestValue"),
        "training_readiness": None,     # tampoc disponible en aquest dispositiu
        "stress_avg": stats.get("averageStressLevel"),
        "garmin_training_status": None,
        "raw": payload,
    }
