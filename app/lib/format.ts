// Formatadors purs per pintar el pla (contracte §6) en text llegible.

export type Target = {
  type: string;
  value?: number;
  tolerance?: number;
  comparator?: string;
  label?: string;
};

export type Step = {
  phase?: string;
  repeats?: number;
  work?: { duration_sec?: number; distance_m?: number; target?: Target; note?: string };
  recovery?: { duration_sec?: number; target?: Target };
  duration_sec?: number;
  distance_m?: number;
  target?: Target;
  note?: string;
};

export function formatDuration(sec: number): string {
  const h = Math.floor(sec / 3600);
  const min = Math.round((sec % 3600) / 60);
  if (h === 0) return `${min} min`;
  return min === 0 ? `${h} h` : `${h} h ${min} min`;
}

function pace(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function formatTarget(t: Target): string {
  let base: string;
  switch (t.type) {
    case 'rpe':
      base = `RPE ${t.value}`;
      break;
    case 'pace_sec_km':
      base = `${pace(t.value!)}/km`;
      break;
    case 'pace_sec_100m':
      base = `${pace(t.value!)}/100 m`;
      break;
    case 'hr_zone':
      base = `Z${t.value}`;
      break;
    case 'open':
      return 'lliure';
    default:
      base = t.label ?? t.type;
  }
  return t.comparator === 'slower_than' ? `més lent de ${base}` : base;
}

const PHASE_LABEL: Record<string, string> = {
  warmup: 'Escalfament',
  cooldown: 'Final suau',
};

function amount(x: { duration_sec?: number; distance_m?: number }): string {
  if (x.distance_m != null) return `${x.distance_m} m`;
  if (x.duration_sec != null) return formatDuration(x.duration_sec);
  return '';
}

export function formatStep(step: Step): string {
  if (step.repeats && step.work) {
    const target = step.work.target ? ` @ ${formatTarget(step.work.target)}` : '';
    const rec = step.recovery?.duration_sec != null ? ` · rec ${step.recovery.duration_sec} s` : '';
    return `${step.repeats} × ${amount(step.work)}${target}${rec}`;
  }
  const phase = step.phase ? PHASE_LABEL[step.phase] : undefined;
  const target = step.target ? ` · ${formatTarget(step.target)}` : '';
  const body = `${amount(step)}${target}`;
  return phase ? `${phase} — ${body}` : body;
}

const VERDICT_COLORS: Record<string, string> = {
  green: '#2e9e5b',
  amber: '#e6a817',
  red: '#d64541',
};

export function verdictColor(verdict: string): string {
  return VERDICT_COLORS[verdict] ?? '#8a8a8a';
}

const SPORT_LABELS: Record<string, string> = {
  run: 'Cursa',
  bike: 'Bici',
  swim: 'Natació',
  brick: 'Brick',
  rest: 'Descans',
};

export function sportLabel(sport: string): string {
  return SPORT_LABELS[sport] ?? sport;
}

export function formatClock(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.round(sec % 60);
  const mmss = `${m}:${String(s).padStart(2, '0')}`;
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : mmss;
}

export function daysUntil(dateISO: string, from: Date = new Date()): number {
  const [y, m, d] = dateISO.split('-').map(Number);
  const target = new Date(y, m - 1, d);
  const start = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  return Math.round((target.getTime() - start.getTime()) / 86400000);
}

const STATUS_COLORS: Record<string, string> = {
  completed: '#2e9e5b',
  partial: '#e6a817',
  missed: '#d64541',
};

export function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? '#8a8a8a';
}

const STATUS_LABELS: Record<string, string> = {
  completed: 'feta',
  partial: 'a mitges',
  missed: 'no feta',
  planned: 'pendent',
  cancelled: 'cancel·lada',
  moved: 'moguda',
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

const WEEKDAYS = ['Diumenge', 'Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 'Divendres', 'Dissabte'];
const MONTHS = [
  'gener', 'febrer', 'març', 'abril', 'maig', 'juny',
  'juliol', 'agost', 'setembre', 'octubre', 'novembre', 'desembre',
];

export function formatDateCa(d: Date): string {
  const month = MONTHS[d.getMonth()];
  const de = /^[aeiou]/.test(month) ? "d'" : 'de ';
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${de}${month}`;
}
