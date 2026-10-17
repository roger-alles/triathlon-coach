import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { AppState } from 'react-native';

const url = process.env.EXPO_PUBLIC_SUPABASE_URL;
const key = process.env.EXPO_PUBLIC_SUPABASE_KEY;

if (!url || !key) {
  throw new Error('Falten EXPO_PUBLIC_SUPABASE_URL / EXPO_PUBLIC_SUPABASE_KEY (app/.env)');
}

export const AUTH_RETRY_DELAY_MS = 2000;

// En tornar de segon pla, supabase-js renova el token caducat just abans de la
// petició, i l'API de dades el pot rebutjar uns segons ("JWT issued at future":
// el seu rellotge va una mica per darrere del del servidor d'autenticació). Un
// 401 vol dir que la petició no s'ha executat: es pot repetir sense risc.
export async function fetchRetryingAuth(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init);
  if (response.status !== 401) return response;
  await new Promise((resolve) => setTimeout(resolve, AUTH_RETRY_DELAY_MS));
  return fetch(input, init);
}

export const supabase = createClient(url, key, {
  auth: {
    storage: AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
  global: { fetch: fetchRetryingAuth },
});

// A React Native el temporitzador que renova la sessió s'atura quan iOS congela
// l'app en segon pla: sense això, en tornar-hi les peticions surten amb el token
// caducat. Recepta de la documentació de Supabase per a React Native.
AppState.addEventListener('change', (state) => {
  if (state === 'active') {
    supabase.auth.startAutoRefresh();
  } else {
    supabase.auth.stopAutoRefresh();
  }
});
