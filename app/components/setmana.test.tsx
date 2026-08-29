jest.mock('@/lib/api', () => ({
  getSessionsForRange: jest.fn(),
  getActivitiesForRange: jest.fn(),
  weekDaysISO: () => [
    '2026-08-24', '2026-08-25', '2026-08-26', '2026-08-27',
    '2026-08-28', '2026-08-29', '2026-08-30',
  ],
  localDateISO: () => '2026-08-29',
}));

import { render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getActivitiesForRange, getSessionsForRange } from '@/lib/api';
import Setmana from './setmana';

const mockSessions = getSessionsForRange as jest.Mock;
const mockActivities = getActivitiesForRange as jest.Mock;

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
      status: 'completed', duration_sec_target: 4500 },
    { id: 24, local_date: '2026-08-27', sport: 'brick', title: 'Primer brick',
      status: 'missed', duration_sec_target: 600 },
    { id: 30, local_date: '2026-08-29', sport: 'run', title: 'Rodatge suau (canvi del coach)',
      status: 'planned', duration_sec_target: 2400 },
  ]);
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
  expect(screen.getByText(/Fora de pla · Natació · 52 min/)).toBeOnTheScreen();
});

test('avui queda marcat', async () => {
  await renderSetmana();
  expect(await screen.findByText(/Dissabte 29 · avui/)).toBeOnTheScreen();
});
