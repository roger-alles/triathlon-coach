# Especificació — Entrenador personal de triatló amb dades de Garmin

**Document d'entrada per a l'agent de codi.** Llegeix-lo sencer abans d'escriure res.
Versió 1.1 · 27 d'agost de 2026 · Atleta: Roger

> **v1.1** — Revisada contra el pla real de Fornells (`seeds/fornells-2026.yaml`). El model de dades s'ha ampliat per poder-lo representar i **sis de les catorze regles s'han corregit** perquè, tal com estaven, rebutjaven un pla bo. Els canvis estan marcats amb 🔺.

---

## 0. Com has de treballar (llegir primer)

L'objectiu del projecte no és només tenir l'app: **l'atleta vol aprendre a desenvolupar-la**. Això canvia com has de treballar.

- Construeix **una peça petita cada vegada**, i atura't perquè la revisi abans de continuar. No entreguis fases senceres d'una tirada.
- Quan escriguis codi que introdueixi un concepte nou (hooks, async, migracions, autenticació), **explica'l breument** en el missatge, no només al codi.
- Commits petits i amb missatge descriptiu. Una feina lògica per commit.
- **Pregunta abans** d'afegir una dependència pesada, canviar d'stack o reestructurar carpetes.
- Si una decisió d'aquest document et sembla equivocada, **digues-ho i argumenta-ho** en lloc d'obeir en silenci. Aquest document és un punt de partida, no dogma.
- No inventis dades ni mètriques. Si una dada de Garmin no existeix o no la trobes, deixa el camp `NULL` i informa'n. Un pla d'entrenament construït sobre dades inventades és pitjor que no tenir-ne.

---

## 1. Què és això

Un sistema personal (un sol usuari) que:

1. **Ingesta** automàticament les dades d'entrenament i recuperació de Garmin Connect.
2. Les **desa** en una base de dades pròpia amb un model estable.
3. Manté un **pla d'entrenament estructurat** orientat a un o més objectius.
4. Un **entrenador basat en Claude** revisa els avenços cada dia i cada setmana i ajusta el pla dins d'unes regles dures.
5. Una **app mòbil** (iOS + Android) ho mostra tot: què toca avui, com va la setmana, com evoluciona la forma.

### Abast dels esports

Els tres del triatló — **natació, bicicleta i cursa a peu** — més força com a suport. El sistema ha de servir tant per a objectius **combinats** (un triatló) com **d'un sol esport** (una 10 km popular, una travessa llarga en bici). Això vol dir que la disciplina no és una propietat global del sistema sinó **de cada objectiu**, i el repartiment de volum setmanal entre esports es deriva de l'objectiu actiu.

### Objectius reals de l'atleta (per configurar a la base de dades)

| Objectiu | Data | Prioritat | Disciplina |
|---|---|---|---|
| 🔺 **Artiem Half Menorca · Short** (Fornells) — 1.000 m / 34 km / 8–9 km | **dg. 27 set. 2026, 08:35** | A | `triathlon` |
| 10 km popular | esporàdic, sense data fixa | C | `run` |
| Transpirinenca | estiu de 2027 | A | `ultra_endurance` |

🔺 El primer objectiu ja està completament definit a `seeds/fornells-2026.yaml`, amb els temps previstos per segment, les normes de la prova (**sense drafting**, **neoprè molt probablement prohibit**) i el context de l'atleta: **primer triatló**, 10 km en 37:30, ve d'un mes sense nedar, unes 5 h setmanals abans del pla, sense gimnàs i amb el dilluns de descans fix. La natació és el **limitant declarat** i córrer, l'esport a **protegir**. Aquestes dues etiquetes no són comentaris: el validador les llegeix (R13).

> ⚠️ **Encara per confirmar:** si el sector a peu són 8 o 9 km (el reglament i les fitxes de la cursa no coincideixen), i si la **Transpirinenca** es farà **en bicicleta o a peu** — canvia completament el repartiment de volum. Fins que no es confirmi, deixa-ho com a camps de configuració i no ho codifiquis dins de la lògica.

### Què NO és (anti-objectius)

- No és un producte multiusuari. Un sol atleta, sense registre ni gestió de comptes.
- No es publica a les botigues d'entrada. L'app corre en local via Expo Go.
- No dona consells mèdics. Detectar patrons de fatiga sí; diagnosticar, mai.
- No reimplementa Garmin Connect. Ensenya el que Garmin no dona: el pla adaptatiu i el raonament.

---

## 2. Stack tècnic

| Capa | Tecnologia | Motiu |
|---|---|---|
| Ingesta | Python 3.12 + [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) | És l'única via realista d'accedir a les dades pròpies |
| Base de dades | Supabase (Postgres) | Postgres de veritat, API i auth incloses, gratis per a aquest volum |
| Entrenador | API de Claude amb sortida estructurada | El raonament |
| Interfície de treball | Servidor **MCP** sobre la base de dades | Permet parlar amb l'entrenador des de Claude abans que existeixi l'app |
| App | Expo (React Native) + TypeScript + Expo Router | Un sol codi per a iOS i Android |
| Programació de tasques | `cron` local o GitHub Actions | La sincronització nocturna i el coach diari |

