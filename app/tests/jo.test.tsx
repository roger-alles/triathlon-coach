jest.mock('@/lib/supabase', () => ({ supabase: { auth: {} } }));

import Route from '@/app/(tabs)/jo';
import Jo from '@/components/jo';

test('la cinquena pestanya és la pantalla Jo', () => {
  expect(Route).toBe(Jo);
});
