#!/usr/bin/env bash
# Consulta la BD per l'API REST de Supabase (HTTPS) — per a entorns on el
# port 5432 està tallat (sessions cloud de Claude Code, per exemple).
# Ús: scripts/db-rest.sh 'load_daily?select=local_date,ctl,atl,tsb&order=local_date.desc&limit=3'
# Necessita: SUPABASE_URL i SUPABASE_SERVICE_KEY a l'entorn (o al .env).
set -euo pipefail

if [ -f "$(dirname "$0")/../.env" ]; then
  set -a; source "$(dirname "$0")/../.env"; set +a
fi

: "${SUPABASE_URL:?Falta SUPABASE_URL}"
: "${SUPABASE_SERVICE_KEY:?Falta SUPABASE_SERVICE_KEY}"

curl -sf "${SUPABASE_URL}/rest/v1/$1" \
  -H "apikey: ${SUPABASE_SERVICE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_KEY}"
echo
