// Capa de dades de l'app: consultes de lectura via supabase-js (passa RLS).

import type { Step } from './format';
import { supabase } from './supabase';

export type DailyReport = {
  id: number;
  createdAt: string;
  verdict: string;
  summary: string;
  rationale: string;
  questions: string[];
};

export type PlanSession = {
  id: number;
  sport: string;
  session_type: string;
  title: string;
  status: string;
  duration_sec_target: number | null;
  distance_m_target: number | null;
  structure: { steps: Step[] } | null;
  rationale: string | null;
  is_test: boolean;
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
      'id, local_date, sport, session_type, title, status, duration_sec_target, distance_m_target, structure, rationale, is_test'
    )
    .gte('local_date', startISO)
    .lte('local_date', endISO)
    .is('superseded_by', null)
    .order('local_date');
  if (error) throw new Error(error.message);
  return (data ?? []) as (PlanSession & { local_date: string })[];
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
  event_date: string;
  profile: Record<string, any>;
};

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
    .select('id, name, event_date, profile')
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

export async function getLatestDailyReport(): Promise<DailyReport | null> {
  const { data, error } = await supabase
    .from('coach_report')
    .select('id, created_at, output')
    .eq('report_type', 'daily')
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const output = data.output as Record<string, any>;
  return {
    id: data.id,
    createdAt: data.created_at,
    verdict: output.readiness?.verdict ?? 'unknown',
    summary: output.summary ?? '',
    rationale: output.rationale ?? '',
    questions: output.questions_for_athlete ?? [],
  };
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
      'id, sport, session_type, title, status, duration_sec_target, distance_m_target, structure, rationale, is_test'
    )
    .eq('local_date', dateISO)
    .is('superseded_by', null)
    .order('sport');
  if (error) throw new Error(error.message);
  return (data ?? []) as PlanSession[];
}
