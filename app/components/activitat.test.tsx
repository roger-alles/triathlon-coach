jest.mock('@/lib/api', () => ({
  getActivity: jest.fn(),
  updateActivitySubjective: jest.fn(),
}));

import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { getActivity, updateActivitySubjective } from '@/lib/api';
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
};

beforeEach(() => {
  jest.clearAllMocks();
  mockGet.mockResolvedValue(activity);
  mockUpdate.mockResolvedValue(undefined);
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
