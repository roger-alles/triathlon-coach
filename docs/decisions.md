# Decisions del projecte

> Per què s'ha fet cada cosa així (spec §11). Una entrada per decisió, amb data.

## 2026-08-27 — F0 com a script solt a l'arrel

`f0_explore.py` viu a l'arrel del repositori, no dins d'`ingest/`. La F0 és exploratòria:
el seu codi es llença quan la F1 escrigui la ingesta de veritat darrere del protocol
`ActivityProvider`. Posar-lo a l'arrel deixa clar que és temporal.

## 2026-08-27 — Repositori propi, separat del workspace

`projects/` està gitignorat pel workspace de PM, així que aquest directori és un
repositori git independent. Identitat git: la global de la màquina (Roger).

## 2026-08-27 — `data/` fora de git

Les respostes crues de Garmin són dades de salut personals (spec §13). Es queden
al disc local, mai al repositori.
