import { extent, polylinePoints } from './chart';

test('polylinePoints escala valors al viewport SVG (y invertida)', () => {
  // 3 punts, min 0 max 10: el 0 va a baix (y=100), el 10 a dalt (y=0)
  expect(polylinePoints([0, 5, 10], 100, 100, 0, 10)).toBe('0,100 50,50 100,0');
});

test('polylinePoints salta forats (null) sense petar', () => {
  expect(polylinePoints([0, null, 10], 100, 100, 0, 10)).toBe('0,100 100,0');
});

test("extent troba el mínim i màxim de totes les sèries alhora, amb marge", () => {
  const { min, max } = extent([[10, 20], [-5, 15]], 0.1);
  // rang cru: -5..20 (span 25); marge 10% = 2.5
  expect(min).toBeCloseTo(-7.5);
  expect(max).toBeCloseTo(22.5);
});
