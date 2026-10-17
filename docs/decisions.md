# Decisions del projecte

> Per què s'ha fet cada cosa així (spec §11). Una entrada per decisió, amb data.

## 2026-10-17 — L'app es publica des del servidor; fora Expo Go i el port 8081

Amb l'app de TestFlight, un PR fusionat no arribava al mòbil fins que algú
feia `eas update` a mà des del Mac. Ara el desplegament diari (`deploy.sh`)
publica l'app (`publish-app.sh`) quan porta canvis a `app/`, després de passar
els tests i el typecheck. Es va triar el servidor i no una GitHub Action per no
afegir una dependència: el servidor ja baixa `main` cada matí i ja té la sessió
d'Expo. Contrapartida: un canvi de l'app arriba l'endemà a les 05:50, o a l'acte
llançant `publish-app.sh` a mà. `eas-cli` va fixat (24.8.0).

De pas, s'atura `expo-dev` i es tanca el 8081 (ufw i Clouding): era el risc A
de la revisió de seguretat de setembre, acceptat fins que hi hagués TestFlight.

## 2026-10-17 — App de TestFlight: sessió i dades en tornar de segon pla

Amb l'app instal·lada (TestFlight), iOS ja no la tanca: queda congelada en
segon pla. En Roger l'havia de tancar del tot gairebé cada matí perquè Avui
ensenyava un error de JWT ("JWT issued at future") al lloc de l'informe.
Amb Expo Go no es notava perquè l'app es tancava sovint.

Tres canvis, tots JavaScript (arriben amb EAS Update, sense compilació nova):

- `AppState` → `supabase.auth.startAutoRefresh()` / `stopAutoRefresh()`, la
  recepta de Supabase per a React Native: el temporitzador de renovació
  s'atura amb l'app congelada.
- `fetch` propi al client: un 401 de JWT (PGRST301/PGRST303) es repeteix un
  cop al cap de 2 s; els altres 401 surten a l'acte. En tornar,
  supabase-js renova el token just abans de la petició i l'API de dades el
  rebutja uns segons perquè el seu rellotge va per darrere del del servidor
  d'autenticació. Un 401 vol dir que la petició no s'ha executat: repetir-la
  és segur, també per a les escriptures.
- Avui torna a carregar en passar a primer pla (`useOnForeground`): sense
  això, al matí ensenyava l'informe d'ahir fins que estiraves per refrescar.

## 2026-10-17 — Informe del matí: sincronització de matí, i correcció si el son canvia

Dos informes del matí (13 i 17/10) es van generar a les 06:00 amb 4,1 i 4,2 h
de son quan la nit real va ser de 7,3 i 9,5 h; el del 17 també veia una body
battery màxima de 58 (real: 90). El mòbil havia sincronitzat a mitja nit i
Garmin publica el son fins aquell moment: `sleepTimeSeconds` ja no és zero i
la porta deixava passar. El coach va posar el semàfor en ambre i va preguntar
per una nit dolenta que no existia.

Dues peces:

- **Porta** (`coach.gate`): a més del son, demana
  `get_stats.lastSyncTimestampGMT` i només genera si l'última sincronització
  és de les 06:00 (hora local) o més tard; una d'abans és de nit. A partir de
  les 10:00 genera igualment, amb el motiu al log. Idea d'en Roger.
- **Correcció** (`coach.recheck`, després de cada sync horari fins a les
  12:00): compara el son i la body battery de l'`input_snapshot` de l'informe
  amb la BD; si han canviat ≥ 1 h o ≥ 15, refà l'informe un sol cop al dia i hi
  posa una nota. Cobreix el cas que la porta no veu: una sincronització
  després de les 6 amb en Roger encara dormint (dissabte que es lleva a les 9).
  Zero peticions a Garmin; en mode híbrid, el segon informe pot aplicar canvis
  petits sobre el pla que ja ha tocat el primer (es poden desfer igual).

Descartats: (a) exigir 10 min entre la fi del son i la sincronització — retarda
l'informe justament quan el mòbil sincronitza en despertar-se, el cas normal;
(b) `sleepWindowConfirmationType == "enhanced_confirmed_final"` — dies amb el
son ja sencer es queden en `enhanced_confirmed` (30/09, 14/10, 17/10 a la
tarda). Pendent de comprovar: si `bodyBatteryAtWakeTime` només apareix en
despertar-se, seria un senyal millor que l'hora (cal veure una sincronització
de nit).

