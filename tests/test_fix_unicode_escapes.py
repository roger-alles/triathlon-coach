"""Reparació dels accents desats com a escapes (04/10/2026)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("fix_unicode_escapes",
                                              ROOT / "scripts" / "fix_unicode_escapes.py")
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)


def test_only_the_broken_columns_change_and_json_keeps_its_shape():
    row = {"id": 84, "title": "Descans", "rationale": "recuperaci\\u00f3 abans del bloc",
           "structure": {"steps": [{"note": "suau \\u00b7 RPE 3"}]}}
    out = fix.fixes(row, ("title", "rationale"), ("structure",))
    assert set(out) == {"rationale", "structure"}
    assert out["rationale"] == "recuperació abans del bloc"
    assert out["structure"].obj == {"steps": [{"note": "suau · RPE 3"}]}


def test_a_healthy_row_is_left_alone():
    row = {"id": 1, "name": "Base 1 · Munic", "intent": "volum suau", "fallback": None}
    assert fix.fixes(row, ("name", "intent", "fallback"), ()) == {}
