#!/bin/bash
# Feina programada de l'entrenador. Ús: coach-job.sh morning|sync|evening|weekly
# Corre igual a launchd (Mac), cron (servidor) o GitHub Actions: tot ve del
# .env / entorn, i "avui" és sempre el dia de l'atleta (TZ), no el de la màquina.
# Si el sync falla, el coach NO s'executa: mai opinions sobre dades velles (spec §9).
#
# morning: cada 5 min. PRIMER la porta (coach.gate: ¿ja hi ha informe? ¿Garmin té
#          el son d'avui? — 0-1 peticions), i només si diu GENERA: sync complet +
#          coach. COACH_FORCE=1 salta la porta.
# sync:    cada hora, sync complet perquè els entrenos surtin a l'app durant el dia.
set -euo pipefail
export TZ="${ATHLETE_TZ:-Europe/Madrid}"
cd "$(dirname "$0")/.."
mkdir -p logs
{
  echo "=== $(date '+%F %T') mode=$1 ==="
  case "$1" in
    morning)
      if .venv/bin/python -m coach.gate morning; then
        make sync
        .venv/bin/python -m coach.run daily --dry-run
      fi ;;
    sync)    make sync ;;
    evening) make sync; .venv/bin/python -m coach.run daily --dry-run --tomorrow ;;
    weekly)  make sync; .venv/bin/python -m coach.run weekly --dry-run ;;
    *) echo "mode desconegut: $1"; exit 1 ;;
  esac
  echo "=== fi $(date '+%F %T') ==="
} >> "logs/coach-$1.log" 2>&1