## 2026-10-09 — Body battery del matí: de la nit, no del resum diari

Tres informes del matí (06, 08 i 09/10) van veure una body battery de 64, 8 i
25 quan en despertar era 87, 53 i 99, i van posar el semàfor en ambre per
això. La porta del matí genera quan Garmin té el son d'avui, però
`body_battery_max` sortia del resum diari (`get_stats.bodyBatteryHighestValue`),
que Garmin actualitza més tard: aquells matins només hi havia el valor de
mitjanit. Ara és el màxim entre el resum, `bodyBatteryAtWakeTime` i la sèrie de
la nit (`sleep.sleepBodyBattery`), que arriba amb el son. Sense migració: la
columna és la mateixa; el mínim es manté (és real).

## 2026-10-04 — L'atleta corregeix activitats: assignar a una sessió i esborrar manuals

El cap de setmana del 3-4/10 en Roger va intercanviar dies (bici dissabte,
cursa diumenge) i, a més, va registrar amb "Ho he fet" una cursa que no havia
fet. Resultat: dues sessions sense la seva activitat, dues activitats de
Garmin "fora de pla" i una entrada manual falsa sumant càrrega. L'app no
deixava arreglar-ho: el vinculador només respectava vincles explícits de files
manuals, i les de Garmin s'aparellaven per dia i esport. Ara, al detall de
qualsevol activitat: "Sessió del pla" (sessions del mateix esport, o brick/
multisport per a un tram, a ±3 dies, o "Fora de pla") i, per a les manuals,
"Esborra". Nova columna `activity.linked_by_athlete` (migració 0014) en lloc
d'un camp de `raw`, perquè el sync de Garmin reescriu `raw` sencer; el
vinculador la tracta com a vincle explícit (també amb `plan_session_id` null:
fora de pla per decisió seva) i una sessió d'avui que perd la seva activitat
torna a `planned`. Esborrar només és possible per a `id < 0` (política RLS),
igual que inserir.

## 2026-10-01 — La setmana no és una proposta: s'aplica i es redissenya a petició

Amb la setmana rodant (S4b) el setmanal arribava a Avui com a proposta amb
Aplica / Descarta, i un cop aplicada hi seguia 7 dies per tenir Desfés a mà.
Però el setmanal escriu la setmana sencera (la del 28/09: 7 `add`, cap pla
previ): descartar-la o desfer-la deixa l'atleta sense pla fins al diumenge
següent, i el Desfés es nega igualment així que s'ha fet una sessió. Decidit
amb en Roger: (1) en mode `hybrid`, el setmanal s'aplica sempre
(`auto_applied`, la classificació es desa igualment); (2) a la pestanya
Setmana, "Demana canvis": l'atleta escriu què vol i el coach redissenya d'avui
a diumenge (`replan`, prompt `replan-v1`), també aplicat sol. Sense migració:
`athlete_request.kind = 'free_text'` amb `payload.scope = 'week'` i
`report_type = 'replan'` ja existien (bústia, S5). Guardes: el model només
pot tocar els dies oberts (`window_errors`), les 15 regles validen la setmana
sencera, les sessions fetes no es toquen (`_guard`) i `REPLAN_DAILY_LIMIT`
(3) acota el cost (~0,18 € per redisseny). Avui ja no ensenya propostes
aplicades per l'atleta; les auto-aplicades, només el dia que es creen.

## 2026-09-14 — Contracte v1.4: camps opcionals → obligatoris i nullables; esforç i sostres

Assajant en sec el setmanal (S4b) han sortit tres coses, totes verificades
amb sondes petites contra l'API. (1) **Cap informe havia produït mai un
`new_session`**: amb els camps opcionals al schema, Sonnet ometia
`new_session` als `add` (i fins i tot escrivia `add` sense res, quatre
intents seguits). Amb `plan_session_id`, `new_session` i `new_date`
obligatoris però nullables (`null` explícit als keep/move/cancel), i el
mateix dins de `new_session` i a `block_changes`, l'emet sempre, també
quan se li demana compacte. És el contracte v1.4 (`$comment` al schema).
(2) `output_config.effort`: `medium` corromp la sortida estructurada (text
amb caràcters aleatoris, camps omesos) — mai per sota de `high`, que és el
que sempre havia corregut. `COACH_EFFORT` al `.env` per pujar-lo. (3) Un
intent es va quedar en bucle escrivint `\n` dins d'un string JSON fins als
64k tokens (0,64 €): el sostre del setmanal i del macro baixa a 32k (una
setmana sencera són ~13k) i el missatge de tall porta el cap i la cua del
text per diagnosticar; si totes les tandes es tallen, l'informe s'escriu
igualment (abans petava). Resultat: el setmanal simulat del 27/09 escriu
la setmana de recuperació sencera (7 sessions, descans dilluns, 4 h amb
l'Alpe d'Huez) al primer intent, sense cap bloqueig.

