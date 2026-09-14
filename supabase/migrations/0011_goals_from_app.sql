-- S2: objectius des de l'app. L'atleta pot crear i editar els seus objectius
-- (nom, disciplina, data, prioritat, perfil amb distàncies, notes) i
-- abandonar-ne un (status). Mai esborrar: els blocs i sessions hi pengen.
-- El coach els llegeix tots al snapshot; el macro (S3) els farà servir.

grant insert (name, discipline, event_date, priority, profile, notes)
  on goal to authenticated;
grant update (name, discipline, event_date, priority, profile, notes, status)
  on goal to authenticated;
grant usage on sequence goal_id_seq to authenticated;

create policy athlete_insert_goal on goal
  for insert to authenticated with check (true);
create policy athlete_update_goal on goal
  for update to authenticated using (true) with check (true);
