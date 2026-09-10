jest.mock('@/lib/supabase', () => ({ supabase: {} }));
jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  getSessionsForRange: jest.fn(),
  getActivitiesForRange: jest.fn(),
  getBlockForRange: jest.fn(),
  localDateISO: () => '2026-08-29',
}));

const mockPush = jest.fn();
jest.mock('expo-router', () => ({ router: { push: (...a: unknown[]) => mockPush(...a) } }));

import { render, screen, userEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getActivitiesForRange, getBlockForRange, getSessionsForRange } from '@/lib/api';
import Setmana from './setmana';

const mockSessions = getSessionsForRange as jest.Mock;
const mockActivities = getActivitiesForRange as jest.Mock;
const mockBlock = getBlockForRange as jest.Mock;

const renderSetmana = () =>
  render(
    <SafeAreaProvider
      initialMetrics={{
        insets: { top: 59, left: 0, right: 0, bottom: 34 },
        frame: { x: 0, y: 0, width: 390, height: 844 },
      }}>
      <Setmana />
    </SafeAreaProvider>
  );

beforeEach(() => {
  jest.clearAllMocks();
  mockSessions.mockResolvedValue([
    { id: 23, local_date: '2026-08-27', sport: 'bike', title: 'Rodatge ondulat',
      status: 'completed', duration_sec_target: 4500, priority: 'support' },
    { id: 24, local_date: '2026-08-27', sport: 'brick', title: 'Primer brick',
      status: 'missed', duration_sec_target: 600, priority: 'optional' },
    { id: 30, local_date: '2026-08-29', sport: 'run', title: 'Rodatge suau (canvi del coach)',
      status: 'planned', duration_sec_target: 2400, priority: 'key',
      structure: { steps: [{ phase: 'main', duration_sec: 2400, target: { type: 'rpe', value: 3 } }] },
      rationale: 'Les cames encara noten la bici de dijous.' },
  ]);
  mockBlock.mockResolvedValue({ phase: 'base', name: "Bloc inicial · tornar a l'aigua i mesurar" });
  mockActivities.mockResolvedValue([
    { id: 1, local_date: '2026-08-24', sport: 'swim', duration_sec: 3121,
      distance_m: 1520, avg_hr: null, plan_session_id: null },
    { id: 3, local_date: '2026-08-27', sport: 'bike', duration_sec: 9237,
      distance_m: 67836, avg_hr: 132, plan_session_id: 23 },
  ]);
});

test('els 7 dies hi són, amb les sessions al seu dia i el seu estat', async () => {
  await renderSetmana();
  expect(await screen.findByText(/Dilluns 24/)).toBeOnTheScreen();
  expect(screen.getByText(/Diumenge 30/)).toBeOnTheScreen();
  expect(screen.getByText('Rodatge ondulat')).toBeOnTheScreen();
  expect(screen.getByText('feta')).toBeOnTheScreen();
  expect(screen.getByText('no feta')).toBeOnTheScreen();
  expect(screen.getByText('pendent')).toBeOnTheScreen();
});

test('la sessió vinculada mostra el real; l\'activitat sense pla surt com a fora de pla', async () => {
  await renderSetmana();
  expect(await screen.findByText(/Real: 2 h 34 min/)).toBeOnTheScreen();
  expect(screen.getByText(/Fora de pla · 🏊 Natació · 52 min/)).toBeOnTheScreen();
});

test("tocar una activitat feta obre el seu detall", async () => {
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  const user = userEvent.setup();
  await user.press(screen.getByText(/Real: 2 h 34 min/));
  expect(mockPush).toHaveBeenCalledWith({ pathname: '/activitat', params: { id: 3 } });

  await user.press(screen.getByText(/Fora de pla · 🏊 Natació/));
  expect(mockPush).toHaveBeenCalledWith({ pathname: '/activitat', params: { id: 1 } });
});

test('avui queda marcat', async () => {
  await renderSetmana();
  expect(await screen.findByText(/Dissabte 29 · avui/)).toBeOnTheScreen();
});

test('la capçalera diu el rang de dates i el nom del bloc del pla', async () => {
  await renderSetmana();
  expect(await screen.findByText("24 – 30 d'agost")).toBeOnTheScreen();
  expect(screen.getByText(/Bloc inicial/)).toBeOnTheScreen();
  expect(mockBlock).toHaveBeenCalledWith('2026-08-24', '2026-08-30');
});

test('la fletxa següent carrega la setmana vinent; Avui torna a l\'actual', async () => {
  mockSessions.mockImplementation(async (start: string) =>
    start === '2026-08-31'
      ? [{ id: 41, local_date: '2026-09-01', sport: 'swim', title: 'Test de referència',
           status: 'planned', duration_sec_target: 2400, priority: 'key' }]
      : []
  );
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  expect(screen.queryByText('Avui')).toBeNull();

  const user = userEvent.setup();
  await user.press(screen.getByLabelText('Setmana següent'));
  expect(await screen.findByText(/Dilluns 31/)).toBeOnTheScreen();
  expect(mockSessions).toHaveBeenLastCalledWith('2026-08-31', '2026-09-06');
  expect(screen.getByText('Test de referència')).toBeOnTheScreen();
  expect(screen.queryByText(/· avui/)).toBeNull();

  await user.press(screen.getByText('Avui'));
  expect(await screen.findByText(/Dissabte 29 · avui/)).toBeOnTheScreen();
  expect(screen.queryByText('Avui')).toBeNull();
});

test('la fletxa anterior demana la setmana passada', async () => {
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  const user = userEvent.setup();
  await user.press(screen.getByLabelText('Setmana anterior'));
  expect(await screen.findByText(/Dilluns 17/)).toBeOnTheScreen();
  expect(mockSessions).toHaveBeenLastCalledWith('2026-08-17', '2026-08-23');
});

test('només les sessions clau porten la marca CLAU', async () => {
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  expect(screen.getAllByText('CLAU')).toHaveLength(1);
});

test('tocar una sessió desplega els passos i la raó; tornar-la a tocar els amaga', async () => {
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  expect(screen.queryByText(/40 min · RPE 3/)).toBeNull();

  const user = userEvent.setup();
  await user.press(screen.getByText('Rodatge suau (canvi del coach)'));
  expect(screen.getByText('40 min · RPE 3')).toBeOnTheScreen();
  expect(screen.getByText('Les cames encara noten la bici de dijous.')).toBeOnTheScreen();

  await user.press(screen.getByText('Rodatge suau (canvi del coach)'));
  expect(screen.queryByText('40 min · RPE 3')).toBeNull();
});

test('cada sessió porta l\'emoji de la seva modalitat davant del títol', async () => {
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  expect(screen.getByText('🚴')).toBeOnTheScreen();
  expect(screen.getByText('🚴🏃')).toBeOnTheScreen();
  expect(screen.getByText('🏃')).toBeOnTheScreen();
});

test('un títol llarg salta de línia dins la targeta en lloc d\'empènyer CLAU fora', async () => {
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  // El títol ha de poder encongir-se dins la fila (flex: 1); si no, el text
  // no fa wrap i CLAU surt de la targeta.
  expect(screen.getByText('Rodatge suau (canvi del coach)')).toHaveStyle({ flex: 1 });
});
