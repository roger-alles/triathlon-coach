#!/bin/bash
# Mostra l'últim informe del coach. Ús: make report
cd "$(dirname "$0")/.."
.venv/bin/python - <<'PY'
import os, psycopg
from dotenv import load_dotenv
load_dotenv(".env")
with psycopg.connect(os.getenv("DATABASE_URL")) as conn:
    row = conn.execute("""select created_at::timestamp(0), report_type, model,
                          summary_md from coach_report
                          order by created_at desc limit 1""").fetchone()
if row is None:
    print("Encara no hi ha cap informe del coach.")
else:
    print(f"── informe {row[1]} · {row[0]} · {row[2]} ──\n")
    print(row[3])
PY
