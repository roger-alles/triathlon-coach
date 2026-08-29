import { useLocalSearchParams } from 'expo-router';

import Activitat from '@/components/activitat';

export default function ActivitatRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <Activitat id={Number(id)} />;
}
