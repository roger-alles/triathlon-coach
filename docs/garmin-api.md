# Garmin Connect API — què dona de veritat aquest compte

> F0, 27/08/2026 · `garminconnect==0.3.11` · dades reals de 90 dies (2026-05-29 → 2026-08-27)
> descarregades a `data/raw/`. 105 mètodes `get_*` disponibles: llista completa a
> `data/raw/meta/available_methods.json`.

## Login

`Garmin(email, password, prompt_mfa=...).login(tokenstore)` — un sol punt d'entrada:

- Si el tokenstore (`~/.garminconnect`) té tokens, entra sense contrasenya.
- Si no, fa login amb credencials i **desa els tokens ell mateix** al final (no cal cap
  `dump` manual; l'atribut `.garth` de versions antigues ja no existeix).
- El login amb credencials prova estratègies en cadena (`mobile+cffi`, `mobile+requests`, …).
  Un **429** vol dir IP bloquejada temporalment per massa intents: esperar 30–60 min,
  no reintentar en bucle.

## ⚠️ El que aquest dispositiu NO dona

Comprovat contra 91 dies reals — tots buits o null:

| Mètrica | Endpoint | Resultat | Impacte a la spec |
|---|---|---|---|
| HRV nocturn | `get_hrv_data(date)` | `[]` els 91 dies | `daily_metric.hrv_*` sempre NULL. **R11 no pot usar `hrv_status`** |
| Training Readiness | `get_training_readiness(date)` | `[]` els 91 dies | `daily_metric.training_readiness` NULL. **R11 tampoc té aquesta via** |
| Sleep score | dins `get_sleep_data` | sense `sleepScores` | `daily_metric.sleep_score` NULL |
| VO₂màx | `get_training_status(date)` | `mostRecentVO2Max: null` | `daily_metric.vo2max_*` NULL |
| Training status | `get_training_status(date)` | `mostRecentTrainingStatus: null` | `daily_metric.garmin_training_status` NULL |
| Training load / TE | detall d'activitat | cap camp `*load*` ni `*effect*` | `activity.garmin_training_load` NULL → **la càrrega es calcula per TRIMP** (spec §5, mètode 3) |

Conseqüència per a la F4: els senyals de recuperació del coach seran **RHR, son
(durada + fases), body battery i estrès** — no HRV ni readiness. R11 s'haurà de
reformular sobre aquests senyals a la F3 (decisió pendent, apuntada per a llavors).

## El que SÍ dona

### `get_activities_by_date(start, end)` → llista d'activitats

Camps útils per a `activity` (spec §3): `activityId`, `startTimeLocal`, `activityType.typeKey`
(`running`, `cycling`, `lap_swimming`, `walking`, `other`), `duration`, `movingDuration`,
`distance` (m), `elevationGain`, `averageHR`, `maxHR`, `averageSpeed` (m/s), `calories`,
`lapCount`, `locationName`.

**`hrTimeInZone_1` … `hrTimeInZone_5`** (segons per zona de FC) — la base del càlcul
TRIMP de càrrega. Present a totes les activitats amb FC.

90 dies reals: 23 running · 12 cycling · 1 lap_swimming · 2 walking · 10 other.

### Detall d'activitat (mostres a `data/raw/activity_detail/`)

- `get_activity(id)` — resum estès.
- `get_activity_details(id)` — sèries temporals (FC, ritme, GPS…). Voluminós; per a F1 només si cal.
- `get_activity_splits(id)` — parcials/laps: per validar sèries (p. ex. 5×1000).
- `get_activity_hr_in_timezones(id)` — temps per zona de FC, versió detallada.

### `get_sleep_data(date)` → son

`dailySleepDTO`: `sleepTimeSeconds`, `deepSleepSeconds`, `lightSleepSeconds`,
`remSleepSeconds`, `awakeSleepSeconds`, `napTimeSeconds`, timestamps d'inici/fi.
També `restingHeartRate` i `bodyBatteryChange` durant la nit.

### `get_rhr_day(date)` → FC en repòs

`allMetrics.metricsMap.WELLNESS_RESTING_HEART_RATE[0].value`. Contrastat: 50 ppm el 26/08.

### `get_stats(date)` → resum diari (el més dens)

`restingHeartRate`, `lastSevenDaysAvgRestingHeartRate`, `bodyBatteryHighestValue`/
`LowestValue`, `averageStressLevel`, `maxStressLevel`, `totalSteps`, `totalKilocalories`,
`sleepingSeconds`, `moderateIntensityMinutes`, `vigorousIntensityMinutes`.

### `get_body_battery(date)` → body battery

Llista amb `charged`, `drained` i la sèrie del dia (`bodyBatteryValuesArray`).

## Per a fases futures (no baixat a F0)

- `get_body_composition` / `get_daily_weigh_ins` — pes per a `daily_metric.weight_kg` (F1).
- `get_heart_rate_zones` — zones de FC configurades al compte.
- `get_all_day_stress` / `get_stress_data` — sèrie d'estrès del dia.
- `get_race_predictions`, `get_endurance_score`, `get_hill_score`, `get_lactate_threshold` —
  per explorar; probablement buits en aquest dispositiu com la resta de mètriques premium.
- `get_workouts`, `upload_workout`, `schedule_workout` — enviar entrenaments al rellotge (F6).

## Notes de plausibilitat (contrastar amb l'app)

- Última activitat: "Town Cycling", 27/08 09:33, 67,8 km, 154 min.
- RHR 26/08: 50 ppm · Son 26/08: 8,08 h.
- FC màxima observada en activitat: 198 ppm (no és un test de FC màx., però és un mínim
  real per al camp `athlete.max_hr` quan es configuri).
