-- L'atleta pot registrar una sessió feta sense rellotge des de l'app (natació
-- a mar, piscina cronometrada). Només files manuals: id < 0, com les que ja
-- entren a mà. Les files de Garmin (id > 0) continuen sent intocables.
-- El sync horari li posa la càrrega (estimada) i l'estat de la sessió del pla.

grant insert (id, start_time, local_date, sport, sub_sport, duration_sec,
              distance_m, perceived_effort, feeling, athlete_notes,
              plan_session_id, load_estimated, raw)
  on activity to authenticated;

create policy athlete_log_manual on activity
  for insert to authenticated with check (id < 0);
