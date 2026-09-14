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
    window_start: '2026-08-29',
    output: {
      summary: 'Rodatge suau en lloc de sèries.',
      rationale: 'El TSB ha caigut…',
      readiness: { verdict: 'amber', confidence: 'medium' },
      questions_for_athlete: ['Com notes les cames?'],
    },
  };
  mockFrom.mockReturnValue(chainResolving({ data: row, error: null }, 'maybeSingle'));

  const report = await getLatestDailyReport('2026-08-29');
  expect(mockFrom).toHaveBeenCalledWith('coach_report');
  expect(report).toEqual({
    id: 7,
    createdAt: '2026-08-29T07:23:51Z',
    verdict: 'amber',
    summary: 'Rodatge suau en lloc de sèries.',
    rationale: 'El TSB ha caigut…',
    questions: ['Com notes les cames?'],
    windowStart: '2026-08-29',
    kind: 'today',
    proposal: null,
  });
});

test('sense cap informe encara: null, no error', async () => {
  mockFrom.mockReturnValue(chainResolving({ data: null, error: null }, 'maybeSingle'));
  expect(await getLatestDailyReport('2026-08-29')).toBeNull();
});

test("a partir de les 21:30 l'últim informe és el preview de demà, i es diu", async () => {
  const chain = chainResolving(
    { data: { id: 8, created_at: '2026-08-28T19:31:00Z', window_start: '2026-08-29', output: { summary: 'Demà rodatge.' } }, error: null },
    'maybeSingle'
  );
  mockFrom.mockReturnValue(chain);
  const report = await getLatestDailyReport('2026-08-28');
  expect(report?.kind).toBe('preview_tomorrow');
  expect(report?.windowStart).toBe('2026-08-29');
});

test("al matí, abans de l'informe del dia, el preview d'ahir parla d'avui", async () => {
  const chain = chainResolving(
    { data: { id: 8, created_at: '2026-08-28T19:31:00Z', window_start: '2026-08-29', output: {} }, error: null },
    'maybeSingle'
  );
  mockFrom.mockReturnValue(chain);
  expect((await getLatestDailyReport('2026-08-29'))?.kind).toBe('preview_today');
});

