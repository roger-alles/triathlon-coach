-- F1: taules del costat de la ingesta (spec §3).
-- goal, plan_* i coach_report arriben a la F3: encara no els necessita ningú.

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
  zones                 jsonb not null,         -- spec §4
  updated_at            timestamptz default now(),
  check (id = 1)
);

create table threshold_history (
  id          bigserial primary key,
  measured_on date not null,
  metric      text not null,   -- 'ftp_watts' | 'css_sec_per_100m' | 'threshold_pace_sec_km' | 'vo2max_run' ...
  value       numeric not null,
  source      text not null    -- 'garmin' | 'garmin_estimate' | 'test' | 'manual'
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
  garmin_training_load  numeric,                     -- NULL en aquest dispositiu (F0)
  aerobic_te            numeric,
  anaerobic_te          numeric,
  load                  numeric,                     -- càrrega normalitzada nostra (spec §5)
  load_estimated        boolean not null default false,
  perceived_effort      int check (perceived_effort between 1 and 10),  -- RPE, manual
  feeling               int check (feeling between 1 and 5),            -- manual
  athlete_notes         text,
  plan_session_id       bigint,                      -- FK quan existeixi plan_session (F3)
  raw                   jsonb not null,              -- resposta sencera de Garmin
  ingested_at           timestamptz default now()
);
create index on activity (local_date);
create index on activity (sport, local_date);

-- Una fila per dia: recuperació i estat de forma.
-- hrv_*, sleep_score, training_readiness i vo2max_* quedaran NULL amb el
-- dispositiu actual (vegeu docs/garmin-api.md) — el model els conserva per si
-- canvia el rellotge o el proveïdor.
create table daily_metric (
  local_date          date primary key,
  resting_hr          int,
  hrv_last_night_ms   numeric,
  hrv_status          text,
  hrv_baseline_low    numeric,
  hrv_baseline_high   numeric,
  sleep_duration_sec  int,
  sleep_score         int,
  deep_sleep_sec      int,
  body_battery_max    int,
  body_battery_min    int,
  training_readiness  int,
  stress_avg          int,
  weight_kg           numeric,
  vo2max_run          numeric,
  vo2max_bike         numeric,
  garmin_training_status text,
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
