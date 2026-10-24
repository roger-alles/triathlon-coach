#!/bin/bash
# Comprovacions de seguretat repetibles contra Supabase des de fora (sense
# privilegis d'admin), amb la clau publicable (la mateixa que va dins de l'app).
# Ús: SERVER_IP=<ip> scripts/security-check.sh   (llegeix app/.env)
# No escriu res. Codi de sortida != 0 si algun check falla.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . app/.env; set +a
URL="${EXPO_PUBLIC_SUPABASE_URL:?}"; KEY="${EXPO_PUBLIC_SUPABASE_KEY:?}"
fail=0
ok(){ echo "  OK  $1"; }
ko(){ echo "  KO  $1"; fail=1; }

echo "== anon no pot llegir dades de salut =="
code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' \
  "$URL/rest/v1/activity?select=id&limit=1" -H "apikey: $KEY" -H "Authorization: Bearer $KEY")
[ "$code" = "401" ] || [ "$code" = "403" ] && ok "GET activity → $code" || ko "GET activity → $code (esperat 401/403)"

echo "== registre de nous usuaris tancat =="
resp=$(curl -s -m 10 "$URL/auth/v1/signup" -H "apikey: $KEY" -H "Content-Type: application/json" \
  -d "{\"email\":\"seccheck-$(date +%s)@example.com\",\"password\":\"$(openssl rand -hex 12)Aa1!\"}")
echo "$resp" | grep -q "signup_disabled" && ok "signup → signup_disabled" || ko "signup NO està tancat: $resp"

echo "== ports oberts (només 22) =="
host=$(echo "$URL" | sed -E 's#https?://##;s#/.*##')
if [ -z "${SERVER_IP:-}" ]; then
  echo "  --  SERVER_IP no definida, salto"
elif command -v nmap >/dev/null; then
  open=$(nmap -Pn -sT -T4 --top-ports 200 "$SERVER_IP" 2>/dev/null | grep -cE "^[0-9]+/tcp +open")
  [ "$open" = "1" ] && ok "ports oberts: $open" || ko "ports oberts: $open (esperat 1, el 22)"
else
  echo "  --  nmap no instal·lat, salto"
fi

echo; [ $fail -eq 0 ] && echo "TOT OK" || echo "HI HA FALLADES"
exit $fail