**Sobre l'accés a Garmin:** no hi ha API oficial per a particulars — el Connect Developer Program només accepta entitats legals. `garminconnect` fa login imitant l'app d'Android i és una llibreria no oficial, mantinguda activament (versió 0.3.12 del 22/08/2026), però **es pot trencar quan Garmin canviï l'autenticació** — va passar el març del 2026. Per això la capa d'ingesta ha d'estar **aïllada darrere d'una interfície pròpia** (`ingest/providers/garmin.py` implementant un protocol `ActivityProvider`), de manera que es pugui substituir per Intervals.icu o per importació de fitxers `.FIT` sense tocar la resta del sistema. Això no és sobreenginyeria: és l'únic punt del disseny on sabem del cert que hi haurà un trencament.

---

## 3. Model de dades

Postgres. Fes migracions versionades des del primer dia (`supabase/migrations/`), mai canvis a mà a la consola.

```sql
-- Perfil i llindars de l'atleta. Una sola fila, però amb historial de llindars.
create table athlete (
  id                    int primary key default 1,
  name                  text not null,
  birth_date            date,
  max_hr                int,
  resting_hr_baseline   int,
  ftp_watts             int,                    -- llindar bici
  css_sec_per_100m      numeric,                -- Critical Swim Speed, natació
  threshold_pace_sec_km numeric,                -- llindar cursa
  zones                 jsonb not null,         -- vegeu §4
  updated_at            timestamptz default now(),
  check (id = 1)
);

create table threshold_history (
  id         bigserial primary key,
  measured_on date not null,
  metric     text not null,   -- 'ftp_watts' | 'css_sec_per_100m' | 'threshold_pace_sec_km' | 'vo2max_run' ...
  value      numeric not null,
  source     text not null    -- 'garmin' | 'test' | 'manual'
);

create table goal (
  id            bigserial primary key,
  name          text not null,
  discipline    text not null check (discipline in
                  ('triathlon','run','bike','swim','ultra_endurance')),
  event_date    date,
  priority      char(1) not null check (priority in ('A','B','C')),
  profile       jsonb,        -- distàncies, desnivell, terreny, durada estimada
  status        text not null default 'active'
                  check (status in ('active','completed','abandoned')),
  notes         text
);

-- Una fila per activitat real feta. L'id és el de Garmin: garanteix idempotència.
create table activity (
  id                    bigint primary key,          -- garmin activityId
  start_time            timestamptz not null,
  local_date            date not null,
  sport                 text not null check (sport in
                          ('swim','bike','run','strength','brick','other')),
  sub_sport             text,                        -- 'open_water','trail','indoor'...
  duration_sec          int not null,
  moving_duration_sec   int,
  distance_m            numeric,
  elevation_gain_m      numeric,
  avg_hr                int,
  max_hr                int,
  avg_power_w           numeric,                     -- bici
  normalized_power_w    numeric,
  avg_pace_sec_km       numeric,                     -- cursa
  avg_pace_sec_100m     numeric,                     -- natació
  avg_cadence           numeric,
  calories              int,
  garmin_training_load  numeric,                     -- càrrega segons Garmin
  aerobic_te            numeric,
  anaerobic_te          numeric,
  load                  numeric,                     -- càrrega normalitzada nostra, §5
  perceived_effort      int check (perceived_effort between 1 and 10),  -- RPE, manual
  feeling               int check (feeling between 1 and 5),            -- manual
  athlete_notes         text,
  plan_session_id       bigint,                      -- FK afegida després, vegeu nota
  raw                   jsonb not null,              -- resposta sencera de Garmin
  ingested_at           timestamptz default now()
);
-- `activity` i `plan_session` es referencien mútuament: afegeix aquesta clau
-- en una migració posterior a la creació de plan_session.
-- alter table activity add constraint activity_plan_session_fk
--   foreign key (plan_session_id) references plan_session(id) on delete set null;
create index on activity (local_date);
create index on activity (sport, local_date);

-- Una fila per dia: recuperació i estat de forma.
create table daily_metric (
  local_date          date primary key,
  resting_hr          int,
  hrv_last_night_ms   numeric,
  hrv_status          text,          -- 'balanced','unbalanced','low' (nomenclatura de Garmin)
  hrv_baseline_low    numeric,
  hrv_baseline_high   numeric,
  sleep_duration_sec  int,
  sleep_score         int,
  deep_sleep_sec      int,
  body_battery_max    int,
  body_battery_min    int,
  training_readiness  int,           -- 0-100 de Garmin, si el dispositiu el dona
  stress_avg          int,
  weight_kg           numeric,
  vo2max_run          numeric,
  vo2max_bike         numeric,
  garmin_training_status text,       -- 'productive','overreaching','detraining'...
  raw                 jsonb,
  ingested_at         timestamptz default now()
);

-- Càrrega agregada i forma. Recalculada, no editada a mà.
create table load_daily (
  local_date date primary key,
  load       numeric not null default 0,   -- suma de load de les activitats del dia
  ctl        numeric not null,             -- forma crònica (fitness), 42 dies
  atl        numeric not null,             -- fatiga aguda, 7 dies
  tsb        numeric not null,             -- ctl - atl (frescor)
  monotony   numeric,                      -- mitjana setmanal / desviació
  strain     numeric
);

-- Blocs de periodització d'un objectiu.
create table plan_block (
  id            bigserial primary key,
  goal_id       bigint not null references goal(id) on delete cascade,
  phase         text not null check (phase in
                  ('base','build','peak','taper','race','recovery','transition')),
  name          text,
  start_date    date not null,
  end_date      date not null,
  focus         text,
  intent        text,               -- 🔺 què busca el bloc, en una frase
  target_weekly_load numeric,
  target_weekly_hours numeric,      -- 🔺 l'atleta pensa en hores, no en unitats de càrrega
  fallback      text,               -- 🔺 "si la setmana se't torça, salva X". Vegeu nota
  return_from_layoff boolean default false  -- 🔺 desactiva R1 i R6, vegeu §8
);

-- La unitat central: una sessió planificada.
create table plan_session (
  id                bigserial primary key,
  block_id          bigint references plan_block(id) on delete cascade,
  goal_id           bigint references goal(id),
  local_date        date not null,
  sport             text not null check (sport in
                      ('swim','bike','run','strength','brick','multisport','rest')),
                      -- 🔺 'multisport': simulacre, escalfament previ, i la cursa mateixa
  session_type      text not null,     -- vegeu §4
  title             text not null,
  structure         jsonb not null,    -- contracte a §6
  duration_sec_target int,
  distance_m_target numeric,
  planned_load      numeric,
  priority          text not null default 'support'
                      check (priority in ('key','support','optional')),
  status            text not null default 'planned'
                      check (status in ('planned','completed','partial','missed','moved','cancelled')),
  rationale         text,              -- per què aquesta sessió, avui
  -- 🔺 camps nous, tots amb un ús concret al validador o a la interfície:
  is_test           boolean default false,   -- sessió de mesura; alimenta test_result
  test_spec         jsonb,                   -- protocol, què es registra, amb quin test es compara
  rehearses_goal    boolean default false,   -- assaig de la prova: exempta de R9
  is_goal_event     boolean default false,   -- la cursa
  chained_after     bigint references plan_session(id),  -- brick encadenat a la bici del mateix dia
  transition_practice text[],                -- {'t1','t2'}
  created_by        text not null default 'coach' check (created_by in ('coach','athlete')),
  version           int not null default 1,
  superseded_by     bigint references plan_session(id),
  created_at        timestamptz default now()
);

-- 🔺 Resultats de les sessions de test, per veure si la feina funciona.
create table test_result (
  id              bigserial primary key,
  plan_session_id bigint references plan_session(id),
  activity_id     bigint references activity(id),
  local_date      date not null,
  metric          text not null,     -- 'swim_continuous','ftp','run_threshold'...
  values          jsonb not null,    -- {"distance_m":800,"pace_sec_100m":112}
  compared_with   bigint references test_result(id),
  delta           jsonb              -- calculat, no escrit pel model
);

-- 🔺 Logística lligada a un objectiu: no és entrenament, però no fer-ho costa la cursa.
create table logistics_task (
  id          bigserial primary key,
  goal_id     bigint not null references goal(id) on delete cascade,
  local_date  date not null,
  title       text not null,
  detail      text,
  blocking    boolean default false,   -- si no es fa, no hi ha cursa
  done        boolean default false
);
create index on plan_session (local_date);
-- Com a molt una sessió `key` viva per esport i dia. Les de suport poden repetir-se
-- (doble sessió del mateix esport en un mateix dia és normal en triatló).
create unique index on plan_session (local_date, sport)
  where priority = 'key' and superseded_by is null
    and status in ('planned','completed','partial');

-- Cada intervenció de l'entrenador queda registrada, amb el que va veure.
create table coach_report (
  id            bigserial primary key,
  created_at    timestamptz default now(),
  report_type   text not null check (report_type in
                  ('daily','weekly','replan','answer')),
  window_start  date,
  window_end    date,
  input_snapshot jsonb not null,   -- exactament el que se li va passar al model
  output        jsonb not null,    -- contracte a §7
  summary_md    text,
  model         text,
  input_tokens  int,
  output_tokens int,
  validation_errors jsonb          -- violacions detectades i corregides, si n'hi va haver
);
```

