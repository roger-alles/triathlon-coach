jest.mock('@/lib/supabase', () => ({ supabase: {} }));
jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  getGoals: jest.fn(),
  getLogistics: jest.fn(),
  setLogisticsDone: jest.fn(),
  upsertGoal: jest.fn(),
  abandonGoal: jest.fn(),
  getBlocks: jest.fn(),
  sendRequest: jest.fn(),
  getRequests: jest.fn(),
  getMacroAnswer: jest.fn(),
}));

import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getBlocks, getGoals, getLogistics, getMacroAnswer, getRequests, sendRequest, upsertGoal } from '@/lib/api';
import Objectius from './objectius';

const mockGoals = getGoals as jest.Mock;
const mockLogistics = getLogistics as jest.Mock;

const goal = {
  id: 2,
  name: 'Artiem Half Menorca · Short — Fornells',
  discipline: 'triathlon',
  event_date: '2026-09-27',
  priority: 'A',
  status: 'active',
  notes: null,
  profile: {
    location: 'Fornells, Menorca',
    start_time: '08:35',
    first_race_ever: true,
    segments: [
      { sport: 'swim', distance_m: 1000, notes: 'Badia de Fornells' },
      { sport: 'bike', distance_m: 34000, notes: "Camí d'en Kane" },
      { sport: 'run', distance_m: 9000, notes: 'Ses Salines' },
    ],
    target_times_sec: {
      swim: [1560, 1380, 1200],
      t1: [180, 135, 105],
      bike: [3960, 3720, 3480],
      t2: [90, 70, 55],
      run: [2320, 2160, 2065],
      total: [8110, 7470, 6895],
    },
    pacing_rules: { swim: 'Primers 100 m al 70 %.' },
    race_day_protocol: [{ time: '05:30', what: 'Despertar i esmorzar', detail: 'Pa amb mel.' }],
  },
};

const renderObjectius = () =>
  render(
    <SafeAreaProvider
      initialMetrics={{
        insets: { top: 59, left: 0, right: 0, bottom: 34 },
        frame: { x: 0, y: 0, width: 390, height: 844 },
      }}>
      <Objectius />
    </SafeAreaProvider>
  );

const popular = {
  id: 4, name: '10 km popular', discipline: 'run', event_date: null, priority: 'C', status: 'active',
  notes: 'quan surti', profile: { segments: [{ sport: 'run', distance_m: 10000 }] },
};

beforeEach(() => {
  jest.clearAllMocks();
  mockGoals.mockResolvedValue([goal, popular]);
  (getBlocks as jest.Mock).mockResolvedValue([
    { id: 7, goal_id: 2, phase: 'peak', name: 'Setmana 3 · específica', start_date: '2026-09-14', end_date: '2026-09-20', target_weekly_hours: 7, intent: null, fallback: null, status: 'active' },
    { id: 8, goal_id: 2, phase: 'taper', name: 'Setmana 4 · afinada i cursa', start_date: '2026-09-21', end_date: '2026-09-27', target_weekly_hours: 3.5, intent: null, fallback: null, status: 'active' },
  ]);
  (getRequests as jest.Mock).mockResolvedValue([]);
  (getMacroAnswer as jest.Mock).mockResolvedValue(null);
  (sendRequest as jest.Mock).mockResolvedValue(undefined);
  mockLogistics.mockResolvedValue([
    { id: 1, local_date: '2026-09-24', title: 'Revisió completa de material', detail: null, blocking: true, done: false },
  ]);
});

test('nom, compte enrere i sectors de la cursa', async () => {
  await renderObjectius();
  expect(await screen.findByText(/Artiem Half Menorca/)).toBeOnTheScreen();
  expect(screen.getByText(/dies/)).toBeOnTheScreen();
  // la data ve de l'objectiu, no d'un text fix
  expect(screen.getByText(/27\/09\/2026/)).toBeOnTheScreen();
  expect(screen.getByText(/1000 m/)).toBeOnTheScreen();
  expect(screen.getByText(/34 km/)).toBeOnTheScreen();
  expect(screen.getByText(/9 km/)).toBeOnTheScreen();
});

