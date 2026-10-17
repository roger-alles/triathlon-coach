jest.mock('@react-native-async-storage/async-storage', () => ({}));

const mockCreateClient = jest.fn((..._args: unknown[]) => ({ marker: 'client' }));
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
  const [url, key, opts] = mockCreateClient.mock.calls[0] as [string, string, any];
  expect(url).toBe(URL);
  expect(key).toBe(KEY);
  expect(opts.auth.persistSession).toBe(true);
  expect(opts.auth.detectSessionInUrl).toBe(false);
});

describe('fetchRetryingAuth', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
    jest.useRealTimers();
  });

  const response = (status: number) => ({ status }) as Response;

  test('una resposta normal passa sense reintentar', async () => {
    const { fetchRetryingAuth } = require('./supabase');
    globalThis.fetch = jest.fn().mockResolvedValue(response(200));
    await expect(fetchRetryingAuth('https://x/rest/v1/coach_report')).resolves.toEqual(response(200));
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  test('un 401 ("JWT issued at future" en tornar de segon pla) es repeteix un cop, uns segons després', async () => {
    jest.useFakeTimers();
    const { fetchRetryingAuth, AUTH_RETRY_DELAY_MS } = require('./supabase');
    globalThis.fetch = jest.fn().mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(200));
    const init = { headers: { Authorization: 'Bearer t' } };

    const pending = fetchRetryingAuth('https://x/rest/v1/coach_report', init);
    await jest.advanceTimersByTimeAsync(AUTH_RETRY_DELAY_MS - 1);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1); // encara esperant
    await jest.advanceTimersByTimeAsync(1);

    await expect(pending).resolves.toEqual(response(200));
    expect(globalThis.fetch).toHaveBeenNthCalledWith(2, 'https://x/rest/v1/coach_report', init);
  });

  test('si el segon intent també és 401, retorna aquest error (no reintenta per sempre)', async () => {
    jest.useFakeTimers();
    const { fetchRetryingAuth, AUTH_RETRY_DELAY_MS } = require('./supabase');
    globalThis.fetch = jest.fn().mockResolvedValue(response(401));
    const pending = fetchRetryingAuth('https://x/rest/v1/coach_report');
    await jest.advanceTimersByTimeAsync(AUTH_RETRY_DELAY_MS);
    await expect(pending).resolves.toEqual(response(401));
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  test('el client fa servir aquest fetch', () => {
    const { fetchRetryingAuth } = require('./supabase');
    const opts = mockCreateClient.mock.calls[0][2] as any;
    expect(opts.global.fetch).toBe(fetchRetryingAuth);
  });
});

describe('renovació de la sessió amb l\'app en primer o segon pla', () => {
  test('la reprèn en tornar a primer pla i l\'atura en anar a segon pla', () => {
    const auth = { startAutoRefresh: jest.fn(), stopAutoRefresh: jest.fn() };
    mockCreateClient.mockReturnValueOnce({ marker: 'client', auth } as any);
    const { AppState } = require('react-native');
    const spy = jest.spyOn(AppState, 'addEventListener');
    require('./supabase');

    const onChange = spy.mock.calls[0][1] as (state: string) => void;
    onChange('background');
    expect(auth.stopAutoRefresh).toHaveBeenCalledTimes(1);
    onChange('active');
    expect(auth.startAutoRefresh).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});
