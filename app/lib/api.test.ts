jest.mock('./supabase', () => ({ supabase: { from: jest.fn() } }));

import { supabase } from './supabase';
import { getLatestDailyReport, getSessionsForDay, localDateISO, logManualActivity } from './api';

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

test('la setmana comença en dilluns, sigui quin sigui el dia', () => {
  const { weekDaysISO } = require('./api');
  // dissabte 29/08/2026 -> dilluns 24 a diumenge 30
  const days = weekDaysISO(new Date(2026, 7, 29));
  expect(days[0]).toBe('2026-08-24');
  expect(days[6]).toBe('2026-08-30');
  expect(days).toHaveLength(7);
  // un dilluns es queda com a primer dia
  expect(weekDaysISO(new Date(2026, 7, 24))[0]).toBe('2026-08-24');
  // un diumenge pertany a la setmana que va començar 6 dies enrere
  expect(weekDaysISO(new Date(2026, 7, 30))[0]).toBe('2026-08-24');
});

test('localDateISO usa la zona horària local, no UTC', () => {
  expect(localDateISO(new Date(2026, 7, 29, 0, 30))).toBe('2026-08-29');
  expect(localDateISO(new Date(2026, 11, 31, 23, 59))).toBe('2026-12-31');
});

test("l'últim informe daily es tradueix al que la pantalla necessita", async () => {
  const row = {
    id: 7,
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
    id: 7,
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

test('sessions i activitats de la setmana es demanen pel rang de dates', async () => {
  const { getSessionsForRange, getActivitiesForRange } = require('./api');
  const chain = chainResolving({ data: [], error: null });
  chain.gte = jest.fn(() => chain);
  chain.lte = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);

  await getSessionsForRange('2026-08-24', '2026-08-30');
  expect(chain.gte).toHaveBeenCalledWith('local_date', '2026-08-24');
  expect(chain.lte).toHaveBeenCalledWith('local_date', '2026-08-30');
  expect(chain.is).toHaveBeenCalledWith('superseded_by', null);

  await getActivitiesForRange('2026-08-24', '2026-08-30');
  expect(mockFrom).toHaveBeenLastCalledWith('activity');
});

test('la corba de forma converteix els numeric (que arriben com a strings)', async () => {
  const { getFormSeries } = require('./api');
  const rows = [
    { local_date: '2026-08-28', load: '20.8', ctl: '45.405', atl: '69.9728', tsb: '-32.1632' },
    { local_date: '2026-08-29', load: '0', ctl: '44.3239', atl: '59.9767', tsb: '-24.5678' },
  ];
  const chain = chainResolving({ data: rows, error: null });
  chain.gte = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);

  const series = await getFormSeries('2026-08-01');
  expect(mockFrom).toHaveBeenCalledWith('load_daily');
  expect(series[0]).toEqual({ local_date: '2026-08-28', load: 20.8, ctl: 45.4, atl: 70, tsb: -32.2 });
  expect(series[1].tsb).toBe(-24.6);
});

test("el detall d'activitat es demana per id", async () => {
  const { getActivity } = require('./api');
  const row = { id: 3, sport: 'bike', duration_sec: 9237 };
  const chain = chainResolving({ data: row, error: null }, 'maybeSingle');
  mockFrom.mockReturnValue(chain);

  expect(await getActivity(3)).toEqual(row);
  expect(mockFrom).toHaveBeenCalledWith('activity');
  expect(chain.eq).toHaveBeenCalledWith('id', 3);
});

test("l'actualització subjectiva envia NOMÉS les tres columnes permeses pel pany", async () => {
  const { updateActivitySubjective } = require('./api');
  const chain = chainResolving({ data: null, error: null });
  chain.update = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);

  await updateActivitySubjective(3, { perceived_effort: 7, feeling: 4, athlete_notes: 'genoll bé' });
  expect(chain.update).toHaveBeenCalledWith({
    perceived_effort: 7,
    feeling: 4,
    athlete_notes: 'genoll bé',
  });
  expect(chain.eq).toHaveBeenCalledWith('id', 3);
});