## 2026-09-14 — S4b: el setmanal escriu la setmana següent dins del bloc

El bloc de recuperació (S3) era buit i el setmanal (`weekly-v1`) només sabia
ajustar setmanes ja escrites. Decisions: (1) prompt `weekly-v2` (versions
per tipus a `PROMPT_VERSION`): el snapshot porta `week_to_write` (dilluns,
diumenge, sessions vives, bloc amb hores objectiu); si la setmana és buida
el coach l'escriu sencera amb un `add` per sessió, descans obligatori (R5),
pressupost d'hores del bloc i sostre de l'atleta, repartiment per disciplina
i fase; si ja té sessions, l'ajusta com abans. (2) Guarda semàntica: un
`add` del setmanal fora de `[dilluns, diumenge]` és error; `scope = week`.
(3) `write_report` rep el dia real: abans el setmanal li passava el dilluns
vinent i la finestra queia una setmana tard (sense test; ara en té).
(4) Els objectius actius amb `event_date` passada es donen per fets al
començament de cada informe: l'endemà de la cursa Fornells passa a
`completed` i el següent A amb data (Transpirinenca) governa; no cal cap
botó. (5) `apply_to_db` conserva el `rationale` propi de la sessió nova.
(6) App: la targeta de proposta mostra el resum, les sessions noves
("+ dl 28/09 · Natació suau · 30 min"), un "Per què" amb el raonament i les
preguntes del coach amb caixa de resposta (també per al macro, que fins ara
no es podia respondre). (7) El macro diu on queden els objectius fora del
seu horitzó. `--today` a `coach.run` per assajar en sec un altre dia.

## 2026-09-14 — Macro buit: el rationale i el JSON han de dir el mateix

El primer macro real (Sonnet) va sortir com a "proposta" sense cap
`block_changes`: el primer intent es va tallar als 64k tokens (raonament +
resposta comparteixen el sostre), i el segon, després del "sigues més
compacte", va deixar caure els blocs però el rationale seguia dient que
afegia la recuperació. L'app no ensenyava res (una proposta sense canvis
no es pinta) i l'atleta es va quedar esperant. Decisions: (1) un macro
sense `block_changes` és una infracció que torna al model, tret que el
summary comenci per "Cap canvi de blocs" (dir explícitament que no cal
tocar res); un macro amb `session_changes` també. (2) Un macro acceptat
sense canvis s'escriu amb `proposal_status = none` (informatiu), no
`proposed`. (3) El missatge de tall diu tokens generats i caràcters de JSON
vs raonament, i per al macro el consell és "només blocs", no "keep sense
comentaris". (4) Objectius mostra la resposta del coach a l'última petició
quan no porta canvis de blocs (abans només es veia el silenci).

## 2026-09-14 — S2b: el perfil de l'atleta surt de l'objectiu; temps objectiu; R15