**Per què `input_snapshot` i `output` sencers:** quan d'aquí a tres mesos una recomanació sembli estranya, has de poder reconstruir exactament què sabia el model quan la va fer. Sense això, depurar un entrenador basat en un LLM és impossible.

---

## 4. Vocabulari del domini

### Tipus de sessió per esport

| Esport | `session_type` |
|---|---|
| `swim` | `technique`, `endurance`, `css_intervals`, `speed`, `open_water`, `race_pace` |
| `bike` | `recovery`, `endurance`, `tempo`, `sweet_spot`, `threshold`, `vo2max`, `long`, `hills` |
| `run` | `recovery`, `easy`, `long`, `tempo`, `threshold`, `intervals`, `hills`, `brick_run`, `race_pace` |
| `strength` | `general`, `core`, `plyometric`, `maintenance` |
| `brick` | `bike_run` (sessió combinada, obligatòria en triatló) |
| `rest` | `full`, `active` |

### Zones (camp `athlete.zones`)

Cinc zones per esport, cadascuna amb la seva referència, perquè les zones de FC de córrer i de la bici **no són les mateixes**:

```json
{
  "run":  {"basis": "threshold_pace", "z1": [0, 0.78], "z2": [0.78, 0.88],
           "z3": [0.88, 0.95], "z4": [0.95, 1.02], "z5": [1.02, 1.20]},
  "bike": {"basis": "ftp",  "z1": [0, 0.55], "z2": [0.55, 0.75],
           "z3": [0.75, 0.90], "z4": [0.90, 1.05], "z5": [1.05, 1.50]},
  "swim": {"basis": "css",  "z1": [0, 0.85], "z2": [0.85, 0.92],
           "z3": [0.92, 0.98], "z4": [0.98, 1.03], "z5": [1.03, 1.15]},
  "hr":   {"basis": "max_hr", "z1": [0, 0.68], "z2": [0.68, 0.78],
           "z3": [0.78, 0.87], "z4": [0.87, 0.93], "z5": [0.93, 1.00]}
}
```

