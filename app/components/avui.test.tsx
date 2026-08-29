jest.mock('@/lib/api', () => ({
  getLatestDailyReport: jest.fn(),
  getSessionsForDay: jest.fn(),
  localDateISO: () => '2026-08-29',
}));
jest.mock('@/lib/supabase', () => ({ supabase: { auth: { signOut: jest.fn() } } }));

import { render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getLatestDailyReport, getSessionsForDay } from '@/lib/api';
import Avui from './avui';

const renderAvui = () =>
  render(
    <SafeAreaProvider
      initialMetrics={{
        insets: { top: 59, left: 0, right: 0, bottom: 34 },
        frame: { x: 0, y: 0, width: 390, height: 844 },
      }}>
      <Avui />
    </SafeAreaProvider>
  );

const mockReport = getLatestDailyReport as jest.Mock;
const mockSessions = getSessionsForDay as jest.Mock;

const report = {
  createdAt: '2026-08-29T07:23:51Z',
  verdict: 'amber',
  summary: 'Rodatge suau en lloc de sèries.',
  rationale: 'El TSB ha caigut a -24.6…',
  questions: ['Com notes les cames?'],
};

const session = {
  id: 1,
  sport: 'run',
  session_type: 'easy',
  title: 'Rodatge suau',
  status: 'planned',
  duration_sec_target: 2400,
  distance_m_target: null,
  structure: { steps: [{ phase: 'main', duration_sec: 2400, target: { type: 'rpe', value: 3 } }] },
  rationale: null,
  is_test: false,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockReport.mockResolvedValue(report);
  mockSessions.mockResolvedValue([session]);
});

test('pinta semàfor, titular, sessió amb passos i preguntes', async () => {
  await renderAvui();
  expect(await screen.findByText('Rodatge suau en lloc de sèries.')).toBeOnTheScreen();
  expect(screen.getByText('ÀMBAR')).toBeOnTheScreen();
  expect(screen.getByText("Sessió d'avui")).toBeOnTheScreen();
  expect(screen.getByText(/Cursa · 40 min · Rodatge suau/)).toBeOnTheScreen();
  expect(screen.getByText(/40 min · RPE 3/)).toBeOnTheScreen();
  expect(screen.getByText(/Com notes les cames\?/)).toBeOnTheScreen();
});

test('sense informe encara: ho diu, però la sessió del dia es veu igualment', async () => {
  mockReport.mockResolvedValue(null);
  await renderAvui();
  expect(await screen.findByText(/Encara no hi ha informe/)).toBeOnTheScreen();
  expect(screen.getByText("Sessió d'avui")).toBeOnTheScreen();
});

test('errors de càrrega es mostren, no es traguen', async () => {
  mockReport.mockRejectedValue(new Error('Network request failed'));
  await renderAvui();
  expect(await screen.findByText(/Network request failed/)).toBeOnTheScreen();
});
