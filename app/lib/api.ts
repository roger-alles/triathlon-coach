// Capa de dades de l'app: consultes de lectura via supabase-js (passa RLS).

import type { Segment, Step } from './format';
import { supabase } from './supabase';

export type DailyReport = {
  id: number;
  createdAt: string;
  verdict: string;
  summary: string;
  rationale: string;
  questions: string[];
  windowStart: string; // el dia de què parla l'informe
  // 'today': informe del matí d'avui · 'preview_tomorrow': el del vespre, parla
  // de demà · 'preview_today': el d'ahir al vespre, parla d'avui (encara no hi
  // ha el del matí)
  kind: 'today' | 'preview_tomorrow' | 'preview_today';
  proposal: Proposal | null; // els canvis al pla que l'informe proposa (cap keep)
};

// --- Propostes del coach (S1a al servidor, S1b a l'app) ---------------------

export type SessionChange = {
  plan_session_id: number;
  action: 'modify' | 'replace' | 'move' | 'cancel';
  reason: string;
  new_date?: string;
  new_session?: { sport: string; title: string; duration_sec_target?: number; priority?: string; rationale?: string };
};

export type ProposalStatus = 'none' | 'auto_applied' | 'proposed' | 'applied' | 'discarded' | 'undone' | 'failed';

export type BlockChange = {
  action: 'add' | 'modify' | 'cancel';
  block_id?: number;
  reason: string;
  new_block?: {
    phase?: string; name?: string; start_date?: string; end_date?: string;
    intent?: string; target_weekly_hours?: number; fallback?: string;
  };
};

export type Proposal = {
  id: number; // = coach_report.id
  createdAt: string;
  reportType: string;
  scope: 'sessions' | 'week' | 'macro';
  status: ProposalStatus;
  classification: { auto: boolean; reasons: string[] } | null;
  changes: SessionChange[];
  blockChanges: BlockChange[];
};

export type PlanBlockFull = {
  id: number;
  goal_id: number;
  phase: string;
  name: string | null;
  start_date: string;
  end_date: string;
  target_weekly_hours: number | null;
  intent: string | null;
  fallback: string | null;
  status: 'active' | 'proposed' | 'cancelled';
};

export type AthleteRequest = {
  id: number;
  kind: string;
  status: 'pending' | 'processing' | 'answered' | 'failed';
  error: string | null;
  report_id: number | null;
  created_at: string;
};

export type Decision = {
  id: number;
  report_id: number;
  decision: 'apply' | 'discard' | 'undo';
  status: 'pending' | 'processing' | 'done' | 'failed';
  error: string | null;
  created_at: string;
};

const PROPOSAL_COLUMNS = 'id, created_at, window_start, report_type, proposal_status, scope, classification, output';

function proposalOf(row: Record<string, any>): Proposal | null {
  const changes: SessionChange[] = (row.output?.session_changes ?? [])
    .filter((c: any) => c.action !== 'keep')
    .map((c: any) => {
      const out: SessionChange = { plan_session_id: c.plan_session_id, action: c.action, reason: c.reason ?? '' };
      if (c.new_date) out.new_date = c.new_date;
      if (c.new_session) {
        const n = c.new_session;
        out.new_session = { sport: n.sport, title: n.title };
        if (n.duration_sec_target != null) out.new_session.duration_sec_target = n.duration_sec_target;
        if (n.priority) out.new_session.priority = n.priority;
        if (n.rationale) out.new_session.rationale = n.rationale;
      }
      return out;
    });
  const blockChanges: BlockChange[] = (row.output?.block_changes ?? []).map((b: any) => {
    const out: BlockChange = { action: b.action, reason: b.reason ?? '' };
    if (b.block_id != null) out.block_id = b.block_id;
    if (b.new_block) out.new_block = { ...b.new_block };
    return out;
  });
  if (changes.length === 0 && blockChanges.length === 0) return null;
  const cl = row.classification;
  return {
    id: row.id,
    createdAt: row.created_at,
    reportType: row.report_type ?? 'daily',
    scope: row.scope ?? (blockChanges.length ? 'macro' : 'sessions'),
    status: row.proposal_status ?? 'none',
    classification: cl ? { auto: !!cl.auto, reasons: cl.reasons ?? [] } : null,
    changes,
    blockChanges,
  };
}

