#!/bin/bash
# Còpia de seguretat diària de la base de dades (Supabase) al servidor.
# Ús: backup-db.sh [dir]   (per defecte ~/backups). Cron: docs/server.md.
# pg_dump de l'esquema public (dades de salut i pla) comprimit; conserva 14 dies.
# Restaurar: gunzip -c db-AAAAMMDD.sql.gz | psql "$DATABASE_URL"   (BD buida!)
set -euo pipefail
# El repo (amb el .env) pot no ser el directori del script (còpia a ~/bin)
cd "${ENTRENADOR_REPO:-$HOME/entrenador-triatlo}"
set -a; . ./.env; set +a
: "${DATABASE_URL:?Falta DATABASE_URL al .env}"
dir="${1:-$HOME/backups}"
mkdir -p "$dir"
out="$dir/db-$(date +%F).sql.gz"
tmp="$out.part"
pg_dump --no-owner --no-privileges --schema=public "$DATABASE_URL" | gzip > "$tmp"
mv "$tmp" "$out"
find "$dir" -name 'db-*.sql.gz' -mtime +14 -delete
echo "$(date '+%F %T') còpia: $out ($(du -h "$out" | cut -f1)); $(ls "$dir"/db-*.sql.gz | wc -l) fitxers"
