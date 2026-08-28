-- F3: el pla com a dades (spec §3). coach_report arriba amb l'entrenador (F4).

create table goal (
  id            bigserial primary key,
  name          text not null,
  discipline    text not null check (discipline in
                  ('triathlon','run','bike','swim','ultra_endurance')),
  event_date    date,
  priority      char(1) not null check (priority in ('A','B','C')),
  profile       jsonb,        -- distàncies, temps objectiu, èmfasi, protocol de cursa
  status        text not null default 'active'
                  check (status in ('active','completed','abandoned')),
  notes         text
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
  intent        text,               -- què busca el bloc, en una frase
  target_weekly_load numeric,
  target_weekly_hours numeric,      -- l'atleta pensa en hores
  fallback      text,               -- "si la setmana se't torça, salva X"
  return_from_layoff boolean default false  -- desactiva R1 i R6 (spec §8)
);

-- La unitat central: una sessió planificada.
create table plan_session (
  id                bigserial primary key,
  block_id          bigint references plan_block(id) on delete cascade,
  goal_id           bigint references goal(id),
  local_date        date not null,
  sport             text not null check (sport in
                      ('swim','bike','run','strength','brick','multisport','rest')),
  session_type      text not null,
  title             text not null,
  structure         jsonb not null,    -- contracte spec §6
  duration_sec_target int,
  distance_m_target numeric,
  planned_load      numeric,
  priority          text not null default 'support'
                      check (priority in ('key','support','optional')),
  status            text not null default 'planned'
                      check (status in ('planned','completed','partial','missed','moved','cancelled')),
  rationale         text,
  is_test           boolean default false,
  test_spec         jsonb,
  rehearses_goal    boolean default false,   -- assaig de la prova: exempta de R9
  is_goal_event     boolean default false,   -- la cursa
  chained_after     bigint references plan_session(id),  -- brick rere la bici del dia
  transition_practice text[],
  created_by        text not null default 'coach' check (created_by in ('coach','athlete')),
  version           int not null default 1,
  superseded_by     bigint references plan_session(id),
  created_at        timestamptz default now()
);
create index on plan_session (local_date);
-- Com a molt una sessió `key` viva per esport i dia (spec §3).
create unique index on plan_session (local_date, sport)
  where priority = 'key' and superseded_by is null
    and status in ('planned','completed','partial');

-- Resultats de les sessions de test, per veure si la feina funciona.
create table test_result (
  id              bigserial primary key,
  plan_session_id bigint references plan_session(id),
  activity_id     bigint references activity(id),
  local_date      date not null,
  metric          text not null,
  values          jsonb not null,
  compared_with   bigint references test_result(id),
  delta           jsonb
);

-- Logística lligada a un objectiu: no és entrenament, però no fer-ho costa la cursa.
create table logistics_task (
  id          bigserial primary key,
  goal_id     bigint not null references goal(id) on delete cascade,
  local_date  date not null,
  title       text not null,
  detail      text,
  blocking    boolean default false,
  done        boolean default false
);

-- La FK diferida de la spec §3: activity i plan_session es referencien mútuament.
alter table activity add constraint activity_plan_session_fk
  foreign key (plan_session_id) references plan_session(id) on delete set null;
