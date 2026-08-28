-- F4: registre de cada intervenció de l'entrenador (spec §3).
-- input_snapshot i output sencers: per reconstruir què sabia el model
-- quan va decidir. Sense això, depurar un coach LLM és impossible.

create table coach_report (
  id            bigserial primary key,
  created_at    timestamptz default now(),
  report_type   text not null check (report_type in
                  ('daily','weekly','replan','answer')),
  window_start  date,
  window_end    date,
  input_snapshot jsonb not null,   -- exactament el que se li va passar al model
  output        jsonb not null,    -- contracte spec §7
  summary_md    text,
  model         text,
  input_tokens  int,
  output_tokens int,
  validation_errors jsonb          -- violacions detectades i corregides, si n'hi va haver
);
create index on coach_report (created_at);
