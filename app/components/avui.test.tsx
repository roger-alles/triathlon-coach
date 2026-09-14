jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  getLatestDailyReport: jest.fn(),
  getSessionsForDay: jest.fn(),
  getAnswers: jest.fn(),
  sendAnswer: jest.fn(),
  getOpenProposals: jest.fn(),
  getSessionsByIds: jest.fn(),
  getDecisions: jest.fn(),
  getSetting: jest.fn(),
  sendDecision: jest.fn(),
  localDateISO: () => '2026-08-29',
}));
jest.mock('@/lib/supabase', () => ({ supabase: { auth: { signOut: jest.fn() } } }));

import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getAnswers, getDecisions, getLatestDailyReport, getOpenProposals, getSessionsByIds, getSessionsForDay, getSetting, sendAnswer, sendDecision } from '@/lib/api';
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
  proposal: null,
};

const proposal = {
  id: 7,
  createdAt: '2026-08-29T07:23:51Z',
  reportType: 'daily',
  status: 'none',
  classification: { auto: true, reasons: [] },
  changes: [{ plan_session_id: 1, action: 'modify', reason: 'cames pesades', new_session: { sport: 'run', title: 'Rodatge suau', duration_sec_target: 2400 } }],
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
  (getOpenProposals as jest.Mock).mockResolvedValue([]);
  (getSessionsByIds as jest.Mock).mockResolvedValue(new Map([[1, { id: 1, local_date: '2026-08-29', sport: 'run', title: 'Sèries 5×1000', status: 'planned' }]]));
  (getDecisions as jest.Mock).mockResolvedValue([]);
  (getSetting as jest.Mock).mockResolvedValue('dry_run');
  (sendDecision as jest.Mock).mockResolvedValue(undefined);
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

test("un informe amb canvis mostra la targeta de proposta; en mode prova, etiquetada", async () => {
  mockReport.mockResolvedValue({ ...report, proposal });
  await renderAvui();
  expect(await screen.findByText(/Proposta del coach/)).toBeOnTheScreen();
  expect(screen.getByText(/Mode prova/)).toBeOnTheScreen();
  expect(screen.getByText(/Ds 29 · Sèries 5×1000/)).toBeOnTheScreen();
  expect(screen.getByText(/→ Rodatge suau · 40 min/)).toBeOnTheScreen();
  expect(getSessionsByIds).toHaveBeenCalledWith([1]);
});

test('un informe que ho manté tot no mostra cap targeta', async () => {
  await renderAvui();
  await screen.findByText('Rodatge suau en lloc de sèries.');
  expect(screen.queryByText(/Proposta del coach/)).toBeNull();
});

test('una proposta oberta d\'un altre informe també surt, i Aplica envia la decisió i recarrega', async () => {
  (getOpenProposals as jest.Mock).mockResolvedValue([{ ...proposal, id: 9, status: 'proposed', classification: { auto: false, reasons: ['sessió clau'] } }]);
  (getSetting as jest.Mock).mockResolvedValue('hybrid');
  await renderAvui();
  expect(await screen.findByText(/Pendent de tu/)).toBeOnTheScreen();
  const { Alert } = require('react-native');
  jest.spyOn(Alert, 'alert').mockImplementation((_t: any, _m: any, buttons: any) => buttons?.find((b: any) => b.style !== 'cancel')?.onPress?.());
  const user = userEvent.setup();
  await user.press(screen.getByText('Aplica'));
  await waitFor(() => expect(sendDecision).toHaveBeenCalledWith(9, 'apply'));
  await waitFor(() => expect(getOpenProposals).toHaveBeenCalledTimes(2));
});
