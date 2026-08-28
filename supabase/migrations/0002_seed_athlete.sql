-- Fila única de l'atleta amb les zones de la spec §4.
-- Llindars (max_hr, ftp, css, ritme llindar) deliberadament NULL: encara no hi ha
-- cap mesura real (spec §6, "Quan no hi ha llindars"). Les zones són fraccions de
-- VELOCITAT sobre la referència, no de ritme (spec §4, convenció crítica).
insert into athlete (id, name, zones) values (
  1,
  'Roger',
  '{
    "run":  {"basis": "threshold_pace", "z1": [0, 0.78], "z2": [0.78, 0.88],
             "z3": [0.88, 0.95], "z4": [0.95, 1.02], "z5": [1.02, 1.20]},
    "bike": {"basis": "ftp",  "z1": [0, 0.55], "z2": [0.55, 0.75],
             "z3": [0.75, 0.90], "z4": [0.90, 1.05], "z5": [1.05, 1.50]},
    "swim": {"basis": "css",  "z1": [0, 0.85], "z2": [0.85, 0.92],
             "z3": [0.92, 0.98], "z4": [0.98, 1.03], "z5": [1.03, 1.15]},
    "hr":   {"basis": "max_hr", "z1": [0, 0.68], "z2": [0.68, 0.78],
             "z3": [0.78, 0.87], "z4": [0.87, 0.93], "z5": [0.93, 1.00]}
  }'::jsonb
);
