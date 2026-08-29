jest.mock('@/lib/use-session', () => ({ useSession: jest.fn() }));

jest.mock('expo-router', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const Stack = ({ children }: any) => React.createElement(React.Fragment, null, children);
  Stack.Screen = ({ name }: any) => React.createElement(Text, null, `screen:${name}`);
  Stack.Protected = ({ guard, children }: any) =>
    guard ? React.createElement(React.Fragment, null, children) : null;
  return { Stack };
});

import { render, screen } from '@testing-library/react-native';
import { useSession } from '@/lib/use-session';
import RootLayout from '@/app/_layout';

const mockUseSession = useSession as jest.Mock;

test('sense sessió: només es pot arribar al login', async () => {
  mockUseSession.mockReturnValue({ session: null, loading: false });
  await render(<RootLayout />);
  expect(screen.getByText('screen:login')).toBeOnTheScreen();
  expect(screen.queryByText('screen:(tabs)')).toBeNull();
});

test('amb sessió: pestanyes visibles i login fora', async () => {
  mockUseSession.mockReturnValue({ session: { user: { id: 'roger' } }, loading: false });
  await render(<RootLayout />);
  expect(screen.getByText('screen:(tabs)')).toBeOnTheScreen();
  expect(screen.queryByText('screen:login')).toBeNull();
});

test('mentre carrega la sessió desada no es mostra res (ni flaix de login)', async () => {
  mockUseSession.mockReturnValue({ session: null, loading: true });
  await render(<RootLayout />);
  expect(screen.toJSON()).toBeNull();
});
