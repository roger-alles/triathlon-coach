import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';

// Crida `onForeground` cada cop que l'app torna de segon pla. Amb l'app
// instal·lada (TestFlight) iOS no la tanca de nit: sense això, al matí la
// pantalla ensenya les dades d'ahir fins que l'atleta estira per refrescar.
export function useOnForeground(onForeground: () => void) {
  const callback = useRef(onForeground);
  useEffect(() => {
    callback.current = onForeground;
  }, [onForeground]);

  useEffect(() => {
    let previous = AppState.currentState;
    const subscription = AppState.addEventListener('change', (next) => {
      if (previous !== 'active' && next === 'active') callback.current();
      previous = next;
    });
    return () => subscription.remove();
  }, []);
}
