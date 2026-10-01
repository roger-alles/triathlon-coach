jest.mock('@/lib/supabase', () => ({ supabase: {} }));
jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  getSessionsForRange: jest.fn(),
  getActivitiesForRange: jest.fn(),
  getBlockForRange: jest.fn(),
  logManualActivity: jest.fn(),
  getWeekRequest: jest.fn(),
  requestWeekRedesign: jest.fn(),
  localDateISO: () => '2026-08-29',
}));

const mockPush = jest.fn();
jest.mock('expo-router', () => ({ router: { push: (...a: unknown[]) => mockPush(...a) } }));

import { render, screen, userEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getActivitiesForRange, getBlockForRange, getSessionsForRange, getWeekRequest, logManualActivity } from '@/lib/api';
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
  (getWeekRequest as jest.Mock).mockResolvedValue(null);
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

test('les sessions passades no fetes ofereixen "Ho he fet"; les fetes i les futures, no', async () => {
  mockSessions.mockResolvedValue([
    { id: 23, local_date: '2026-08-27', sport: 'bike', title: 'Rodatge ondulat',
      status: 'completed', duration_sec_target: 4500, priority: 'support' },
    { id: 24, local_date: '2026-08-27', sport: 'brick', title: 'Primer brick',
      status: 'missed', duration_sec_target: 600, priority: 'optional' },
    { id: 26, local_date: '2026-08-28', sport: 'swim', title: 'Test de referència',
      status: 'partial', duration_sec_target: 2400, priority: 'key' },
    { id: 30, local_date: '2026-08-29', sport: 'run', title: 'Rodatge suau (canvi del coach)',
      status: 'planned', duration_sec_target: 2400, priority: 'key' },
    { id: 31, local_date: '2026-08-30', sport: 'swim', title: 'Primer contacte al mar',
      status: 'planned', duration_sec_target: 1800, priority: 'key' },
  ]);
  mockActivities.mockResolvedValue([
    { id: 3, local_date: '2026-08-27', sport: 'bike', duration_sec: 9237, distance_m: 67836, avg_hr: 132, plan_session_id: 23 },
    // la natació parcial del 28 ja té la seva activitat: no cal tornar-la a registrar
    { id: 4, local_date: '2026-08-28', sport: 'swim', duration_sec: 1500, distance_m: 1000, avg_hr: null, plan_session_id: 26 },
  ]);
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  // brick perdut del 27: sí, com la cursa del brick
  expect(screen.getByText('Ho he fet · cursa del brick')).toBeOnTheScreen();
  // la d'avui (29, planned): sí
  expect(screen.getAllByText('Ho he fet')).toHaveLength(1);
  // la feta (23), la parcial amb activitat (26) i la de demà (31): no
  expect(screen.getAllByText(/Ho he fet/)).toHaveLength(2);
});

test('registrar des de Setmana envia el dia de la sessió i recarrega la setmana', async () => {
  (logManualActivity as jest.Mock).mockResolvedValue(undefined);
  mockSessions.mockResolvedValue([
    { id: 24, local_date: '2026-08-27', sport: 'swim', title: 'Natació perduda',
      status: 'missed', duration_sec_target: 2400, distance_m_target: 1600, priority: 'key' },
  ]);
  mockActivities.mockResolvedValue([]);
  await renderSetmana();
  await screen.findByText(/Dilluns 24/);
  expect(mockSessions).toHaveBeenCalledTimes(1);
  const user = userEvent.setup();
  await user.press(screen.getByText('Ho he fet'));
  expect(screen.getByDisplayValue('2026-08-27')).toBeOnTheScreen();
  await user.press(screen.getByText('Registra'));
  await screen.findByText(/Registrada/);
  expect((logManualActivity as jest.Mock).mock.calls[0][0]).toMatchObject({ local_date: '2026-08-27', plan_session_id: 24 });
  expect(mockSessions).toHaveBeenCalledTimes(2);
});

test('la setmana actual porta la caixa de Demana canvis; una de passada, no', async () => {
  await renderSetmana();
  expect(await screen.findByText('Demana canvis a la setmana')).toBeOnTheScreen();
  expect(getWeekRequest).toHaveBeenCalledWith('2026-08-24');
  const user = userEvent.setup();
  await user.press(screen.getByLabelText('Setmana anterior'));
  await screen.findByText(/Dilluns 17/);
  expect(screen.queryByText('Demana canvis a la setmana')).toBeNull();
});
