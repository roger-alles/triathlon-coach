jest.mock('@/lib/supabase', () => ({ supabase: {} }));
jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  upsertGoal: jest.fn(),
  abandonGoal: jest.fn(),
}));

import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import { abandonGoal, upsertGoal } from '@/lib/api';
import GoalForm from './goal-form';

const mockUpsert = upsertGoal as jest.Mock;
const mockAbandon = abandonGoal as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  mockUpsert.mockResolvedValue(undefined);
  mockAbandon.mockResolvedValue(undefined);
});

test('objectiu nou: cursa, sense data, prioritat C, 10 km → upsertGoal amb el perfil', async () => {
  const onDone = jest.fn();
  await render(<GoalForm onDone={onDone} onCancel={() => {}} />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Nom'), '10 km popular');
  await user.press(screen.getByText('Cursa'));
  await user.press(screen.getByText('C'));
  // sense data: el camp Data queda buit i no bloqueja
  await user.type(screen.getByLabelText('Distància (km)'), '10');
  await user.type(screen.getByLabelText('Notes'), 'quan surti una a prop');
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(mockUpsert).toHaveBeenCalledTimes(1));
  expect(mockUpsert.mock.calls[0][0]).toEqual({
    name: '10 km popular',
    discipline: 'run',
    event_date: null,
    priority: 'C',
    notes: 'quan surti una a prop',
    profile: { segments: [{ sport: 'run', distance_m: 10000 }] },
  });
  expect(onDone).toHaveBeenCalled();
});

test('triatló: tres distàncies (natació m, bici km, cursa km) i data', async () => {
  await render(<GoalForm onDone={() => {}} onCancel={() => {}} />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Nom'), 'Olímpic de Banyoles');
  await user.press(screen.getByText('Triatló'));
  await user.type(screen.getByLabelText('Data'), '2027-05-16');
  await user.type(screen.getByLabelText('Natació (m)'), '1500');
  await user.type(screen.getByLabelText('Bici (km)'), '40');
  await user.type(screen.getByLabelText('Cursa (km)'), '10');
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(mockUpsert).toHaveBeenCalledTimes(1));
  expect(mockUpsert.mock.calls[0][0]).toMatchObject({
    discipline: 'triathlon',
    event_date: '2027-05-16',
    priority: 'A',
    profile: { segments: [
      { sport: 'swim', distance_m: 1500 }, { sport: 'bike', distance_m: 40000 }, { sport: 'run', distance_m: 10000 },
    ] },
  });
});

test('sense nom, o amb data mal escrita, no es pot desar', async () => {
  await render(<GoalForm onDone={() => {}} onCancel={() => {}} />);
  const user = userEvent.setup();
  await user.press(screen.getByText('Desa'));
  expect(mockUpsert).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText('Nom'), 'X');
  await user.type(screen.getByLabelText('Data'), '16/05/2027');
  await user.press(screen.getByText('Desa'));
  expect(mockUpsert).not.toHaveBeenCalled();
  expect(screen.getByText(/AAAA-MM-DD/)).toBeOnTheScreen();
});

test('editar preomple i envia amb id; abandonar demana confirmació i crida abandonGoal', async () => {
  const existing = {
    id: 4, name: '10 km popular', discipline: 'run' as const, event_date: null, priority: 'C' as const,
    status: 'active' as const, notes: 'x', profile: { segments: [{ sport: 'run', distance_m: 10000 }] },
  };
  const onDone = jest.fn();
  jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons) => {
    const yes = buttons?.find((b) => b.style === 'destructive');
    yes?.onPress?.();
  });
  await render(<GoalForm goal={existing} onDone={onDone} onCancel={() => {}} />);
  expect(screen.getByDisplayValue('10 km popular')).toBeOnTheScreen();
  expect(screen.getByDisplayValue('10')).toBeOnTheScreen();
  const user = userEvent.setup();
  await user.clear(screen.getByLabelText('Nom'));
  await user.type(screen.getByLabelText('Nom'), '10 km Bombers');
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(mockUpsert).toHaveBeenCalledTimes(1));
  expect(mockUpsert.mock.calls[0][0]).toMatchObject({ id: 4, name: '10 km Bombers' });

  await user.press(screen.getByText('Abandona'));
  await waitFor(() => expect(mockAbandon).toHaveBeenCalledWith(4));
  expect(onDone).toHaveBeenCalledTimes(2);
});
