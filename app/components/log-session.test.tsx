jest.mock('@/lib/api', () => ({ logManualActivity: jest.fn() }));

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
