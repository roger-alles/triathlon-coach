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
| Logs de les feines | `/home/entrenador/entrenador-triatlo/logs/coach-{morning,sync,evening,weekly,decisions}.log` |
| Log del desplegament diari | `.../logs/deploy.log` |
| Programació | `crontab -l -u entrenador` |

## Programació (hora local Europe/Madrid, fixada al sistema)

| Feina | Cron | Què fa |
|---|---|---|
| Matí | `*/5 6-11 * * *` | `coach-job.sh morning`: primer `coach.gate` (¿ja hi ha informe? → BD; ¿Garmin té el son d'avui? → 1 petició; ¿l'última sincronització és de les 06:00 ençà? → 1 petició més; a partir de les 10:00 genera igualment); només si GENERA: sync complet + informe. Un cop al dia; després, zero peticions |
| Sync horari | `1 6-22 * * *` | `coach-job.sh sync`: sync complet perquè els entrenos surtin a l'app en menys d'una hora. Després, `coach.recheck`: fins a les 12:00, si el son o la body battery d'avui han canviat respecte del que va fer servir l'informe del matí (≥ 1 h / ≥ 15), el refà un cop amb una nota (zero peticions a Garmin) |
| Vespre | `30 21 * * *` | `coach-job.sh evening`: sync + preview de demà |
| Setmanal | `30 20 * * 0` | `coach-job.sh weekly`: sync + revisió setmanal |
| Decisions i peticions | `3-58/5 6-23 * * *` | `coach-job.sh decisions`: aplica / descarta / desfà les propostes segons el que l'atleta ha tocat a l'app (`coach_decision`), i processa les peticions (`athlete_request`: ara `regenerate_macro`, màxim un macro al dia, ~1 € amb Opus). Inert mentre `coach_apply_mode` sigui `dry_run` |
| Còpia BD | `50 4 * * *` | `backup-db.sh`: pg_dump comprimit, 14 dies |
| Desplegament (crontab de root) | `50 5 * * *` | `scripts/deploy.sh` com a `entrenador`: `git pull --ff-only` de `main` + `pip install`; si hi ha canvis a `app/`, `npm ci` + `scripts/publish-app.sh` (tests de l'app i EAS Update). Log: `logs/deploy.log` |

Cost amb Garmin un dia típic: ~25 intents buits × 1-2 peticions + 1 sync del matí
+ 17 syncs horaris × ~17 ≈ 330 peticions, repartides tot el dia.

Totes les feines comparteixen un lock (`logs/coach.lock`, `flock`): `morning` i
`sync` desisteixen si està ocupat, `evening`/`weekly` esperen fins a 10 min,
`decisions` fins a 15 (perquè passin DESPRÉS del setmanal). Els minuts van
esglaonats (matí :00/:05…, sync :01, decisions :03/:08…) perquè cap feina que
desisteix no coincideixi mai amb una altra: cron les arrenca al mateix segon i
la que perd el `flock` salta el tick (l'11/09 `morning` va perdre 24 de 63
intents contra `decisions` i l'informe va sortir 25 min tard). El mode d'aplicació
del coach (`dry_run` / `hybrid`) és a la BD, `app_setting.coach_apply_mode`, no
al script: l'app el canvia. Fins al 28/09: `dry_run`.

Tot el que es fusiona a `main` a GitHub és al servidor l'endemà a les 05:50.
El desplegament NO aplica migracions: quan un PR en porta una, executar
`make migrate` (des del Mac o del servidor, mateixa BD) ABANS que el codi nou
arrenqui, i afegir a mà al crontab les línies noves de la taula de dalt.
Per desplegar a l'acte: `ssh entrenador 'sudo -u entrenador -H bash ~/entrenador-triatlo/scripts/deploy.sh'`.

## Còpia de seguretat de la base de dades

`scripts/backup-db.sh` (cron de `entrenador`, 04:50): `pg_dump` de l'esquema
`public` comprimit a `/home/entrenador/backups/db-AAAAMMDD.sql.gz`, 14 dies de
retenció (~1,5 MB cadascun). Log: `logs/backup.log`. Fins que el PR arribi a
`main`, el cron té com a alternativa una còpia del script a `~/bin/`.

Restaurar en un projecte Supabase buit (mai sobre el que té dades):

```bash
gunzip -c ~/backups/db-2026-09-10.sql.gz | psql "$DATABASE_URL_NOU"
```

Comprovació ràpida: `gunzip -c fitxer | grep -c "^COPY "` ha de donar 16 (taules,
des de la migració 0010).

### Fora de la VM (des del 13/09)

Les còpies del servidor viuen al mateix disc que la BD que protegeixen. Dues
capes més:

- **Mac d'en Roger**: `scripts/backup-pull.sh` baixa per rsync tots els
  `db-*.sql.gz` a `~/Backups/entrenador-triatlo/` i no n'esborra mai cap.
  launchd `cat.entrenador.backup-pull` a les 08:15 (si el Mac dormia, en
  despertar). Instal·lar: copiar el plist de `scripts/launchd/` a
  `~/Library/LaunchAgents/` i `launchctl bootstrap gui/$UID <plist>`.
  Log: `logs/launchd-backup-pull.log`. Comprovar: `ls ~/Backups/entrenador-triatlo`
  ha de tenir el `db-` d'avui. Després de restaurar o migrar el Mac cal tornar-lo
  a instal·lar (19/10: s'havia perdut amb una restauració, i el plist encara
  apuntava a la carpeta antiga del projecte).
- **Snapshot de Clouding**: snapshot de la VM sencera (inclou `~/backups`, el
  `.env` i els tokens de Garmin) des del panell de Clouding, setmanal, fet a
  mà per en Roger (diumenge, després del setmanal). Restaurar un snapshot
  torna la màquina sencera a aquell dia; les còpies de la BD del Mac cobreixen
  els dies entremig.

Restauració real en una BD buida: pendent de fer (no hi ha Postgres local);
vegeu `docs/security-review-2026-09.md`.

## Models del coach

`.env`: `COACH_MODEL` (diari i setmanal; per defecte `claude-sonnet-5`),
`COACH_MODEL_MACRO` (macro; per defecte `claude-opus-5`; al servidor ara
`claude-sonnet-5` mentre es fan proves) i `MACRO_DAILY_LIMIT` (macros per
dia; per defecte 1; al servidor 10 durant les proves). `REPLAN_DAILY_LIMIT`:
redissenys de setmana demanats des de l'app per dia (per defecte 3). Costos
reals: diari ~0,11 €, setmanal ~0,18 € (un redisseny, semblant), macro
~0,26 € amb Opus / ~0,10 € amb Sonnet.

Des del 01/10 el coach passa per OpenRouter (API compatible amb Anthropic):
`ANTHROPIC_BASE_URL=https://openrouter.ai/api`, `ANTHROPIC_AUTH_TOKEN` (clau
`sk-or-…`), models amb prefix (`anthropic/claude-sonnet-5`). La clau directa
d'Anthropic queda comentada; còpia del `.env` anterior a `.env.bak-anthropic-*`.
Els tokens d'entrada que registra `coach_report` no són fiables per aquesta via:
el cost real és al panell d'OpenRouter.

`COACH_EFFORT` (per defecte `high`; `low | medium | high | xhigh | max`):
esforç del raonament adaptatiu. **No baixar-lo a `medium`**: sonda del 14/09
amb sortida estructurada, `medium` dona text corromput i omet `new_session`.
Sostres de sortida (`llm.MAX_TOKENS`): diari 16k, setmanal i macro 32k; el
14/09 un setmanal es va quedar en bucle escrivint `\n` dins d'un string
fins als 64k (0,64 € l'intent): el sostre acota el cost d'un bucle, i el
cicle reintenta.

## Seguretat del servidor (hardening 13/09/2026)

| Capa | Estat | Verificar |
|---|---|---|
| SSH | només claus: `PermitRootLogin prohibit-password`, `PasswordAuthentication no`, `MaxAuthTries 3` (`/etc/ssh/sshd_config.d/10-hardening.conf`) | `sshd -T \| grep -E "permitrootlogin\|passwordauth"`; des del Mac `ssh -o PubkeyAuthentication=no entrenador` ha de dir `Permission denied (publickey)` |
| fail2ban | jail `sshd`, 3 intents en 10 min → 1 h de ban (`/etc/fail2ban/jail.local`, backend systemd) | `fail2ban-client status sshd` |
| ufw | entrada denegada per defecte; només 22/tcp | `ufw status verbose` |
| Tallafocs de Clouding | `alberfirewall`, només per a aquest servidor: 22/tcp i ICMP (ping). **No** `default`: és compartit amb (d'altres persones del compte) i obre molts més ports; tocar-lo els afecta | Panell → `alberginia` → Xarxa → Firewalls Vinculats; des del Mac, `nc -z -G 4 <IP del servidor> 8081` ha de fallar |
| Actualitzacions | `unattended-upgrades` diari (`/etc/apt/apt.conf.d/20auto-upgrades`) | `systemctl status unattended-upgrades`; `ls /var/run/reboot-required` |
| Secrets | `.env` i `app/.env` 600 de `entrenador`; tokens Garmin a `~/.garminconnect` 700 | `ls -la ~entrenador/entrenador-triatlo/.env` |

Abans del hardening: 13.105 intents de login fallits en 24 h (3 IPs), root amb
contrasenya obert. El pas a "només claus" es va fer amb una sessió oberta i
verificant una sessió nova abans de tancar-la: **fer-ho sempre així**. Si un
dia el Mac perd la clau, l'accés és per la consola del panell de Clouding.

Desbloquejar una IP bandejada per error: `fail2ban-client set sshd unbanip <ip>`.

Riscos acceptats i data de revisió: `docs/security-review-2026-09.md`.

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

## App mòbil: TestFlight + EAS Update (des del 2026-10-17)

L'app s'instal·la amb TestFlight (compilació d'EAS, perfil `production`). El
codi JavaScript li arriba amb EAS Update pel canal `production`: l'app el baixa
en obrir-se i l'aplica la vegada següent.

- **Publicar**: `scripts/publish-app.sh` passa els tests i el typecheck de
  l'app i fa `eas update --channel production --environment production`, amb
  `eas-cli` a una versió fixa. Ho fa sol `deploy.sh` quan el desplegament porta
  canvis a `app/`; a mà:
  `ssh entrenador 'sudo -u entrenador -H bash ~/entrenador-triatlo/scripts/publish-app.sh'`.
- **Sessió d'Expo**: la del compte `rogeralles`, a `/home/entrenador/.expo/state.json`
  (copiada del Mac el 07/09). Si caduca: `npx eas-cli login` com a `entrenador`,
  o un `EXPO_TOKEN` a l'entorn.
- **Variables de l'app** (`EXPO_PUBLIC_SUPABASE_*`): les de l'entorn
  "production" d'EAS (`eas env:list --environment production`). `app/.env` del
  servidor ja no fa falta per publicar.
- **Codi natiu**: amb `runtimeVersion` per fingerprint, una actualització només
  arriba a les compilacions amb el mateix codi natiu. Si un PR afegeix un mòdul
  natiu (p. ex. notificacions), cal `eas build` + `eas submit` des del Mac.
- **Les compilacions de TestFlight caduquen als 90 dies**: encara que no
  canviï res, cal pujar-ne una de nova abans. EAS Update no allarga el termini.
- **Tornar enrere**: `eas update:republish --group <id anterior>` (l'id surt a
  `eas update:list --branch production`).

Fins al 17/10 l'app s'obria amb Expo Go contra un servidor d'Expo (`expo-dev`,
port 8081 obert a Internet: risc A de la revisió de seguretat). Amb TestFlight
ja no feia falta: servei aturat i desactivat, port tancat a ufw i a Clouding
(el servidor passa del tallafocs compartit `default` al seu, `alberfirewall`).

## Què NO hi ha al servidor

- El servidor MCP del workspace: corre al Mac.
- Cap dada de salut en fitxers: tot va a Supabase; `data/` no es fa servir aquí.
