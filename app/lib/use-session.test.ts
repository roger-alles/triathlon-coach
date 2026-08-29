jest.mock('./supabase', () => ({
  supabase: { auth: { getSession: jest.fn(), onAuthStateChange: jest.fn() } },
}));

import { act, renderHook } from '@testing-library/react-native';
import { supabase } from './supabase';
import { useSession } from './use-session';

const mockGetSession = supabase.auth.getSession as jest.Mock;
const mockOnAuthStateChange = supabase.auth.onAuthStateChange as jest.Mock;
const mockUnsubscribe = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  mockGetSession.mockResolvedValue({ data: { session: null } });
  mockOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: mockUnsubscribe } } });
});

test('comença carregant i acaba sense sessió si no n\'hi ha cap de desada', async () => {
  let resolveSession!: (v: unknown) => void;
  mockGetSession.mockReturnValue(new Promise((r) => (resolveSession = r)));

  const { result } = await renderHook(() => useSession());
  expect(result.current.loading).toBe(true);

  await act(async () => resolveSession({ data: { session: null } }));
  expect(result.current.loading).toBe(false);
  expect(result.current.session).toBeNull();
});

test('exposa la sessió desada i reacciona als canvis (login/logout)', async () => {
  const stored = { user: { id: 'roger' } };
  mockGetSession.mockResolvedValue({ data: { session: stored } });

  const { result, unmount } = await renderHook(() => useSession());
  expect(result.current.session).toEqual(stored);

  const onChange = mockOnAuthStateChange.mock.calls[0][0];
  await act(async () => onChange('SIGNED_OUT', null));
  expect(result.current.session).toBeNull();

  await unmount();
  expect(mockUnsubscribe).toHaveBeenCalled();
});
