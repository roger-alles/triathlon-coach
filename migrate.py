"""Runner de migracions: aplica els .sql de supabase/migrations/ en ordre.

Cada migració s'executa dins d'una transacció i es registra a schema_migrations;
les ja aplicades es salten. Tornar-lo a executar és sempre segur (idempotent).

Ús:
    .venv/bin/python migrate.py            # aplica les pendents
    .venv/bin/python migrate.py --status   # només mostra l'estat
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).parent
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"


def pending_migrations(files: list[Path], applied: set[str]) -> list[Path]:
    """Migracions per aplicar, en ordre de nom de fitxer."""
    return [f for f in sorted(files, key=lambda f: f.name) if f.name not in applied]


def get_applied(conn) -> set[str]:
    conn.execute("""
        create table if not exists schema_migrations (
          filename   text primary key,
          applied_at timestamptz not null default now()
        )
    """)
    rows = conn.execute("select filename from schema_migrations").fetchall()
    return {r[0] for r in rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true",
                        help="mostra l'estat sense aplicar res")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Falta DATABASE_URL al .env (connexió Postgres de Supabase).")

    files = list(MIGRATIONS_DIR.glob("*.sql"))
    with psycopg.connect(url) as conn:
        applied = get_applied(conn)
        pending = pending_migrations(files, applied)

        if args.status:
            for f in sorted(files, key=lambda f: f.name):
                estat = "aplicada" if f.name in applied else "PENDENT"
                print(f"  {estat:9} {f.name}")
            return

        if not pending:
            print("Res per aplicar: tot al dia.")
            return

        for f in pending:
            # Una transacció per migració: o entra sencera, o no entra.
            with conn.transaction():
                conn.execute(f.read_text())
                conn.execute("insert into schema_migrations (filename) values (%s)",
                             (f.name,))
            print(f"aplicada: {f.name}")


if __name__ == "__main__":
    main()
