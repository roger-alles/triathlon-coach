import { renderHook } from '@testing-library/react-native';
import { AppState } from 'react-native';

import { useOnForeground } from './use-foreground';

let listener: (state: string) => void;
const mockRemove = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_type, fn) => {
    listener = fn as (state: string) => void;
    return { remove: mockRemove } as any;
  });
  Object.defineProperty(AppState, 'currentState', { value: 'active', configurable: true });
});

test("crida la funció quan l'app torna de segon pla", async () => {
  const onForeground = jest.fn();
  await renderHook(() => useOnForeground(onForeground));
  listener('background');
  expect(onForeground).not.toHaveBeenCalled();
  listener('active');
  expect(onForeground).toHaveBeenCalledTimes(1);
});

test('no la crida si l\'app ja era activa', async () => {
  const onForeground = jest.fn();
  await renderHook(() => useOnForeground(onForeground));
  listener('active');
  expect(onForeground).not.toHaveBeenCalled();
});

test('també compta tornar d\'inactive (centre de control, canvi d\'app a mig gest): refrescar no fa mal', async () => {
  const onForeground = jest.fn();
  await renderHook(() => useOnForeground(onForeground));
  listener('inactive');
  listener('active');
  expect(onForeground).toHaveBeenCalledTimes(1);
});

test('fa servir la funció més recent sense tornar a subscriure', async () => {
  const first = jest.fn();
  const second = jest.fn();
  const { rerender } = await renderHook(({ fn }: { fn: () => void }) => useOnForeground(fn), { initialProps: { fn: first } });
  await rerender({ fn: second });
  listener('background');
  listener('active');
  expect(first).not.toHaveBeenCalled();
  expect(second).toHaveBeenCalledTimes(1);
  expect(AppState.addEventListener).toHaveBeenCalledTimes(1);
});

test("es dessubscriu quan la pantalla desapareix", async () => {
  const { unmount } = await renderHook(() => useOnForeground(jest.fn()));
  await unmount();
  expect(mockRemove).toHaveBeenCalledTimes(1);
});
