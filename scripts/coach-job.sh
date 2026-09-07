#!/bin/bash
# Feina programada de l'entrenador. Ús: coach-job.sh morning|evening|weekly
# Corre igual a launchd (Mac), cron (servidor) o GitHub Actions: tot ve del
# .env / entorn, i "avui" és sempre el dia de l'atleta (TZ), no el de la màquina.
# Si el sync falla, el coach NO s'executa: mai opinions sobre dades velles (spec §9).
# morning: s'executa cada 20 min; només genera quan coach.gate diu que el son
# d'avui ja hi és i encara no hi ha informe del matí (COACH_FORCE=1 el salta).
set -euo pipefail
export TZ="${ATHLETE_TZ:-Europe/Madrid}"
cd "$(dirname "$0")/.."
mkdir -p logs
{
  echo "=== $(date '+%F %T') mode=$1 ==="
  make sync
  case "$1" in
    morning)
      if .venv/bin/python -m coach.gate morning; then
        .venv/bin/python -m coach.run daily --dry-run
      fi ;;
    evening) .venv/bin/python -m coach.run daily --dry-run --tomorrow ;;
    weekly)  .venv/bin/python -m coach.run weekly --dry-run ;;
    *) echo "mode desconegut: $1"; exit 1 ;;
  esac
  echo "=== fi $(date '+%F %T') ==="
} >> "logs/coach-$1.log" 2>&1
