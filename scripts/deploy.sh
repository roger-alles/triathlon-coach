#!/bin/bash
# Desplegament diari (crontab de root, 05:50, com a usuari entrenador):
#   50 5 * * * sudo -u entrenador -H bash /home/entrenador/entrenador-triatlo/scripts/deploy.sh >> /home/entrenador/entrenador-triatlo/logs/deploy.log 2>&1
# Baixa main, instal·la les dependències de Python i, si hi ha canvis a app/,
# instal·la les de l'app i la publica (publish-app.sh). NO aplica migracions.
#
# Tot va dins de main(): git pull pot reescriure aquest mateix fitxer, i bash
# llegeix els scripts a mesura que els executa.
set -euo pipefail

main() {
  cd "$(dirname "$0")/.."
  echo "=== $(date '+%F %T') deploy ==="
  local before after
  before=$(git rev-parse HEAD)
  git pull -q --ff-only
  after=$(git rev-parse HEAD)
  .venv/bin/pip install -q -r requirements.txt
  if git diff --quiet "$before" "$after" -- app/; then
    echo "app sense canvis (${before:0:7}..${after:0:7}): no es publica"
  else
    (cd app && npm ci --no-audit --no-fund --silent)
    bash scripts/publish-app.sh
  fi
  echo "=== fi $(date '+%F %T') ==="
}

main "$@"
exit
