jest.mock('@/lib/supabase', () => ({ supabase: { auth: {} } }));
jest.mock('react-native-svg', () => {
  const { View } = require('react-native');
  return { __esModule: true, default: View, Svg: View, Polyline: View, Line: View };
});

import Route from '@/app/(tabs)/forma';
import Forma from '@/components/forma';

test('la tercera pestanya és la pantalla Forma', () => {
  expect(Route).toBe(Forma);
});
