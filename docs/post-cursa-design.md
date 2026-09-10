# Disseny: el pla d'entrenament després de Fornells

> Planificació rodant, bústia de peticions i aprovació híbrida. Acordat amb en Roger el
> 10/09/2026; revisat contra el codi i la BD real el mateix dia. Cada tall (S0-S6) tindrà la seva
> spec curta, tests primer i PR propi. Res es desplega abans de la cursa del 27/09.

## Context

El 27/09 s'acaba el pla de Fornells i el coach es queda sense res sobre què actuar: només pot
`modify`/`move`/`cancel` sessions que ja existeixen, no hi ha acció `add`, cap objectiu ni bloc es
pot crear fora del yaml + terminal, i `--dry-run` és una constant al script del cron. Roger vol
que a partir de la cursa **tot passi des de l'app**: afegir objectius, tenir un pla generat i
mantingut pel coach, demanar canvis de manera simple, i aprovar el que és estructural.

Decisions preses al xat del 10/09:
- **Planificació rodant**: macro (blocs) proposat pel coach a partir dels objectius i aprovat a
  l'app; cada diumenge el setmanal escriu la setmana següent dins del bloc vigent.
- **Bústia de peticions** estructurada + text lliure, no un xat.
- **Aprovació híbrida**: canvis petits automàtics per regla al codi, amb Desfés; estructurals amb
  Aplica a l'app.
- **Models**: Sonnet 5 per a diari, setmanal i peticions; Opus 5 només per al macro.
- Cost estimat: 10 a 13 $/mes (dades reals: diari 0,11 $, setmanal 0,18 $, 3,08 $ en 13 dies).

Res d'això es desplega abans de la cursa. Es construeix en branques; el diari/setmanal segueixen
en dry-run fins al 28/09.

## Què hi ha i què condiciona (verificat al codi el 10/09)

- `contracts/coach-output.schema.json`: `session_changes[]` amb `action ∈ {keep, modify, replace,
  move, cancel}` i `plan_session_id` obligatori. `report_type` ja admet `replan` i `answer` (també el
  check de `coach_report`), sense productor.
- `coach/run.py`: `coach_cycle` (3 intents amb feedback del validador), `apply_to_db` (clona files
  existents; versionat amb `superseded_by`), `write_report`. `--dry-run` CLI; `scripts/coach-job.sh`
  el passa sempre.
- `coach/context.py`: snapshot amb `goals` (tots els actius), `current_block`, `plan_next_14d`,
  `athlete_answers_last_7d`, etc. `coach/plan_loader.py:54` només carrega el pla del primer
  objectiu (`limit 1`) → el validador veu un sol objectiu.
- `coach/gate.py:17`: "COACH_FORCE=1 salta la porta (decisió humana explícita, futur botó a l'app)".
- RLS (`0005`, `0007`): `authenticated` només llegeix `goal`, `plan_block`, `plan_session`; escriu
  `activity` (subjectiu, manual id<0), `logistics_task.done`, `athlete_answer` insert. Taules noves
  neixen sense grants.
- App: `getActiveGoal` és single-goal; escriptures: 4 funcions a `app/lib/api.ts`.
- Servidor `alberginia`: cron matí `*/5 6-11` amb gate, sync horari, vespre 21:30, setmanal dg 20:30,
  deploy 05:50. Cap endpoint HTTP: l'app només parla amb Supabase.

## Forats trobats a la revisió (10/09, verificats contra codi i BD real)

Bloquejants que el disseny inicial no cobria:
- **B1 `add` trenca el cicle sencer**: `semantic_errors` i `apply_changes` indexen per
  `plan_session_id` (`run.py:62,94`); una sessió sense bloc cau a fase `build` per defecte
  (`rules.py:177`) i R2/R4/R7 avaluen malament. El bloc s'ha de resoldre ABANS de validar.
- **B2 bricks encadenats són inexpressables** (`new_session` no té `parent_of_day`), i ja avui
  `modify`/`move` perden `chained_after`, `test_spec`, `transition_practice` (`run.py:178-200`): el
  primer modify real d'un brick fa fallar R14/R3 al cicle següent. Bug latent, tapat pel dry-run.
