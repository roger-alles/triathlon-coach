# Revisió de seguretat — setembre 2026

Autor: sessió de treball amb Claude (Roger al comandament). Data: 13/09/2026.
Àmbit: sistema "entrenador de triatló" sencer, tots actius propis d'en Roger:
servidor `alberginia` (Clouding, <IP del servidor>), base de dades Supabase, repo
privat de GitHub i app Expo. Autoritzat per l'amo dels sistemes.

## Resum

Es va endurir el servidor, es van treure les còpies de la base de dades fora de
la VM i es va fer un pentest de caixa negra i grisa des de fora. La troballa
important — registre obert de nous usuaris a Supabase — es va comprovar i **ja
estava tancada**: cap dada de salut era accessible amb la clau pública. No es va
trobar cap fuga de secrets al codi ni a l'historial. Queden tres riscos acceptats
conscientment, tots amb data de revisió posterior a la cursa (27/09).

## Metodologia

- Inventari del servidor per SSH (configuració, ports, serveis, actualitzacions).
- Escaneig extern de ports (`nmap -sT`, 200 ports més comuns).
- Enumeració dels endpoints de Metro (port 8081) amb `curl` i `nuclei`.
- Proves contra l'API de Supabase des de fora amb la clau publicable: lectura
  anònima, registre de nous usuaris, i (amb la sessió d'en Roger) intents
  d'escriptura no autoritzada.
- Secrets: `gitleaks` sobre tot l'historial (70 commits).
- Dependències: `pip-audit` (Python) i `npm audit` (app).
- Totes les proves repetibles amb `scripts/security-check.sh`.

## Troballes

| # | Gravetat | Troballa | Estat |
|---|---|---|---|
| 1 | Alta (potencial) | Registre de nous usuaris a Supabase Auth: si estigués obert, qualsevol amb la clau publicable (va dins de l'app) es podria registrar i llegir totes les dades de salut | **Ja tancat.** `POST /auth/v1/signup` → `signup_disabled`. Verificat |
| 2 | Mitjana | SSH acceptava root amb contrasenya; 13.105 intents de login fallits en 24 h | **Corregit.** Només claus, fail2ban, MaxAuthTries 3 |
| 3 | Mitjana | Sense tallafocs (ufw inactiu), sense actualitzacions automàtiques, 111 paquets pendents | **Corregit.** ufw (només 22 i 8081), unattended-upgrades, tot actualitzat |
| 4 | Baixa | 14 vulnerabilitats moderades a dependències de l'app, totes dins de les eines de desenvolupament d'Expo (`@expo/cli`, `xcode`, `query-string`), no al codi que corre a producció | Acceptada. El fix exigeix pujar de major version d'Expo; es farà amb la migració a TestFlight post-cursa |
| 5 | Informativa | Metro (8081) cau si rep una petició pesada (compilació del bundle) en aquest servidor d'1 vCPU. Un atacant ho pot fer servir per deixar l'app inaccessible | Acceptada fins al 27/09 (vegeu risc A) |

Sense troballes: `nmap` només veu 22 i 8081; `nuclei` sense resultats; `gitleaks`
sense secrets a l'historial; `pip-audit` net; `anon` no pot llegir cap taula.

## Escriptures no autoritzades (amb la sessió d'en Roger)

L'usuari autenticat pot llegir el que li toca i només pot escriure el que la RLS
li permet (RPE, sensacions, notes; i activitats manuals amb id < 0). Es va
confirmar que NO pot: inserir activitats de Garmin (id > 0), modificar durades o
distàncies, esborrar files, ni tocar el pla (`plan_session`). Migracions `0005`
i `0007`.

## Riscos acceptats (revisar després del 27/09)

- **A — Metro 8081 obert a Internet.** El paquet JavaScript i els endpoints de
  desenvolupament són accessibles per qualsevol. No hi ha secrets de servidor al
  paquet (només la clau publicable de Supabase, pública per disseny), i les dades
  segueixen protegides per RLS. Decisió: es queda fins a la cursa per no tocar
  l'app; després, Tailscale (xarxa privada) o TestFlight. Data de revisió: 28/09.
- **B — La BD s'usa amb el rol `postgres` (admin) des del servidor.** Còmode, però
  si el `.env` del servidor es comprometés, l'atacant tindria admin de la BD. Cap
  a un rol amb permisos mínims per a les feines del coach. Data de revisió: post-cursa.
- **C — Restauració de la còpia no provada de veritat.** Les còpies es fan i es
  baixen; encara no s'ha restaurat cap en una BD buida (no hi ha Postgres local).
  Fer-ho abans de dependre'n seriosament. Data de revisió: post-cursa.

## Com repetir les comprovacions

```bash
scripts/security-check.sh        # anon, signup, ports (necessita nmap)
ssh entrenador 'fail2ban-client status sshd; ufw status verbose'
ssh entrenador 'sshd -T | grep -E "permitrootlogin|passwordauth"'
gitleaks detect --source . --log-opts=--all
```
