import { useEffect, useRef } from 'react';
import { Keyboard, ScrollView, ScrollViewProps, TextInput } from 'react-native';

// Marge entre el camp on s'escriu i el teclat.
const MARGIN = 24;

// Quant s'ha de desplaçar la pantalla perquè el camp (la seva vora de baix, en
// coordenades de pantalla) quedi per sobre del teclat (la seva vora de dalt).
export function keyboardOverlap(inputBottom: number, keyboardTop: number, margin = MARGIN): number {
  return Math.max(0, inputBottom + margin - keyboardTop);
}

// Pantalles amb camps de text (respostes al coach, "Demana canvis", notes,
// perfil, objectius). Quan surt el teclat, si tapa el camp on s'escriu, la
// pantalla es desplaça fins a deixar-lo a la vista. automaticallyAdjustKeyboardInsets
// sol no ho fa (09/10: només amplia el marge per poder desplaçar a mà), per
// això es mesura el camp i es fa scrollTo. Només el ScrollView que conté el camp
// es mou (les altres pestanyes també estan muntades). Tocar un botó amb el
// teclat obert funciona al primer toc, i arrossegar l'amaga.
export default function FormScrollView({ onScroll, ...props }: ScrollViewProps) {
  const ref = useRef<ScrollView>(null);
  const offset = useRef(0);

  useEffect(() => {
    const sub = Keyboard.addListener('keyboardDidShow', (e) => {
      const input = TextInput.State.currentlyFocusedInput();
      const scroll = ref.current?.getNativeScrollRef();
      if (!input || !scroll) return;
      // measureLayout falla si el camp no és dins d'aquest ScrollView
      input.measureLayout(
        scroll,
        () =>
          input.measureInWindow((_x, y, _w, h) => {
            const delta = keyboardOverlap(y + h, e.endCoordinates.screenY);
            if (delta > 0) ref.current?.scrollTo({ y: offset.current + delta, animated: true });
          }),
        () => {}
      );
    });
    return () => sub.remove();
  }, []);

  return (
    <ScrollView
      ref={ref}
      automaticallyAdjustKeyboardInsets
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="interactive"
      scrollEventThrottle={16}
      onScroll={(ev) => {
        offset.current = ev.nativeEvent.contentOffset.y;
        onScroll?.(ev);
      }}
      {...props}
    />
  );
}
