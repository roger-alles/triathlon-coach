"""Proveïdor Garmin Connect (implementa ActivityProvider).

Login idèntic al de F0: tokens desats si n'hi ha (~/.garminconnect), i si no,
credencials del .env — la llibreria desa els tokens ella mateixa. Un 429 al
login vol dir IP bloquejada temporalment: esperar, no reintentar en bucle.
"""

import os
import sys
import time
from datetime import date
from pathlib import Path

from garminconnect import Garmin

TOKENSTORE = "~/.garminconnect"
PAUSE_SEC = 0.5  # amable amb el servidor (spec §9)


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
