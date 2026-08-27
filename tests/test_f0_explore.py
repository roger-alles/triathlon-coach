"""Tests de les funcions pures de f0_explore (les de xarxa no es testegen a F0)."""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from f0_explore import date_range, save_json


def test_date_range_includes_both_ends():
    days = date_range(date(2026, 8, 1), date(2026, 8, 3))
    assert days == [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]


def test_date_range_single_day():
    assert date_range(date(2026, 8, 1), date(2026, 8, 1)) == [date(2026, 8, 1)]


def test_save_json_creates_folder_and_readable_file(tmp_path):
    save_json(tmp_path, "sleep", "2026-08-27", {"score": 82, "text": "olé"})
    content = json.loads((tmp_path / "sleep" / "2026-08-27.json").read_text())
    assert content == {"score": 82, "text": "olé"}


def test_save_json_serializes_non_json_types(tmp_path):
    # Les respostes de Garmin poden dur dates; default=str no ha de petar.
    save_json(tmp_path, "meta", "x", {"when": date(2026, 8, 27)})
    content = json.loads((tmp_path / "meta" / "x.json").read_text())
    assert content == {"when": "2026-08-27"}
