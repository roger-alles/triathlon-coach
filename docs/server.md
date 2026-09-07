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
| Desplegament | `50 5 * * *` | `git pull --ff-only` de `main` + `pip install -r requirements.txt` |

Cost amb Garmin un dia típic: ~25 intents buits × 1 petició + 1 sync del matí
+ 17 syncs horaris × ~17 ≈ 330 peticions, repartides tot el dia.

Tot el que es fusiona a `main` a GitHub és al servidor l'endemà a les 05:50.
Per desplegar a l'acte: `ssh entrenador 'sudo -u entrenador -H git -C ~/entrenador-triatlo pull --ff-only'`.

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

## Què NO hi ha al servidor

- L'app mòbil: encara es serveix des del Mac amb Expo Go (pendent: TestFlight o PWA).
- El servidor MCP del workspace: corre al Mac.
- Cap dada de salut en fitxers: tot va a Supabase; `data/` no es fa servir aquí.
