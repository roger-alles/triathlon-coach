"""Tests de la lògica pura del runner de migracions (sense base de dades)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from migrate import pending_migrations


def test_pending_keeps_order_and_skips_applied():
    files = [Path("0002_b.sql"), Path("0001_a.sql"), Path("0003_c.sql")]
    pending = pending_migrations(files, applied={"0001_a.sql"})
    assert [p.name for p in pending] == ["0002_b.sql", "0003_c.sql"]


def test_pending_empty_when_all_applied():
    files = [Path("0001_a.sql")]
    assert pending_migrations(files, applied={"0001_a.sql"}) == []


def test_pending_all_on_fresh_database():
    files = [Path("0002_b.sql"), Path("0001_a.sql")]
    pending = pending_migrations(files, applied=set())
    assert [p.name for p in pending] == ["0001_a.sql", "0002_b.sql"]
