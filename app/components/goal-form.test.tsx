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

// --- S2b: temps objectiu ---------------------------------------------------

test('cursa amb temps objectiu: es desa com a escenari central de target_times_sec.total', async () => {
  await render(<GoalForm onDone={() => {}} onCancel={() => {}} />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Nom'), '10 km Bombers');
  await user.press(screen.getByText('Cursa'));
  await user.type(screen.getByLabelText('Distància (km)'), '10');
  await user.type(screen.getByLabelText('Temps objectiu (h:mm:ss)'), '36:30');
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(mockUpsert).toHaveBeenCalledTimes(1));
  expect(mockUpsert.mock.calls[0][0].profile).toEqual({
    segments: [{ sport: 'run', distance_m: 10000 }],
    target_times_sec: { total: [null, 2190, null] },
  });
});

test('triatló: un temps per segment i el total és la suma', async () => {
  await render(<GoalForm onDone={() => {}} onCancel={() => {}} />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Nom'), 'Banyoles');
  await user.type(screen.getByLabelText('Natació (h:mm:ss)'), '30:00');
  await user.type(screen.getByLabelText('Bici (h:mm:ss)'), '1:10:00');
  await user.type(screen.getByLabelText('Córrer (h:mm:ss)'), '40:00');
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(mockUpsert).toHaveBeenCalledTimes(1));
  expect(mockUpsert.mock.calls[0][0].profile.target_times_sec).toEqual({
    swim: [null, 1800, null], bike: [null, 4200, null], run: [null, 2400, null], total: [null, 8400, null],
  });
});

test('ultra: els dies es desen a profile.days', async () => {
  await render(<GoalForm onDone={() => {}} onCancel={() => {}} />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Nom'), 'Transpirinenca');
  await user.press(screen.getByText('Ultra'));
  await user.type(screen.getByLabelText('Distància (km)'), '800');
  await user.type(screen.getByLabelText('Dies'), '7');
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(mockUpsert).toHaveBeenCalledTimes(1));
  expect(mockUpsert.mock.calls[0][0].profile).toEqual({
    segments: [{ sport: 'bike', distance_m: 800000 }],
    days: 7,
  });
});

test('un temps mal escrit bloqueja el desar amb un missatge', async () => {
  await render(<GoalForm onDone={() => {}} onCancel={() => {}} />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Nom'), 'X');
  await user.press(screen.getByText('Cursa'));
  await user.type(screen.getByLabelText('Temps objectiu (h:mm:ss)'), '36 minuts');
  await user.press(screen.getByText('Desa'));
  expect(mockUpsert).not.toHaveBeenCalled();
  expect(screen.getByText(/h:mm:ss o mm:ss/)).toBeOnTheScreen();
});

test('un objectiu amb tres escenaris (Fornells) es preomple amb el central i no es reescriu si no es toca', async () => {
  const fornells = {
    id: 2, name: 'Fornells', discipline: 'triathlon' as const, event_date: '2026-09-27', priority: 'A' as const,
    status: 'active' as const, notes: null,
    profile: {
      segments: [{ sport: 'swim', distance_m: 1000 }, { sport: 'bike', distance_m: 34000 }, { sport: 'run', distance_m: 9000 }],
      target_times_sec: {
        swim: [1560, 1380, 1200], t1: [180, 135, 105], bike: [3960, 3720, 3480], t2: [90, 70, 55],
        run: [2320, 2160, 2065], total: [8110, 7470, 6895], note: 'sector a peu de 9 km',
      },
    },
  };
  await render(<GoalForm goal={fornells} onDone={() => {}} onCancel={() => {}} />);
  expect(screen.getByDisplayValue('23:00')).toBeOnTheScreen();   // natació objectiu
  expect(screen.getByDisplayValue('1:02:00')).toBeOnTheScreen(); // bici objectiu
  const user = userEvent.setup();
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(mockUpsert).toHaveBeenCalledTimes(1));
  expect(mockUpsert.mock.calls[0][0].profile.target_times_sec).toEqual(fornells.profile.target_times_sec);

  // canviar només la cursa reescriu aquesta clau i el total; la resta queda
  await user.clear(screen.getByLabelText('Córrer (h:mm:ss)'));
  await user.type(screen.getByLabelText('Córrer (h:mm:ss)'), '35:00');
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(mockUpsert).toHaveBeenCalledTimes(2));
  const t = mockUpsert.mock.calls[1][0].profile.target_times_sec;
  expect(t.run).toEqual([null, 2100, null]);
  expect(t.swim).toEqual([1560, 1380, 1200]);
  expect(t.t1).toEqual([180, 135, 105]);
  expect(t.total).toEqual([null, 1380 + 135 + 3720 + 70 + 2100, null]);
  expect(t.note).toBe('sector a peu de 9 km');
});
