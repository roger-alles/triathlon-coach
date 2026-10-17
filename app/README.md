# App mòbil

Client Expo (React Native + TypeScript, Expo Router) de l'entrenador de triatló.
Descripció del sistema sencer al [README de l'arrel](../README.md).

```bash
npm install
cp .env.example .env     # URL i clau publicable de Supabase
npx expo start           # provar canvis amb Expo Go, al Mac i a la mateixa WiFi
npx jest                 # tests
```

- `app/(tabs)/`: pestanyes Avui, Setmana, Forma, Objectius.
- `app/activitat.tsx`: detall d'una activitat (RPE, sensacions, notes).
- `lib/api.ts`: totes les consultes a Supabase; `lib/format.ts`: formats de ritme, durada, segments.
- `components/`: peces reutilitzades per les pantalles, amb els seus tests al costat.

L'app que fa servir en Roger és la de TestFlight. Els canvis de JavaScript li
arriben amb EAS Update: el servidor els publica en el desplegament diari
(`../scripts/publish-app.sh`, vegeu `../docs/server.md`).
