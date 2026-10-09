import { router } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import LogSession from '@/components/log-session';
import WeekRequestBox from '@/components/week-request';
import { ThemedText } from '@/components/themed-text';
import {
  Activity,
  PlanBlock,
  PlanSession,
  getActivitiesForRange,
  getBlockForRange,
  getSessionsForRange,
  localDateISO,
  parseLocalISO,
  weekDaysISO,
} from '@/lib/api';
import {
  formatDuration,
  formatSegment,
  formatStep,
  formatWeekRangeCa,
  droppedLast,
  isDropped,
  sportEmoji,
  sportLabel,
  statusColor,
  statusLabel,
} from '@/lib/format';

const WEEKDAY_NAMES = ['Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 'Divendres', 'Dissabte', 'Diumenge'];

type WeekSession = PlanSession & { local_date: string };

export default function Setmana() {
  const [sessions, setSessions] = useState<WeekSession[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [block, setBlock] = useState<PlanBlock | null>(null);
  const [weekOffset, setWeekOffset] = useState(0);
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const insets = useSafeAreaInsets();

  const today = localDateISO();
  // Setmana relativa a avui (offset 0 = actual). Es deriva de localDateISO()
  // i no de new Date() perquè els tests fixin el dia.
  const days = useMemo(() => {
    const base = parseLocalISO(today);
    base.setDate(base.getDate() + 7 * weekOffset);
    return weekDaysISO(base);
  }, [today, weekOffset]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, a, b] = await Promise.all([
        getSessionsForRange(days[0], days[6]),
        getActivitiesForRange(days[0], days[6]),
        getBlockForRange(days[0], days[6]),
      ]);
      setSessions(s);
      setActivities(a);
      setBlock(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
    setRefreshing(false);
  }, [days]);

  useEffect(() => {
    // load() només fa setState després d'un await (no és síncron); la regla
    // del React Compiler no distingeix el codi que hi ha després de l'await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    load();
  }, [load]);

  const toggle = (id: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const linked = new Map(activities.filter((a) => a.plan_session_id != null).map((a) => [a.plan_session_id, a]));

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
      }>
      <View style={styles.header}>
        <TouchableOpacity
          accessibilityRole="button"
          accessibilityLabel="Setmana anterior"
          onPress={() => setWeekOffset((o) => o - 1)}
          hitSlop={12}>
          <ThemedText style={styles.arrow}>‹</ThemedText>
        </TouchableOpacity>
        <ThemedText style={styles.range}>{formatWeekRangeCa(days[0], days[6])}</ThemedText>
        <TouchableOpacity
          accessibilityRole="button"
          accessibilityLabel="Setmana següent"
          onPress={() => setWeekOffset((o) => o + 1)}
          hitSlop={12}>
          <ThemedText style={styles.arrow}>›</ThemedText>
        </TouchableOpacity>
      </View>
      <View style={styles.subheader}>
        <ThemedText style={styles.block}>{block?.name ?? ''}</ThemedText>
        {weekOffset !== 0 && (
          <TouchableOpacity accessibilityRole="button" onPress={() => setWeekOffset(0)} hitSlop={12}>
            <ThemedText style={styles.todayLink}>Avui</ThemedText>
          </TouchableOpacity>
        )}
      </View>

      {error && <ThemedText style={styles.error}>{error}</ThemedText>}

      {/* una setmana ja passada no es pot redissenyar */}
      {days[6] >= today && <WeekRequestBox weekStart={days[0]} onApplied={load} />}

      {loading && (
        <View style={styles.center}>
          <ActivityIndicator size="large" />
        </View>
      )}

      {!loading && days.map((day, i) => {
        const daySessions = droppedLast(sessions.filter((s) => s.local_date === day));
        const extras = activities.filter((a) => a.local_date === day && a.plan_session_id == null);
        const isToday = day === today;
        return (
          <View key={day} style={[styles.day, isToday && styles.today]}>
            <ThemedText style={styles.dayTitle}>
              {WEEKDAY_NAMES[i]} {Number(day.slice(8))}
              {isToday && ' · avui'}
            </ThemedText>

            {daySessions.length === 0 && extras.length === 0 && (
              <ThemedText style={styles.emptyDay}>—</ThemedText>
            )}

            {daySessions.map((s) => {
              const real = linked.get(s.id);
              const dropped = isDropped(s.status);
              return (
                <View key={s.id} style={[styles.session, dropped && styles.dropped]}>
                  <View style={[styles.dot, dropped ? styles.droppedDot : { backgroundColor: statusColor(s.status) }]} />
                  <TouchableOpacity
                    style={styles.sessionBody}
                    accessibilityRole="button"
                    onPress={() => toggle(s.id)}>
                    <View style={styles.titleRow}>
                      <ThemedText style={styles.emoji}>{sportEmoji(s.sport)}</ThemedText>
                      <ThemedText style={[styles.sessionTitle, dropped && styles.strike]}>{s.title}</ThemedText>
                      {s.priority === 'key' && s.sport !== 'rest' && !dropped && (
                        <ThemedText style={styles.key}>CLAU</ThemedText>
                      )}
                    </View>
                    <ThemedText style={styles.sessionMeta}>
                      {sportLabel(s.sport)}
                      {s.duration_sec_target != null && ` · ${formatDuration(s.duration_sec_target)}`}
                      {' · '}
                      <ThemedText style={[styles.sessionMeta, { color: statusColor(s.status) }]}>
                        {statusLabel(s.status)}
                      </ThemedText>
                    </ThemedText>
                    {real?.duration_sec != null && (
                      <TouchableOpacity
                        onPress={() => router.push({ pathname: '/activitat', params: { id: real.id } })}>
                        <ThemedText style={styles.real}>
                          Real: {formatDuration(real.duration_sec)} ›
                        </ThemedText>
                      </TouchableOpacity>
                    )}
                    {open.has(s.id) && (
                      <View style={styles.detail}>
                        {(s.structure?.steps ?? []).map((step, j) => (
                          <ThemedText key={`s${j}`} style={styles.step}>
                            {formatStep(step)}
                          </ThemedText>
                        ))}
                        {(s.structure?.segments ?? []).map((seg, j) => (
                          <ThemedText key={`g${j}`} style={styles.step}>
                            {formatSegment(seg)}
                          </ThemedText>
                        ))}
                        {s.rationale && <ThemedText style={styles.rationale}>{s.rationale}</ThemedText>}
                      </View>
                    )}
                    {day <= today && (
                      <LogSession
                        session={s}
                        dateISO={s.local_date}
                        logged={new Set(activities.filter((a) => a.plan_session_id === s.id).map((a) => a.sport))}
                        onSaved={load}
                      />
                    )}
                  </TouchableOpacity>
                </View>
              );
            })}

            {extras.map((a) => (
              <TouchableOpacity
                key={a.id}
                style={styles.session}
                onPress={() => router.push({ pathname: '/activitat', params: { id: a.id } })}>
                <View style={[styles.dot, styles.extraDot]} />
                <ThemedText style={styles.sessionMeta}>
                  Fora de pla · {sportEmoji(a.sport)} {sportLabel(a.sport)}
                  {a.duration_sec != null && ` · ${formatDuration(a.duration_sec)}`} ›
                </ThemedText>
              </TouchableOpacity>
            ))}
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, gap: 10, paddingBottom: 48 },
  center: { paddingVertical: 48, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  arrow: { fontSize: 30, lineHeight: 34, paddingHorizontal: 12, fontWeight: '600' },
  range: { fontSize: 18, fontWeight: '700' },
  subheader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  block: { flex: 1, fontSize: 13, opacity: 0.8 },
  todayLink: { fontSize: 14, fontWeight: '600', color: '#2e9e5b' },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  emoji: { fontSize: 15 },
  key: { fontSize: 11, fontWeight: '700', color: '#2e9e5b', letterSpacing: 0.5, marginTop: 4 },
  detail: { marginTop: 4, gap: 2 },
  step: { fontSize: 13, opacity: 0.85 },
  rationale: { fontSize: 13, opacity: 0.7, fontStyle: 'italic', marginTop: 2 },
  day: { borderRadius: 12, padding: 12, gap: 6, backgroundColor: 'rgba(127,127,127,0.08)' },
  today: { borderWidth: 1.5, borderColor: '#2e9e5b' },
  dayTitle: { fontSize: 15, fontWeight: '700' },
  emptyDay: { opacity: 0.4 },
  session: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 5 },
  extraDot: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: '#8a8a8a' },
  sessionBody: { flex: 1 },
  sessionTitle: { fontSize: 15, fontWeight: '600', flex: 1 },
  dropped: { opacity: 0.45 },
  droppedDot: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: '#8a8a8a' },
  strike: { textDecorationLine: 'line-through' },
  sessionMeta: { fontSize: 13, opacity: 0.8 },
  real: { fontSize: 13, opacity: 0.7, fontStyle: 'italic' },
  error: { color: '#d64541', textAlign: 'center' },
});
