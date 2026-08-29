// Capa de dades de l'app: consultes de lectura via supabase-js (passa RLS).

import type { Step } from './format';
import { supabase } from './supabase';

export type DailyReport = {
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

export async function getLatestDailyReport(): Promise<DailyReport | null> {
  const { data, error } = await supabase
    .from('coach_report')
    .select('created_at, output')
    .eq('report_type', 'daily')
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const output = data.output as Record<string, any>;
  return {
    createdAt: data.created_at,
    verdict: output.readiness?.verdict ?? 'unknown',
    summary: output.summary ?? '',
    rationale: output.rationale ?? '',
    questions: output.questions_for_athlete ?? [],
  };
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
