import { useCallback, useEffect, useState } from 'react';
import {ActivityIndicator, Alert, StyleSheet, TouchableOpacity, View} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import FormScrollView from '@/components/form-scroll-view';
import GoalForm from '@/components/goal-form';
import { ThemedText } from '@/components/themed-text';
import { AthleteRequest, getBlocks, getGoals, getLogistics, getMacroAnswer, getRequests, Goal, localDateISO, LogisticsTask, MacroAnswer, PlanBlockFull, sendRequest, setLogisticsDone } from '@/lib/api';
import { daysUntil, formatClock, pace, sportLabel } from '@/lib/format';

const SCENARIOS = ['Prudent', 'Objectiu', 'Gran dia'];
const TIME_ROWS: [string, string][] = [
  ['swim', 'Natació'],
  ['t1', 'T1'],
  ['bike', 'Bici'],
  ['t2', 'T2'],
  ['run', 'Cursa'],
  ['total', 'Total'],
];

// "2026-09-27" -> "27/09/2026"; sense data -> "sense data"
function shortDate(iso: string | null): string {
  if (!iso) return 'sense data';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}
function ddmm(iso: string): string {
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
}

// Ritme de l'escenari "Objectiu" d'una fila de temps, si es coneix la distància
// del segment: cursa i bici per km, natació per 100 m.
function derivedPace(key: string, sec: number | null, segments: any[] | undefined): string | null {
  if (sec == null || !Array.isArray(segments)) return null;
  const sport = key === 'total' ? (segments.length === 1 ? segments[0].sport : null) : key;
  const seg = segments.find((s: any) => s.sport === sport);
  if (!seg || !seg.distance_m) return null;
  if (sport === 'swim') return `≈ ${pace((sec / seg.distance_m) * 100)}/100 m`;
  if (sport === 'run' || sport === 'bike') return `≈ ${pace((sec / seg.distance_m) * 1000)}/km`;
  return null;
}

const PHASE_LABEL: Record<string, string> = {
  base: 'base', build: 'construcció', peak: 'pic', taper: 'afinament', race: 'cursa',
  recovery: 'recuperació', transition: 'transició',
};

