-- S3: el coach proposa blocs (macro) i l'atleta els aprova des de l'app.
-- Els blocs guanyen estat (mai s'esborren: hi pengen sessions), els informes
-- poden ser 'macro', els efectes registren canvis de bloc (per desfer), i
-- l'atleta pot demanar coses al coach (athlete_request; ara: regenerate_macro).

alter table plan_block
  add column status text not null default 'active'
    check (status in ('active', 'proposed', 'cancelled')),
  add column created_by text not null default 'seed';

alter table coach_report drop constraint coach_report_report_type_check;
alter table coach_report add constraint coach_report_report_type_check
  check (report_type in ('daily', 'weekly', 'replan', 'answer', 'macro'));

alter table coach_report_effect drop constraint coach_report_effect_kind_check;
alter table coach_report_effect add constraint coach_report_effect_kind_check
  check (kind in ('created', 'superseded', 'cancelled', 'moved',
                  'block_created', 'block_cancelled', 'block_modified'));
alter table coach_report_effect
  add column block_id bigint references plan_block(id),
  add column prev_values jsonb;   -- camps previs d'un block_modified

-- Peticions de l'atleta al coach (bústia). L'app hi insereix; el servidor
-- (cron decisions) les processa i hi enllaça l'informe resultant.
create table athlete_request (
  id          bigserial primary key,
  created_at  timestamptz default now(),
  kind        text not null check (kind in
                ('unavailable', 'no_sport', 'discomfort', 'new_goal', 'free_text', 'regenerate_macro')),
  payload     jsonb not null default '{}'::jsonb,
  status      text not null default 'pending'
                check (status in ('pending', 'processing', 'answered', 'failed')),
  report_id   bigint references coach_report(id),
  error       text
);
create index on athlete_request (status, created_at);

alter table athlete_request enable row level security;
grant select on athlete_request to authenticated;
grant insert (kind, payload) on athlete_request to authenticated;
grant usage on sequence athlete_request_id_seq to authenticated;
create policy athlete_read on athlete_request for select to authenticated using (true);
create policy athlete_ask on athlete_request for insert to authenticated with check (true);
