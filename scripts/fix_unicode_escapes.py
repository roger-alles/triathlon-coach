"""Repara els accents desats com a escapes literals (\\u00f3 en lloc de ó).

Del 04/10/2026 (macros 73-74, setmanal 75, per OpenRouter amb streaming) el
model va escriure accents com a escapes dins del JSON i van arribar així a la
BD: informes, sessions del pla i blocs. coach/llm.py ja ho decodifica per a
les respostes noves; això arregla el que ja hi era. Només canvia text: cap
data, hora, estat ni vincle del pla.

    .venv/bin/python scripts/fix_unicode_escapes.py           # què canviaria
    .venv/bin/python scripts/fix_unicode_escapes.py --apply   # ho canvia (una transacció)
"""

import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from coach.llm import unescape_unicode  # noqa: E402

# taula -> (columnes de text, columnes jsonb)
TARGETS = {
    "coach_report": (("summary_md",), ("output",)),
    "plan_session": (("title", "rationale"), ("structure",)),
    "plan_block": (("name", "intent", "fallback"), ()),
}


def fixes(row: dict, text_cols, json_cols) -> dict:
    """Columnes que canvien i el seu valor nou (buit: la fila ja està bé)."""
    out = {}
    for col in (*text_cols, *json_cols):
        value = row.get(col)
        fixed = unescape_unicode(value)
        if fixed != value:
            out[col] = Jsonb(fixed) if col in json_cols else fixed
    return out


def main() -> None:
    apply = "--apply" in sys.argv
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env.")
    total = 0
    with psycopg.connect(url) as conn, conn.transaction():
        for table, (text_cols, json_cols) in TARGETS.items():
            cols = ("id", *text_cols, *json_cols)
            rows = [dict(zip(cols, r)) for r in
                    conn.execute(f"select {', '.join(cols)} from {table}").fetchall()]
            changed = [(r["id"], fixes(r, text_cols, json_cols)) for r in rows]
            changed = [(rid, f) for rid, f in changed if f]
            total += len(changed)
            print(f"{table}: {len(changed)} files a reparar"
                  + (f" ({', '.join(str(rid) for rid, _ in changed)})" if changed else ""))
            if changed:
                rid, f = changed[0]
                col = next(iter(f))
                sample = f[col].obj if isinstance(f[col], Jsonb) else f[col]
                print(f"  ex. {table} {rid}.{col}: {json.dumps(sample, ensure_ascii=False)[:120]}")
            if apply:
                for rid, f in changed:
                    sets = ", ".join(f"{c} = %s" for c in f)
                    conn.execute(f"update {table} set {sets} where id = %s", (*f.values(), rid))
        if not apply:
            print(f"\n{total} files. Res canviat (afegeix --apply per reparar-les).")
            raise SystemExit(0)
    print(f"\n{total} files reparades.")


if __name__ == "__main__":
    main()
