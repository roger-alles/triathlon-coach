"""El proveïdor Garmin ha de complir el protocol ActivityProvider (spec §2)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.providers.base import ActivityProvider
from ingest.providers.garmin import GarminProvider


class _StubClient:
    def get_activities_by_date(self, start, end): return []
    def get_stats(self, d): return {}
    def get_sleep_data(self, d): return {}


def test_garmin_provider_satisfies_protocol():
    provider = GarminProvider(client=_StubClient())
    assert isinstance(provider, ActivityProvider)
