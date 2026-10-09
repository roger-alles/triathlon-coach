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
