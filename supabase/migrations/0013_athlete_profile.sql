-- S2b: el que l'atleta declara de si mateix (dia de descans fix, sostre
-- d'hores, dies disponibles, piscina, salut, marques conegudes, notes) deixa
-- de viure dins del perfil de l'objectiu Fornells (goal.profile.athlete_context,
-- que desapareixeria del context del coach en completar la cursa) i passa a
-- la fila de l'atleta, editable des de l'app (pestanya Jo).

alter table athlete add column profile jsonb not null default '{}'::jsonb;

update athlete
   set profile = coalesce((select profile->'athlete_context' from goal
                           where profile ? 'athlete_context' order by id limit 1),
                          '{}'::jsonb)
 where id = 1;

update goal set profile = profile - 'athlete_context' where profile ? 'athlete_context';

-- l'app pot escriure el perfil (només aquesta columna); llegir ja podia (0005)
grant update (profile) on athlete to authenticated;
create policy athlete_update_profile on athlete
  for update to authenticated using (true) with check (true);
