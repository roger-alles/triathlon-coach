# Decisions del projecte

> Per què s'ha fet cada cosa així (spec §11). Una entrada per decisió, amb data.

## 2026-09-07 — Porta del matí barata: primer preguntar, després sincronitzar

La primera versió de la porta feia el sync complet (15-20 peticions a Garmin,
19 s) a cada intent i mirava la porta al final: sis syncs inútils cada matí
després de l'informe, i cada 20 min com a màxim raonable. Es reordena:
(1) ¿ja hi ha informe del matí avui? (BD, 0 peticions) → (2) ¿Garmin té el
son d'avui? (`fetch_sleep_seconds`, 1 petició) → (3) sync + coach. Un intent
buit costa 0-1 peticions i 2 s, així que el cron passa a cada 5 min de 06:00
a 11:55 sense pujar el cost: informe 5 min després que el rellotge
sincronitzi, ~45 peticions al dia per al matí en lloc de ~300.

Efecte secundari que es perdia: els syncs repetits del matí feien que un
entreno aparegués a l'app en 20 min. Es compensa amb un `coach-job.sh sync`
cada hora de 06:00 a 22:00: qualsevol entreno surt en menys d'una hora, a
qualsevol hora (abans, a la tarda no sortia fins a les 21:30).

## 2026-09-07 — Les feines del coach surten del Mac: servidor `alberginia`

L'objectiu d'en Roger és que l'app funcioni sense obrir l'ordinador. El Mac
dorm de nit i la feina del matí quedava a mitges fins que obria la tapa.
Les tres feines passen a un servidor Linux sempre encès (Clouding, Ubuntu
26.04) amb `cron`, usuari sense privilegis `entrenador`, clon de `main` amb
deploy key de només lectura, i desplegament automàtic diari (`git pull` a les
05:50). Els mateixos scripts, sense canvis: `coach-job.sh` ja era agnòstic.
Es descarta GitHub Actions perquè el servidor ja existia: estat persistent
(tokens de Garmin que es renoven sols), cron exacte, i cada 20 min surt gratis.
Els `launchd` del Mac queden desinstal·lats (els plists es conserven a
`scripts/launchd/` per referència). Runbook: `docs/server.md`.

Verificat des del servidor: 114 tests, `make sync` real contra Garmin (els
tokens copiats funcionen des d'una IP de centre de dades), `coach.gate`
respon, i una execució sencera de `coach-job.sh morning`.

## 2026-09-07 — Informe del matí disparat per dades (son present), no per hora

La feina de les 06:15 generava l'informe sense el son de la nit: Garmin només
el publica quan el rellotge sincronitza amb el mòbil, després que en Roger es
desperti (avui, 11:43). El coach acabava preguntant "quantes hores has
dormit?" i l'informe no deia res útil. A més, el Mac s'adormia a mitja feina
(sync a les 06:46, informe escrit a les 09:43 en obrir la tapa).

Canvi: la feina del matí s'intenta cada 20 min de 06:00 a 11:40 i passa per
`coach.gate`, que només deixa generar quan (a) `daily_metric` d'avui té
`sleep_duration_sec` i (b) encara no hi ha cap informe diari d'avui amb
`window_start` = avui creat avui (el preview del vespre anterior no compta).
`COACH_FORCE=1` salta la porta: és la palanca per a un futur botó a l'app.

"Avui" és el dia a la zona de l'atleta (`ATHLETE_TZ`, per defecte
Europe/Madrid) i `coach-job.sh` exporta `TZ`, de manera que el mateix script
corre igual a launchd, a un cron d'un servidor en UTC o a GitHub Actions. El
següent pas és treure la feina del Mac (que dorm): està decidit, pendent de
tenir accés al servidor d'en Roger.

## 2026-09-07 — App pujada a Expo SDK 57 (Expo Go de l'App Store ja no obre SDK 54)

El 02/09 Apple va aprovar Expo Go 57.0.9; cada versió d'Expo Go només porta un
SDK, i l'iPhone d'en Roger es va actualitzar sol: el projecte (SDK 54) va
desaparèixer d'Expo Go. No es pot tornar a Expo Go 54 a iOS, així que l'app
salta 54→57 d'un cop (`npx expo install expo@^57 --fix` + codemod
`sdk-56-expo-router-react-navigation-replace`). Conseqüències:

- `expo-router` ja no depèn de `@react-navigation/*`: s'importa de
  `expo-router/react-navigation` i `expo-router/js-tabs`; els paquets
  `@react-navigation/*` surten de `package.json`.
- `newArchEnabled` i `edgeToEdgeEnabled` desapareixen d'`app.json` (ara són
  obligatoris, l'opció ja no existeix).
- npm deixava `expo-modules-core` niat sota `expo/` i `jest-expo` no el
  trobava: es declara com a dependència directa.
- TypeScript 6 ja no carrega tots els `@types/*` sols: `tsconfig.json` declara
  `types: ["jest"]`.
- RN 0.86 afegeix `'unspecified'` a `ColorSchemeName`: `hooks/use-color-scheme`
  normalitza a `'light' | 'dark'` i la resta de l'app no ho ha de saber.
- Reanimated 4 i Worklets exigeixen runtime natiu: `jest-setup.js` carrega els
  mocks oficials (`react-native-worklets/src/mock`, `react-native-reanimated/mock`).
- La regla nova `react-hooks/set-state-in-effect` marca `load()` als effects
  d'Avui/Setmana/Forma com si fos setState síncron; no ho és (va després de
  l'`await`). Es desactiva línia a línia amb el motiu, no es reestructura.

Verificat: 61 tests jest, `tsc` net, `expo-doctor` 21/21, lint 0 errors,
bundle iOS generat per Metro amb `runtimeVersion exposdk:57.0.0`.

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