test("l'informe del matí (creat el mateix dia que descriu) és el d'avui", async () => {
  const chain = chainResolving(
    { data: { id: 9, created_at: '2026-08-29T06:20:00Z', window_start: '2026-08-29', output: {} }, error: null },
    'maybeSingle'
  );
  mockFrom.mockReturnValue(chain);
  expect((await getLatestDailyReport('2026-08-29'))?.kind).toBe('today');
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

test('getGoals: actius ordenats (A per data, sense data al final, després B i C)', async () => {
  const { getGoals } = require('./api');
  const rows = [
    { id: 3, name: 'Transpirinenca', discipline: 'ultra_endurance', event_date: null, priority: 'A', status: 'active', notes: null, profile: {} },
    { id: 2, name: 'Fornells', discipline: 'triathlon', event_date: '2026-09-27', priority: 'A', status: 'active', notes: null, profile: {} },
    { id: 4, name: '10 km popular', discipline: 'run', event_date: null, priority: 'C', status: 'active', notes: null, profile: {} },
  ];
  const chain = chainResolving({ data: rows, error: null });
  mockFrom.mockReturnValue(chain);
  const goals = await getGoals();
  expect(chain.eq).toHaveBeenCalledWith('status', 'active');
  expect(goals.map((g: any) => g.id)).toEqual([2, 3, 4]);
});

test('upsertGoal: sense id insereix, amb id actualitza; abandonGoal només toca status', async () => {
  const { upsertGoal, abandonGoal } = require('./api');
  const chain = chainResolving({ error: null });
  chain.insert = jest.fn(() => chain);
  chain.update = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  const input = { name: '10 km popular', discipline: 'run', event_date: null, priority: 'C', notes: 'quan surti',
                  profile: { segments: [{ sport: 'run', distance_m: 10000 }] } };
  await upsertGoal(input);
  expect(chain.insert).toHaveBeenCalledWith(input);
  expect(chain.update).not.toHaveBeenCalled();

  await upsertGoal({ ...input, id: 4, name: '10 km Bombers' });
  expect(chain.update).toHaveBeenCalledWith({ ...input, name: '10 km Bombers' });
  expect(chain.eq).toHaveBeenCalledWith('id', 4);

  await abandonGoal(4);
  expect(chain.update).toHaveBeenLastCalledWith({ status: 'abandoned' });
  expect(chain.eq).toHaveBeenLastCalledWith('id', 4);
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
  await expect(getLatestDailyReport('2026-08-29')).rejects.toThrow('permission denied');
});

test('marcar una tasca de logística com a feta: només la columna done', async () => {
  const { setLogisticsDone } = require('./api');
  const chain = chainResolving({ data: null, error: null });
  chain.update = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  await setLogisticsDone(4, true);
  expect(mockFrom).toHaveBeenCalledWith('logistics_task');
  expect(chain.update).toHaveBeenCalledWith({ done: true });
  expect(chain.eq).toHaveBeenCalledWith('id', 4);
});

test("registrar una sessió sense rellotge: fila manual amb id negatiu, mai una fila de Garmin", async () => {
  const chain = chainResolving({ data: null, error: null });
  chain.insert = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  const now = new Date(2026, 8, 10, 18, 42, 7);
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
  expect(row.id).toBe(-20260910184207);
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

test('dos trams registrats al mateix minut tenen ids diferents (segons)', async () => {
  const chain = chainResolving({ error: null });
  chain.insert = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  await logManualActivity({ local_date: '2026-09-12', sport: 'swim', duration_sec: 1110 }, new Date(2026, 8, 12, 12, 40, 5));
  await logManualActivity({ local_date: '2026-09-12', sport: 'bike', duration_sec: 4031 }, new Date(2026, 8, 12, 12, 40, 9));
  const ids = chain.insert.mock.calls.map((c: any[]) => c[0].id);
  expect(ids).toEqual([-20260912124005, -20260912124009]);
});

test("una sessió d'un dia passat porta l'hora d'aquell dia, no d'avui", async () => {
  const chain = chainResolving({ error: null });
  chain.insert = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  const now = new Date(2026, 8, 14, 9, 30, 0);
  await logManualActivity({ local_date: '2026-09-11', sport: 'swim', duration_sec: 2400 }, now);
  const row = chain.insert.mock.calls[0][0];
  // migdia local del dia registrat: el sync horari només mira local_date, però
  // el detall de l'activitat i l'ordre del dia usen start_time
  expect(new Date(row.start_time)).toEqual(new Date(2026, 8, 11, 12, 0, 0));
  // el mateix dia, es manté l'hora real (acabada ara)
  await logManualActivity({ local_date: '2026-09-14', sport: 'run', duration_sec: 600 }, now);
  expect(new Date(chain.insert.mock.calls[1][0].start_time)).toEqual(new Date(2026, 8, 14, 9, 20, 0));
});

test('parseLocalISO dona el dia local a mitjanit, no el UTC', () => {
  const { parseLocalISO } = require('./api');
  const d = parseLocalISO('2026-08-29');
  expect([d.getFullYear(), d.getMonth(), d.getDate(), d.getHours()]).toEqual([2026, 7, 29, 0]);
});

test("el bloc del pla d'una setmana és el que la solapa", async () => {
  const { getBlockForRange } = require('./api');
  const block = { phase: 'peak', name: 'Setmana 3 · específica, tot a ritme de cursa' };
  const chain = chainResolving({ data: block, error: null }, 'maybeSingle');
  chain.gte = jest.fn(() => chain);
  chain.lte = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);

  expect(await getBlockForRange('2026-09-14', '2026-09-20')).toEqual(block);
  expect(mockFrom).toHaveBeenCalledWith('plan_block');
  expect(chain.lte).toHaveBeenCalledWith('start_date', '2026-09-20');
  expect(chain.gte).toHaveBeenCalledWith('end_date', '2026-09-14');
});

test('les sessions de la setmana porten la prioritat (clau / suport / opcional)', async () => {
  const { getSessionsForRange } = require('./api');
  const chain = chainResolving({ data: [], error: null });
  chain.gte = jest.fn(() => chain);
  chain.lte = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  await getSessionsForRange('2026-08-24', '2026-08-30');
  expect(chain.select).toHaveBeenCalledWith(expect.stringContaining('priority'));
});

// --- S1b: propostes del coach i decisions ----------------------------------

const changesRow = {
  id: 27,
  created_at: '2026-09-10T19:32:04Z',
  window_start: '2026-09-11',
  report_type: 'daily',
  proposal_status: 'none',
  classification: { auto: false, reasons: ['sessió clau afectada'], n_sessions: 1 },
  output: {
    summary: 'Mou la natació a demà.',
    readiness: { verdict: 'amber' },
    session_changes: [
      { plan_session_id: 44, action: 'keep', reason: 'tal com estava' },
      { plan_session_id: 43, action: 'move', new_date: '2026-09-11', reason: 'no es pot saltar' },
      { plan_session_id: 44, action: 'modify', reason: 'retallar', new_session: { sport: 'run', session_type: 'easy', title: 'Rodatge 25 min', structure_json: '{}', duration_sec_target: 1500 } },
    ],
  },
};

test("l'informe porta la proposta: només els canvis que no són keep, amb estat i classificació", async () => {
  mockFrom.mockReturnValue(chainResolving({ data: changesRow, error: null }, 'maybeSingle'));
  const report = await getLatestDailyReport('2026-09-11');
  expect(report?.proposal).toEqual({
    id: 27,
    createdAt: '2026-09-10T19:32:04Z',
    reportType: 'daily',
    scope: 'sessions',
    status: 'none',
    classification: { auto: false, reasons: ['sessió clau afectada'] },
    blockChanges: [],
    changes: [
      { plan_session_id: 43, action: 'move', new_date: '2026-09-11', reason: 'no es pot saltar' },
      { plan_session_id: 44, action: 'modify', reason: 'retallar', new_session: { sport: 'run', title: 'Rodatge 25 min', duration_sec_target: 1500 } },
    ],
  });
});

test('un informe que ho manté tot no té proposta', async () => {
  const row = { ...changesRow, output: { ...changesRow.output, session_changes: [{ plan_session_id: 44, action: 'keep', reason: 'ok' }] } };
  mockFrom.mockReturnValue(chainResolving({ data: row, error: null }, 'maybeSingle'));
  expect((await getLatestDailyReport('2026-09-11'))?.proposal).toBeNull();
});

test('getOpenProposals: només estats oberts dels últims 7 dies, més recents primer', async () => {
  const { getOpenProposals } = require('./api');
  const chain = chainResolving({ data: [changesRow], error: null });
  chain.in = jest.fn(() => chain);
  chain.gte = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  const out = await getOpenProposals('2026-09-14');
  expect(mockFrom).toHaveBeenCalledWith('coach_report');
  expect(chain.in).toHaveBeenCalledWith('proposal_status', ['proposed', 'auto_applied', 'applied', 'failed']);
  expect(chain.gte).toHaveBeenCalledWith('created_at', '2026-09-07');
  expect(chain.order).toHaveBeenCalledWith('created_at', { ascending: false });
  expect(out).toHaveLength(1);
  expect(out[0].changes).toHaveLength(2);
});

test('getSessionsByIds demana només els ids donats; buit no consulta', async () => {
  const { getSessionsByIds } = require('./api');
  const rows = [{ id: 43, local_date: '2026-09-10', sport: 'swim', title: 'Ritme de cursa amb orientació', status: 'completed' }];
  const chain = chainResolving({ data: rows, error: null });
  chain.in = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  const map = await getSessionsByIds([43, 43, 44]);
  expect(chain.in).toHaveBeenCalledWith('id', [43, 44]);
  expect(map.get(43)?.title).toBe('Ritme de cursa amb orientació');
  mockFrom.mockClear();
  expect((await getSessionsByIds([])).size).toBe(0);
  expect(mockFrom).not.toHaveBeenCalled();
});

test('sendDecision insereix la decisió; getDecisions torna les dels informes donats', async () => {
  const { sendDecision, getDecisions } = require('./api');
  const chain = chainResolving({ error: null });
  chain.insert = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  await sendDecision(27, 'apply');
  expect(mockFrom).toHaveBeenCalledWith('coach_decision');
  expect(chain.insert).toHaveBeenCalledWith({ report_id: 27, decision: 'apply' });

  const rows = [{ id: 1, report_id: 27, decision: 'apply', status: 'failed', error: 'proposta caducada', created_at: '2026-09-14T10:00:00Z' }];
  const chain2 = chainResolving({ data: rows, error: null });
  chain2.in = jest.fn(() => chain2);
  mockFrom.mockReturnValue(chain2);
  const ds = await getDecisions([27]);
  expect(chain2.in).toHaveBeenCalledWith('report_id', [27]);
  expect(ds).toEqual(rows);
});

test('getSetting / setSetting sobre app_setting', async () => {
  const { getSetting, setSetting } = require('./api');
  mockFrom.mockReturnValue(chainResolving({ data: { value: 'dry_run' }, error: null }, 'maybeSingle'));
  expect(await getSetting('coach_apply_mode')).toBe('dry_run');
  const chain = chainResolving({ error: null });
  chain.update = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  await setSetting('coach_apply_mode', 'hybrid');
  expect(mockFrom).toHaveBeenCalledWith('app_setting');
  expect(chain.update).toHaveBeenCalledWith({ value: 'hybrid' });
  expect(chain.eq).toHaveBeenCalledWith('key', 'coach_apply_mode');
});

// --- S3: blocs i peticions al coach ----------------------------------------

test('getBlocks: només actius i proposats, per data', async () => {
  const { getBlocks } = require('./api');
  const rows = [{ id: 8, goal_id: 2, phase: 'taper', name: 'Afinada', start_date: '2026-09-21', end_date: '2026-09-27',
                  target_weekly_hours: 3.5, intent: 'i', fallback: 'f', status: 'active' }];
  const chain = chainResolving({ data: rows, error: null });
  chain.in = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  expect(await getBlocks()).toEqual(rows);
  expect(mockFrom).toHaveBeenCalledWith('plan_block');
  expect(chain.in).toHaveBeenCalledWith('status', ['active', 'proposed']);
  expect(chain.order).toHaveBeenCalledWith('start_date');
});

test("la proposta d'un macro porta els canvis de blocs i l'abast", async () => {
  const row = {
    ...changesRow, id: 40, report_type: 'macro', proposal_status: 'proposed',
    output: { summary: 'Recuperació i base.', readiness: { verdict: 'green' }, session_changes: [],
              block_changes: [
                { action: 'add', reason: 'cal descansar', new_block: { phase: 'recovery', name: 'Recuperació', start_date: '2026-09-28', end_date: '2026-10-18', target_weekly_hours: 3, intent: 'x', fallback: 'y' } },
                { action: 'modify', block_id: 8, reason: 'r', new_block: { target_weekly_hours: 3 } },
                { action: 'cancel', block_id: 7, reason: 'c' },
              ] },
  };
  mockFrom.mockReturnValue(chainResolving({ data: row, error: null }, 'maybeSingle'));
  const report = await getLatestDailyReport('2026-09-14');
  expect(report?.proposal?.scope).toBe('macro');
  expect(report?.proposal?.reportType).toBe('macro');
  expect(report?.proposal?.changes).toEqual([]);
  expect(report?.proposal?.blockChanges).toHaveLength(3);
  expect(report?.proposal?.blockChanges[0]).toMatchObject({ action: 'add', new_block: { phase: 'recovery', target_weekly_hours: 3 } });
});

test('sendRequest insereix la petició; getRequests torna les últimes', async () => {
  const { sendRequest, getRequests } = require('./api');
  const chain = chainResolving({ error: null });
  chain.insert = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  await sendRequest('regenerate_macro', { goal_id: 2 });
  expect(mockFrom).toHaveBeenCalledWith('athlete_request');
  expect(chain.insert).toHaveBeenCalledWith({ kind: 'regenerate_macro', payload: { goal_id: 2 } });
  const rows = [{ id: 1, kind: 'regenerate_macro', status: 'failed', error: 'ja hi ha un macro', report_id: null, created_at: 'x' }];
  const chain2 = chainResolving({ data: rows, error: null });
  mockFrom.mockReturnValue(chain2);
  expect(await getRequests(3)).toEqual(rows);
  expect(chain2.order).toHaveBeenCalledWith('created_at', { ascending: false });
  expect(chain2.limit).toHaveBeenCalledWith(3);
});

// --- S2b: perfil de l'atleta ----------------------------------------------

test('getAthlete llegeix la fila 1 amb el perfil (buit si és null)', async () => {
  const { getAthlete } = require('./api');
  const row = { id: 1, name: 'Roger', birth_date: '2005-01-01', max_hr: 211, profile: null };
  const chain = chainResolving({ data: row, error: null }, 'maybeSingle');
  mockFrom.mockReturnValue(chain);
  const a = await getAthlete();
  expect(mockFrom).toHaveBeenCalledWith('athlete');
  expect(chain.select).toHaveBeenCalledWith('id, name, birth_date, max_hr, profile');
  expect(chain.eq).toHaveBeenCalledWith('id', 1);
  expect(a).toEqual({ ...row, profile: {} });
});

test('updateAthleteProfile escriu només la columna profile de la fila 1', async () => {
  const { updateAthleteProfile } = require('./api');
  const chain = chainResolving({ error: null });
  chain.update = jest.fn(() => chain);
  mockFrom.mockReturnValue(chain);
  const profile = { constraints: { weekly_hours_ceiling: 7 }, notes: 'vacances a l’agost' };
  await updateAthleteProfile(profile);
  expect(mockFrom).toHaveBeenCalledWith('athlete');
  expect(chain.update).toHaveBeenCalledWith({ profile });
  expect(chain.eq).toHaveBeenCalledWith('id', 1);
});
