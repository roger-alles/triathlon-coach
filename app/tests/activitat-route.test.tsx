jest.mock('expo-router', () => ({ useLocalSearchParams: () => ({ id: '42' }) }));
jest.mock('@/lib/supabase', () => ({ supabase: { auth: {} } }));

const mockActivitat = jest.fn((_props: unknown) => null);
jest.mock('@/components/activitat', () => ({ __esModule: true, default: (p: any) => mockActivitat(p) }));

import { render } from '@testing-library/react-native';
import ActivitatRoute from '@/app/activitat';

test("la ruta passa l'id de la URL (string) com a número", async () => {
  await render(<ActivitatRoute />);
  expect(mockActivitat).toHaveBeenCalledWith(expect.objectContaining({ id: 42 }));
});
