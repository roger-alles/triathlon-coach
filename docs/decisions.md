# Decisions del projecte

> Per què s'ha fet cada cosa així (spec §11). Una entrada per decisió, amb data.

## 2026-08-27 — F0 com a script solt a l'arrel

`f0_explore.py` viu a l'arrel del repositori, no dins d'`ingest/`. La F0 és exploratòria:
el seu codi es llença quan la F1 escrigui la ingesta de veritat darrere del protocol
`ActivityProvider`. Posar-lo a l'arrel deixa clar que és temporal.

## 2026-08-27 — Repositori propi, separat del workspace

`projects/` està gitignorat pel workspace de PM, així que aquest directori és un
repositori git independent. Identitat git: la global de la màquina (Roger).

## 2026-08-28 — Accés a Postgres amb psycopg i runner de migracions propi

El backend parla amb Supabase per la connexió Postgres directa (psycopg 3,
queries parametritzades), no per l'API REST amb supabase-py: es veu el SQL de
veritat, que és el que cal aprendre. Migracions amb un runner de 60 línies
(`migrate.py` + taula `schema_migrations`) en lloc del CLI de Supabase: cap
dependència de brew/Docker i el mecanisme queda transparent. Si algun dia cal
el CLI (branching, shadow DB), els fitxers de `supabase/migrations/` són
compatibles amb la seva convenció de carpeta.

## 2026-08-28 — Taules de pla ajornades a la F3

La migració 0001 només crea el costat de la ingesta (athlete, threshold_history,
activity, daily_metric, load_daily). goal, plan_block, plan_session, test_result,
logistics_task i coach_report arriben a la F3, que és quan algú els necessita.
`activity.plan_session_id` queda com a columna sense FK fins llavors (spec §3).

## 2026-08-27 — `data/` fora de git

Les respostes crues de Garmin són dades de salut personals (spec §13). Es queden
al disc local, mai al repositori.
