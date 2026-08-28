"""Tests del proveïdor Garmin amb client fals (la xarxa no es testeja)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import ingest.providers.garmin as garmin_mod
from ingest.providers.garmin import GarminProvider


class _FakeClient:
    def __init__(self):
        self.calls = []

    def get_activities_by_date(self, start, end):
        self.calls.append(("activities", start, end))
        return [{"activityId": 1}]

    def get_stats(self, d):
        self.calls.append(("stats", d))
        return {"restingHeartRate": 50}

    def get_sleep_data(self, d):
        self.calls.append(("sleep", d))
        return {"dailySleepDTO": {}}


def test_fetch_activities_passes_iso_dates(monkeypatch):
    monkeypatch.setattr(garmin_mod, "PAUSE_SEC", 0)
    fake = _FakeClient()
    provider = GarminProvider(client=fake)
    result = provider.fetch_activities(date(2026, 5, 29), date(2026, 8, 27))
    assert result == [{"activityId": 1}]
    assert fake.calls == [("activities", "2026-05-29", "2026-08-27")]


def test_fetch_daily_returns_stats_and_sleep(monkeypatch):
    monkeypatch.setattr(garmin_mod, "PAUSE_SEC", 0)
    provider = GarminProvider(client=_FakeClient())
    payload = provider.fetch_daily(date(2026, 8, 26))
    assert payload["stats"] == {"restingHeartRate": 50}
    assert payload["sleep"] == {"dailySleepDTO": {}}
