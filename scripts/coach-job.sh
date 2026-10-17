#!/bin/bash
# Feina programada de l'entrenador. Ús: coach-job.sh morning|sync|evening|weekly|decisions
# Corre igual a launchd (Mac), cron (servidor) o GitHub Actions: tot ve del
# .env / entorn, i "avui" és sempre el dia de l'atleta (TZ), no el de la màquina.
# Si el sync falla, el coach NO s'executa: mai opinions sobre dades velles (spec §9).
#
# morning:   cada 5 min. PRIMER la porta (coach.gate: ¿ja hi ha informe? ¿Garmin té
#            el son d'avui, sincronitzat de les 06:00 ençà? — 0-2 peticions), i només
#            si diu GENERA: sync complet + coach. COACH_FORCE=1 salta la porta.
# sync:      cada hora, sync complet perquè els entrenos surtin a l'app durant el dia.
#            Després, coach.recheck: fins a les 12:00, si el son d'avui ha canviat
#            respecte del que va fer servir l'informe del matí, el refà (un cop).
# decisions: cada 5 min, processa Aplica/Descarta/Desfés de l'atleta (coach.decisions).
#
# Un sol lock per a totes les feines (logs/coach.lock): dues generacions alhora, o
# una decisió aplicant-se mentre el setmanal escriu, corromprien el pla. Les
# feines curtes (morning, sync) desisteixen si està ocupat: tornaran al següent
# tick. Les llargues i les decisions esperen (les decisions, prou perquè passin
# DESPRÉS del setmanal).
#
# El mode d'aplicació (dry_run / hybrid) NO és aquí: coach.run el llegeix de la
# BD (app_setting.coach_apply_mode), que l'app pot canviar.
set -euo pipefail
export TZ="${ATHLETE_TZ:-Europe/Madrid}"
cd "$(dirname "$0")/.."
mkdir -p logs
exec 9>logs/coach.lock
case "$1" in
  morning|sync) flock -n 9 || { echo "$(date '+%F %T') mode=$1: ocupat, salto" >> "logs/coach-$1.log"; exit 0; } ;;
  evening|weekly) flock -w 600 9 ;;
  decisions) flock -w 900 9 ;;
esac
{
  echo "=== $(date '+%F %T') mode=$1 ==="
  case "$1" in
    morning)
      if .venv/bin/python -m coach.gate morning; then
        make sync
        .venv/bin/python -m coach.run daily
      fi ;;
    sync)      make sync; .venv/bin/python -m coach.recheck ;;
    evening)   make sync; .venv/bin/python -m coach.run daily --tomorrow ;;
    weekly)    make sync; .venv/bin/python -m coach.run weekly ;;
    decisions) .venv/bin/python -m coach.decisions ;;
    *) echo "mode desconegut: $1"; exit 1 ;;
  esac
  echo "=== fi $(date '+%F %T') ==="
} >> "logs/coach-$1.log" 2>&1
