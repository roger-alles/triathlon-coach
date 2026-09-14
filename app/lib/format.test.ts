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

test('temps de cursa: mm:ss fins a una hora, h:mm:ss després', () => {
  const { formatClock } = require('./format');
  expect(formatClock(90)).toBe('1:30');
  expect(formatClock(2320)).toBe('38:40');
  expect(formatClock(3600)).toBe('1:00:00');
  expect(formatClock(7470)).toBe('2:04:30');
});

test('daysUntil compta dies de calendari, no de 24h exactes', () => {
  const { daysUntil } = require('./format');
  expect(daysUntil('2026-09-27', new Date(2026, 7, 29, 23, 0))).toBe(29);
  expect(daysUntil('2026-09-27', new Date(2026, 8, 27, 6, 0))).toBe(0);
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

test('formatDuration arrossega els minuts: mai "1 h 60 min"', () => {
  expect(formatDuration(3599)).toBe('1 h');
  expect(formatDuration(7190)).toBe('2 h');
  expect(formatDuration(5370)).toBe('1 h 30 min');
});

test('segments de simulacre i cursa (multisport)', () => {
  const { formatSegment } = require('./format');
  expect(sportLabel('multisport')).toBe('Triatló');
  expect(
    formatSegment({ sport: 'swim', venue: 'open_water', target: { type: 'rpe', value: 7 }, distance_m: 800 })
  ).toBe('Natació 800 m · RPE 7 · mar');
  expect(formatSegment({ sport: 'transition', timed: true, transition: 't1' })).toBe('T1 cronometrada');
  expect(
    formatSegment({ sport: 'bike', target: { type: 'rpe', value: 7, label: 'esforç de cursa' }, distance_m: 34000 })
  ).toBe('Bici 34 km · RPE 7');
  expect(
    formatSegment({ sport: 'run', target: { type: 'pace_sec_km', value: 250, label: 'ritme objectiu' }, distance_m: 3000 })
  ).toBe('Cursa 3 km · 4:10/km');
  expect(formatSegment({ sport: 'run', distance_m: 9500 })).toBe('Cursa 9,5 km');
});

test('rang de setmana en català: un mes o dos, amb apòstrof on toca', () => {
  const { formatWeekRangeCa } = require('./format');
  expect(formatWeekRangeCa('2026-08-24', '2026-08-30')).toBe("24 – 30 d'agost");
  expect(formatWeekRangeCa('2026-09-14', '2026-09-20')).toBe('14 – 20 de setembre');
  expect(formatWeekRangeCa('2026-09-28', '2026-10-04')).toBe("28 de setembre – 4 d'octubre");
});

test('emoji de modalitat per llegir la setmana d\'un cop d\'ull', () => {
  const { sportEmoji } = require('./format');
  expect(sportEmoji('swim')).toBe('🏊');
  expect(sportEmoji('bike')).toBe('🚴');
  expect(sportEmoji('run')).toBe('🏃');
  expect(sportEmoji('brick')).toBe('🚴🏃');
  expect(sportEmoji('multisport')).toBe('🏊🚴🏃');
  expect(sportEmoji('rest')).toBe('🛌');
  expect(sportEmoji('strength')).toBe('🏋️');
  expect(sportEmoji('desconegut')).toBe('');
});

test('parseClock: mm:ss i h:mm:ss en segons; el que no ho és, null', () => {
  const { parseClock, pace } = require('./format');
  expect(parseClock('36:30')).toBe(2190);
  expect(parseClock('1:05:00')).toBe(3900);
  expect(parseClock(' 36:30.5 ')).toBe(2191);
  expect(parseClock('')).toBeNull();
  expect(parseClock('36')).toBeNull();
  expect(parseClock('36:70')).toBeNull();
  expect(parseClock('abc')).toBeNull();
  expect(pace(219)).toBe('3:39');
});