Tot el que el coach sabia de l'atleta que no ve de Garmin (dia de descans fix,
sostre d'hores, piscina, genoll, marca dels 10 km) vivia a
`goal.profile.athlete_context` de Fornells, copiat pel seed: en completar la
cursa el 28/09 hauria desaparegut del context (només entren objectius
actius), i l'app no ho podia editar. Decisions: (1) columna `athlete.profile`
(jsonb) amb el mateix contingut; la migració 0013 hi mou l'`athlete_context`
i l'esborra de l'objectiu (una sola font de veritat); el seed ja no el fusiona
a l'objectiu sinó que actualitza l'atleta. (2) El context desplega el perfil
dins d'`athlete` (`athlete.constraints`, `athlete.health`, `athlete.notes`…),
que és com els prompts el citen. (3) Regla R15 "disponibilitat declarada":
sostre d'hores, dia de descans fix i dies disponibles, només avisos i només
setmanes no passades — és una negociació amb l'atleta, no fisiologia; el
macro, en canvi, no pot proposar blocs per sobre del sostre (error a
`block_errors`). (4) Objectius: temps objectiu editable des de l'app
(`profile.target_times_sec` amb la forma de sempre, `[prudent, objectiu,
gran dia]`, entrant només l'objectiu), dies per a ultra (`profile.days`), i
les notes es mostren. El coach contrasta el temps objectiu amb `test_results`
i activitats al `rationale`: l'app no prediu cap temps a partir d'hores,
perquè cap fórmula honesta ho dona. (5) Un A sense data és un objectiu de
forma: mana si cap A té data (regla de S2), i el prompt del macro li
planifica cicles base/build sense taper. (6) Pestanya "Jo" a l'app amb el
perfil, l'interruptor del coach (abans a Objectius) i "Surt" (abans a Avui).
Ajornat, apuntat: repartiment d'esports per bloc segons l'objectiu del bloc
(multi-objectiu real) — Roger accepta el comportament actual per al seu cas
(ultra bici A a l'estiu + 10 km B a l'hivern).

## 2026-09-14 — S3: el macro (blocs) el proposa el coach amb Opus; l'atleta l'aprova

Els blocs de Fornells acaben el 27/09 i després no hi ha on escriure. El
macro proposa la seqüència de blocs (fase, dates, hores/setmana, intenció,
fallback) fins a l'objectiu A més proper i la recuperació; mai sessions;
mai s'aplica sol. Decisions: (1) es dispara des de l'app (`athlete_request`
`regenerate_macro`, màxim un macro al dia) i el processa el cron
`decisions`, que obre connexions curtes al voltant de la crida al model
(1-3 min amb Opus: el pooler mata connexions ocioses). (2) Els blocs tenen
`status` i mai s'esborren; els efectes de bloc (`block_created`,
`block_cancelled`, `block_modified` amb `prev_values`) fan el desfer
simètric al de les sessions. (3) Validació pròpia dels blocs
(`coach/blocks.py`): no toca el passat, no toca blocs amb sessions
planificades, cap solapament, taper 7-10 dies acabant a la cursa A curta,
recovery l'endemà de 7-21 dies i amb menys hores, rampa ≤ 15% entre blocs i
del primer bloc nou contra les hores reals. (4) Model del macro:
`COACH_MODEL_MACRO` (per defecte `claude-opus-5`); el diari i el setmanal
segueixen amb Sonnet. (5) `run_report()` s'extreu de `main` perquè el
processador de peticions el pugui cridar. Cost estimat d'un macro: ~1 €.

## 2026-09-14 — S4a: el coach pot crear sessions; el validador jutja contra la realitat

Preparació del pla rodant (S3 macro, S4b setmana). Decisions: (1) acció
`add` al contracte (v1.2): `plan_session_id` passa a opcional (l'API admet
propietats opcionals), `new_session.local_date` i `parent_of_day` (el brick
penja de la sessió d'aquell esport del mateix dia, creada al mateix informe
o ja viva). Un `add` fora de tot bloc és error semàntic: "cal macro"; a la
BD, `apply_to_db` fa dues passades com el seed (crear, després encadenar) i
un `add` es desfà cancel·lant la fila nova. `classify` mai el fa automàtic.
(2) `plan_from_db` retorna també els blocs (per situar sessions en blocs
encara buits) i l'historial real de les 8 setmanes fins al dilluns d'avui
(hores i llarga per esport), no només les anteriors al pla. (3) R1 i R6
compten les setmanes passades amb les hores REALS si n'hi ha registre; el
passat no es jutja, és la base. (4) R8 només bloqueja quan el taper és
escrit sencer (sessions fins a la vigília); si és parcial, avisa. (5) El
setmanal parla del dilluns vinent: bloc i finestra `[dilluns, diumenge]`,
pla vist dues setmanes. Verificat que el pla real de Fornells dona el mateix
veredicte amb el codi nou que amb el vell.

## 2026-09-14 — S1b: propostes del coach a l'app; adeu al dry-run fins al 28

