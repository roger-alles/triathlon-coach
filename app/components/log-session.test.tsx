jest.mock('@/lib/supabase', () => ({ supabase: {} }));
jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  logManualActivity: jest.fn(),
  localDateISO: () => '2026-09-14',
}));

import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { logManualActivity } from '@/lib/api';
import LogSession from './log-session';

const mockLog = logManualActivity as jest.Mock;

const swim = {
  id: 43,
  sport: 'swim',
  session_type: 'race_pace',
  title: 'Ritme de cursa amb orientació',
  status: 'planned',
  duration_sec_target: 2400,
  distance_m_target: 1600,
  structure: null,
  rationale: null,
  is_test: false,
  priority: 'support' as const,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockLog.mockResolvedValue(undefined);
});

test('natació sense rellotge: durada i distància del pla, lloc, RPE, i queda registrada', async () => {
  await render(<LogSession session={swim} dateISO="2026-09-10" />);
  const user = userEvent.setup();
  await user.press(screen.getByText('Ho he fet'));
  // els valors del pla venen preomplerts
  expect(screen.getByDisplayValue('40')).toBeOnTheScreen();
  expect(screen.getByDisplayValue('1600')).toBeOnTheScreen();
  await user.press(screen.getByText('Piscina'));
  await user.press(screen.getByText('6'));
  await user.type(screen.getByPlaceholderText(/Notes/), 'els 400 a 2:16');
  await user.press(screen.getByText('Registra'));
  await waitFor(() => expect(mockLog).toHaveBeenCalledTimes(1));
  expect(mockLog.mock.calls[0][0]).toEqual({
    local_date: '2026-09-10',
    sport: 'swim',
    sub_sport: 'lap_swimming',
    duration_sec: 2400,
    distance_m: 1600,
    perceived_effort: 6,
    athlete_notes: 'els 400 a 2:16',
    plan_session_id: 43,
  });
  expect(await screen.findByText(/Registrada/)).toBeOnTheScreen();
  expect(screen.queryByText('Ho he fet')).toBeNull();
});

test('la durada es pot canviar; buida no deixa registrar', async () => {
  await render(<LogSession session={{ ...swim, sport: 'run', distance_m_target: null }} dateISO="2026-09-10" />);
  const user = userEvent.setup();
  await user.press(screen.getByText('Ho he fet'));
  const durada = screen.getByDisplayValue('40');
  await user.clear(durada);
  await user.press(screen.getByText('Registra'));
  expect(mockLog).not.toHaveBeenCalled();
  await user.type(durada, '35');
  await user.press(screen.getByText('Registra'));
  await waitFor(() => expect(mockLog).toHaveBeenCalledTimes(1));
  expect(mockLog.mock.calls[0][0].duration_sec).toBe(2100);
  expect(mockLog.mock.calls[0][0].sub_sport).toBeUndefined();
  expect(mockLog.mock.calls[0][0].distance_m).toBeNull();
});

test('un error de la BD es mostra i el botó torna', async () => {
  mockLog.mockRejectedValue(new Error('permission denied'));
  await render(<LogSession session={swim} dateISO="2026-09-10" />);
  const user = userEvent.setup();
  await user.press(screen.getByText('Ho he fet'));
  await user.press(screen.getByText('Registra'));
  expect(await screen.findByText(/permission denied/)).toBeOnTheScreen();
});

test('descans i sessions ja fetes no ofereixen el botó', async () => {
  const { rerender } = await render(<LogSession session={{ ...swim, sport: 'rest' }} dateISO="2026-09-10" />);
  expect(screen.queryByText('Ho he fet')).toBeNull();
  await rerender(<LogSession session={{ ...swim, status: 'completed' }} dateISO="2026-09-10" />);
  expect(screen.queryByText('Ho he fet')).toBeNull();
});

test("una sessió perduda d'un dia passat es pot registrar, i el dia es pot canviar", async () => {
  await render(<LogSession session={{ ...swim, status: 'missed' }} dateISO="2026-09-10" />);
  const user = userEvent.setup();
  await user.press(screen.getByText('Ho he fet'));
  // el dia ve preomplert amb el de la sessió; la va fer l'endemà
  const dia = screen.getByDisplayValue('2026-09-10');
  await user.clear(dia);
  await user.type(dia, '2026-09-11');
  await user.press(screen.getByText('Registra'));
  await waitFor(() => expect(mockLog).toHaveBeenCalledTimes(1));
  expect(mockLog.mock.calls[0][0]).toMatchObject({ local_date: '2026-09-11', plan_session_id: 43 });
});

