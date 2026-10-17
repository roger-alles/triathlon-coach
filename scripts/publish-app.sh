#!/bin/bash
# Publica l'app instal·lada (TestFlight) amb EAS Update, canal production, si
# els tests i el typecheck de l'app passen. Només JavaScript: si un canvi toca
# codi natiu, el fingerprint canvia, l'actualització surt amb un runtime nou
# que cap compilació instal·lada no té, i cal `eas build` + `eas submit`.
#
# La crida deploy.sh quan el desplegament diari porta canvis a app/. A mà:
#   ssh entrenador 'sudo -u entrenador -H bash ~/entrenador-triatlo/scripts/publish-app.sh'
#
# Sessió d'Expo: la del compte rogeralles a ~/.expo/state.json. Variables de
# l'app (EXPO_PUBLIC_*): les de l'entorn "production" d'EAS.
set -euo pipefail
cd "$(dirname "$0")/../app"
export CI=1 EXPO_NO_TELEMETRY=1 NODE_OPTIONS=--max-old-space-size=1024
EAS_CLI="eas-cli@24.8.0"  # versió fixa: una de nova no entra sense revisar-la

echo "$(date '+%F %T') tests de l'app"
# 1 vCPU: en fred (sense la memòria cau de Jest) alguns tests passen dels 5 s
npx jest --silent --runInBand --testTimeout=30000
npx tsc --noEmit

message=$(git log -1 --format='%h %s')
echo "$(date '+%F %T') publicant: $message"
npx -y "$EAS_CLI" update --channel production --environment production \
  --message "$message" --non-interactive
echo "$(date '+%F %T') publicat"
