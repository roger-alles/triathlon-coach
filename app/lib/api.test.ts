jest.mock('./supabase', () => ({ supabase: { from: jest.fn() } }));

import { supabase } from './supabase';
import { getLatestDailyReport, getSessionsForDay, localDateISO } from './api';

const mockFrom = supabase.from as jest.Mock;

// Builder encadenable de PostgREST: tots els mètodes retornen el mateix
// objecte; el resultat final es resol via maybeSingle() o await del builder.
function chainResolving(result: unknown, terminal?: string) {
  const chain: any = {};
  for (const m of ['select', 'eq', 'is', 'order', 'limit']) chain[m] = jest.fn(() => chain);
  if (terminal) chain[terminal] = jest.fn(async () => result);
  else chain.then = (onOk: (v: unknown) => unknown) => Promise.resolve(result).then(onOk);
  return chain;
}

beforeEach(() => jest.clearAllMocks());

test('localDateISO usa la zona horària local, no UTC', () => {
  expect(localDateISO(new Date(2026, 7, 29, 0, 30))).toBe('2026-08-29');
  expect(localDateISO(new Date(2026, 11, 31, 23, 59))).toBe('2026-12-31');
});

test("l'últim informe daily es tradueix al que la pantalla necessita", async () => {
  const row = {
    created_at: '2026-08-29T07:23:51Z',
    output: {
      summary: 'Rodatge suau en lloc de sèries.',
      rationale: 'El TSB ha caigut…',
      readiness: { verdict: 'amber', confidence: 'medium' },
      questions_for_athlete: ['Com notes les cames?'],
    },
  };
  mockFrom.mockReturnValue(chainResolving({ data: row, error: null }, 'maybeSingle'));

  const report = await getLatestDailyReport();
  expect(mockFrom).toHaveBeenCalledWith('coach_report');
  expect(report).toEqual({
    createdAt: '2026-08-29T07:23:51Z',
    verdict: 'amber',
    summary: 'Rodatge suau en lloc de sèries.',
    rationale: 'El TSB ha caigut…',
    questions: ['Com notes les cames?'],
  });
});

test('sense cap informe encara: null, no error', async () => {
  mockFrom.mockReturnValue(chainResolving({ data: null, error: null }, 'maybeSingle'));
  expect(await getLatestDailyReport()).toBeNull();
});

test('les sessions del dia només inclouen la versió vigent (superseded_by null)', async () => {
  const rows = [{ id: 1, sport: 'run', title: 'Primeres sèries' }];
  const chain = chainResolving({ data: rows, error: null });
  mockFrom.mockReturnValue(chain);

  const sessions = await getSessionsForDay('2026-08-29');
  expect(mockFrom).toHaveBeenCalledWith('plan_session');
  expect(chain.eq).toHaveBeenCalledWith('local_date', '2026-08-29');
  expect(chain.is).toHaveBeenCalledWith('superseded_by', null);
  expect(sessions).toEqual(rows);
});

test('els errors de la BD no es traguen en silenci', async () => {
  mockFrom.mockReturnValue(chainResolving({ data: null, error: { message: 'permission denied' } }, 'maybeSingle'));
  await expect(getLatestDailyReport()).rejects.toThrow('permission denied');
});