**Convenció crítica:** totes les fraccions són de **velocitat**, no de ritme. Z5 de cursa a `[1.02, 1.20]` vol dir *entre un 2% i un 20% més ràpid* que el llindar — o sigui, un ritme per km **més baix**. El mateix per a la natació amb el CSS. Fes la conversió en un sol lloc (`zones.py` / `zones.ts`) i cobreix-la amb un test, perquè invertir-la és l'error silenciós més fàcil de cometre en tot el projecte i produeix plans absurds que semblen correctes.

Les zones són **configuració, no codi**. Que ningú escrigui `if pace < 4.30` enlloc.

### Repartiment de volum per disciplina de l'objectiu

Percentatge del **temps** setmanal, com a punt de partida que el coach pot moure ±10 punts segons els punts febles de l'atleta:

| Disciplina | swim | bike | run | strength |
|---|---|---|---|---|
| `triathlon` | 22% | 45% | 28% | 5% |
| `run` | 5% | 15% | 75% | 5% |
| `bike` | 0% | 85% | 10% | 5% |
| `swim` | 80% | 10% | 5% | 5% |
| `ultra_endurance` | 0% | 70%¹ | 20%¹ | 10% |

¹ Per a la Transpirinenca, `bike` i `run` s'intercanvien segons si es fa en bici o a peu. **Confirmar amb l'atleta.**

---

## 5. Càlcul de la càrrega i la forma

Sense una mesura de càrrega comparable entre esports, res de tot això funciona. Un migdia de natació i tres hores de bici han de poder sumar-se.

**Càrrega d'una activitat** (`activity.load`), per ordre de preferència segons les dades disponibles:

1. Si Garmin dona `garmin_training_load`, fes-la servir com a base.
2. Si no, i hi ha potència (bici): `load = (NP/FTP)² × durada_hores × 100`.
3. Si no, però hi ha FC: TRIMP amb ponderació exponencial per zona — `load = Σ(minuts_zona_i × factor_i)`, amb factors `[1, 1.5, 2.5, 4, 6]` per a Z1–Z5.
4. Si no hi ha res: `durada_hores × 50` i marca l'activitat com a `load_estimated = true`.

Documenta al README quin mètode s'ha fet servir en cada cas. Les càrregues de mètodes diferents no són perfectament comparables i cal saber-ho.

**Forma** (taula `load_daily`), mitjanes mòbils exponencials estàndard:

```
CTL_avui = CTL_ahir + (càrrega_avui − CTL_ahir) / 42
ATL_avui = ATL_ahir + (càrrega_avui − ATL_ahir) / 7
TSB_avui = CTL_ahir − ATL_ahir
```

Recalcula la sèrie sencera des de zero a cada sincronització. És barat, i evita divergències quan arriba una activitat endarrerida.

**Monotonia** (mitjana de càrrega diària de 7 dies / desviació estàndard) i **strain** (monotonia × càrrega setmanal): són els indicadors clàssics de risc de sobreentrenament, i un pla molt regular en pot disparar la monotonia sense que la càrrega pugi. Val la pena tenir-los.

---

## 6. Contracte JSON d'una sessió

El camp `plan_session.structure`. **Aquest contracte és sagrat**: el valida el codi, el genera Claude, el pinta l'app i, més endavant, es tradueix a un entrenament del rellotge.

```json
{
  "schema_version": "1.0",
  "steps": [
    {
      "phase": "warmup",
      "duration_sec": 900,
      "target": {"type": "hr_zone", "value": 2},
      "note": "progressiu"
    },
    {
      "phase": "main",
      "repeats": 4,
      "work":     {"duration_sec": 480, "target": {"type": "ftp_pct", "value": 0.95}},
      "recovery": {"duration_sec": 240, "target": {"type": "ftp_pct", "value": 0.55}}
    },
    {
      "phase": "cooldown",
      "duration_sec": 600,
      "target": {"type": "hr_zone", "value": 1}
    }
  ]
}
```

**Tipus de `target` admesos** (i només aquests):

| `type` | Unitat | Esport |
|---|---|---|
| `hr_zone` | 1–5 | qualsevol |
| `ftp_pct` | fracció de l'FTP | bici |
| `pace_sec_km` | segons per km | cursa |
| `pace_pct_threshold` | fracció del ritme llindar | cursa |
| `css_pct` | fracció del CSS | natació |
| `pace_sec_100m` | segons per 100 m | natació |
| `rpe` | 1–10 | qualsevol |
| `open` | — | rodatges lliures, tècnica |

Per a natació, `duration_sec` es pot substituir per `distance_m` dins de qualsevol pas. Un pas ha de tenir **exactament un** de `duration_sec` o `distance_m`. Pot haver-hi **més d'un pas amb `phase: "main"`**: una sessió de natació típica són quatre o cinc blocs seguits.

