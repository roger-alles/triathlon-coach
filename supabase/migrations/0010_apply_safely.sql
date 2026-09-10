-- S1a: aplicar canvis del coach amb seguretat (docs/post-cursa-design.md).
-- Inert mentre coach_apply_mode sigui 'dry_run' (valor inicial).

-- Configuració editable des de l'app. Valors validats per clau.
create table app_setting (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz default now(),
  check (key <> 'coach_apply_mode' or value in ('"dry_run"'::jsonb, '"hybrid"'::jsonb))
);
insert into app_setting (key, value) values ('coach_apply_mode', '"dry_run"');

-- Estat de la proposta d'un informe i per què s'ha classificat com a auto o proposta.
alter table coach_report
  add column proposal_status text not null default 'none'
    check (proposal_status in ('none','auto_applied','proposed','applied','discarded','undone','failed')),
  add column scope text not null default 'sessions'
    check (scope in ('sessions','week','macro')),
  add column classification jsonb;

-- Decisions de l'atleta sobre una proposta (Aplica / Descarta / Desfés). L'app
-- hi insereix; coach.decisions les processa.
create table coach_decision (
  id         bigserial primary key,
  created_at timestamptz default now(),
  report_id  bigint not null references coach_report(id),
  decision   text not null check (decision in ('apply','discard','undo')),
  status     text not null default 'pending'
               check (status in ('pending','processing','done','failed')),
  error      text
);

-- Rastre de cada mutació que fa un informe al pla: sense això no hi ha Desfés.
create table coach_report_effect (
  id                 bigserial primary key,
  report_id          bigint not null references coach_report(id),
  decision_id        bigint references coach_decision(id),
  kind               text not null check (kind in ('created','superseded','cancelled','moved')),
  session_id         bigint references plan_session(id),
  new_session_id     bigint references plan_session(id),
  prev_status        text,
  prev_superseded_by bigint
);
create index on coach_report_effect (report_id);

-- Permisos (post-0007 cap taula nova en té).
alter table app_setting enable row level security;
alter table coach_decision enable row level security;
alter table coach_report_effect enable row level security;
grant select on app_setting, coach_decision, coach_report_effect to authenticated;
grant update (value) on app_setting to authenticated;
grant insert (report_id, decision) on coach_decision to authenticated;
grant usage on sequence coach_decision_id_seq to authenticated;
create policy athlete_read on app_setting for select to authenticated using (true);
create policy athlete_set on app_setting for update to authenticated using (true) with check (true);
create policy athlete_read on coach_decision for select to authenticated using (true);
create policy athlete_decide on coach_decision for insert to authenticated with check (true);
create policy athlete_read on coach_report_effect for select to authenticated using (true);

-- 0007 només va revocar anon: authenticated encara tenia update/references.
revoke update, references on athlete_answer from authenticated;
