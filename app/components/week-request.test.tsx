jest.mock('@/lib/supabase', () => ({ supabase: {} }));
jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  getWeekRequest: jest.fn(),
  requestWeekRedesign: jest.fn(),
}));

import { act, render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { getWeekRequest, requestWeekRedesign } from '@/lib/api';
import WeekRequestBox from './week-request';

const mockGet = getWeekRequest as jest.Mock;
const mockSend = requestWeekRedesign as jest.Mock;

const base = { id: 3, error: null, text: 'dijous no puc', createdAt: '2026-10-07T08:00:00Z', summary: null, rationale: null };

beforeEach(() => {
  jest.clearAllMocks();
  mockGet.mockResolvedValue(null);
  mockSend.mockResolvedValue(undefined);
});

test('escriure i demanar envia la petició de la setmana i mostra que està enviada', async () => {
  await render(<WeekRequestBox weekStart="2026-10-05" onApplied={jest.fn()} />);
  await waitFor(() => expect(mockGet).toHaveBeenCalledWith('2026-10-05'));
  mockGet.mockResolvedValue({ ...base, status: 'pending' });
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText(/Què vols canviar/), 'dijous no puc');
  await user.press(screen.getByText('Demana'));
  await waitFor(() => expect(mockSend).toHaveBeenCalledWith('2026-10-05', 'dijous no puc'));
  expect(await screen.findByText(/Enviada/)).toBeOnTheScreen();
  expect(screen.getByText(/Has demanat: «dijous no puc»/)).toBeOnTheScreen();
});

test('mentre el coach hi treballa no es pot demanar una altra cosa', async () => {
  mockGet.mockResolvedValue({ ...base, status: 'processing' });
  await render(<WeekRequestBox weekStart="2026-10-05" onApplied={jest.fn()} />);
  expect(await screen.findByText(/està redissenyant/)).toBeOnTheScreen();
  expect(screen.getByRole('button')).toBeDisabled();
});

test('una petició resposta ensenya què ha canviat; una de fallida, per què', async () => {
  mockGet.mockResolvedValue({ ...base, status: 'answered', summary: 'Dijous lliure: natació a divendres', rationale: 'He mogut…' });
  const { unmount } = await render(<WeekRequestBox weekStart="2026-10-05" onApplied={jest.fn()} />);
  expect(await screen.findByText('Fet: Dijous lliure: natació a divendres')).toBeOnTheScreen();
  expect(screen.getByText('He mogut…')).toBeOnTheScreen();
  await unmount();
  mockGet.mockResolvedValue({ ...base, status: 'failed', error: 'avui ja s’han fet 3 redissenys' });
  await render(<WeekRequestBox weekStart="2026-10-05" onApplied={jest.fn()} />);
  expect(await screen.findByText(/No s'ha pogut: avui ja s’han fet 3 redissenys/)).toBeOnTheScreen();
});

test('quan el coach acaba, es refresca sol i avisa la setmana perquè es recarregui', async () => {
  jest.useFakeTimers();
  const onApplied = jest.fn();
  mockGet.mockResolvedValue({ ...base, status: 'processing' });
  await render(<WeekRequestBox weekStart="2026-10-05" onApplied={onApplied} />);
  await screen.findByText(/està redissenyant/);
  mockGet.mockResolvedValue({ ...base, status: 'answered', summary: 'Fet i fet' });
  await act(async () => { jest.advanceTimersByTime(20000); });
  expect(await screen.findByText('Fet: Fet i fet')).toBeOnTheScreen();
  expect(onApplied).toHaveBeenCalledTimes(1);
  jest.useRealTimers();
});
