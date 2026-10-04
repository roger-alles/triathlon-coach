-- L'atleta corregeix les seves activitats des de l'app (detall d'activitat):
--   · assignar-ne una a una sessió del pla d'un altre dia (dies intercanviats),
--     també les de Garmin, o marcar-la "fora de pla";
--   · esborrar una entrada manual feta per error.
-- linked_by_athlete: el vincle (o la seva absència) l'ha decidit ell; el
-- vinculador (ingest/link.py) no el toca. Columna pròpia i no dins de raw,
-- perquè el sync de Garmin reescriu raw sencer.

alter table activity add column linked_by_athlete boolean not null default false;

-- la política d'update (athlete_write_subjective, 0005) ja existeix; només calen les columnes
grant update (plan_session_id, linked_by_athlete) on activity to authenticated;

-- esborrar: només files manuals (id < 0). Les de Garmin són intocables.
grant delete on activity to authenticated;
create policy athlete_delete_manual on activity
  for delete to authenticated using (id < 0);
