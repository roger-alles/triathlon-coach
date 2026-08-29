jest.mock('@/lib/api', () => ({
  getFormSeries: jest.fn(),
  localDateISO: () => '2026-08-29',
}));

jest.mock('react-native-svg', () => {
  const { View } = require('react-native');
  return { __esModule: true, default: View, Svg: View, Polyline: View, Line: View };
});

import { render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { getFormSeries } from '@/lib/api';
import Forma from './forma';

const mockSeries = getFormSeries as jest.Mock;

const renderForma = () =>
  render(
    <SafeAreaProvider
      initialMetrics={{
        insets: { top: 59, left: 0, right: 0, bottom: 34 },
        frame: { x: 0, y: 0, width: 390, height: 844 },
      }}>
      <Forma />
    </SafeAreaProvider>
  );

beforeEach(() => {
  jest.clearAllMocks();
  mockSeries.mockResolvedValue([
    { local_date: '2026-08-28', load: 20.8, ctl: 45.4, atl: 70, tsb: -32.2 },
    { local_date: '2026-08-29', load: 0, ctl: 44.3, atl: 60, tsb: -24.6 },
  ]);
});

test("els tres números d'avui, amb les seves etiquetes en llenguatge d'atleta", async () => {
  await renderForma();
  expect(await screen.findByText('44.3')).toBeOnTheScreen();
  expect(screen.getByText('60')).toBeOnTheScreen();
  expect(screen.getByText('-24.6')).toBeOnTheScreen();
  expect(screen.getByText('Forma')).toBeOnTheScreen();
  expect(screen.getByText('Fatiga')).toBeOnTheScreen();
  expect(screen.getByText('Frescor')).toBeOnTheScreen();
});

test('sense dades encara: missatge, no pantalla trencada', async () => {
  mockSeries.mockResolvedValue([]);
  await renderForma();
  expect(await screen.findByText(/Encara no hi ha dades de forma/)).toBeOnTheScreen();
});

test('els errors de càrrega es mostren', async () => {
  mockSeries.mockRejectedValue(new Error('Network request failed'));
  await renderForma();
  expect(await screen.findByText(/Network request failed/)).toBeOnTheScreen();
});