Un `target` admet tres camps opcionals més: `label` (el nom que l'atleta li dona: *"esforç de cursa"*), `tolerance` (marge acceptat en la mateixa unitat) i `comparator` (`slower_than` / `faster_than`, per a instruccions com "tot per sota de 4:45/km").

### 🔺 Sessions multiesport

Un simulacre, un escalfament previ i la cursa mateixa no són una llista de passos sinó una seqüència de **segments** amb transicions pel mig. Quan `sport = 'multisport'`, `structure` porta `segments` en lloc de `steps`:

```json
{
  "schema_version": "1.1",
  "segments": [
    {"sport": "swim", "distance_m": 800, "venue": "open_water",
     "target": {"type": "rpe", "value": 7}},
    {"sport": "transition", "transition": "t1", "timed": true},
    {"sport": "bike", "distance_m": 34000,
     "target": {"type": "rpe", "value": 7, "label": "esforç de cursa"}},
    {"sport": "transition", "transition": "t2", "timed": true},
    {"sport": "run", "distance_m": 3000,
     "target": {"type": "pace_sec_km", "value": 250}}
  ]
}
```

Un segment pot contenir `steps` propis si cal detallar-lo. La càrrega d'una sessió multiesport és la suma de la dels seus segments, i **es reparteix per esport** a l'hora de calcular la distribució setmanal de §4 — si no, un simulacre de dues hores compta com un esport inexistent i desquadra tots els percentatges.

### 🔺 Quan no hi ha llindars

Aquest atleta **no té FTP, ni CSS, ni FC màxima mesurada**, i el pla real està escrit amb esforç percebut i ritmes de cursa. El sistema ha de funcionar igual:

- `athlete.ftp_watts`, `css_sec_per_100m`, `threshold_pace_sec_km` i `max_hr` són `NULL` fins que hi hagi una mesura. **No inventis estimacions ni les prenguis de Garmin sense marcar-les** com a `source = 'garmin_estimate'` a `threshold_history`.
- Si un llindar és `NULL`, els `target` que hi depenen (`ftp_pct`, `css_pct`, `pace_pct_threshold`) **no es poden fer servir**. El validador ha de rebutjar un pla que els faci servir sense la referència corresponent, i el coach ha de caure a `rpe` o a valors absoluts (`pace_sec_km`).
- Quan aparegui una mesura (un test, o un canvi d'estimació de Garmin), escriu-la a `threshold_history` i **no reescriguis les sessions passades**: el pla es va fer amb el que se sabia llavors.

Escriu un **validador de l'esquema** (`pydantic` al backend, `zod` a l'app) i comparteix-ne la definició via un JSON Schema a `contracts/`. Que no hi hagi dues definicions que puguin divergir.

---

## 7. L'entrenador

### Com funciona

Una feina programada, no una crida des de l'app. Dos ritmes:

- **Diari, al matí** (06:00): mira les dades de recuperació de la nit i l'activitat d'ahir, i decideix sobre la sessió d'avui.
- **Setmanal, diumenge al vespre**: revisió de la setmana i ajust de la següent.
- **Sota demanda**: quan l'atleta reporta una molèstia, un canvi d'agenda o una cursa nova.

### El bucle, pas a pas

1. **Recollir el context** (determinista, en codi — el model no consulta la base de dades sol):
   - Perfil, zones i llindars actuals
   - Objectius actius, ordenats per data i prioritat
   - Bloc de periodització en curs
   - Últims 28 dies: activitats (resumides, no crues), càrrega diària, CTL/ATL/TSB
   - Últims 14 dies de mètriques de recuperació
   - Compliment: planificat vs real de les últimes 3 setmanes
   - El pla dels propers 14 dies
   - Notes recents de l'atleta i molèsties obertes
2. **Cridar Claude** amb sortida estructurada obligatòria (tool use amb JSON Schema, no text lliure).
3. **Validar** la resposta amb el motor de regles de §8.
4. Si hi ha violacions, **tornar-les-hi** amb les infraccions concretes i demanar correcció. **Màxim 2 intents.**
5. Si encara falla: **descartar la proposta**, deixar el pla existent, marcar `coach_report.validation_errors` i avisar l'atleta. Un pla que incompleix les regles no s'aplica mai, per bo que soni el raonament.
6. Escriure el resultat: sessions noves amb `version + 1`, les antigues marcades amb `superseded_by`. **Res s'esborra mai**, així es pot veure l'historial de decisions.

### Contracte de sortida del coach

```json
{
  "schema_version": "1.0",
  "report_type": "daily",
  "readiness": {
    "verdict": "green|amber|red",
    "drivers": ["hrv_below_baseline_2d", "sleep_debt"],
    "confidence": "high|medium|low"
  },
  "summary": "Frase curta per a la pantalla d'avui.",
  "rationale": "Explicació completa del perquè, en el llenguatge de l'atleta.",
  "session_changes": [
    {
      "plan_session_id": 412,
      "action": "keep|modify|replace|move|cancel",
      "new_session": { },
      "reason": "HRV per sota de la línia base dos dies seguits; les sèries no rendirien."
    }
  ],
  "flags": ["monotony_high"],
  "questions_for_athlete": ["Com tens el bessó esquerre després del rodatge de dimarts?"]
}
```

`rationale` no és decoració. **És el producte.** Un pla que no s'explica és un PDF; un pla que s'explica i que pots discutir és un entrenador.

### Regles de conducta del model (van al prompt de sistema)

- Prescriu entrenament, no medicina. Davant d'un dolor persistent, la recomanació és aturar-se i consultar un professional; no diagnostiquis.
- Ets **conservador per defecte**. Davant del dubte, la sessió fàcil. El cost d'una sessió dura perduda és petit; el d'una lesió, tota la temporada.
- No inventis xifres. Si una dada falta, digues que falta.
- Treballa **dins de les regles dures**. Si creus que una regla t'impedeix fer el correcte, digues-ho a `flags` en lloc d'incomplir-la.
- Escriu en català, en segona persona, directe i sense floritures.

**Model:** consulta l'identificador vigent a `docs.claude.com/en/docs/about-claude/models` en lloc de codificar-ne un. Posa'l a la configuració i desa'l a `coach_report.model` en cada crida.

---

## 8. Regles dures (el validador)

Codi determinista, `coach/rules.py`, amb la signatura:

```python
def validate_plan(plan: list[PlanSession], athlete: Athlete,
                  history: LoadHistory, goals: list[Goal]) -> list[Violation]
```

Cada regla és una funció independent i **té el seu test unitari**. Aquesta és la part del sistema on no hi ha creativitat: si el validador és fluix, tot el projecte és un generador de text maco.

> 🔺 **Aquestes regles s'han provat contra el pla real de Fornells i sis estaven malament.** Un validador massa estricte és pitjor que no tenir-ne: rebutja els plans bons, el coach reintenta, i acabes amb entrenament mediocre validat. Els llindars de sota són els corregits; a §8.1 hi ha què va fallar i per què.

| # | Regla | Llindar |
|---|---|---|
| R1 | Rampa de càrrega setmanal | ≤ +8% sobre la mitjana de les 4 setmanes anteriors (dur: +12%). 🔺 **No s'aplica** si el bloc té `return_from_layoff`, ni si la setmana anterior va ser < 60% de `target_weekly_load`, ni per sota d'un terra absolut de càrrega baixa (configurable, per defecte 5 h setmanals) |
| R2 | Setmana de descàrrega | cada 4a setmana com a màxim, al 60–70% de la precedent. 🔺 **Cedeix davant de R8**: dins d'un taper, o en un bloc de menys de 4 setmanes fins a una cursa A, no s'exigeix |
| R3 | Separació entre sessions clau | ≥ 48 h entre dues `key` del **mateix** esport. 🔺 Entre esports diferents, **≥ 18 h**: l'apilament de cap de setmana (qualitat de córrer divendres + llarga de bici dissabte) és un patró deliberat del triatló, no un error |
| R4 | Distribució d'intensitat | 🔺 **Depèn de la fase**: `base`/`build` ≥ 75% del temps en Z1–Z2; `peak`/específic ≥ 60%; `taper` ≥ 80%. Les sessions amb `rehearses_goal` o `is_goal_event` **queden fora del càlcul** |
| R5 | Descans | ≥ 1 dia de descans complet per setmana (2 en setmana de descàrrega) |
| R6 | Creixement de la sessió llarga | ≤ +10% de durada per setmana i esport. 🔺 Mateixes exempcions que R1 |
| R7 | Freqüència mínima (triatló) | ≥ 2 natacions/setmana; ≥ 1 brick/setmana en fases `build` i `peak` |
| R8 | Taper | comença 7–10 dies abans (sprint/curta) o 14 dies (mig o superior). Volum −40% i després −60%; **la intensitat es manté** |
| R9 | Novetats prop de la cursa | cap **material nou** ni cap tipus de sessió **mai practicat abans** en els 10 dies previs a una cursa A. 🔺 Els assajos de la prova (`rehearses_goal`) hi estan **explícitament permesos**: fer els 1.000 m al mar set dies abans no és una novetat, és l'assaig general |
| R10 | Recuperació post-cursa | ≥ 1 dia fàcil per cada hora de cursa a intensitat alta, sense sessions `key` |
| R11 | Senyals vermells | si `hrv_status = 'unbalanced'` o `training_readiness < 30` **dos dies seguits** → cap sessió `key`; substituir per fàcil o descans |
| R12 | Monotonia | si la monotonia de 7 dies > 2,0 → introduir variabilitat abans d'afegir volum |
| R13 | Coherència amb l'objectiu | ±10 punts del perfil de la disciplina (§4). 🔺 Si `goal.profile.emphasis.limiter` declara un esport limitant, aquest esport té **±20 punts** i el declarat a `protect` pot quedar per sota sense penalització |
| R14 | Integritat estructural | tota sessió compleix el contracte de §6, cap sessió al passat, cap solapament de dues `key` el mateix dia (els bricks encadenats amb `chained_after` no compten com a solapament) |

**R1, R3, R5, R8, R11 i R14 són bloquejants** (violació → es rebutja el pla). La resta són avisos que s'adjunten al `coach_report` i es tornen al model per a la següent iteració.

### 8.1 🔺 Què va fallar en provar-les contra el pla real

Aquesta taula és la millor prova de regressió que tens. **Escriu-la com a test**: el pla de `seeds/fornells-2026.yaml` ha de passar el validador sencer. Si un canvi teu el trenca, el canvi és sospitós.

| Regla | Què deia el pla real | Per què la regla estava malament |
|---|---|---|
| **R1** | Bloc inicial 4 h 45 → setmana 1, 7 h 15: **+53%** | La regla del 8% és per a atletes en règim. Reprenent després d'un mes aturat, s'aplica sobre una base artificialment baixa i bloqueja qualsevol represa raonable |
| **R2** | Quatre setmanes seguides sense descàrrega abans del taper | Amb la cursa a 4 setmanes, la descàrrega **és** el taper. Exigir-ne una altra abans destrossaria la setmana del simulacre |
| **R3** | Sèries de córrer divendres + llarga de bici dissabte, cada setmana | En triatló, apilar esports diferents el cap de setmana és estructural. La regla de 24 h creuada prohibia el patró que fa funcionar el pla |
| **R4** | Setmanes 1–3 amb 72%, 51% i 67% de temps fàcil | El 80/20 és per a blocs de base. En les quatre setmanes específiques prèvies a una cursa curta, la densitat d'intensitat és intencionada; a més, el simulacre de 2 h comptava sencer com a intensitat |
| **R6** | Bici llarga 1 h 15 → 1 h 45: **+40%** | Mateix problema que R1: creixement sobre una base de represa |
| **R13** | Natació al 29–37% del temps quan el perfil deia 22% | La natació és el limitant declarat i és on l'entrenament encara canvia el resultat. Sense un mecanisme per declarar-ho, el sistema empeny cap a la mitjana i esborra la decisió d'entrenament més important del pla |

El patró és sempre el mateix: **una regla escrita per a l'estat estacionari, aplicada a una situació de transició** — tornar després d'una aturada, o les últimes setmanes abans d'una cursa. Quan afegeixis regles noves, pregunta't sempre en quin d'aquests dos estats s'ha de desactivar.

---

## 9. Ingesta de Garmin

`ingest/providers/garmin.py`, darrere del protocol `ActivityProvider`.

**Autenticació**: `garminconnect` desa els tokens OAuth a `~/.garminconnect/garmin_tokens.json` amb permisos 0600 i els refresca sol. La contrasenya **només** s'usa al primer login (i per a l'MFA, si el compte el té actiu). **Mai desis la contrasenya a la base de dades, ni al repositori, ni a un fitxer de configuració versionat.** Variables d'entorn i `.env` fora de git.

