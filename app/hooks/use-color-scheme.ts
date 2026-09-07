import { useColorScheme as useRNColorScheme } from 'react-native';

export type ColorScheme = 'light' | 'dark';

// RN 0.86 pot retornar 'unspecified'; l'app només coneix light/dark.
export function useColorScheme(): ColorScheme {
  return useRNColorScheme() === 'dark' ? 'dark' : 'light';
}
