import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { Goal, LogisticsTask, getActiveGoal, getLogistics } from '@/lib/api';
import { daysUntil, formatClock, sportLabel } from '@/lib/format';

const SCENARIOS = ['Prudent', 'Objectiu', 'Gran dia'];
const TIME_ROWS: [string, string][] = [
  ['swim', 'Natació'],
  ['t1', 'T1'],
  ['bike', 'Bici'],
  ['t2', 'T2'],
  ['run', 'Cursa'],
  ['total', 'Total'],
];

export default function Objectius() {
  const [goal, setGoal] = useState<Goal | null>(null);
  const [logistics, setLogistics] = useState<LogisticsTask[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const insets = useSafeAreaInsets();

  useEffect(() => {
    getActiveGoal()
      .then(async (g) => {
        setGoal(g);
        if (g) setLogistics(await getLogistics(g.id));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  if (!goal) {
    return (
      <View style={styles.center}>
        <ThemedText>{error ?? 'Cap objectiu actiu.'}</ThemedText>
      </View>
    );
  }

  const p = goal.profile;
  const days = daysUntil(goal.event_date);
  const times = p.target_times_sec ?? {};

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}>
      <View style={styles.hero}>
        <ThemedText style={styles.raceName}>{goal.name}</ThemedText>
        <ThemedText style={styles.raceMeta}>
          {p.location} · 27/09/2026{p.start_time && ` · sortida ${p.start_time}`}
        </ThemedText>
        <ThemedText style={styles.countdown}>{days} dies</ThemedText>
        {p.first_race_ever && <ThemedText style={styles.firstRace}>La teva primera cursa.</ThemedText>}
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
        {TIME_ROWS.filter(([k]) => Array.isArray(times[k])).map(([key, label]) => (
          <View key={key} style={styles.timeRow}>
            <ThemedText style={[styles.timeLabel, key === 'total' && styles.timeTotal]}>{label}</ThemedText>
            {times[key].map((sec: number, i: number) => (
              <ThemedText key={i} style={[styles.timeCell, key === 'total' && styles.timeTotal]}>
                {formatClock(sec)}
              </ThemedText>
            ))}
          </View>
        ))}
        {times.note && <ThemedText style={styles.note}>{times.note}</ThemedText>}
      </View>

      {logistics.length > 0 && (
        <>
          <ThemedText style={styles.sectionTitle}>Setmana de cursa</ThemedText>
          <View style={styles.card}>
            {logistics.map((t) => {
              const [, m, d] = t.local_date.split('-');
              return (
                <ThemedText key={t.id} style={styles.logistics}>
                  {t.done ? '✓' : '·'} {d}/{m} — {t.title}
                </ThemedText>
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
    </ScrollView>
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
  logistics: { fontSize: 14 },
  protocolRow: { flexDirection: 'row', gap: 10 },
  protocolTime: { fontWeight: '700', width: 48, fontVariant: ['tabular-nums'] },
  protocolBody: { flex: 1 },
  protocolWhat: { fontWeight: '600' },
  protocolDetail: { fontSize: 13, opacity: 0.7 },
  pacing: { fontSize: 13, lineHeight: 19 },
  pacingKey: { fontSize: 13, fontWeight: '800' },
});
