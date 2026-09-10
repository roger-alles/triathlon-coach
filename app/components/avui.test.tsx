jest.mock('@/lib/api', () => ({
  getLatestDailyReport: jest.fn(),
  getSessionsForDay: jest.fn(),
  getAnswers: jest.fn(),
  sendAnswer: jest.fn(),
  localDateISO: () => '2026-08-29',
}));
jest.mock('@/lib/supabase', () => ({ supabase: { auth: { signOut: jest.fn() } } }));

import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getAnswers, getLatestDailyReport, getSessionsForDay, sendAnswer } from '@/lib/api';
import Avui from './avui';

const mockGetAnswers = getAnswers as jest.Mock;
const mockSendAnswer = sendAnswer as jest.Mock;

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
  id: 7,
  createdAt: '2026-08-29T07:23:51Z',
  verdict: 'amber',
  summary: 'Rodatge suau en lloc de sèries.',
  rationale: 'El TSB ha caigut a -24.6…',
  questions: ['Com notes les cames?'],
  windowStart: '2026-08-29',
  kind: 'today',
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
  priority: 'support' as const,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockReport.mockResolvedValue(report);
  mockSessions.mockResolvedValue([session]);
  mockGetAnswers.mockResolvedValue([]);
  mockSendAnswer.mockResolvedValue(undefined);
});

test('respondre una pregunta del coach: escriure, enviar, confirmació', async () => {
  await renderAvui();
  await screen.findByText(/Com notes les cames\?/);

  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText(/Respon/), 'Bé, sense agulletes');
  await user.press(screen.getByText('Envia'));

  await waitFor(() =>
    expect(mockSendAnswer).toHaveBeenCalledWith(7, 'Com notes les cames?', 'Bé, sense agulletes')
  );
  expect(await screen.findByText(/Tu: Bé, sense agulletes/)).toBeOnTheScreen();
});

test('una pregunta ja resposta mostra la resposta, no la caixa', async () => {
  mockGetAnswers.mockResolvedValue([
    { id: 1, question: 'Com notes les cames?', answer: 'Una mica pesades' },
  ]);
  await renderAvui();
  expect(await screen.findByText(/Tu: Una mica pesades/)).toBeOnTheScreen();
  expect(screen.queryByPlaceholderText(/Respon/)).toBeNull();
});

test('pinta semàfor, titular, sessió amb passos i preguntes', async () => {
  await renderAvui();
  expect(await screen.findByText('Rodatge suau en lloc de sèries.')).toBeOnTheScreen();
  expect(screen.getByText('ÀMBAR')).toBeOnTheScreen();
  expect(screen.getByText("Sessió d'avui")).toBeOnTheScreen();
  expect(screen.getByText(/Cursa · 40 min · Rodatge suau/)).toBeOnTheScreen();
  expect(screen.getByText(/🏃 Cursa · 40 min · Rodatge suau/)).toBeOnTheScreen();
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

test('a la nit, el preview de demà surt amb el dia de què parla', async () => {
  mockReport.mockResolvedValue({ ...report, createdAt: '2026-08-29T19:31:00Z', windowStart: '2026-08-30', kind: 'preview_tomorrow' });
  await renderAvui();
  expect(await screen.findByText(/Preview per a demà, diumenge 30 d'agost/)).toBeOnTheScreen();
  expect(mockReport).toHaveBeenCalledWith('2026-08-29');
});

test("al matí sense informe del dia, el preview d'ahir es marca com a tal", async () => {
  mockReport.mockResolvedValue({ ...report, createdAt: '2026-08-28T19:31:00Z', kind: 'preview_today' });
  await renderAvui();
  expect(await screen.findByText(/Preview d'ahir al vespre per a avui/)).toBeOnTheScreen();
});

test('el simulacre (segments) es pinta, no surt buit', async () => {
  mockSessions.mockResolvedValue([
    {
      ...session,
      id: 2,
      sport: 'multisport',
      session_type: 'race_simulation',
      title: 'SIMULACRE COMPLET DE CURSA',
      duration_sec_target: 7200,
      structure: {
        segments: [
          { sport: 'swim', venue: 'open_water', target: { type: 'rpe', value: 7 }, distance_m: 800 },
          { sport: 'transition', timed: true, transition: 't1' },
          { sport: 'bike', target: { type: 'rpe', value: 7 }, distance_m: 34000 },
        ],
      },
    },
  ]);
  await renderAvui();
  expect(await screen.findByText(/Triatló · 2 h · SIMULACRE/)).toBeOnTheScreen();
  expect(screen.getByText('Natació 800 m · RPE 7 · mar')).toBeOnTheScreen();
  expect(screen.getByText('T1 cronometrada')).toBeOnTheScreen();
  expect(screen.getByText('Bici 34 km · RPE 7')).toBeOnTheScreen();
});