Roger (14/09): "no podem treure el dry_run i fer-ho tot bé directament?". Sí,
amb una condició: veure i desfer des del mòbil. Això és S1b. La targeta
d'Avui pinta el diff de cada informe amb canvis (dia i títol actual → què
proposa, i la raó), amb botons segons `proposal_status`: `proposed` → Aplica /
Descarta; `auto_applied` i `applied` → Desfés; en dry-run, etiqueta "Mode
prova" i cap botó. L'app només encua a `coach_decision`; `coach.decisions`
(cron cada 5 min) executa, i la targeta ensenya "Aplicant…" o l'error si
falla (una proposta pot haver caducat). L'interruptor del mode és a Objectius
(secció Coach), amb confirmació en activar l'híbrid. Decisió: l'híbrid
s'activa tan bon punt S1b és al mòbil, no el 28: els primers canvis reals del
coach passen sobre un pla que l'atleta es sap de memòria i amb ell mirant
cada matí, no sobre un bloc nou. `apply_to_db` fa la primera escriptura real
llavors; es vigila `coach_report_effect` el primer dia.

## 2026-09-14 — S2: objectius des de l'app; l'A més proper governa

Primer tall del camí cap a un pla generat pel coach i un segon usuari
(decisió Roger 14/09: no esperar al 27/09; única congelació fins al 28 és
`coach_apply_mode = dry_run`). L'atleta crea, edita i abandona objectius des
de la pestanya Objectius (abans "Fornells", un sol objectiu i la data
escrita al codi). Decisions: (1) `goal` mai s'esborra, s'abandona (blocs i
sessions hi pengen); (2) el perfil que escriu l'app és `profile.segments`
amb la mateixa forma que el de Fornells, i en editar es conserva la resta del
perfil (temps objectiu, protocol) que l'app no toca; (3) l'objectiu que
governa el pla és l'**A amb data més propera** (`rules.primary_goal`), no el
primer de la llista: R13 i, més endavant, el macro, el fan servir; (4) un
objectiu sense data (un 10 km "quan surti") és vàlid i no afecta cap regla.
Migració 0011: només grants i policies d'escriptura sobre `goal`.

## 2026-09-14 — "Ho he fet" des de Setmana; el vincle explícit de l'atleta mana

Tres natacions en una setmana registrades per xat perquè el botó només sortia a
Avui, el mateix dia i per a sessions `planned`. Cas que ho va destapar: la
sessió del 10/09 feta l'11 va quedar `missed` encara que la fila manual portava
`plan_session_id`, perquè `ingest.link` només aparella pel mateix dia i
ignorava aquell camp. Decisions: (1) una fila manual (`raw.manual`) amb
`plan_session_id` és la paraula de l'atleta — compta per a aquella sessió sigui
del dia que sigui, no passa per l'heurística de durada i no se li reescriu el
vincle; (2) el botó surt a Setmana per a qualsevol sessió de dia passat o d'avui
en `planned`/`partial`/`missed` sense activitat lligada, amb el dia editable;
(3) un `multisport` es registra per trams (un per segment swim/bike/run, cada
tram una activitat lligada a la mateixa sessió) i un `brick` com la cursa del
brick; (4) l'id manual passa a `-AAAAMMDDhhmmss` perquè dos trams del mateix
minut no xoquin. Sense migració: la RLS de la 0008 ja ho permet (`id < 0`).

## 2026-09-10 — S1a: aplicar amb seguretat (servidor), inert fins al 28/09

Primer tall del disseny post-cursa, construït ABANS de la cursa perquè el
dia 28 activar el coach real sigui canviar un valor, no programar. Tot queda
inert: `app_setting.coach_apply_mode` neix a `dry_run` i `coach.run` el
llegeix de la BD (el `--dry-run` del script del cron desapareix; el flag
queda com a override). Què canvia per sota: (1) `apply_to_db` exigeix que
cada sessió tocada sigui la viva i pendent (`StaleProposal` si no), copia
TOTES les columnes a la versió nova (fins ara modify/move perdien
`chained_after`, `test_spec`, `transition_practice` i `distance_m_target`:
el brick perdia la bici pare, bug latent que el dry-run amagava) i re-enllaça
els fills; (2) cada mutació queda a `coach_report_effect`: sense aquest
rastre Desfés és impossible; (3) informe + canvis + efectes en una sola
transacció; (4) `coach/classify.py` decideix per regla, no pel model, si un
informe és auto o proposta, i el resultat es desa SEMPRE a
`coach_report.classification` (també en dry_run: l'11-20/09 veurem com hauria
classificat cada proposta real abans de donar-li la clau); (5)
`coach/decisions.py` processa Aplica/Descarta/Desfés amb revalidació contra el
pla viu; (6) un sol `flock` per a totes les feines del cron; (7) el setmanal
té 64k tokens de sortida (streaming) i una resposta tallada és una tanda de
correcció, no un crash sense informe; el context es marca per a la cache;
(8) `plan_from_db` retorna tots els objectius actius i tolera que no n'hi
hagi cap; (9) el seed es nega a córrer si el coach ja ha versionat el pla.
Fora: `add`, prompts, `effort` del model, app (S1b).

