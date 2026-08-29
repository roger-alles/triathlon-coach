jest.mock('@/lib/supabase', () => ({
  supabase: { auth: { signInWithPassword: jest.fn() } },
}));

import { render, screen, userEvent } from '@testing-library/react-native';
import { supabase } from '@/lib/supabase';
import LoginScreen from './login';

const mockSignIn = supabase.auth.signInWithPassword as jest.Mock;

beforeEach(() => jest.clearAllMocks());

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText('Email'), 'roger@example.com');
  await user.type(screen.getByPlaceholderText('Contrasenya'), 'secreta');
  await user.press(screen.getByText('Entra'));
}

test('envia email i contrasenya a Supabase', async () => {
  mockSignIn.mockResolvedValue({ error: null });
  await render(<LoginScreen />);
  await fillAndSubmit();
  expect(mockSignIn).toHaveBeenCalledWith({ email: 'roger@example.com', password: 'secreta' });
});

test('mostra un error clar si les credencials són dolentes', async () => {
  mockSignIn.mockResolvedValue({ error: { message: 'Invalid login credentials' } });
  await render(<LoginScreen />);
  await fillAndSubmit();
  expect(screen.getByText(/Email o contrasenya incorrectes/)).toBeOnTheScreen();
});

test('mostra l\'error original si és un altre problema (p. ex. xarxa)', async () => {
  mockSignIn.mockResolvedValue({ error: { message: 'Network request failed' } });
  await render(<LoginScreen />);
  await fillAndSubmit();
  expect(screen.getByText(/Network request failed/)).toBeOnTheScreen();
});
