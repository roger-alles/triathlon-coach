jest.mock('@/lib/supabase', () => ({ supabase: { auth: { signOut: jest.fn() } } }));
jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  getAthlete: jest.fn(),
  updateAthleteProfile: jest.fn(),
  getSetting: jest.fn(),
  setSetting: jest.fn(),
}));

import { fireEvent, render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getAthlete, getSetting, setSetting, updateAthleteProfile } from '@/lib/api';
import { supabase } from '@/lib/supabase';
import Jo from './jo';

const athlete = {
  id: 1,
  name: 'Roger',
  birth_date: '2005-01-01',
  max_hr: 211,
  profile: {
    health: { knee: 'protuberància òssia' },
    known: { run_10k_pr_sec: 2250 },
    constraints: {
      fixed_rest_day: 'monday',
      weekly_hours_ceiling: 8,
      pool_availability: 'total, tots els dies',
      gym: false,
      power_meter: false,
    },
  },
};

const renderJo = () =>
  render(
    <SafeAreaProvider
      initialMetrics={{
        insets: { top: 59, left: 0, right: 0, bottom: 34 },
        frame: { x: 0, y: 0, width: 390, height: 844 },
      }}>
      <Jo />
    </SafeAreaProvider>
  );

const confirmAlerts = () => {
  const { Alert } = require('react-native');
  jest.spyOn(Alert, 'alert').mockImplementation((_t: any, _m: any, buttons: any) => buttons?.find((b: any) => b.style !== 'cancel')?.onPress?.());
};

beforeEach(() => {
  jest.clearAllMocks();
  (getAthlete as jest.Mock).mockResolvedValue(athlete);
  (updateAthleteProfile as jest.Mock).mockResolvedValue(undefined);
  (getSetting as jest.Mock).mockResolvedValue('dry_run');
  (setSetting as jest.Mock).mockResolvedValue(undefined);
});

test('pinta el perfil: nom, dia de descans, hores, piscina', async () => {
  await renderJo();
  expect(await screen.findByText(/Roger/)).toBeOnTheScreen();
  expect(screen.getByDisplayValue('8')).toBeOnTheScreen();
  expect(screen.getByDisplayValue('total, tots els dies')).toBeOnTheScreen();
  // el xip de dilluns (descans) està actiu; els 7 dies disponibles també
  expect(screen.getByLabelText('Descans Dl').props.accessibilityState?.selected).toBe(true);
  expect(screen.getByLabelText('Descans Dt').props.accessibilityState?.selected).toBe(false);
  expect(screen.getByLabelText('Disponible Dg').props.accessibilityState?.selected).toBe(true);
});

test('desar fusiona el perfil: conserva health/known i escriu constraints i notes', async () => {
  await renderJo();
  await screen.findByDisplayValue('8');
  const user = userEvent.setup();
  await user.clear(screen.getByLabelText('Hores màximes per setmana'));
  await user.type(screen.getByLabelText('Hores màximes per setmana'), '7');
  await user.press(screen.getByLabelText('Descans Dc'));
  await user.press(screen.getByLabelText('Disponible Dg'));
  await user.type(screen.getByLabelText('Notes per al coach'), 'Vacances a l’agost');
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(updateAthleteProfile).toHaveBeenCalledTimes(1));
  expect((updateAthleteProfile as jest.Mock).mock.calls[0][0]).toEqual({
    health: { knee: 'protuberància òssia' },
    known: { run_10k_pr_sec: 2250 },
    constraints: {
      fixed_rest_day: 'wednesday',
      weekly_hours_ceiling: 7,
      available_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'],
      pool_availability: 'total, tots els dies',
      gym: false,
      power_meter: false,
    },
    notes: 'Vacances a l’agost',
  });
  expect(await screen.findByText('Desat')).toBeOnTheScreen();
});

test('tots els dies disponibles es desa com a llista buida; "Cap" treu el dia de descans', async () => {
  await renderJo();
  await screen.findByDisplayValue('8');
  const user = userEvent.setup();
  await user.press(screen.getByLabelText('Descans Cap'));
  await user.press(screen.getByText('Desa'));
  await waitFor(() => expect(updateAthleteProfile).toHaveBeenCalledTimes(1));
  const written = (updateAthleteProfile as jest.Mock).mock.calls[0][0];
  expect(written.constraints.fixed_rest_day).toBeNull();
  expect(written.constraints.available_days).toEqual([]);
  expect(written.notes).toBeNull();
});

test("l'interruptor del coach llegeix el mode, i activar-lo confirma i escriu 'hybrid'", async () => {
  confirmAlerts();
  await renderJo();
  const sw = (await screen.findAllByRole('switch')).find((s) => s.props.accessibilityLabel === 'mode híbrid')!;
  expect(sw.props.value).toBe(false);
  expect(screen.getByText(/mode prova/i)).toBeOnTheScreen();
  fireEvent(sw, 'valueChange', true);
  await waitFor(() => expect(setSetting).toHaveBeenCalledWith('coach_apply_mode', 'hybrid'));
});

test('Surt tanca la sessió', async () => {
  await renderJo();
  await screen.findByText('Surt');
  const user = userEvent.setup();
  await user.press(screen.getByText('Surt'));
  expect(supabase.auth.signOut).toHaveBeenCalled();
});