## 2026-09-10 — Després de Fornells: planificació rodant, bústia i aprovació híbrida

Disseny complet a `docs/post-cursa-design.md`. Decisions d'en Roger: (1) el coach
proposa un **macro** de blocs a partir dels objectius, s'aprova a l'app i es
regenera quan canvien els objectius; cada diumenge el setmanal **escriu la
setmana següent** dins del bloc vigent (planificació rodant, no un pla de mesos
d'una tirada). (2) Els canvis es demanen des d'una **bústia** estructurada amb
text lliure, no un xat. (3) **Aprovació híbrida**: canvis petits (≤3 dies, ≤2
sessions, modificar/moure dins la setmana/cancel·lar no-clau, sense afegir
càrrega, validador net) s'apliquen sols amb Desfés; la resta espera un Aplica a
l'app. (4) Sonnet 5 per a diari, setmanal i peticions; Opus 5 només per al
macro. Cost estimat 10-13 $/mes (dades reals: diari 0,11 $, setmanal 0,18 $).
La revisió va trobar 7 bloquejants al codi actual (sense `add`, bricks que es
perden en modify/move, cap lock, Desfés impossible sense rastre, `sys.exit`
sense objectiu actiu, R1/R6 contra hores planificades, R8 amb taper parcial):
tots amb arreglo al disseny. L'usuari no ha de tocar mai el terminal.

## 2026-09-10 — Barcelona 15-18/09 sense bici: la bici del 16 s'absorbeix a la del 19

En Roger és a Barcelona del 15 al matí al 18 al vespre, sense bici, amb pista
d'atletisme i piscina de 50 m. La bici clau del 16 ("Dos blocs de vint" +
brick) no cap. No es mou al 14 (48 h després del simulacre del 12, dos blocs
de 20' a esforç de cursa és massa) ni al 20 (dues bicis seguides abans del
taper, i el genoll). El seu contingut específic, 2×20' a esforç de cursa,
substitueix els 3×10' de la bici del 19 ("Última llarga: dos blocs de vint",
75'). El 16 passa a dia suau amb dues sessions support: piscina de tècnica amb
10 drills de viratge obert (en Roger para a cada paret; objectiu viratge < 2 s
perquè els 2×500 del 17 siguin continus) i rodatge 40' RPE 3. El 18 queda com
estava (pista); la natació regenerativa de divendres tarda es descarta (Roger).

Mecànica: 16 bike+brick surten del yaml; a la BD queden `status=moved`,
`superseded_by` la bici i el brick del 19 (50→54, 51→55; noves 73 natació, 74 rodatge). El validador dona
dos avisos R13 nous i acceptats per a la setmana del 14: bici al 19% (marge
35-55) i natació al 44% (marge 2-42). Són correctes: aquella setmana no hi ha
bici possible. Bricks encadenats al pla: 7 → 6.

## 2026-09-10 — Tres decisions de pla després de la revisió (aprovades per en Roger)

1. **Simulacre del 12/09 = assaig de nutrició.** L'únic assaig previst (bici
   llarga del 05/09) es va perdre. El simulacre incorpora l'esmorzar de cursa
   3 h abans, gel + aigua 25 min abans de sortir, i gels als minuts 30 i 60 de
   bici; notes als segments perquè surtin a l'app i al rellotge.
2. **18/09 rebaixada**: de 4×1000 a 3:37/km a 3×1000 a 3:45 (ritme de 10 km),
   recuperació 2'. No s'ha fet cap sessió de qualitat a peu en tot el pla
   (29/08 substituïda, 04/09 perduda); estrenar-la a tope a 9 dies de la cursa
   és risc sense benefici. Córrer és el punt fort a protegir.