```python
from garminconnect import Garmin

client = Garmin(os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD"),
                prompt_mfa=lambda: input("Codi MFA: "))
client.login("~/.garminconnect")
```

**Descobreix els mètodes disponibles a la teva versió abans d'escriure la ingesta**, en comptes de fiar-te de tutorials desactualitzats:

```python
print([m for m in dir(client) if m.startswith("get_")])
```

La llibreria exposa més de 130 mètodes. Els que necessites cobreixen: activitats per rang de dates, detall i splits d'una activitat, son, HRV, freqüència cardíaca en repòs, body battery, estat d'entrenament, training readiness, VO₂màx i composició corporal. Escriu els noms exactes a `docs/garmin-api.md` a mesura que els confirmis, amb un exemple de la resposta de cadascun.

**Regles de la sincronització:**

- **Idempotent.** Executar-la dues vegades no ha de duplicar res: `insert ... on conflict (id) do update`.
- **Incremental** per defecte (des de l'última activitat coneguda menys 3 dies de marge, perquè Garmin de vegades reprocessa), amb un `--full --since YYYY-MM-DD` per a la càrrega inicial.
- **Guarda sempre el JSON cru** a `activity.raw` i `daily_metric.raw`. El cost és menyspreable i t'estalvia haver de tornar a baixar-ho tot quan descobreixis un camp que no havies mapat.
- **Amable amb el servidor.** Pausa entre peticions, i a la càrrega inicial ves per trossos de 30 dies. Res de baixar dos anys en un bucle sense fre.
- **Falla amb soroll.** Si l'autenticació es trenca (i algun dia passarà), que el log ho digui clar i que el sistema no ensenyi dades velles com si fossin d'avui. Cada pantalla ha de saber de quan és l'última sincronització correcta.

**Vinculació planificat ↔ real:** després de cada sincronització, associa cada activitat nova a la seva `plan_session` — mateix dia i mateix esport; si n'hi ha més d'una candidata, la de durada més propera. Marca la sessió com `completed` si la càrrega real és ≥ 80% de la planificada, `partial` si és menys, i `missed` si al final del dia no hi ha cap activitat. Aquesta taula de compliment és **l'entrada principal de l'entrenador**: sense ella, opina a cegues.

---

## 10. Fases d'entrega

Cada fase té un criteri d'acceptació verificable. **No comencis una fase sense que l'anterior el compleixi.**

### F0 — Explorar Garmin (mig dia)
Script solt que fa login, baixa els últims 90 dies i els desa com a JSON al disc.
✅ **Acceptació:** un directori amb les activitats i les mètriques diàries reals, i `docs/garmin-api.md` amb els camps que ofereix cada endpoint.
*Aquesta fase és la que decideix si el projecte és viable. Fes-la abans que res.*

### F1 — Base de dades i sincronització
Migracions, model, sincronització incremental idempotent, càlcul de càrrega i CTL/ATL/TSB.
✅ **Acceptació:** `make sync` dos cops seguits no crea duplicats; una consulta SQL retorna la corba de forma dels últims 90 dies i els números són plausibles comparats amb Garmin Connect.

### F2 — Servidor MCP
Eines de lectura (`get_recent_activities`, `get_form_curve`, `get_week`, `get_compliance`) i d'escriptura del pla (`propose_sessions`, `update_session`).
✅ **Acceptació:** des de Claude, en una conversa, es pot preguntar "com he anat aquesta setmana?" i obtenir números reals de la base de dades.
*Aquí ja tens valor real sense cap app. És el moment de comprovar si els consells són bons abans d'invertir en la interfície.*

### F3 — El pla com a dades
Objectius, blocs de periodització, sessions, i el validador de §8 complet amb tests.
🔺 **El pla ja existeix**: `seeds/fornells-2026.yaml` conté les 5 setmanes reals fins al 27 de setembre, amb 45 sessions, la logística i el protocol de cursa. Escriu un loader idempotent (`ingest/seed.py`) i carrega'l; no generis res inventat en aquesta fase.
✅ **Acceptació:** el seed es carrega dues vegades sense duplicar; el pla de Fornells **passa les 14 regles corregides**; un pla amb una rampa del 30% en règim estacionari és rebutjat amb el motiu concret.

### F4 — L'entrenador
Feina diària i setmanal, sortida estructurada, bucle de validació i correcció, registre a `coach_report`.
✅ **Acceptació:** durant 7 dies seguits, la feina diària s'executa sola i produeix una recomanació coherent i explicada; una violació provocada artificialment es corregeix o es rebutja, i queda registrada.

### F5 — L'app
Expo. Pantalles: **Avui** (estat de recuperació + sessió + el perquè), **Setmana** (calendari i compliment), **Activitat** (detall, planificat vs real), **Forma** (corba CTL/ATL/TSB), **Objectius**.
✅ **Acceptació:** funciona al mòbil via Expo Go, amb dades reals, i es pot marcar una sessió i afegir-hi RPE i sensacions.

### F6 — Extres (només si les anteriors són sòlides)
Notificacions matinals · xat amb les pròpies dades via MCP · **enviar l'entrenament al rellotge** (la llibreria permet `upload_running_workout`, `schedule_workout` i `push_workout_to_device`: és la funció que tanca el cercle — el pla apareix al Garmin sense copiar res a mà) · importació de `.FIT` com a proveïdor alternatiu.

---

## 11. Estructura del repositori

```
├─ contracts/            # JSON Schemas compartits (sessió, sortida del coach)
├─ ingest/
│  ├─ providers/         # garmin.py, intervals_icu.py, fit_files.py
│  ├─ sync.py            # orquestració, idempotència
│  └─ load.py            # càrrega, CTL/ATL/TSB
├─ coach/
│  ├─ context.py         # construcció del context (determinista)
│  ├─ prompts/           # prompts versionats, en fitxers, no incrustats
│  ├─ rules.py           # el validador de §8
│  └─ run.py             # bucle diari/setmanal
├─ mcp_server/
├─ seeds/
│  └─ fornells-2026.yaml  # el pla real de l'atleta, punt de partida del sistema
├─ supabase/migrations/
├─ app/                  # Expo
├─ tests/
│  └─ fixtures/          # dades reals anonimitzades per als tests
├─ docs/
│  ├─ garmin-api.md
│  └─ decisions.md       # per què s'ha fet cada cosa així
└─ SPEC.md               # aquest document
```

**Prompts en fitxers versionats**, mai dins del codi Python. Quan canviïs un prompt vols veure'n el diff i poder-hi tornar.

---

## 12. Tests

No cal cobertura completa, però hi ha quatre punts on un test val el seu pes en or:

1. **El validador.** Un cas per regla, amb un pla que la incompleix i un que la respecta. És la xarxa de seguretat de tot el sistema.
2. **Idempotència de la sincronització.** Sincronitzar les mateixes dades dues vegades → mateix nombre de files.
3. **Aritmètica de CTL/ATL.** Una sèrie coneguda amb el resultat calculat a mà.
4. **Contracte de sortida del coach.** Respostes d'exemple (una vàlida, una malformada, una que incompleix regles) i comprovar que el bucle reacciona bé a cadascuna. **Sense cridar l'API** — respostes desades a `tests/fixtures/`.

---

## 13. Seguretat i privacitat

Aquí hi ha dades de salut d'una persona real. No és paranoia, és higiene:

- Cap credencial al repositori. `.env` a `.gitignore` des del primer commit.
- Les claus de servei de Supabase només al backend; l'app només fa servir la clau anònima.
- No enviïs a l'API de Claude res que no calgui: resums i agregats, no fitxers `.FIT` sencers ni traces de GPS. Menys dades enviades és millor consell i menys exposició alhora.
- Fes una còpia de seguretat de la base de dades abans de cada migració destructiva.
- Si algun dia es publica: aquestes dades, en molts marcs legals, són categoria especial. Aquell dia caldrà una conversa a part.

---

## 14. Primera pregunta que has de fer a l'atleta

🔺 Bona part del que faltava a la v1.0 ja és a `seeds/fornells-2026.yaml`. Queda això:

1. **Sector a peu: 8 o 9 km?** Canvia els temps previstos uns 4 minuts.
2. **Lesions o molèsties** actuals o recurrents. No hi ha res al pla i cal preguntar-ho explícitament.
3. **Disponibilitat de piscina**: quins dies i en quines franges. El pla demana quatre entrades a l'aigua per setmana i la quarta ja està marcada com a flexible.
4. **Té potenciòmetre a la bici?** Determina si `ftp_watts` podrà existir mai o si tot anirà per esforç percebut.
5. **La Transpirinenca**: bici o a peu, i quants dies. Encara no urgeix, però condiciona el model de `ultra_endurance`.

I una advertència sobre el calendari: **la cursa és d'aquí a un mes**. El sistema no hi arribarà a temps i no ha d'intentar-ho. Fins al 27 de setembre el pla el segueix l'atleta des de l'artefacte HTML que ja té; el que estàs construint recollirà les dades d'aquestes setmanes i entrarà en servei per al cicle següent. **No canviïs el pla de Fornells** — carrega'l i mesura'l.
