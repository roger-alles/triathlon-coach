#!/bin/bash
# Feina programada de l'entrenador (launchd). Ús: coach-job.sh morning|evening|weekly
# Si el sync falla, el coach NO s'executa: mai opinions sobre dades velles (spec §9).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
{
  echo "=== $(date '+%F %T') mode=$1 ==="
  make sync
  case "$1" in
    morning) .venv/bin/python -m coach.run daily --dry-run ;;
    evening) .venv/bin/python -m coach.run daily --dry-run --tomorrow ;;
    weekly)  .venv/bin/python -m coach.run weekly --dry-run ;;
    *) echo "mode desconegut: $1"; exit 1 ;;
  esac
  echo "=== fi $(date '+%F %T') ==="
} >> "logs/coach-$1.log" 2>&1