3. **Test de 1000 m del 20/09: NO** (decisió d'en Roger). Els 1000 m del
   simulacre del 12/09 seran la segona referència; entrenar val més que un
   altre test.

Correcció de registre: la bici específica + brick del 02/09 es van fer el
03/09 (bici 83', cursa 14'). Les sessions passen al 03/09 (`superseded_by`
31→69, 32→70), la bici com a `support` perquè aquell dia la clau és la natació
(R14). Validador OK (44 sessions).
## 2026-09-10 — Alerta taronja del 09/09: bici traslladada al 10/09, i natació del 08/09 recuperada

El 09/09 (alerta taronja per tempestes a les Balears) no es va poder fer ni
la bici de blocs ni res. El 10/09, amb el millor despertar del mes (FC repòs
45, estrès 9, bateria 100) i una setmana molt buida, es fan les dues sessions:
bici + brick al matí (repunts asseguts si fa vent), natació de ritme de cursa
a la tarda a piscina (avís costaner, aigua prohibida). Mecànica del pla: les
sessions del 09/09 queden `superseded_by` les del 10/09 (versionat, res
s'esborra; les entrades surten del yaml perquè el seed no reinserti la data
vella), i la bici del 10/09 és `support`, no `key`: R14 no admet dues clau el
mateix dia, i si només es pot fer una és la natació (limitador); la bici la
cobreixen el simulacre del 12 i els blocs del 16. Sense el supersede, R1
comptava les hores del 09/09 perdut més les del 10/09 (+16% setmanal).

La natació del 08/09 ("Sèries mitjanes") constava com a perduda: es va fer a
piscina cronometrada amb el rellotge, sense registrar; les dues bicis curtes
del dia eren el trajecte. Entrada manual -202609081 (45 min, 1700 m = valors
del pla, no mesurats; càrrega estimada) i relink: completed.

## 2026-09-09 — El coach veu les marques (`test_results` al snapshot)

`test_result` existia des de la F3 però cap codi la llegia: els tests eren
notes d'activitat per al coach. Es registra el 1000 m a mar del 03/09 (22:30,
135 s/100, mesurat per l'entrenador) com a primer resultat, i el snapshot del
coach incorpora `test_results` (tots, sense finestra: una marca val fins que
n'hi ha una de més nova; valors aplanats + títol de la sessió). Els prompts
daily/weekly v1 en descriuen l'ús; no es bumpa la versió perquè és una
addició, no un canvi de conducta.
## 2026-09-09 — El test de 800 m del 10/09 se substitueix per natació a ritme de cursa

En Roger va qüestionar el test ("ja sé que faig els 1000 m en 22 min a mar").
Tenia raó: el test comparava amb el de l'01/09, que no es va fer (cap resultat
a `test_result`), i un 800 a piscina no es pot posar al costat del 1000 m a
mar del 03/09 (22:30, 2:15/100, mesurat per l'entrenador). Un tot-o-res en
setmana de càrrega (TSB -12,7), entre la bici de repunts i el simulacre de
dissabte, sense res a mesurar. Substituït per 3×400 m a 2:15/100 amb
orientació (1600 m, 40 min), millor a mar: entrena mantenir el ritme i
orientar-se, que és el que falta per Fornells. Un test de piscina té sentit
després de la cursa, com a base del 2027. Validador: 44 sessions, només els 2
avisos R9 coneguts. Aprovat per en Roger en conversa el 09/09.
## 2026-09-07 — L'app també surt del Mac: servidor d'Expo a `alberginia`

Amb les feines al servidor, l'única dependència del Mac que quedava era la
pròpia app: Expo Go la descarrega del servidor de desenvolupament, que corria
al Mac (adormit de nit, i només a la WiFi de casa). En Roger té el programa de
desenvolupador d'Apple, però prefereix seguir amb Expo Go: els canvis es veuen
sense compilar. Solució: el servidor d'Expo passa a `alberginia` com a servei
`systemd` (`expo-dev`), exposat a `exp://<IP del servidor>:8081` (regla TCP 8081
al tallafocs de Clouding), amb la sessió d'Expo d'en Roger copiada perquè
Expo Go 57 exigeix el mateix compte als dos costats. El desplegament diari
també fa `npm install` i reinicia el servei. Verificat: manifest i paquet iOS
(9,5 MB, 1820 mòduls, 58 s la primera vegada) servits des de la IP pública.
Queda documentat a `docs/server.md` que TestFlight és el pas següent quan
calgui icona pròpia, notificacions o independència dels SDK d'Expo Go.

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
