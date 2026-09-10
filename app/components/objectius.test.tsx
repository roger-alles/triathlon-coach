jest.mock('@/lib/api', () => ({
  getActiveGoal: jest.fn(),
  getLogistics: jest.fn(),
  setLogisticsDone: jest.fn(),
}));

import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getActiveGoal, getLogistics } from '@/lib/api';
import Objectius from './objectius';

const mockGoal = getActiveGoal as jest.Mock;
const mockLogistics = getLogistics as jest.Mock;

const goal = {
  id: 2,
  name: 'Artiem Half Menorca · Short — Fornells',
  event_date: '2026-09-27',
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

beforeEach(() => {
  jest.clearAllMocks();
  mockGoal.mockResolvedValue(goal);
  mockLogistics.mockResolvedValue([
    { id: 1, local_date: '2026-09-24', title: 'Revisió completa de material', detail: null, blocking: true, done: false },
  ]);
});

test('nom, compte enrere i sectors de la cursa', async () => {
  await renderObjectius();
  expect(await screen.findByText(/Artiem Half Menorca/)).toBeOnTheScreen();
  expect(screen.getByText(/dies/)).toBeOnTheScreen();
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
