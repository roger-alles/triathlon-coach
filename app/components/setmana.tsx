import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import {
  Activity,
  PlanSession,
  getActivitiesForRange,
  getSessionsForRange,
  localDateISO,
  weekDaysISO,
} from '@/lib/api';
import { formatDuration, sportLabel, statusColor, statusLabel } from '@/lib/format';

const WEEKDAY_NAMES = ['Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 'Divendres', 'Dissabte', 'Diumenge'];

type WeekSession = PlanSession & { local_date: string };

export default function Setmana() {
  const [sessions, setSessions] = useState<WeekSession[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const insets = useSafeAreaInsets();

  const days = weekDaysISO();
  const today = localDateISO();

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, a] = await Promise.all([
        getSessionsForRange(days[0], days[6]),
        getActivitiesForRange(days[0], days[6]),
      ]);
      setSessions(s);
      setActivities(a);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
    setRefreshing(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  const linked = new Map(activities.filter((a) => a.plan_session_id != null).map((a) => [a.plan_session_id, a]));

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
      }>
      {error && <ThemedText style={styles.error}>{error}</ThemedText>}

      {days.map((day, i) => {
        const daySessions = sessions.filter((s) => s.local_date === day);
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
              return (
                <View key={s.id} style={styles.session}>
                  <View style={[styles.dot, { backgroundColor: statusColor(s.status) }]} />
                  <View style={styles.sessionBody}>
                    <ThemedText style={styles.sessionTitle}>{s.title}</ThemedText>
                    <ThemedText style={styles.sessionMeta}>
                      {sportLabel(s.sport)}
                      {s.duration_sec_target != null && ` · ${formatDuration(s.duration_sec_target)}`}
                      {' · '}
                      <ThemedText style={[styles.sessionMeta, { color: statusColor(s.status) }]}>
                        {statusLabel(s.status)}
                      </ThemedText>
                    </ThemedText>
                    {real?.duration_sec != null && (
                      <ThemedText style={styles.real}>Real: {formatDuration(real.duration_sec)}</ThemedText>
                    )}
                  </View>
                </View>
              );
            })}

            {extras.map((a) => (
              <View key={a.id} style={styles.session}>
                <View style={[styles.dot, styles.extraDot]} />
                <ThemedText style={styles.sessionMeta}>
                  Fora de pla · {sportLabel(a.sport)}
                  {a.duration_sec != null && ` · ${formatDuration(a.duration_sec)}`}
                </ThemedText>
              </View>
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
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  day: { borderRadius: 12, padding: 12, gap: 6, backgroundColor: 'rgba(127,127,127,0.08)' },
  today: { borderWidth: 1.5, borderColor: '#2e9e5b' },
  dayTitle: { fontSize: 15, fontWeight: '700' },
  emptyDay: { opacity: 0.4 },
  session: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 5 },
  extraDot: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: '#8a8a8a' },
  sessionBody: { flex: 1 },
  sessionTitle: { fontSize: 15, fontWeight: '600' },
  sessionMeta: { fontSize: 13, opacity: 0.8 },
  real: { fontSize: 13, opacity: 0.7, fontStyle: 'italic' },
  error: { color: '#d64541', textAlign: 'center' },
});
