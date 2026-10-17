"""Proveïdor Garmin Connect (implementa ActivityProvider).

Login idèntic al de F0: tokens desats si n'hi ha (~/.garminconnect), i si no,
credencials del .env — la llibreria desa els tokens ella mateixa. Un 429 al
login vol dir IP bloquejada temporalment: esperar, no reintentar en bucle.
"""

import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

from garminconnect import Garmin

TOKENSTORE = "~/.garminconnect"
PAUSE_SEC = 0.5  # amable amb el servidor (spec §9)


class SleepStatus(NamedTuple):
    seconds: int
    end: datetime | None        # fi del son segons Garmin (UTC)
    last_sync: datetime | None  # última sincronització del rellotge avui (UTC)


def _login() -> Garmin:
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    had_tokens = (Path(TOKENSTORE).expanduser() / "garmin_tokens.json").exists()
    if not had_tokens and not (email and password):
        sys.exit("Ni tokens desats ni GARMIN_EMAIL/GARMIN_PASSWORD al .env.")
    client = Garmin(email=email, password=password,
                    prompt_mfa=lambda: input("Codi MFA: "))
    client.login(TOKENSTORE)
    return client


class GarminProvider:
    def __init__(self, client=None):
        # client injectable per als tests; en producció fa login de veritat
        self.client = client or _login()

    def fetch_activities(self, start: date, end: date) -> list[dict]:
        activities = self.client.get_activities_by_date(start.isoformat(),
                                                        end.isoformat())
        time.sleep(PAUSE_SEC)
        return activities

    def fetch_daily(self, day: date) -> dict:
        payload = {}
        for key, method in (("stats", self.client.get_stats),
                            ("sleep", self.client.get_sleep_data)):
            payload[key] = method(day.isoformat())
            time.sleep(PAUSE_SEC)
        return payload

    def fetch_sleep_status(self, day: date) -> SleepStatus | None:
        """El son d'un dia i l'última sincronització del rellotge: per a la porta del matí.
        None mentre Garmin encara no ha rebut la nit (una petició); si l'ha rebut,
        una segona petició (stats) per saber si el rellotge ha sincronitzat després
        de despertar-se. Una sincronització a mitja nit publica un son parcial."""
        payload = self.client.get_sleep_data(day.isoformat())
        time.sleep(PAUSE_SEC)
        dto = (payload or {}).get("dailySleepDTO") or {}
        if not dto.get("sleepTimeSeconds"):
            return None
        stats = self.client.get_stats(day.isoformat()) or {}
        time.sleep(PAUSE_SEC)
        end_ms = dto.get("sleepEndTimestampGMT")
        last_sync = stats.get("lastSyncTimestampGMT")  # "2026-10-17T13:17:45.558", GMT
        return SleepStatus(
            seconds=dto["sleepTimeSeconds"],
            end=datetime.fromtimestamp(end_ms / 1000, timezone.utc) if end_ms else None,
            last_sync=(datetime.fromisoformat(last_sync).replace(tzinfo=timezone.utc)
                       if last_sync else None))
