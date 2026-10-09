import { render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';
import FormScrollView from './form-scroll-view';

test('les pantalles amb camps de text es desplacen perquè el teclat no els tapi', async () => {
  await render(
    <FormScrollView testID="scroll">
      <Text>hola</Text>
    </FormScrollView>
  );
  const scroll = screen.getByTestId('scroll');
  expect(scroll.props.automaticallyAdjustKeyboardInsets).toBe(true);
  expect(scroll.props.keyboardShouldPersistTaps).toBe('handled');
  expect(scroll.props.keyboardDismissMode).toBe('interactive');
});

test("el desplaçament és el que el teclat tapa del camp, més un marge; si no el tapa, res", () => {
  const { keyboardOverlap } = require('./form-scroll-view');
  // camp que acaba a 900 px, teclat que comença a 620 px (iPhone): 280 + 24 de marge
  expect(keyboardOverlap(900, 620)).toBe(304);
  // camp a dalt de tot, per sobre del teclat
  expect(keyboardOverlap(300, 620)).toBe(0);
});

test('escolta el teclat mentre la pantalla és muntada i deixa de fer-ho en sortir', async () => {
  const { Keyboard } = require('react-native');
  const remove = jest.fn();
  const spy = jest.spyOn(Keyboard, 'addListener').mockReturnValue({ remove } as any);
  const { unmount } = await render(<FormScrollView><Text>hola</Text></FormScrollView>);
  expect(spy).toHaveBeenCalledWith('keyboardDidShow', expect.any(Function));
  await unmount();
  expect(remove).toHaveBeenCalled();
  spy.mockRestore();
});
