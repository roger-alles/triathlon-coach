# Entrenador de triatló

Entrenador personal automàtic per a un sol atleta. Cada matí llegeix les dades
de Garmin (entrenaments, son, FC de repòs, estrès), les creua amb un pla
d'entrenament estructurat i un coach basat en Claude escriu l'informe del dia:
semàfor, què toca, què canviaria i per què. L'atleta ho veu en una app mòbil.

Objectiu actual: Artiem Half Menorca Short (Fornells, 27/09/2026). Fins a la
cursa el coach corre en mode *dry-run*: proposa, no toca el pla.

## Com està muntat

```
Garmin Connect ──sync──▶ Postgres (Supabase) ◀──── app mòbil (Expo, iOS/Android)
                              │        ▲
                        pla + dades    │ informe validat
                              ▼        │
                        coach (Claude) ─┘   14 regles dures, 3 intents
```

| Peça | Carpeta | Què fa |
|---|---|---|
| Ingesta | `ingest/` | Baixa activitats i mètriques diàries de Garmin, calcula càrrega (TRIMP) i forma (CTL/ATL/TSB), lliga cada activitat amb la sessió del pla |
| Pla | `seeds/`, `coach/plan_loader.py` | El pla és dades, no text: blocs, sessions amb estructura (escalfament, sèries, objectius de ritme), prioritat, tests |
| Coach | `coach/` | Construeix el context, crida l'API de Claude amb sortida estructurada (`contracts/`), valida el resultat amb 14 regles (`rules.py`) i el desa. Prompts versionats a `coach/prompts/` |
| Base de dades | `supabase/migrations/`, `migrate.py` | Migracions SQL numerades, aplicades amb un script propi. RLS: l'app només llegeix i escriu el que li toca |
| App | `app/` | Expo Router + TypeScript. Pestanyes Avui / Setmana / Forma / Objectius, login, detall d'activitat amb RPE i notes |
| Servidor MCP | `mcp_server/` | Exposa les dades a assistents (setmana, forma, compliment) |
| Operació | `scripts/`, `docs/server.md` | Feines de cron al servidor (matí, sync horari, vespre, setmanal, decisions), còpia de seguretat, exportació de sessions al rellotge |

## Per on mirar

1. `SPEC-entrenador-triatlo.md`: què és, model de dades, les 14 regles del coach, fases.
2. `docs/decisions.md`: per què cada cosa és com és (decisions amb data).
3. `coach/run.py` i `coach/rules.py`: el cor. Generació de l'informe i validació.
4. `app/app/(tabs)/index.tsx`: la pantalla Avui.
5. `docs/post-cursa-design.md`: cap on va després del 27/09 (planificació rodant, aprovació de propostes des de l'app).

## Executar

Cal Python 3.12, Node 20+ i un `.env` (vegeu `.env.example` i `app/.env.example`).
Sense les claus (Supabase, Garmin, Anthropic) no arrenca res: és un sistema
d'un sol usuari amb dades reals.

```bash
make test        # 171 tests Python (ingesta, regles, coach, migracions)
cd app && npx jest   # 89 tests de l'app
make sync        # ingesta Garmin -> BD
make report      # últim informe del coach
```

## Estat

- Ingesta, pla, coach diari/setmanal, validador i app: en producció al servidor
  des del 07/09/2026, sense dependre de cap màquina personal.
- Coach en *dry-run* fins a la cursa. Infraestructura per aplicar propostes amb
  seguretat (transacció única, efectes registrats, desfer) desplegada i inert.
- Pendent: registrar des de l'app sessions de dies anteriors o multisport (avui
  només les del dia, via "Ho he fet"), objectius des de l'app, planificació
  rodant post-cursa.
