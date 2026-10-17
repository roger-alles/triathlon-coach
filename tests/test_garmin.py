"""Tests del proveïdor Garmin amb client fals (la xarxa no es testeja)."""

import sys
from datetime import date, datetime, timezone
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


def test_fetch_sleep_status_son_fi_i_sincronitzacio(monkeypatch):
    # Valors reals del 17/10/2026: fi del son 06:17 UTC, sincronització 13:17 UTC
    monkeypatch.setattr(garmin_mod, "PAUSE_SEC", 0)
    fake = _FakeClient()
    fake.get_sleep_data = lambda d: (fake.calls.append(("sleep", d)) or
                                     {"dailySleepDTO": {"sleepTimeSeconds": 34320,
                                                        "sleepEndTimestampGMT": 1792217820000}})
    fake.get_stats = lambda d: (fake.calls.append(("stats", d)) or
                                {"lastSyncTimestampGMT": "2026-10-17T13:17:45.558"})
    status = GarminProvider(client=fake).fetch_sleep_status(date(2026, 10, 17))
    assert status.seconds == 34320
    assert status.end == datetime(2026, 10, 17, 6, 17, tzinfo=timezone.utc)
    assert status.last_sync == datetime(2026, 10, 17, 13, 17, 45, 558000, tzinfo=timezone.utc)
    assert fake.calls == [("sleep", "2026-10-17"), ("stats", "2026-10-17")]


def test_fetch_sleep_status_sense_hores_retorna_none_ni_valors(monkeypatch):
    monkeypatch.setattr(garmin_mod, "PAUSE_SEC", 0)
    fake = _FakeClient()
    fake.get_sleep_data = lambda d: {"dailySleepDTO": {"sleepTimeSeconds": 30120}}
    fake.get_stats = lambda d: {}
    status = GarminProvider(client=fake).fetch_sleep_status(date(2026, 9, 7))
    assert status.end is None and status.last_sync is None


def test_fetch_sleep_status_sense_nit_retorna_none_sense_demanar_stats(monkeypatch):
    monkeypatch.setattr(garmin_mod, "PAUSE_SEC", 0)
    fake = _FakeClient()  # dailySleepDTO buit: Garmin encara no té la nit
    assert GarminProvider(client=fake).fetch_sleep_status(date(2026, 9, 7)) is None
    assert fake.calls == [("sleep", "2026-09-07")]


def test_fetch_sleep_status_son_zero_compta_com_absent(monkeypatch):
    # Garmin retorna sleepTimeSeconds=0 mentre no ha rebut la nit
    monkeypatch.setattr(garmin_mod, "PAUSE_SEC", 0)
    fake = _FakeClient()
    fake.get_sleep_data = lambda d: {"dailySleepDTO": {"sleepTimeSeconds": 0}}
    assert GarminProvider(client=fake).fetch_sleep_status(date(2026, 9, 7)) is None