test('els tres escenaris de temps, formatats', async () => {
  await renderObjectius();
  await screen.findByText(/Artiem/);
  expect(screen.getByText('38:40')).toBeOnTheScreen();   // run prudent
  expect(screen.getByText('2:04:30')).toBeOnTheScreen(); // total objectiu
  expect(screen.getByText('1:54:55')).toBeOnTheScreen(); // total gran dia
});

test('la logística surt amb la seva data', async () => {
  await renderObjectius();
  expect(await screen.findByText(/Revisió completa de material/)).toBeOnTheScreen();
  expect(screen.getByText(/24\/09/)).toBeOnTheScreen();
});

test('una tasca de logística es marca com a feta tocant-la, i mostra el detall', async () => {
  const { setLogisticsDone } = require('@/lib/api');
  (setLogisticsDone as jest.Mock).mockResolvedValue(undefined);
  mockLogistics.mockResolvedValue([
    { id: 4, local_date: '2026-09-26', title: 'Recollida de dorsal', detail: 'Fira, 16-20 h', blocking: true, done: false },
  ]);
  await renderObjectius();
  expect(await screen.findByText(/Recollida de dorsal/)).toBeOnTheScreen();
  expect(screen.getByText(/Fira, 16-20 h/)).toBeOnTheScreen();
  expect(screen.getByText(/imprescindible/i)).toBeOnTheScreen();
  const user = userEvent.setup();
  await user.press(screen.getByText(/Recollida de dorsal/));
  await waitFor(() => expect(setLogisticsDone).toHaveBeenCalledWith(4, true));
  expect(await screen.findByText(/✓ 26\/09/)).toBeOnTheScreen();
});

test("la llista mostra tots els objectius actius amb prioritat; els sense data ho diuen", async () => {
  await renderObjectius();
  expect(await screen.findByText('10 km popular')).toBeOnTheScreen();
  expect(screen.getByText('C')).toBeOnTheScreen();
  expect(screen.getByText(/sense data/)).toBeOnTheScreen();
  // només l'A principal té compte enrere gran
  expect(screen.getAllByText(/\d+ dies/)).toHaveLength(1);
});

test('sense cap objectiu: missatge i botó de nou', async () => {
  mockGoals.mockResolvedValue([]);
  await renderObjectius();
  expect(await screen.findByText(/Cap objectiu/)).toBeOnTheScreen();
  expect(screen.getByText('Nou objectiu')).toBeOnTheScreen();
});

test('Nou objectiu obre el formulari; desar recarrega la llista', async () => {
  (upsertGoal as jest.Mock).mockResolvedValue(undefined);
  await renderObjectius();
  await screen.findByText(/Artiem/);
  const user = userEvent.setup();
  await user.press(screen.getByText('Nou objectiu'));
  await user.type(screen.getByLabelText('Nom'), 'Mitja de Barcelona');
  await user.press(screen.getByText('Cursa'));
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(upsertGoal).toHaveBeenCalledTimes(1));
  expect(mockGoals).toHaveBeenCalledTimes(2);
});

test('tocar un objectiu de la llista obre el formulari preomplert', async () => {
  await renderObjectius();
  await screen.findByText('10 km popular');
  const user = userEvent.setup();
  await user.press(screen.getByText('10 km popular'));
  expect(screen.getByDisplayValue('10 km popular')).toBeOnTheScreen();
  expect(screen.getByText('Abandona')).toBeOnTheScreen();
});

