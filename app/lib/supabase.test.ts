jest.mock('@react-native-async-storage/async-storage', () => ({}));

const mockCreateClient = jest.fn(() => ({ marker: 'client' }));
jest.mock('@supabase/supabase-js', () => ({ createClient: mockCreateClient }));

const URL = 'https://example.supabase.co';
const KEY = 'sb_publishable_test';

beforeEach(() => {
  jest.resetModules();
  mockCreateClient.mockClear();
  process.env.EXPO_PUBLIC_SUPABASE_URL = URL;
  process.env.EXPO_PUBLIC_SUPABASE_KEY = KEY;
});

test("peta a l'arrencada si falta la configuració (millor que fallar en silenci)", () => {
  delete process.env.EXPO_PUBLIC_SUPABASE_URL;
  expect(() => require('./supabase')).toThrow(/EXPO_PUBLIC_SUPABASE_URL/);
});

test("crea el client amb la URL i la clau de l'entorn, amb sessió persistent", () => {
  const { supabase } = require('./supabase');
  expect(supabase).toEqual({ marker: 'client' });
  const [url, key, opts] = mockCreateClient.mock.calls[0];
  expect(url).toBe(URL);
  expect(key).toBe(KEY);
  expect(opts.auth.persistSession).toBe(true);
  expect(opts.auth.detectSessionInUrl).toBe(false);
});