- **B3 cap lock** a `coach-job.sh` (el matí corre cada 5 min i una generació pot durar més) i
  `apply_to_db` no comprova `superseded_by is null` (una proposta caducada clona una fila morta).
- **B4 Desfés no es pot fer** només amb `coach_report.output`: `apply_to_db` no guarda els ids nous
  ni l'estat previ; `plan_block` no té estat i `block_id` és `on delete cascade`.
- **B5 marcar Fornells `completed` mata tots els crons**: `plan_loader.py:53-56` fa `sys.exit` sense
  objectiu actiu.
- **B6 R1/R6 comparen contra hores PLANIFICADES**, i la història real està congelada a les 5
  setmanes abans del 26/08 (`plan_loader.py:77-83`): una setmana saltada compta al 100%.
- **B7 R8 bloqueja la primera setmana d'un taper** escrit setmana a setmana (`rules.py:380-406`).

Alts: `MAX_TOKENS=16000` ja és just per al setmanal (14.9k de sortida, ~12k són pensament) i un
tall mata el procés SENSE escriure informe; informe i aplicació no són atòmics (`run.py:269-273`);
el seed sobreescriu versions del coach si es torna a executar (`seed.py:112-118`); no hi ha
`planned_load` a cap fila (la càrrega es calcula amb `rules.session_seconds`); la dedup per
`window_start` no serveix per a peticions.

## Arquitectura

Principi: **la base de dades és la cua**. L'app escriu files (objectius, peticions, decisions); el
servidor les recull amb un cron cada 5 minuts i executa el coach; el resultat torna com a
`coach_report` que l'app mostra. Sense servidor HTTP nou. Latència ≤ 5 min, visible a l'app com
"El coach hi està treballant".

### Taules noves (migració `0010_post_race_planning.sql`)

```sql
-- Peticions de l'atleta al coach (bústia). L'app hi insereix; el servidor les processa.
create table athlete_request (
  id          bigserial primary key,
  created_at  timestamptz default now(),
  kind        text not null check (kind in
                ('unavailable','no_sport','discomfort','new_goal','free_text','regenerate_macro')),
  payload     jsonb not null,      -- {date_from,date_to,sports[],text,goal_id...}
  status      text not null default 'pending'
                check (status in ('pending','processing','answered','failed')),
  report_id   bigint references coach_report(id),   -- la proposta resultant
  error       text
);

-- Decisions de l'atleta sobre una proposta (Aplica / Descarta / Desfés).
create table coach_decision (
  id          bigserial primary key,
  created_at  timestamptz default now(),
  report_id   bigint not null references coach_report(id),
  decision    text not null check (decision in ('apply','discard','undo')),
  status      text not null default 'pending'
                check (status in ('pending','done','failed')),
  error       text
);

-- Estat d'una proposta (columnes noves a coach_report)
alter table coach_report
  add column proposal_status text not null default 'none'
    check (proposal_status in ('none','auto_applied','proposed','applied','discarded','undone')),
  add column scope text not null default 'sessions'
    check (scope in ('sessions','week','macro')),
  add column classification jsonb;   -- per què és auto o proposta (regles avaluades)

-- Rastre de cada mutació que fa un informe (imprescindible per a Desfés i per a auditoria).
create table coach_report_effect (
  id             bigserial primary key,
  report_id      bigint not null references coach_report(id),
  decision_id    bigint references coach_decision(id),
  kind           text not null check (kind in
                   ('created','superseded','cancelled','moved','block_created','block_cancelled')),
  session_id     bigint references plan_session(id),
  new_session_id bigint references plan_session(id),
  block_id       bigint references plan_block(id),
  prev_status    text,
  prev_superseded_by bigint
);

-- Blocs amb estat (mai esborrar: block_id és on delete cascade).
alter table plan_block add column status text not null default 'active'
  check (status in ('active','proposed','cancelled'));

-- Configuració editable des de l'app (clau/valor, valors validats).
create table app_setting (key text primary key, value jsonb not null, updated_at timestamptz default now(),
  check (key <> 'coach_apply_mode' or value in ('"dry_run"','"hybrid"')));
insert into app_setting values ('coach_apply_mode', '"dry_run"');
```
Grants (post-0007 cap taula nova en té): `enable row level security` a les tres taules noves;
`grant select, insert` a `athlete_request`, `coach_decision` + `usage` de les seqüències;
`grant insert (name, discipline, event_date, priority, profile, notes)` i `update (…, status)` a
`goal` + `usage goal_id_seq`; `select` + `update (value)` a `app_setting`; policies `using(true)`.
Revocar l'`update`/`references` sobrant d'`athlete_answer`. El servidor tracta qualsevol
`coach_apply_mode` desconegut com a `dry_run`. `goal.profile` es valida de forma al servidor
(`rules.py:126-131` peta amb un perfil malformat).
### Contracte del coach (`contracts/coach-output.schema.json` v1.1)