test("l'actualització subjectiva propaga l'error de la BD (p. ex. RLS)", async () => {
  const { updateActivitySubjective } = require('./api');
  const chain = chainResolving({ data: null, error: { message: 'permission denied' } });
  chain.update = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);

  await expect(updateActivitySubjective(3, { perceived_effort: 5 })).rejects.toThrow('permission denied');
});

test("l'objectiu actiu i la seva logística es llegeixen sencers", async () => {
  const { getActiveGoal, getLogistics } = require('./api');
  const goal = { id: 2, name: 'Fornells', event_date: '2026-09-27', profile: { location: 'Menorca' } };
  const chain = chainResolving({ data: goal, error: null }, 'maybeSingle');
  mockFrom.mockReturnValue(chain);
  expect(await getActiveGoal()).toEqual(goal);
  expect(chain.eq).toHaveBeenCalledWith('status', 'active');

  const rows = [{ id: 1, local_date: '2026-09-24', title: 'Revisió', detail: null, blocking: true, done: false }];
  const chain2 = chainResolving({ data: rows, error: null });
  mockFrom.mockReturnValue(chain2);
  expect(await getLogistics(2)).toEqual(rows);
  expect(chain2.eq).toHaveBeenCalledWith('goal_id', 2);
});

test("respondre una pregunta del coach fa un INSERT (mai update: és un quadern)", async () => {
  const { sendAnswer } = require('./api');
  const chain = chainResolving({ data: null, error: null });
  chain.insert = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);

  await sendAnswer(7, 'Com notes les cames?', 'Bé, sense agulletes');
  expect(mockFrom).toHaveBeenCalledWith('athlete_answer');
  expect(chain.insert).toHaveBeenCalledWith({
    report_id: 7,
    question: 'Com notes les cames?',
    answer: 'Bé, sense agulletes',
  });
});

test("les respostes ja donades d'un informe es poden recuperar", async () => {
  const { getAnswers } = require('./api');
  const rows = [{ id: 1, question: 'p?', answer: 'r' }];
  const chain = chainResolving({ data: rows, error: null });
  mockFrom.mockReturnValue(chain);

  expect(await getAnswers(7)).toEqual(rows);
  expect(chain.eq).toHaveBeenCalledWith('report_id', 7);
});

test('els errors de la BD no es traguen en silenci', async () => {
  mockFrom.mockReturnValue(chainResolving({ data: null, error: { message: 'permission denied' } }, 'maybeSingle'));
  await expect(getLatestDailyReport()).rejects.toThrow('permission denied');
});

test("registrar una sessió sense rellotge: fila manual amb id negatiu, mai una fila de Garmin", async () => {
  const chain = chainResolving({ data: null, error: null });
  chain.insert = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  const now = new Date(2026, 8, 10, 18, 42);
  await logManualActivity(
    {
      local_date: '2026-09-10',
      sport: 'swim',
      sub_sport: 'lap_swimming',
      duration_sec: 2400,
      distance_m: 1600,
      perceived_effort: 6,
      athlete_notes: '3×400 a 2:16',
      plan_session_id: 43,
    },
    now
  );
  expect(mockFrom).toHaveBeenCalledWith('activity');
  const row = chain.insert.mock.calls[0][0];
  expect(row.id).toBe(-202609101842);
  expect(row.id).toBeLessThan(0);
  expect(row.local_date).toBe('2026-09-10');
  expect(row.sport).toBe('swim');
  expect(row.sub_sport).toBe('lap_swimming');
  expect(row.duration_sec).toBe(2400);
  expect(row.distance_m).toBe(1600);
  expect(row.perceived_effort).toBe(6);
  expect(row.plan_session_id).toBe(43);
  expect(row.load_estimated).toBe(true);
  expect(row.raw).toEqual({ manual: true, source: 'app', plan_session_id: 43 });
  // l'activitat ha acabat ara: comença durada enrere
  expect(new Date(row.start_time).getTime()).toBe(now.getTime() - 2400 * 1000);
});

test('registrar una sessió: els errors de la BD pugen', async () => {
  const chain = chainResolving({ data: null, error: { message: 'new row violates row-level security policy' } });
  chain.insert = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  await expect(
    logManualActivity({ local_date: '2026-09-10', sport: 'run', duration_sec: 600 })
  ).rejects.toThrow('row-level security');
});