export default function Objectius() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [logistics, setLogistics] = useState<LogisticsTask[]>([]);
  const [editing, setEditing] = useState<Goal | 'new' | null>(null);
  const [blocks, setBlocks] = useState<PlanBlockFull[]>([]);
  const [requests, setRequests] = useState<AthleteRequest[]>([]);
  const [answer, setAnswer] = useState<MacroAnswer | null>(null);
  const [requested, setRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const insets = useSafeAreaInsets();

  const toggleLogistics = async (t: LogisticsTask) => {
    const done = !t.done;
    setLogistics((prev) => prev.map((x) => (x.id === t.id ? { ...x, done } : x)));
    try {
      await setLogisticsDone(t.id, done);
    } catch (e) {
      setLogistics((prev) => prev.map((x) => (x.id === t.id ? { ...x, done: t.done } : x)));
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const load = useCallback(async () => {
    try {
      const gs = await getGoals();
      setGoals(gs);
      setLogistics(gs.length > 0 ? await getLogistics(gs[0].id) : []);
      const [bs, rs] = await Promise.all([getBlocks(), getRequests(3)]);
      setBlocks(bs);
      setRequests(rs);
      const last = rs[0];
      setAnswer(last?.status === 'answered' && last.report_id != null ? await getMacroAnswer(last.report_id) : null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    // load() només fa setState després d'un await (no és síncron); la regla
    // del React Compiler no distingeix el codi que hi ha després de l'await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  if (editing) {
    return (
      <FormScrollView style={styles.container} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}>
        <GoalForm
          goal={editing === 'new' ? undefined : editing}
          onDone={() => { setEditing(null); load(); }}
          onCancel={() => setEditing(null)}
        />
      </FormScrollView>
    );
  }

  const goal = goals[0] ?? null;
  const others = goals.slice(1);

  const askMacro = () => {
    Alert.alert(
      'Demanar un macro nou?',
      'El coach proposarà la seqüència de blocs fins a l’objectiu i la recuperació. Res s’aplica fins que ho aprovis a Avui. Un al dia.',
      [
        { text: 'Cancel·la', style: 'cancel' },
        {
          text: 'Demana',
          style: 'default',
          onPress: async () => {
            try {
              await sendRequest('regenerate_macro', { goal_id: goal?.id ?? null });
              setRequested(true);
            } catch (e) {
              setError(e instanceof Error ? e.message : String(e));
            }
          },
        },
      ]
    );
  };
  const lastRequest = requests[0];
  const today = localDateISO();
  const planSection = (
    <>
      <ThemedText style={styles.sectionTitle}>Pla</ThemedText>
      <View style={styles.card}>
        {blocks.length === 0 && <ThemedText style={styles.emptyOthers}>Cap bloc. Demana un macro al coach.</ThemedText>}
        {blocks.map((b) => {
          const current = b.start_date <= today && today <= b.end_date;
          return (
            <View key={b.id} style={[styles.blockRow, current && styles.blockCurrent]}>
              <ThemedText style={styles.phaseChip}>{PHASE_LABEL[b.phase] ?? b.phase}</ThemedText>
              <View style={styles.goalBody}>
                <ThemedText style={styles.goalName}>{b.name ?? b.phase}</ThemedText>
                <ThemedText style={styles.goalMeta}>
                  {ddmm(b.start_date)} – {ddmm(b.end_date)}
                  {b.target_weekly_hours != null && ` · ${b.target_weekly_hours} h/set`}
                  {b.status === 'proposed' && ' · proposat'}
                </ThemedText>
              </View>
            </View>
          );
        })}
        {requested || lastRequest?.status === 'pending' || lastRequest?.status === 'processing' ? (
          <ThemedText style={styles.working}>El coach hi treballa: la proposta surt a Avui en menys de 5 minuts.</ThemedText>
        ) : (
          <TouchableOpacity style={styles.newButton} onPress={askMacro}>
            <ThemedText style={styles.newButtonText}>Demana un macro nou</ThemedText>
          </TouchableOpacity>
        )}
        {!requested && lastRequest?.status === 'failed' && lastRequest.error && (
          <ThemedText style={styles.error}>{lastRequest.error}</ThemedText>
        )}
        {!requested && answer && (
          <ThemedText style={styles.note}>
            {answer.hasBlockChanges
              ? answer.proposalStatus === 'proposed'
                ? 'Proposta de blocs pendent: mira-la a Avui.'
                : `Última resposta del coach: ${answer.summary}`
              : `El coach ha respost sense canviar blocs: ${answer.summary}`}
          </ThemedText>
        )}
      </View>
    </>
  );

  const newButton = (
    <TouchableOpacity style={styles.newButton} onPress={() => setEditing('new')}>
      <ThemedText style={styles.newButtonText}>Nou objectiu</ThemedText>
    </TouchableOpacity>
  );

  if (!goal) {
    return (
      <FormScrollView style={styles.container} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}>
        <ThemedText>{error ?? 'Cap objectiu actiu.'}</ThemedText>
        {newButton}
        {planSection}
      </FormScrollView>
    );
  }

  const p = goal.profile ?? {};
  const days = goal.event_date ? daysUntil(goal.event_date) : null;
  const times = p.target_times_sec ?? {};

  return (
    <FormScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}>
      {error && <ThemedText style={styles.error}>{error}</ThemedText>}
      <View style={styles.hero}>
        <ThemedText style={styles.raceName}>{goal.name}</ThemedText>
        <ThemedText style={styles.raceMeta}>
          {p.location ? `${p.location} · ` : ''}{shortDate(goal.event_date)}{p.start_time && ` · sortida ${p.start_time}`}
        </ThemedText>
        {days != null && <ThemedText style={styles.countdown}>{days} dies</ThemedText>}
        {p.first_race_ever && <ThemedText style={styles.firstRace}>La teva primera cursa.</ThemedText>}
        <TouchableOpacity onPress={() => setEditing(goal)} hitSlop={8}>
          <ThemedText style={styles.editLink}>Edita</ThemedText>
        </TouchableOpacity>
      </View>

      {Array.isArray(p.segments) && (
        <View style={styles.card}>
          {p.segments.map((s: any, i: number) => (
            <View key={i} style={styles.segmentRow}>
              <ThemedText style={styles.segmentSport}>{sportLabel(s.sport)}</ThemedText>
              <ThemedText style={styles.segmentDist}>
                {s.sport === 'swim' ? `${s.distance_m} m` : `${s.distance_m / 1000} km`}
              </ThemedText>
              <ThemedText style={styles.segmentNotes}>{s.notes}</ThemedText>
            </View>
          ))}
        </View>
      )}

      {goal.notes && (
        <View style={styles.card}>
          <ThemedText style={styles.notesTitle}>Per al coach</ThemedText>
          <ThemedText style={styles.notes}>{goal.notes}</ThemedText>
        </View>
      )}

      <ThemedText style={styles.sectionTitle}>Temps objectiu</ThemedText>
      <View style={styles.card}>
        <View style={styles.timeRow}>
          <ThemedText style={styles.timeLabel} />
          {SCENARIOS.map((s) => (
            <ThemedText key={s} style={[styles.timeCell, styles.timeHeader]}>
              {s}
            </ThemedText>
          ))}
        </View>
        {TIME_ROWS.filter(([k]) => Array.isArray(times[k])).map(([key, label]) => {
          const derived = derivedPace(key, times[key][1] ?? null, p.segments);
          return (
            <View key={key}>
              <View style={styles.timeRow}>
                <ThemedText style={[styles.timeLabel, key === 'total' && styles.timeTotal]}>{label}</ThemedText>
                {times[key].map((sec: number | null, i: number) => (
                  <ThemedText key={i} style={[styles.timeCell, key === 'total' && styles.timeTotal]}>
                    {sec == null ? '—' : formatClock(sec)}
                  </ThemedText>
                ))}
              </View>
              {derived && <ThemedText style={styles.derivedPace}>{derived}</ThemedText>}
            </View>
          );
        })}
        {times.note && <ThemedText style={styles.note}>{times.note}</ThemedText>}
      </View>

      {logistics.length > 0 && (
        <>
          <ThemedText style={styles.sectionTitle}>Setmana de cursa</ThemedText>
          <View style={styles.card}>
            {logistics.map((t) => {
              const [, m, d] = t.local_date.split('-');
              return (
                <TouchableOpacity key={t.id} onPress={() => toggleLogistics(t)} style={styles.logisticsRow}>
                  <ThemedText style={[styles.logistics, t.done && styles.logisticsDone]}>
                    {t.done ? '✓' : '·'} {d}/{m} — {t.title}
                    {t.blocking && !t.done ? ' · imprescindible' : ''}
                  </ThemedText>
                  {t.detail && !t.done && <ThemedText style={styles.logisticsDetail}>{t.detail}</ThemedText>}
                </TouchableOpacity>
              );
            })}
          </View>
        </>
      )}

      {Array.isArray(p.race_day_protocol) && (
        <>
          <ThemedText style={styles.sectionTitle}>El dia de la cursa</ThemedText>
          <View style={styles.card}>
            {p.race_day_protocol.map((step: any, i: number) => (
              <View key={i} style={styles.protocolRow}>
                <ThemedText style={styles.protocolTime}>{step.time}</ThemedText>
                <View style={styles.protocolBody}>
                  <ThemedText style={styles.protocolWhat}>{step.what}</ThemedText>
                  {step.detail && <ThemedText style={styles.protocolDetail}>{step.detail}</ThemedText>}
                </View>
              </View>
            ))}
          </View>
        </>
      )}

      {p.pacing_rules && (
        <>
          <ThemedText style={styles.sectionTitle}>Com córrer-la</ThemedText>
          <View style={styles.card}>
            {Object.entries(p.pacing_rules).map(([k, v]) => (
              <ThemedText key={k} style={styles.pacing}>
                <ThemedText style={styles.pacingKey}>{k.toUpperCase()}</ThemedText> {String(v)}
              </ThemedText>
            ))}
          </View>
        </>
      )}

      {planSection}

      <ThemedText style={styles.sectionTitle}>Altres objectius</ThemedText>
      <View style={styles.card}>
        {others.length === 0 && <ThemedText style={styles.emptyOthers}>Cap més. El coach només mira aquest.</ThemedText>}
        {others.map((g) => (
          <TouchableOpacity key={g.id} style={styles.goalRow} onPress={() => setEditing(g)}>
            <ThemedText style={styles.priorityChip}>{g.priority}</ThemedText>
            <View style={styles.goalBody}>
              <ThemedText style={styles.goalName}>{g.name}</ThemedText>
              <ThemedText style={styles.goalMeta}>
                {sportLabel(g.discipline === 'triathlon' ? 'multisport' : g.discipline)} · {shortDate(g.event_date)}
              </ThemedText>
              {g.notes && <ThemedText style={styles.goalNotes}>{g.notes}</ThemedText>}
            </View>
          </TouchableOpacity>
        ))}
        {newButton}
      </View>

    </FormScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, gap: 12, paddingBottom: 48 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  hero: { alignItems: 'center', gap: 4 },
  raceName: { fontSize: 18, fontWeight: '800', textAlign: 'center', lineHeight: 24 },
  raceMeta: { fontSize: 13, opacity: 0.7 },
  countdown: { fontSize: 44, lineHeight: 52, fontWeight: '900', color: '#2e9e5b' },
  firstRace: { fontSize: 13, opacity: 0.7, fontStyle: 'italic' },
  card: { backgroundColor: 'rgba(127,127,127,0.1)', borderRadius: 12, padding: 14, gap: 8 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 4 },
  segmentRow: { flexDirection: 'row', alignItems: 'baseline', gap: 8 },
  segmentSport: { fontWeight: '700', width: 70 },
  segmentDist: { width: 64 },
  segmentNotes: { flex: 1, fontSize: 12, opacity: 0.7 },
  timeRow: { flexDirection: 'row' },
  timeLabel: { flex: 1.2, fontSize: 14 },
  timeCell: { flex: 1, fontSize: 14, textAlign: 'right', fontVariant: ['tabular-nums'] },
  timeHeader: { fontWeight: '700', fontSize: 12, opacity: 0.7 },
  timeTotal: { fontWeight: '800' },
  note: { fontSize: 12, opacity: 0.6, marginTop: 4 },
  derivedPace: { fontSize: 12, opacity: 0.6, textAlign: 'right', marginTop: -2 },
  notesTitle: { fontSize: 12, fontWeight: '700', opacity: 0.7 },
  notes: { fontSize: 14 },
  goalNotes: { fontSize: 12, opacity: 0.6, fontStyle: 'italic' },
  logisticsRow: { paddingVertical: 4 },
  logistics: { fontSize: 14 },
  logisticsDone: { opacity: 0.5, textDecorationLine: 'line-through' },
  logisticsDetail: { fontSize: 12, opacity: 0.7, marginLeft: 16 },
  protocolRow: { flexDirection: 'row', gap: 10 },
  protocolTime: { fontWeight: '700', width: 48, fontVariant: ['tabular-nums'] },
  protocolBody: { flex: 1 },
  protocolWhat: { fontWeight: '600' },
  protocolDetail: { fontSize: 13, opacity: 0.7 },
  pacing: { fontSize: 13, lineHeight: 19 },
  pacingKey: { fontSize: 13, fontWeight: '800' },
  error: { color: '#d64541', textAlign: 'center' },
  editLink: { fontSize: 13, color: '#3b82c4', fontWeight: '600', marginTop: 2 },
  emptyOthers: { fontSize: 13, opacity: 0.6 },
  goalRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 4 },
  priorityChip: { width: 26, height: 26, lineHeight: 26, borderRadius: 13, textAlign: 'center', fontWeight: '800', backgroundColor: 'rgba(127,127,127,0.15)', overflow: 'hidden' },
  goalBody: { flex: 1 },
  goalName: { fontSize: 15, fontWeight: '600' },
  goalMeta: { fontSize: 13, opacity: 0.7 },
  newButton: { alignSelf: 'flex-start', marginTop: 4, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 8, backgroundColor: '#1D3D47' },
  newButtonText: { color: '#fff', fontWeight: '700' },
  blockRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 4, borderRadius: 8, paddingHorizontal: 4 },
  blockCurrent: { backgroundColor: 'rgba(46,158,91,0.12)' },
  phaseChip: { fontSize: 11, fontWeight: '700', paddingVertical: 3, paddingHorizontal: 8, borderRadius: 10, backgroundColor: 'rgba(127,127,127,0.15)', overflow: 'hidden' },
  working: { fontSize: 13, fontStyle: 'italic', opacity: 0.8, marginTop: 4 },
});
