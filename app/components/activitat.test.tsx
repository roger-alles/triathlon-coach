jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  getActivity: jest.fn(),
  updateActivitySubjective: jest.fn(),
  getAssignableSessions: jest.fn(),
  assignActivity: jest.fn(),
  deleteManualActivity: jest.fn(),
}));
jest.mock('@/lib/supabase', () => ({ supabase: {} }));
const mockBack = jest.fn();
jest.mock('expo-router', () => ({ router: { back: () => mockBack() } }));

import { Alert } from 'react-native';
import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { assignActivity, deleteManualActivity, getActivity, getAssignableSessions, updateActivitySubjective } from '@/lib/api';
import Activitat from './activitat';

const mockGet = getActivity as jest.Mock;
const mockUpdate = updateActivitySubjective as jest.Mock;

const activity = {
  id: 3,
  local_date: '2026-08-27',
  sport: 'bike',
  duration_sec: 9237,
  distance_m: 67836,
  avg_hr: 132,
  max_hr: 171,
  avg_pace_sec_km: null,
  avg_pace_sec_100m: null,
  elevation_gain_m: 520,
  load: 359,
  perceived_effort: null,
  feeling: null,
  athlete_notes: null,
  plan_session_id: 23,
  linked_by_athlete: false,
};

const runSat = { id: 82, local_date: '2026-10-03', sport: 'run', title: 'Primer contacte suau', status: 'missed',
                 session_type: 'easy', duration_sec_target: 1200, distance_m_target: null, structure: null,
                 rationale: null, is_test: false, priority: 'optional' };

const confirmAlerts = () =>
  jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons) => {
    buttons?.find((b) => b.style !== 'cancel')?.onPress?.();
  });

beforeEach(() => {
  jest.clearAllMocks();
  mockGet.mockResolvedValue(activity);
  mockUpdate.mockResolvedValue(undefined);
  (getAssignableSessions as jest.Mock).mockResolvedValue([]);
  (assignActivity as jest.Mock).mockResolvedValue(undefined);
  (deleteManualActivity as jest.Mock).mockResolvedValue(undefined);
});

test('mostra les mètriques reals de la sortida', async () => {
  await render(<Activitat id={3} />);
  expect(await screen.findByText(/🚴 Bici/)).toBeOnTheScreen();
  expect(screen.getByText(/2 h 34 min/)).toBeOnTheScreen();
  expect(screen.getByText(/67.8 km/)).toBeOnTheScreen();
  expect(screen.getByText(/132/)).toBeOnTheScreen();
  expect(screen.getByText(/359/)).toBeOnTheScreen();
});

test('desa RPE, sensació i notes amb un sol botó', async () => {
  await render(<Activitat id={3} />);
  await screen.findByText(/Bici/);

  const user = userEvent.setup();
  await user.press(screen.getByText('7'));       // RPE 7
  await user.press(screen.getByText('Bé'));      // feeling 4
  await user.type(screen.getByPlaceholderText(/Notes/), 'genoll perfecte');
  await user.press(screen.getByText('Desa'));

  await waitFor(() =>
    expect(mockUpdate).toHaveBeenCalledWith(3, {
      perceived_effort: 7,
      feeling: 4,
      athlete_notes: 'genoll perfecte',
    })
  );
  expect(await screen.findByText(/Desat/)).toBeOnTheScreen();
});

test("si el desat falla, l'error es veu", async () => {
  mockUpdate.mockRejectedValue(new Error('permission denied'));
  await render(<Activitat id={3} />);
  await screen.findByText(/Bici/);

  const user = userEvent.setup();
  await user.press(screen.getByText('5'));
  await user.press(screen.getByText('Desa'));
  expect(await screen.findByText(/permission denied/)).toBeOnTheScreen();
});

test('valors ja desats apareixen preseleccionats', async () => {
  mockGet.mockResolvedValue({ ...activity, perceived_effort: 6, feeling: 3, athlete_notes: 'dur' });
  await render(<Activitat id={3} />);
  await screen.findByText(/Bici/);
  expect(screen.getByDisplayValue('dur')).toBeOnTheScreen();
});

test("dies intercanviats: una cursa de Garmin fora de pla s'assigna a la sessió d'ahir", async () => {
  const run = { ...activity, id: 24598098311, local_date: '2026-10-04', sport: 'run', plan_session_id: null };
  mockGet.mockResolvedValue(run);
  (getAssignableSessions as jest.Mock).mockResolvedValue([runSat]);
  confirmAlerts();
  await render(<Activitat id={run.id} />);
  expect(await screen.findByText(/✓ Fora de pla/)).toBeOnTheScreen();
  expect(getAssignableSessions).toHaveBeenCalledWith('run', '2026-10-04');
  const user = userEvent.setup();
  await user.press(screen.getByText(/Ds 3 · .* Primer contacte suau/));
  await waitFor(() => expect(assignActivity).toHaveBeenCalledWith(24598098311, 82));
  expect(await screen.findByText(/✓ Ds 3/)).toBeOnTheScreen();
  expect(screen.getByText(/propera sincronització/)).toBeOnTheScreen();
  // Garmin: no es pot esborrar
  expect(screen.queryByText(/Esborra aquesta entrada/)).toBeNull();
});

test('marcar fora de pla desvincula; tornar a tocar la mateixa sessió no fa res', async () => {
  mockGet.mockResolvedValue({ ...activity, plan_session_id: 82, local_date: '2026-10-03', sport: 'run' });
  (getAssignableSessions as jest.Mock).mockResolvedValue([runSat]);
  confirmAlerts();
  await render(<Activitat id={3} />);
  const user = userEvent.setup();
  await user.press(await screen.findByText(/✓ Ds 3/));
  expect(assignActivity).not.toHaveBeenCalled();
  await user.press(screen.getByText('Fora de pla'));
  await waitFor(() => expect(assignActivity).toHaveBeenCalledWith(3, null));
});

test("una entrada manual es pot esborrar, amb confirmació, i es torna enrere", async () => {
  mockGet.mockResolvedValue({ ...activity, id: -20261003092709, plan_session_id: 82 });
  confirmAlerts();
  await render(<Activitat id={-20261003092709} />);
  const user = userEvent.setup();
  await user.press(await screen.findByText('Esborra aquesta entrada manual'));
  await waitFor(() => expect(deleteManualActivity).toHaveBeenCalledWith(-20261003092709));
  expect(mockBack).toHaveBeenCalled();
});
