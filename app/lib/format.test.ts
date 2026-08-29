import {
  formatDateCa,
  formatDuration,
  formatStep,
  formatTarget,
  sportLabel,
  verdictColor,
} from './format';

test('dates en català, amb apòstrof on toca', () => {
  expect(formatDateCa(new Date(2026, 7, 29))).toBe("Dissabte 29 d'agost");
  expect(formatDateCa(new Date(2026, 8, 27))).toBe('Diumenge 27 de setembre');
  expect(formatDateCa(new Date(2026, 3, 1))).toBe("Dimecres 1 d'abril");
});

test('durades en segons -> text llegible', () => {
  expect(formatDuration(600)).toBe('10 min');
  expect(formatDuration(3300)).toBe('55 min');
  expect(formatDuration(5400)).toBe('1 h 30 min');
  expect(formatDuration(7200)).toBe('2 h');
});

test('targets del contracte §6 -> text', () => {
  expect(formatTarget({ type: 'rpe', value: 6 })).toBe('RPE 6');
  expect(formatTarget({ type: 'pace_sec_km', value: 222 })).toBe('3:42/km');
  expect(formatTarget({ type: 'pace_sec_100m', value: 110 })).toBe('1:50/100 m');
  expect(formatTarget({ type: 'hr_zone', value: 2 })).toBe('Z2');
  expect(formatTarget({ type: 'open' })).toBe('lliure');
  expect(formatTarget({ type: 'pace_sec_km', value: 285, comparator: 'slower_than' })).toBe(
    'més lent de 4:45/km'
  );
});

test('passos: repeticions amb feina i recuperació', () => {
  const step = {
    phase: 'main',
    repeats: 5,
    work: { distance_m: 1000, target: { type: 'pace_sec_km', value: 222, tolerance: 3 } },
    recovery: { duration_sec: 90 },
  };
  expect(formatStep(step)).toBe('5 × 1000 m @ 3:42/km · rec 90 s');
});

test('passos simples: durada o distància amb fase', () => {
  expect(formatStep({ phase: 'warmup', duration_sec: 900, target: { type: 'rpe', value: 4 } })).toBe(
    'Escalfament — 15 min · RPE 4'
  );
  expect(formatStep({ phase: 'main', distance_m: 800, target: { type: 'rpe', value: 6 } })).toBe(
    '800 m · RPE 6'
  );
  expect(formatStep({ phase: 'cooldown', duration_sec: 600, target: { type: 'rpe', value: 3 } })).toBe(
    'Final suau — 10 min · RPE 3'
  );
});

test('estats de sessió: color i etiqueta', () => {
  const { statusColor, statusLabel } = require('./format');
  expect(statusColor('completed')).toBe('#2e9e5b');
  expect(statusColor('partial')).toBe('#e6a817');
  expect(statusColor('missed')).toBe('#d64541');
  expect(statusColor('planned')).toBe('#8a8a8a');
  expect(statusLabel('completed')).toBe('feta');
  expect(statusLabel('partial')).toBe('a mitges');
  expect(statusLabel('missed')).toBe('no feta');
  expect(statusLabel('planned')).toBe('pendent');
  expect(statusLabel('cancelled')).toBe('cancel·lada');
  expect(statusLabel('moved')).toBe('moguda');
});

test('semàfor i esports', () => {
  expect(verdictColor('green')).toBe('#2e9e5b');
  expect(verdictColor('amber')).toBe('#e6a817');
  expect(verdictColor('red')).toBe('#d64541');
  expect(verdictColor('desconegut')).toBe('#8a8a8a');
  expect(sportLabel('run')).toBe('Cursa');
  expect(sportLabel('swim')).toBe('Natació');
  expect(sportLabel('bike')).toBe('Bici');
  expect(sportLabel('brick')).toBe('Brick');
  expect(sportLabel('rest')).toBe('Descans');
});
