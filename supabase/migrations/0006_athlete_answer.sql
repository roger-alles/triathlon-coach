-- F6-P1: respostes de l'atleta a les preguntes del coach, des de l'app.
-- El coach les llegeix al snapshot del cicle següent (coach/context.py).

create table athlete_answer (
  id          bigserial primary key,
  created_at  timestamptz default now(),
  report_id   bigint references coach_report(id),
  question    text not null,
  answer      text not null
);
create index on athlete_answer (created_at);

alter table athlete_answer enable row level security;

-- L'app pot llegir i AFEGIR respostes; mai modificar-les ni esborrar-les
-- (són testimoni del que es va dir — com un quadern d'entrenament).
grant select, insert on athlete_answer to authenticated;
grant usage on sequence athlete_answer_id_seq to authenticated;

create policy athlete_read on athlete_answer
  for select to authenticated using (true);
create policy athlete_write on athlete_answer
  for insert to authenticated with check (true);
