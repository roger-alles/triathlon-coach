# Decisions del projecte

> Per què s'ha fet cada cosa així (spec §11). Una entrada per decisió, amb data.

## 2026-08-28 — Validador: interpretacions calibrades contra el pla de Fornells

La spec §8.1 mana que el pla real passi les 14 regles; aquestes són les
interpretacions preses on la spec era ambigua o inconsistent, totes amb el
criteri de §8.1 ("un validador massa estricte és pitjor que no tenir-ne"):

1. **R1/R6, exempció de represa**: l'exempció `return_from_layoff` cobreix
   també la setmana següent al bloc de represa (la base de comparació és
   artificialment baixa — el cas +53% de §8.1). Amb un bloc de represa al pla,
   l'historial pre-layoff tampoc s'usa com a base.
2. **R4, fases**: una setmana `build` dins dels 28 dies previs a una cursa A
   compta com a específica (llindar de `peak`, 60%): és l'argument literal de
   §8.1 sobre les "quatre setmanes específiques". El llindar de `taper` és 75%
   i no el 80% de la taula: R8 exigeix mantenir intensitat, i en un taper
   d'una setmana per cursa curta els tocs de ritme pesen ~20-25% del poc temps
   total. Els dos llindars conviuen documentats aquí.
3. **R4/R9, classificació fàcil/dur**: fàcil = RPE ≤ 6, hr_zone ≤ 2, `open`,
   o `slower_than`; qualsevol ritme concret és dur. Distància→temps amb el
   ritme real de l'atleta (natació 2:15/100) o el ritme del target.
4. **R6**: només vigila sessions amb `session_type: long` (la "sessió llarga"
   literal), no el màxim setmanal de qualsevol sessió.
5. **R7**: els mínims (2 natacions, 1 brick) apliquen a setmanes `build`/`peak`,
   no al taper (el taper de Fornells té 1 natació i cap brick, per disseny).
6. **R8**: la durada del taper compta el dia de cursa inclòs (21→27 set = 7
   dies ✓ per a curta); volum del taper entre 30% i 70% de la mitjana de les
   2 setmanes prèvies.
7. **R14, passat**: la validació del pla sencer usa `reference_date` = inici
   del pla (el pla es valida com el dia que es va escriure); en el bucle del
   coach (F4) la referència serà "avui" i la regla mossega de veritat.
8. **Setmana completa**: només s'exclou la primera setmana parcial (el pla
   comença dimecres); que el pla acabi en diumenge de cursa no fa parcial
   l'última.

## 2026-08-28 — Validador en Python pur, pydantic ajornat

`coach/structure.py` valida el contracte §6 a mà (150 línies, testejades);
`contracts/session-structure.schema.json` és l'equivalent declaratiu per a
l'app (zod, F5). Pydantic s'afegirà a la F4 si la sortida estructurada del
coach ho demana; de moment seria una dependència sense feina.

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
