-- F5-P1: RLS abans que cap clau viatgi dins l'app mòbil (spec §8).
-- L'anon key és pública per construcció; la defensa és de la BD, no de la clau.
-- Model: usuari únic (Roger, via Supabase Auth) + signups desactivats al dashboard.
--   anon           -> zero accés (ni select)
--   authenticated  -> lectura de tot; escriptura NOMÉS de les columnes
--                     subjectives d'activity (RPE, sensacions, notes)
-- El sync/coach del Mac connecta com a postgres (propietari de les taules):
-- el propietari no passa per RLS, per això segueix funcionant sense canvis.

alter table activity          enable row level security;
alter table athlete           enable row level security;
alter table coach_report      enable row level security;
alter table daily_metric      enable row level security;
alter table goal              enable row level security;
alter table load_daily        enable row level security;
alter table logistics_task    enable row level security;
alter table plan_block        enable row level security;
alter table plan_session      enable row level security;
alter table schema_migrations enable row level security;
alter table test_result       enable row level security;
alter table threshold_history enable row level security;

-- Supabase concedeix privilegis amplis a anon/authenticated per defecte:
-- es retiren i es reconcedeixen només els necessaris.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

grant select on activity, athlete, coach_report, daily_metric, goal,
                load_daily, logistics_task, plan_block, plan_session,
                test_result, threshold_history
  to authenticated;
-- schema_migrations queda sense cap grant: és intern del runner.

grant update (perceived_effort, feeling, athlete_notes) on activity
  to authenticated;

-- Sense policy no hi ha files visibles encara que hi hagi grant;
-- amb usuari únic i signups tancats, el rol authenticated ÉS en Roger.
create policy athlete_read on activity          for select to authenticated using (true);
create policy athlete_read on athlete           for select to authenticated using (true);
create policy athlete_read on coach_report      for select to authenticated using (true);
create policy athlete_read on daily_metric      for select to authenticated using (true);
create policy athlete_read on goal              for select to authenticated using (true);
create policy athlete_read on load_daily        for select to authenticated using (true);
create policy athlete_read on logistics_task    for select to authenticated using (true);
create policy athlete_read on plan_block        for select to authenticated using (true);
create policy athlete_read on plan_session      for select to authenticated using (true);
create policy athlete_read on test_result       for select to authenticated using (true);
create policy athlete_read on threshold_history for select to authenticated using (true);

create policy athlete_write_subjective on activity
  for update to authenticated using (true) with check (true);
