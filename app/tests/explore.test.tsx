jest.mock('@/lib/supabase', () => ({ supabase: { auth: {} } }));

import Route from '@/app/(tabs)/explore';
import Setmana from '@/components/setmana';

test('la segona pestanya és la pantalla Setmana', () => {
  expect(Route).toBe(Setmana);
});