// Blocs vius del pla (actius i proposats), per data.
export async function getBlocks(): Promise<PlanBlockFull[]> {
  const { data, error } = await supabase
    .from('plan_block')
    .select('id, goal_id, phase, name, start_date, end_date, target_weekly_hours, intent, fallback, status')
    .in('status', ['active', 'proposed'])
    .order('start_date');
  if (error) throw new Error(error.message);
  return (data ?? []) as PlanBlockFull[];
}

// Petició de l'atleta al coach (bústia). El servidor la processa en ≤ 5 min.
export async function sendRequest(kind: string, payload: Record<string, unknown> = {}): Promise<void> {
  const { error } = await supabase.from('athlete_request').insert({ kind, payload });
  if (error) throw new Error(error.message);
}

export async function getRequests(limit = 3): Promise<AthleteRequest[]> {
  const { data, error } = await supabase
    .from('athlete_request')
    .select('id, kind, status, error, report_id, created_at')
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  return (data ?? []) as AthleteRequest[];
}

export type MacroAnswer = { id: number; proposalStatus: string; summary: string; hasBlockChanges: boolean };

// L'informe que ha respost una petició de macro: si no porta canvis de blocs
// no surt a Avui (no hi ha res a aprovar), i Objectius n'ensenya el resum.
export async function getMacroAnswer(reportId: number): Promise<MacroAnswer | null> {
  const { data, error } = await supabase
    .from('coach_report')
    .select('id, proposal_status, output')
    .eq('id', reportId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const row = data as Record<string, any>;
  return {
    id: row.id,
    proposalStatus: row.proposal_status,
    summary: row.output?.summary ?? '',
    hasBlockChanges: (row.output?.block_changes ?? []).length > 0,
  };
}

// Propostes obertes o acabades de resoldre (últims 7 dies), sense el keep.
// En dry_run no n'hi ha cap: tot queda a 'none'.
export async function getOpenProposals(todayISO: string): Promise<Proposal[]> {
  const since = parseLocalISO(todayISO);
  since.setDate(since.getDate() - 7);
  const { data, error } = await supabase
    .from('coach_report')
    .select(PROPOSAL_COLUMNS)
    .in('proposal_status', ['proposed', 'auto_applied', 'applied', 'failed'])
    .gte('created_at', localDateISO(since))
    .order('created_at', { ascending: false });
  if (error) throw new Error(error.message);
  return ((data ?? []) as Record<string, any>[]).map(proposalOf).filter((p): p is Proposal => p != null);
}

export type SessionRef = { id: number; local_date: string; sport: string; title: string; status: string };

export async function getSessionsByIds(ids: number[]): Promise<Map<number, SessionRef>> {
  const unique = Array.from(new Set(ids));
  if (unique.length === 0) return new Map();
  const { data, error } = await supabase
    .from('plan_session')
    .select('id, local_date, sport, title, status')
    .in('id', unique);
  if (error) throw new Error(error.message);
  return new Map(((data ?? []) as SessionRef[]).map((s) => [s.id, s]));
}

// L'app només encua; coach.decisions (cron cada 5 min) executa i marca done/failed.
export async function sendDecision(reportId: number, decision: Decision['decision']): Promise<void> {
  const { error } = await supabase.from('coach_decision').insert({ report_id: reportId, decision });
  if (error) throw new Error(error.message);
}

export async function getDecisions(reportIds: number[]): Promise<Decision[]> {
  if (reportIds.length === 0) return [];
  const { data, error } = await supabase
    .from('coach_decision')
    .select('id, report_id, decision, status, error, created_at')
    .in('report_id', reportIds)
    .order('created_at', { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as Decision[];
}

export async function getSetting(key: string): Promise<string | null> {
  const { data, error } = await supabase.from('app_setting').select('value').eq('key', key).maybeSingle();
  if (error) throw new Error(error.message);
  return (data?.value as string | undefined) ?? null;
}

export async function setSetting(key: string, value: string): Promise<void> {
  const { error } = await supabase.from('app_setting').update({ value }).eq('key', key);
  if (error) throw new Error(error.message);
}

export type PlanSession = {
  id: number;
  sport: string;
  session_type: string;
  title: string;
  status: string;
  duration_sec_target: number | null;
  distance_m_target: number | null;
  structure: { steps?: Step[]; segments?: Segment[] } | null;
  rationale: string | null;
  is_test: boolean;
  priority: 'key' | 'support' | 'optional';
};

export type PlanBlock = {
  phase: string;
  name: string | null;
};

export function localDateISO(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export type Activity = {
  id: number;
  local_date: string;
  sport: string;
  duration_sec: number | null;
  distance_m: number | null;
  avg_hr: number | null;
  plan_session_id: number | null;
};

export type ActivityDetail = Activity & {
  max_hr: number | null;
  avg_pace_sec_km: number | null;
  avg_pace_sec_100m: number | null;
  elevation_gain_m: number | null;
  load: number | null;
  perceived_effort: number | null;
  feeling: number | null;
  athlete_notes: string | null;
};

export type SubjectiveUpdate = {
  perceived_effort?: number | null;
  feeling?: number | null;
  athlete_notes?: string | null;
};

export async function getActivity(id: number): Promise<ActivityDetail | null> {
  const { data, error } = await supabase
    .from('activity')
    .select(
      'id, local_date, sport, duration_sec, distance_m, avg_hr, max_hr, avg_pace_sec_km, avg_pace_sec_100m, elevation_gain_m, load, perceived_effort, feeling, athlete_notes, plan_session_id'
    )
    .eq('id', id)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data as ActivityDetail | null;
}

export async function updateActivitySubjective(id: number, changes: SubjectiveUpdate): Promise<void> {
  const { error } = await supabase.from('activity').update(changes).eq('id', id);
  if (error) throw new Error(error.message);
}

// 'YYYY-MM-DD' -> mitjanit local. new Date('YYYY-MM-DD') seria UTC i, a l'oest
// de Greenwich, el dia abans.
export function parseLocalISO(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function weekDaysISO(d: Date = new Date()): string[] {
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => {
    const day = new Date(monday);
    day.setDate(monday.getDate() + i);
    return localDateISO(day);
  });
}

export async function getSessionsForRange(
  startISO: string,
  endISO: string
): Promise<(PlanSession & { local_date: string })[]> {
  const { data, error } = await supabase
    .from('plan_session')
    .select(
      'id, local_date, sport, session_type, title, status, duration_sec_target, distance_m_target, structure, rationale, is_test, priority'
    )
    .gte('local_date', startISO)
    .lte('local_date', endISO)
    .is('superseded_by', null)
    .order('local_date');
  if (error) throw new Error(error.message);
  return (data ?? []) as (PlanSession & { local_date: string })[];
}

// El bloc del pla que solapa el rang (els blocs són setmanes senceres).
export async function getBlockForRange(startISO: string, endISO: string): Promise<PlanBlock | null> {
  const { data, error } = await supabase
    .from('plan_block')
    .select('phase, name')
    .eq('status', 'active')
    .lte('start_date', endISO)
    .gte('end_date', startISO)
    .order('start_date')
    .limit(1)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data as PlanBlock | null;
}

export async function getActivitiesForRange(startISO: string, endISO: string): Promise<Activity[]> {
  const { data, error } = await supabase
    .from('activity')
    .select('id, local_date, sport, duration_sec, distance_m, avg_hr, plan_session_id')
    .gte('local_date', startISO)
    .lte('local_date', endISO)
    .order('local_date');
  if (error) throw new Error(error.message);
  return (data ?? []) as Activity[];
}

export type FormDay = {
  local_date: string;
  load: number;
  ctl: number;
  atl: number;
  tsb: number;
};

const round1 = (v: unknown) => Math.round(Number(v) * 10) / 10;

export async function getFormSeries(sinceISO: string): Promise<FormDay[]> {
  const { data, error } = await supabase
    .from('load_daily')
    .select('local_date, load, ctl, atl, tsb')
    .gte('local_date', sinceISO)
    .order('local_date');
  if (error) throw new Error(error.message);
  // PostgREST serialitza els numeric de Postgres com a strings: es converteixen aquí.
  return (data ?? []).map((r) => ({
    local_date: r.local_date,
    load: round1(r.load),
    ctl: round1(r.ctl),
    atl: round1(r.atl),
    tsb: round1(r.tsb),
  }));
}

export type Goal = {
  id: number;
  name: string;
  discipline: 'triathlon' | 'run' | 'bike' | 'swim' | 'ultra_endurance';
  event_date: string | null;
  priority: 'A' | 'B' | 'C';
  status: 'active' | 'completed' | 'abandoned';
  notes: string | null;
  profile: Record<string, any>;
};

export type GoalInput = Omit<Goal, 'id' | 'status'> & { id?: number };

const GOAL_COLUMNS = 'id, name, discipline, event_date, priority, status, notes, profile';

// Objectius actius: primer els A amb data (la més propera davant), després els
// A sense data, i després B i C. És l'ordre que fa servir el coach (primary_goal).
export async function getGoals(): Promise<Goal[]> {
  const { data, error } = await supabase.from('goal').select(GOAL_COLUMNS).eq('status', 'active');
  if (error) throw new Error(error.message);
  const rank = (g: Goal) => `${g.priority}${g.event_date ? '0' + g.event_date : '1'}`;
  return ((data ?? []) as Goal[]).sort((a, b) => rank(a).localeCompare(rank(b)));
}

// Sense id: objectiu nou (la RLS de la 0011 deixa inserir). Amb id: edició.
export async function upsertGoal(input: GoalInput): Promise<void> {
  const { id, ...fields } = input;
  const { error } =
    id == null
      ? await supabase.from('goal').insert(fields)
      : await supabase.from('goal').update(fields).eq('id', id);
  if (error) throw new Error(error.message);
}

// Mai esborrar: blocs i sessions hi pengen. Abandonar = status.
export async function abandonGoal(id: number): Promise<void> {
  const { error } = await supabase.from('goal').update({ status: 'abandoned' }).eq('id', id);
  if (error) throw new Error(error.message);
}

export type LogisticsTask = {
  id: number;
  local_date: string;
  title: string;
  detail: string | null;
  blocking: boolean;
  done: boolean;
};

export async function getActiveGoal(): Promise<Goal | null> {
  const { data, error } = await supabase
    .from('goal')
    .select(GOAL_COLUMNS)
    .eq('status', 'active')
    .order('event_date')
    .limit(1)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data as Goal | null;
}

export async function getLogistics(goalId: number): Promise<LogisticsTask[]> {
  const { data, error } = await supabase
    .from('logistics_task')
    .select('id, local_date, title, detail, blocking, done')
    .eq('goal_id', goalId)
    .order('local_date');
  if (error) throw new Error(error.message);
  return (data ?? []) as LogisticsTask[];
}

export async function setLogisticsDone(id: number, done: boolean): Promise<void> {
  const { error } = await supabase.from('logistics_task').update({ done }).eq('id', id);
  if (error) throw new Error(error.message);
}

// L'últim informe diari, etiquetat segons de quin dia parla respecte d'avui:
// a partir de les 21:30 és el preview de demà (per preparar-lo i visualitzar-lo);
// al matí, fins que arriba l'informe del dia, és el preview d'ahir per avui.
export async function getLatestDailyReport(todayISO: string): Promise<DailyReport | null> {
  const { data, error } = await supabase
    .from('coach_report')
    .select(PROPOSAL_COLUMNS)
    .eq('report_type', 'daily')
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const output = data.output as Record<string, any>;
  const kind =
    data.window_start > todayISO
      ? 'preview_tomorrow'
      : localDateISO(new Date(data.created_at)) < data.window_start
        ? 'preview_today'
        : 'today';
  return {
    id: data.id,
    createdAt: data.created_at,
    verdict: output.readiness?.verdict ?? 'unknown',
    summary: output.summary ?? '',
    rationale: output.rationale ?? '',
    questions: output.questions_for_athlete ?? [],
    windowStart: data.window_start,
    kind,
    proposal: proposalOf(data),
  };
}

export type ManualActivityInput = {
  local_date: string;
  sport: string;
  sub_sport?: string;
  duration_sec: number;
  distance_m?: number | null;
  perceived_effort?: number | null;
  feeling?: number | null;
  athlete_notes?: string | null;
  plan_session_id?: number | null;
};

// Sessió feta sense rellotge (natació a mar, piscina cronometrada). Fila manual
// amb id negatiu (-AAAAMMDDhhmmss, dia de la sessió + hora del registre amb
// segons perquè dos trams d'un multisport no xoquin): RLS només deixa inserir
// ids < 0, i el sync horari li posa la càrrega estimada i l'estat de la sessió
// del pla. Un dia passat s'apunta al migdia d'aquell dia (l'hora real no es
// coneix); el dia d'avui, a l'hora real (acabada ara).
export async function logManualActivity(input: ManualActivityInput, now: Date = new Date()): Promise<void> {
  const pad = (n: number) => String(n).padStart(2, '0');
  const hhmmss = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const id = -Number(`${input.local_date.replace(/-/g, '')}${hhmmss}`);
  const isToday = input.local_date === localDateISO(now);
  const start = isToday
    ? new Date(now.getTime() - input.duration_sec * 1000)
    : new Date(parseLocalISO(input.local_date).setHours(12, 0, 0, 0));
  const row = {
    id,
    start_time: start.toISOString(),
    local_date: input.local_date,
    sport: input.sport,
    sub_sport: input.sub_sport ?? null,
    duration_sec: input.duration_sec,
    distance_m: input.distance_m ?? null,
    perceived_effort: input.perceived_effort ?? null,
    feeling: input.feeling ?? null,
    athlete_notes: input.athlete_notes ?? null,
    plan_session_id: input.plan_session_id ?? null,
    load_estimated: true,
    raw: { manual: true, source: 'app', plan_session_id: input.plan_session_id ?? null },
  };
  const { error } = await supabase.from('activity').insert(row);
  if (error) throw new Error(error.message);
}

export type AthleteAnswer = {
  id: number;
  question: string;
  answer: string;
};

export async function sendAnswer(reportId: number, question: string, answer: string): Promise<void> {
  const { error } = await supabase
    .from('athlete_answer')
    .insert({ report_id: reportId, question, answer });
  if (error) throw new Error(error.message);
}

export async function getAnswers(reportId: number): Promise<AthleteAnswer[]> {
  const { data, error } = await supabase
    .from('athlete_answer')
    .select('id, question, answer')
    .eq('report_id', reportId)
    .order('id');
  if (error) throw new Error(error.message);
  return (data ?? []) as AthleteAnswer[];
}

export async function getSessionsForDay(dateISO: string): Promise<PlanSession[]> {
  const { data, error } = await supabase
    .from('plan_session')
    .select(
      'id, sport, session_type, title, status, duration_sec_target, distance_m_target, structure, rationale, is_test, priority'
    )
    .eq('local_date', dateISO)
    .is('superseded_by', null)
    .order('sport');
  if (error) throw new Error(error.message);
  return (data ?? []) as PlanSession[];
}

// --- Perfil de l'atleta (S2b) ---------------------------------------------
// El que el coach ha de saber de mi i no ve de Garmin: disponibilitat, salut,
// notes. Viu a athlete.profile (jsonb); l'app només edita constraints i notes
// i conserva la resta (health, known, unknown...).

export type AthleteProfile = {
  constraints?: {
    fixed_rest_day?: string | null;
    weekly_hours_ceiling?: number | null;
    available_days?: string[];
    pool_availability?: string | null;
    gym?: boolean | null;
    [k: string]: any;
  };
  notes?: string | null;
  [k: string]: any;
};

export type Athlete = {
  id: number;
  name: string;
  birth_date: string | null;
  max_hr: number | null;
  profile: AthleteProfile;
};

export async function getAthlete(): Promise<Athlete | null> {
  const { data, error } = await supabase
    .from('athlete')
    .select('id, name, birth_date, max_hr, profile')
    .eq('id', 1)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  return { ...(data as Athlete), profile: (data as Athlete).profile ?? {} };
}

export async function updateAthleteProfile(profile: AthleteProfile): Promise<void> {
  const { error } = await supabase.from('athlete').update({ profile }).eq('id', 1);
  if (error) throw new Error(error.message);
}
