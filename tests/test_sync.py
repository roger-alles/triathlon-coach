"""Tests de la lògica pura de sync (finestra incremental)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.sync import compute_start_date


def test_incremental_goes_back_margin_days_from_last_known():
    # Garmin de vegades reprocessa: 3 dies de marge (spec §9)
    start = compute_start_date(last_known=date(2026, 8, 25), since_arg=None)
    assert start == date(2026, 8, 22)


def test_explicit_since_wins_over_incremental():
    start = compute_start_date(last_known=date(2026, 8, 25),
                               since_arg=date(2026, 5, 29))
    assert start == date(2026, 5, 29)


def test_empty_database_requires_since():
    try:
        compute_start_date(last_known=None, since_arg=None)
        assert False, "hauria d'haver petat"
    except SystemExit:
        pass
