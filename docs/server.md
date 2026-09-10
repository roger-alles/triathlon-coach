# Servidor `alberginia` — on corren les feines del coach

> Des del 2026-09-07 les tres feines programades (matí, vespre, setmanal) corren
> en un servidor Linux sempre encès, no al Mac. El Mac pot estar apagat.

## Accés

- Host: `<IP del servidor>` (Clouding), Ubuntu 26.04, 1 vCPU / 2 GB / 15 GB.
- Des del Mac d'en Roger: `ssh entrenador` (alias a `~/.ssh/config`, usuari `root`,
  clau `~/.ssh/id_ed25519`). Per a una màquina nova: afegir la seva clau pública
  a `/root/.ssh/authorized_keys` amb `ssh-copy-id`.
- Les feines corren com l'usuari `entrenador` (sense sudo). Per obrir un shell seu:
  `sudo -u entrenador -H bash`.

## On és cada cosa

| Què | On |
|---|---|
| Repo (clon de `main`, deploy key de només lectura) | `/home/entrenador/entrenador-triatlo` |
| Secrets (`.env`, mateix contingut que al Mac) | `/home/entrenador/entrenador-triatlo/.env` (600) |
| Tokens de Garmin | `/home/entrenador/.garminconnect/garmin_tokens.json` (600) |
| Entorn Python | `/home/entrenador/entrenador-triatlo/.venv` (Python 3.14) |
| Logs de les feines | `/home/entrenador/entrenador-triatlo/logs/coach-{morning,sync,evening,weekly}.log` |
| Log del desplegament diari | `.../logs/deploy.log` |
| Programació | `crontab -l -u entrenador` |

## Programació (hora local Europe/Madrid, fixada al sistema)

