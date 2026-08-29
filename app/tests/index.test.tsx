jest.mock('@/lib/supabase', () => ({ supabase: { auth: {} } }));

import Route from '@/app/(tabs)/index';
import Avui from '@/components/avui';

test('la pestanya inicial és la pantalla Avui', () => {
  expect(Route).toBe(Avui);
});
