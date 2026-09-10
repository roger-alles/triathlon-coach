-- L'atleta marca les tasques de logística com a fetes des de l'app (pestanya
-- Fornells). Només la columna done: títol, data i blocking són del pla (seed).
grant update (done) on logistics_task to authenticated;

create policy athlete_tick_logistics on logistics_task
  for update to authenticated using (true) with check (true);
