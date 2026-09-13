# App mòbil

Client Expo (React Native + TypeScript, Expo Router) de l'entrenador de triatló.
Descripció del sistema sencer al [README de l'arrel](../README.md).

```bash
npm install
cp .env.example .env     # URL i clau publicable de Supabase
npx expo start           # obrir amb Expo Go al mòbil
npx jest                 # tests
```

- `app/(tabs)/`: pestanyes Avui, Setmana, Forma, Objectius.
- `app/activitat.tsx`: detall d'una activitat (RPE, sensacions, notes).
- `lib/api.ts`: totes les consultes a Supabase; `lib/format.ts`: formats de ritme, durada, segments.
- `components/`: peces reutilitzades per les pantalles, amb els seus tests al costat.
