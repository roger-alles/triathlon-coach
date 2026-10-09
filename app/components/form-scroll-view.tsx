import { ScrollView, ScrollViewProps } from 'react-native';

// Pantalles amb camps de text (respostes al coach, "Demana canvis", notes,
// perfil, objectius): quan surt el teclat, iOS ajusta el desplaçament perquè
// el camp on s'escriu quedi per sobre del teclat (abans el tapava). Tocar un
// botó amb el teclat obert funciona al primer toc, i arrossegar l'amaga.
export default function FormScrollView(props: ScrollViewProps) {
  return (
    <ScrollView
      automaticallyAdjustKeyboardInsets
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="interactive"
      {...props}
    />
  );
}
