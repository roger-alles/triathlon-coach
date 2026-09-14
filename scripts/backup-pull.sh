#!/bin/bash
# Baixa al Mac les còpies diàries de la BD que fa el servidor (backup-db.sh).
# És la còpia FORA de la VM: si el servidor mor, això queda. Mai s'esborra res
# al destí (rsync sense esborrat): el servidor conserva 14 dies, el Mac tot.
# Ús: backup-pull.sh [destí]   (per defecte ~/Backups/entrenador-triatlo)
# launchd: scripts/launchd/cat.entrenador.backup-pull.plist (docs/server.md).
set -euo pipefail
host="${ENTRENADOR_SSH_HOST:-entrenador}"          # alias de ~/.ssh/config
remote="${ENTRENADOR_BACKUP_DIR:-/home/entrenador/backups}"
dest="${1:-$HOME/Backups/entrenador-triatlo}"
mkdir -p "$dest"
rsync -az --timeout=60 --include='db-*.sql.gz' --exclude='*' "$host:$remote/" "$dest/"
latest=$(ls -1 "$dest"/db-*.sql.gz | tail -n 1)
tables=$(gunzip -c "$latest" | grep -c '^COPY ' || true)
echo "$(date '+%F %T') còpia al Mac: $(ls "$dest"/db-*.sql.gz | wc -l | tr -d ' ') fitxers; última $(basename "$latest") ($tables taules)"
