jest.mock('@/lib/supabase', () => ({ supabase: { auth: {} } }));

import Route from '@/app/(tabs)/objectius';
import Objectius from '@/components/objectius';

test('la quarta pestanya és la pantalla Objectius', () => {
  expect(Route).toBe(Objectius);
});