test('un dia futur o mal escrit no deixa registrar; el xip Avui posa el dia d\'avui', async () => {
  await render(<LogSession session={{ ...swim, status: 'missed' }} dateISO="2026-09-10" />);
  const user = userEvent.setup();
  await user.press(screen.getByText('Ho he fet'));
  const dia = screen.getByDisplayValue('2026-09-10');
  await user.clear(dia);
  await user.type(dia, '2026-09-20');
  await user.press(screen.getByText('Registra'));
  expect(mockLog).not.toHaveBeenCalled();
  await user.press(screen.getByText('Avui'));
  expect(screen.getByDisplayValue('2026-09-14')).toBeOnTheScreen();
  await user.press(screen.getByText('Registra'));
  await waitFor(() => expect(mockLog).toHaveBeenCalledTimes(1));
  expect(mockLog.mock.calls[0][0].local_date).toBe('2026-09-14');
});

const simulacre = {
  ...swim,
  id: 45,
  sport: 'multisport',
  title: 'SIMULACRE COMPLET DE CURSA',
  duration_sec_target: 7200,
  distance_m_target: null,
  structure: {
    segments: [
      { sport: 'swim', venue: 'open_water', distance_m: 800 },
      { sport: 'transition', timed: true, transition: 't1' },
      { sport: 'bike', distance_m: 34000 },
      { sport: 'transition', timed: true, transition: 't2' },
      { sport: 'run', distance_m: 3000 },
    ],
  },
};

test('un multisport es registra per trams; els altres trams continuen disponibles', async () => {
  await render(<LogSession session={simulacre} dateISO="2026-09-12" />);
  const user = userEvent.setup();
  expect(screen.getByText('Ho he fet · natació 800 m')).toBeOnTheScreen();
  expect(screen.getByText('Ho he fet · bici 34 km')).toBeOnTheScreen();
  expect(screen.getByText('Ho he fet · cursa 3 km')).toBeOnTheScreen();
  await user.press(screen.getByText('Ho he fet · natació 800 m'));
  expect(screen.getByDisplayValue('800')).toBeOnTheScreen();
  // el segment no porta durada: sense minuts no es pot registrar
  await user.press(screen.getByText('Registra'));
  expect(mockLog).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText('Minuts'), '18');
  // el lloc ve del segment (mar), es pot canviar però no cal
  await user.press(screen.getByText('Registra'));
  await waitFor(() => expect(mockLog).toHaveBeenCalledTimes(1));
  expect(mockLog.mock.calls[0][0]).toMatchObject({
    local_date: '2026-09-12', sport: 'swim', sub_sport: 'open_water', distance_m: 800, duration_sec: 1080, plan_session_id: 45,
  });
  expect(await screen.findByText(/Registrada natació/)).toBeOnTheScreen();
  expect(screen.queryByText('Ho he fet · natació 800 m')).toBeNull();
  expect(screen.getByText('Ho he fet · bici 34 km')).toBeOnTheScreen();
  expect(screen.getByText('Ho he fet · cursa 3 km')).toBeOnTheScreen();
});

test('els trams que ja tenen activitat no ofereixen botó', async () => {
  await render(<LogSession session={simulacre} dateISO="2026-09-12" logged={new Set(['bike', 'run'])} />);
  expect(screen.getByText('Ho he fet · natació 800 m')).toBeOnTheScreen();
  expect(screen.queryByText(/bici 34 km/)).toBeNull();
  expect(screen.queryByText(/cursa 3 km/)).toBeNull();
});

test('un brick es registra com la cursa del brick, i avisa qui escolta', async () => {
  const onSaved = jest.fn();
  const brick = { ...swim, id: 68, sport: 'brick', title: 'Brick', duration_sec_target: 600, distance_m_target: null };
  await render(<LogSession session={brick} dateISO="2026-09-10" onSaved={onSaved} />);
  const user = userEvent.setup();
  await user.press(screen.getByText('Ho he fet · cursa del brick'));
  expect(screen.getByDisplayValue('10')).toBeOnTheScreen();
  await user.press(screen.getByText('Registra'));
  await waitFor(() => expect(mockLog).toHaveBeenCalledTimes(1));
  expect(mockLog.mock.calls[0][0]).toMatchObject({ sport: 'run', duration_sec: 600, plan_session_id: 68 });
  expect(onSaved).toHaveBeenCalledTimes(1);
});