- `session_changes[].action` guanya `add`. Per a `add`: `plan_session_id` opcional (el codi
  n'exigeix la presència segons l'acció), `new_session` obligatori amb `local_date`; el servidor
  assigna `goal_id`/`block_id` pel bloc actiu que conté la data.
- `new_session` guanya `parent_of_day` (esport) per als bricks; `apply_to_db` fa dues passades com
  el seed (`(data, esport)` → id nou) per enllaçar `chained_after` dins del mateix informe.
- Nou `block_changes[]` (només `scope = macro`): `{action: add|modify|cancel, block_id?, new_block:
  {phase, name, start_date, end_date, intent, target_weekly_hours, fallback}}`.
- `report_type` produïts: `daily`, `weekly` (ara també escriu la setmana següent), `replan`
  (petició), `macro` (afegir a l'enum del schema i al check de la taula).

### Coach (`coach/`)

- `run.py`: `apply_to_db(conn, report_id, changes)` amb guardes (`where id=%s and superseded_by is
  null and status='planned'`, error si `rowcount=0`), escriu `coach_report_effect` per mutació,
  copia TOTES les columnes (`chained_after`, `test_spec`, `transition_practice`,
  `distance_m_target`) i re-enllaça els fills (`update … set chained_after=new where
  chained_after=old`). Informe + aplicació + efectes en UNA transacció (insert report → apply →
  commit). `apply_changes(plan, changes, blocks)` retorna llista, ids sintètics negatius per als
  `add`, i resol el bloc per data abans de validar (sense bloc → error semàntic "cal macro").
- `run.py`: modes nous `weekly` (revisar + **escriure** la setmana entrant: prompt `weekly-v2`),
  `replan --request <id>` (prompt `replan-v1`: la petició al context), `macro` (prompt `macro-v1`,
  model Opus via `COACH_MODEL_MACRO`). `apply_to_db` aprèn `add` (insert des de zero, `created_by
  'coach'`) i `block_changes`.
- `classify.py` (nou): regla determinista **auto vs proposta**. Auto només si TOT: horitzó ≤ 3 dies,
  ≤ 2 sessions, accions ⊆ {modify, move dins la mateixa setmana, cancel de no-clau}, càrrega
  resultant ≤ planificada, validador sense bloqueig. Guarda el resultat a `coach_report.classification`.
- Flux d'aplicació: `apply_mode = dry_run` → tot com ara. `hybrid` → auto: `apply_to_db` +
  `proposal_status = auto_applied`; proposta: `proposed`, res a la BD fins a `coach_decision`.
- `llm.py`: `max_tokens` per mode (diari 16k; setmanal i macro 64k amb `messages.stream` +
  `get_final_message`), `output_config.effort` (`medium` al diari: la sortida és el 70% del cost),
  `cache_control` al missatge de context (els intents 2 i 3 rellegeixen el mateix prefix: el
  04/09 un diari va costar 56k tokens d'entrada), i `stop_reason=max_tokens` tractat com a error de
  validació amb feedback, no com a crash.
- `inbox.py` (nou, cron `*/5 6-23`): processa `athlete_request` pendents (executa `replan`/`macro`;
  màxim 6 crides LLM/dia, la resta s'encuen) i `coach_decision` pendents. Idempotència per fila:
  `update … set status='processing' where id=%s and status='pending' returning id`. `apply` només
  si `proposal_status='proposed'` i torna a passar `semantic_errors` + `validate_plan` contra el
  pla viu (la proposta pot haver caducat). `undo` només sobre `auto_applied`/`applied`: recorre
  els efectes a l'inrevés (creades → amagades amb `superseded_by` cap enrere; velles → `status` i
  `superseded_by` restaurats); es nega si alguna fila creada ja té activitat enllaçada, està
  `completed`/`partial`, o ja ha estat superseded per un informe posterior.
- `scripts/coach-job.sh`: un sol `flock` per a tots els modes (`-n` matí/sync, `-w 900` inbox
  perquè les peticions passin DESPRÉS del setmanal). `coach.run` llegeix `coach_apply_mode` de la
  BD; `--dry-run` queda com a override.
- `ingest/seed.py`: guarda que es nega a córrer si hi ha cap `plan_session.version > 1` o cap
  informe aplicat. S0 és l'última execució del seed; CLAUDE.md passa a dir "la BD és la veritat".
- `plan_loader.py`: carregar **tots** els objectius actius (llista, pot ser buida: mai `sys.exit`)
  i el pla sencer; `validate_plan` rep la llista. R13 usa la disciplina de l'objectiu A més proper.
  Tots els blocs pengen de l'objectiu A més proper (una sola línia temporal).
- `rules.py`: R1/R6 comparen contra hores REALS de les setmanes ja passades (`History.weekly_hours`
  de les últimes 8 setmanes fins a `reference_date`, no fins a `plan_start`); R8 avalua el volum
  del taper només quan el pla cobreix `[inici taper, cursa]` sencer, si no és avís. El validador
  sempre valida el pla sencer (R3 creua diumenge/dilluns), no "la setmana nova" sola.
- `context.py`: afegir `pending_requests`, `macro` (tots els blocs futurs, estat `active`),
  `goals` amb `notes`; el setmanal rep `block_for(next_monday)`, no el bloc d'avui (diumenge
  retorna el que acaba). `write_report`: finestra del setmanal = dilluns-diumenge vinents.
- `classify.py`: `classify(changes, plan_by_id, candidate, today, blocking) -> Classification`
  amb `auto`, `reasons`, horitzó, nombre de sessions, segons totals i segons durs abans/després
  (`rules.session_seconds` i `session_easy_hard`; no hi ha `planned_load`).
- `gate.py`: dedup per `(report_type, window_start)` també per a `replan`/`macro` per petició.
- Post-cursa automàtic (setmanal 27/09 nit o 28/09 matí): `goal.status = completed` quan
  `event_date < today` i és `A`; bloc `recovery` d'1-2 setmanes creat pel macro (R10).

### Prompts

- `weekly-v2`: revisa la setmana i **proposa la setmana següent sencera** dins del bloc vigent
  (hores objectiu del bloc, disciplina de l'objectiu, compliment real). `add` per a cada sessió.
- `replan-v1`: la petició manda; canviar el mínim; explicar què es perd.
- `macro-v1`: dels objectius actius i la història, blocs fins a l'objectiu A més proper (i encaix
  dels B/C), fase, dates, hores/setmana, intenció, fallback. Sense sessions.

### App

- **Objectius**: pestanya Fornells passa a "Objectius": llista (A/B/C, data, compte enrere), l'actiu
  A destacat amb el que hi ha ara (segments, temps, logística). Formulari nou/edita: nom,
  disciplina, data, prioritat, distàncies, notes. Desar un objectiu nou crea `athlete_request`
  `regenerate_macro`.
- **Macro**: vista de blocs (fase, dates, hores) sota els objectius; proposta de macro amb Aplica.
- **Propostes** (targeta a Avui i a Setmana): diff de sessions (nou / mogut / canviat / cancel·lat)
  amb la raó; botons Aplica / Descarta / Demana un canvi; estat Aplicant… / Aplicat. Auto-aplicades:
  mateixa targeta amb Desfés.
- **Demana un canvi**: full amb tipus (no puc aquests dies, no tinc aquest esport, molèstia, text
  lliure), camps segons tipus, envia → `athlete_request`. Historial amb estat.
- **Ajustos**: interruptor "Coach aplica canvis" (`app_setting.coach_apply_mode`).
- `api.ts`: `getGoals`, `upsertGoal`, `getBlocks`, `getProposals` (consulta pròpia per
  `proposal_status`, no `getLatestDailyReport`), `sendRequest`, `getRequests`, `sendDecision`,
  `getSetting`/`setSetting`.
- Supòsits single-goal a arreglar: `getActiveGoal` limit 1, "27/09/2026" hardcodejat a
  `objectius.tsx:75`, `daysUntil` amb `event_date` null → NaN, títol de pestanya "Fornells",
  `getBlockForRange` sense objectiu. Decidir si les cancel·lades auto-aplicades s'amaguen a
  Setmana (ara sortirien com a "cancel·lada").

## Lliurament per talls (cada tall = spec curta + tests primer + PR + deploy)

| # | Tall | Contingut | Quan |
|---|---|---|---|
| S0 | Tancament de Fornells | yaml: bloc `recovery` 28/09 – **18/10** (3 setmanes, marge per a S2-S4); `goal` completed; ÚLTIMA execució del seed | 27-28/09 |
| S1a | Aplicar amb seguretat (servidor) | `app_setting` + mode llegit de la BD; `flock`; `apply_to_db` amb guardes + efectes + una transacció + columnes completes + re-enllaç de bricks; `classify.py`; `coach_decision` apply/discard/undo amb revalidació; objectius com a llista (sense `sys.exit`); guarda del seed; `max_tokens` per mode + cache. Provable amb decisions inserides a mà mentre encara és `dry_run` | setmana 28/09 |
| S1b | Aplicar amb seguretat (app) | targeta de proposta a Avui (auto amb Desfés; proposta amb Aplica/Descarta); interruptor a Ajustos | setmana 28/09 |
| S2 | Objectius des de l'app | grants goal, pantalla Objectius multi-objectiu, `upsertGoal`, validador multi-objectiu, arreglar supòsits single-goal | 1a setmana oct |
| S4a | Validador per a pla rodant | `add` a `apply_changes`/`semantic_errors`/`apply_to_db`, `parent_of_day`, R1/R6 amb hores reals, R8 tolerant, `block_for(next_monday)`. Provable dins del bloc recovery escrit a mà, sense macro | 1a-2a setmana oct, en paral·lel amb S2 |
| S3 | Macro | `block_changes`, `plan_block.status`, prompt `macro-v1` amb Opus, vista de blocs, Aplica | 2a setmana oct |
| S4b | Setmana rodant | `weekly-v2`, proposta setmanal amb Aplica | abans del 18/10 |
| S5 | Bústia | `athlete_request`, pantalla Demana un canvi, `replan-v1`, `inbox.py` complet, límit diari | novembre |
| S6 | Xat amb dades (opcional) | només si S1-S5 són sòlids | més endavant |

Ordre justificat: S1 desbloqueja el valor immediat (el coach que ja tenim, aplicant de debò i
amb control a l'app), i és més gran del que semblava: arrossega lock, efectes, transacció única i
guarda del seed. S4a és el tall de més risc i el que de debò dona el pla d'octubre; per això va en
paral·lel amb S2 i el bloc de recuperació escrit a mà s'allarga fins al 18/10.

## Riscos

- **Concurrència**: un sol `flock`; peticions després del setmanal; `apply` revalida contra el pla viu.
- **Desfés** només una versió enrere per sessió i mai sobre sessions amb activitat enllaçada o ja
  fetes; el linker (`ingest/link.py:47`) re-avalua estats cada sync, compatible amb restaurar files.
- **Cost descontrolat per peticions**: límit 6/dia i mai més d'una `macro` per dia.
- **Dues sessions clau el mateix dia** (índex únic): `add` valida R14 abans d'inserir.
- **Sortides llargues**: `max_tokens` 64k al setmanal/macro; el prompt demana `add` i `keep`
  compactes, sense repetir estructures que no canvien.
- **Calendari**: S2 + S3 + S4 han d'estar abans del 18/10 o cal allargar el bloc a mà una setmana més.

## Verificació (global)

- Tests Python per a `classify.py` (taula de casos auto/proposta), `apply_to_db` amb `add` i
  `block_changes`, `inbox.py` (idempotència, límit diari, undo), validador multi-objectiu.
- Tests jest per pantalla nova (objectius, propostes, petició, ajustos).
- Assaig end-to-end amb `apply_mode = dry_run` a la BD real fins al 28/09; després `hybrid`.