| Feina | Cron | Què fa |
|---|---|---|
| Matí | `*/5 6-11 * * *` | `coach-job.sh morning`: primer `coach.gate` (¿ja hi ha informe? → BD; ¿Garmin té el son d'avui? → 1 petició); només si GENERA: sync complet + informe. Un cop al dia; després, zero peticions |
| Sync horari | `0 6-22 * * *` | `coach-job.sh sync`: sync complet perquè els entrenos surtin a l'app en menys d'una hora |
| Vespre | `30 21 * * *` | `coach-job.sh evening`: sync + preview de demà |
| Setmanal | `30 20 * * 0` | `coach-job.sh weekly`: sync + revisió setmanal |
| Còpia BD | `50 4 * * *` | `backup-db.sh`: pg_dump comprimit, 14 dies |
| Desplegament (crontab de root) | `50 5 * * *` | `git pull --ff-only` de `main` + `pip install` + `npm install` a `app/` + reinici del servei `expo-dev` |

Cost amb Garmin un dia típic: ~25 intents buits × 1 petició + 1 sync del matí
+ 17 syncs horaris × ~17 ≈ 330 peticions, repartides tot el dia.

Tot el que es fusiona a `main` a GitHub és al servidor l'endemà a les 05:50.
Per desplegar a l'acte: `ssh entrenador 'sudo -u entrenador -H git -C ~/entrenador-triatlo pull --ff-only && systemctl restart expo-dev'`.

## Còpia de seguretat de la base de dades

`scripts/backup-db.sh` (cron de `entrenador`, 04:50): `pg_dump` de l'esquema
`public` comprimit a `/home/entrenador/backups/db-AAAAMMDD.sql.gz`, 14 dies de
retenció (~1,5 MB cadascun). Log: `logs/backup.log`. Fins que el PR arribi a
`main`, el cron té com a alternativa una còpia del script a `~/bin/`.

Restaurar en un projecte Supabase buit (mai sobre el que té dades):

```bash
gunzip -c ~/backups/db-2026-09-10.sql.gz | psql "$DATABASE_URL_NOU"
```

Comprovació ràpida: `gunzip -c fitxer | grep -c "^COPY "` ha de donar 13 (taules).

## Operacions habituals

```bash
ssh entrenador 'tail -30 /home/entrenador/entrenador-triatlo/logs/coach-morning.log'   # què ha passat avui
ssh entrenador 'sudo -u entrenador -H bash -c "cd ~/entrenador-triatlo && .venv/bin/python -m coach.gate morning"'  # què diu la porta ara
ssh entrenador 'sudo -u entrenador -H bash -c "cd ~/entrenador-triatlo && COACH_FORCE=1 bash scripts/coach-job.sh morning"'  # forçar l'informe (gasta API)
```

## Si Garmin deixa d'entrar (401/403 al sync)

Els tokens caduquen o Garmin els invalida. Regenerar-los des del Mac (`make sync`
allà fa login amb `GARMIN_EMAIL`/`GARMIN_PASSWORD` i desa tokens nous) i copiar-los:

```bash
scp ~/.garminconnect/garmin_tokens.json entrenador:/root/ && ssh entrenador 'install -o entrenador -g entrenador -m 600 /root/garmin_tokens.json /home/entrenador/.garminconnect/garmin_tokens.json && rm /root/garmin_tokens.json'
```

Un `429` al login vol dir IP bloquejada temporalment: esperar, no reintentar en bucle.

## App mòbil: Expo Go contra el servidor (des del 2026-09-07 nit)

L'app no s'instal·la: Expo Go la descarrega del servidor d'Expo (Metro), que
corre aquí com a servei `systemd`, permanent i amb reinici automàtic.

- Adreça per a Expo Go: **`exp://<IP del servidor>:8081`** (Enter URL manually, o
  surt sola a Home > Development servers). Cal el mateix compte d'Expo al mòbil
  i al servidor (`rogeralles`; sessió copiada a `/home/entrenador/.expo/state.json`).
- Servei: `/etc/systemd/system/expo-dev.service` (usuari `entrenador`,
  `npx expo start --port 8081 --host lan`, `REACT_NATIVE_PACKAGER_HOSTNAME=<IP del servidor>`).
  `systemctl status|restart expo-dev`. Log: `logs/expo-dev.log`.
- Tallafocs de Clouding: regla d'entrada TCP 8081 des de qualsevol origen
  (afegida per en Roger al panell). Sense ella, el port no respon des de fora.
- Primera compilació del paquet iOS: ~60 s (1 vCPU); després queda en memòria
  i l'app s'obre en segons. Si el servei es reinicia, la primera obertura torna
  a trigar un minut.
- Secrets de l'app: `app/.env` (`EXPO_PUBLIC_*`, clau anon de Supabase; van
  dins del paquet, com al Mac).
- L'avís `react-native-devtools: libatk-1.0.so.0` al log és innocu: és el
  depurador gràfic, que no té sentit en un servidor sense pantalla.

Per què això i no TestFlight: en Roger prefereix seguir amb Expo Go de moment
(canvis visibles a l'acte sense compilar). Limitacions: cada SDK nou d'Expo Go
trenca l'app fins que es puja; sense notificacions push.

**Risc conegut (revisió 10/09)**: el port 8081 és HTTP obert a tot Internet.
El login d'Expo Go 57 protegeix l'app dins d'Expo Go, NO el port: qualsevol
pot descarregar el paquet JavaScript (amb la URL i la clau *publicable* de
Supabase, que és pública per disseny; cap secret de servidor) i veure els
endpoints de Metro. Amb un sol usuari i la clau publicable és tolerable a curt
termini; no ho és com a estat permanent. Sortides, de menys a més feina:
(1) regla del tallafocs limitada a la IP d'en Roger (falla fora de casa);
(2) Tailscale al servidor i al mòbil, i Metro només a la xarxa privada;
(3) TestFlight (compte de desenvolupador ja disponible): l'app instal·lada,
sense Metro exposat, amb notificacions. La (3) és la recomanada després del 27/09.

## Què NO hi ha al servidor

- El servidor MCP del workspace: corre al Mac.
- Cap dada de salut en fitxers: tot va a Supabase; `data/` no es fa servir aquí.