test('la secció Pla mostra els blocs amb fase, dates i hores, i el d\'avui destacat', async () => {
  await renderObjectius();
  expect(await screen.findByText('Setmana 3 · específica')).toBeOnTheScreen();
  expect(screen.getByText(/14\/09 – 20\/09 · 7 h\/set/)).toBeOnTheScreen();
  expect(screen.getByText(/21\/09 – 27\/09 · 3.5 h\/set/)).toBeOnTheScreen();
  expect(screen.getByText('pic')).toBeOnTheScreen();
  expect(screen.getByText('afinament')).toBeOnTheScreen();
});

test('Demana un macro nou: confirma, insereix la petició i ho diu; una petició fallida ensenya l\'error', async () => {
  const { Alert } = require('react-native');
  jest.spyOn(Alert, 'alert').mockImplementation((_t: any, _m: any, buttons: any) => buttons?.find((b: any) => b.style !== 'cancel')?.onPress?.());
  await renderObjectius();
  await screen.findByText('Setmana 3 · específica');
  const user = userEvent.setup();
  await user.press(screen.getByText('Demana un macro nou'));
  await waitFor(() => expect(sendRequest).toHaveBeenCalledWith('regenerate_macro', { goal_id: 2 }));
  expect(await screen.findByText(/El coach hi treballa/)).toBeOnTheScreen();

  (getRequests as jest.Mock).mockResolvedValue([
    { id: 9, kind: 'regenerate_macro', status: 'failed', error: "ja hi ha un macro d'avui", report_id: null, created_at: '2026-09-16T10:00:00Z' },
  ]);
  await renderObjectius();
  expect(await screen.findByText(/ja hi ha un macro d'avui/)).toBeOnTheScreen();
});

test('una petició resposta sense canvis de blocs mostra el resum del coach a Objectius', async () => {
  (getRequests as jest.Mock).mockResolvedValue([
    { id: 1, kind: 'regenerate_macro', status: 'answered', error: null, report_id: 36, created_at: '2026-09-14T17:16:00Z' },
  ]);
  (getMacroAnswer as jest.Mock).mockResolvedValue({ id: 36, proposalStatus: 'none', summary: 'Cap canvi de blocs: el pla és correcte', hasBlockChanges: false });
  await renderObjectius();
  expect(await screen.findByText(/sense canviar blocs: Cap canvi de blocs/)).toBeOnTheScreen();
  expect(getMacroAnswer).toHaveBeenCalledWith(36);
  expect(screen.getByText('Demana un macro nou')).toBeOnTheScreen();
});

// --- S2b: temps objectiu de l'app, ritme derivat, notes -------------------

test('un objectiu amb només el temps central mostra "—" als altres escenaris i el ritme derivat', async () => {
  mockGoals.mockResolvedValue([
    {
      id: 5, name: '10 km Bombers', discipline: 'run', event_date: '2026-11-15', priority: 'A', status: 'active',
      notes: 'vull baixar de 37', profile: { segments: [{ sport: 'run', distance_m: 10000 }], target_times_sec: { total: [null, 2190, null] } },
    },
  ]);
  mockLogistics.mockResolvedValue([]);
  await renderObjectius();
  expect(await screen.findByText('36:30')).toBeOnTheScreen();
  expect(screen.getAllByText('—')).toHaveLength(2);
  expect(screen.getByText('≈ 3:39/km')).toBeOnTheScreen();
  // les notes de l'objectiu principal es veuen
  expect(screen.getByText('Per al coach')).toBeOnTheScreen();
  expect(screen.getByText('vull baixar de 37')).toBeOnTheScreen();
});

test('Fornells: ritme derivat per segment (natació per 100 m) i les notes dels altres objectius', async () => {
  await renderObjectius();
  await screen.findByText(/Artiem/);
  expect(screen.getByText('≈ 2:18/100 m')).toBeOnTheScreen(); // 1380 s / 1000 m
  expect(screen.getByText('≈ 4:00/km')).toBeOnTheScreen();     // 2160 s / 9 km
  expect(screen.queryByText('Per al coach')).toBeNull();        // Fornells no té notes
  expect(screen.getByText('quan surti')).toBeOnTheScreen();     // notes del 10 km popular
});
