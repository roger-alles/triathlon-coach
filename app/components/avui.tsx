import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';

import {
  DailyReport,
  PlanSession,
  getLatestDailyReport,
  getSessionsForDay,
  localDateISO,
} from '@/lib/api';
import { formatDateCa, formatDuration, formatStep, sportLabel, verdictColor } from '@/lib/format';
import { supabase } from '@/lib/supabase';

const VERDICT_LABEL: Record<string, string> = { green: 'VERD', amber: 'ÀMBAR', red: 'VERMELL' };

export default function Avui() {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [sessions, setSessions] = useState<PlanSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const insets = useSafeAreaInsets();

  const load = useCallback(async () => {
    setError(null);
    try {
      const [r, s] = await Promise.all([getLatestDailyReport(), getSessionsForDay(localDateISO())]);
      setReport(r);
      setSessions(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
    setRefreshing(false);
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

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
      }>
      <ThemedText style={styles.date}>{formatDateCa(new Date())}</ThemedText>

      {error && <ThemedText style={styles.error}>{error}</ThemedText>}

      {report ? (
        <View style={[styles.banner, { backgroundColor: verdictColor(report.verdict) }]}>
          <Text style={styles.bannerVerdict}>{VERDICT_LABEL[report.verdict] ?? report.verdict}</Text>
          <Text style={styles.bannerSummary}>{report.summary}</Text>
        </View>
      ) : (
        !error && <ThemedText style={styles.muted}>Encara no hi ha informe del coach.</ThemedText>
      )}

      {sessions.map((s, i) => (
        <View key={s.id} style={styles.card}>
          <ThemedText style={styles.cardTitle}>
            {sessions.length > 1 ? `Sessió d'avui (${i + 1} de ${sessions.length})` : "Sessió d'avui"}
          </ThemedText>
          <ThemedText style={styles.cardMeta}>
            {sportLabel(s.sport)}
            {s.duration_sec_target != null && ` · ${formatDuration(s.duration_sec_target)}`}
            {` · ${s.title}`}
            {s.is_test && ' · TEST'}
          </ThemedText>
          {(s.structure?.steps ?? []).map((step, i) => (
            <ThemedText key={i} style={styles.step}>
              {formatStep(step)}
            </ThemedText>
          ))}
        </View>
      ))}

      {report && (
        <>
          <ThemedText style={styles.rationale}>{report.rationale}</ThemedText>
          {report.questions.length > 0 && (
            <View style={styles.card}>
              <ThemedText style={styles.cardTitle}>El coach et pregunta</ThemedText>
              {report.questions.map((q, i) => (
                <ThemedText key={i} style={styles.step}>
                  · {q}
                </ThemedText>
              ))}
            </View>
          )}
        </>
      )}

      <TouchableOpacity onPress={() => supabase.auth.signOut()}>
        <ThemedText style={styles.logout}>Surt</ThemedText>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, gap: 12, paddingBottom: 48 },
  date: { fontSize: 22, fontWeight: '800' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  banner: { borderRadius: 12, padding: 16 },
  bannerVerdict: { color: '#fff', fontWeight: '800', fontSize: 13, letterSpacing: 2 },
  bannerSummary: { color: '#fff', fontSize: 17, fontWeight: '600', marginTop: 6 },
  card: { backgroundColor: 'rgba(127,127,127,0.1)', borderRadius: 12, padding: 14, gap: 4 },
  cardTitle: { fontSize: 16, fontWeight: '700' },
  cardMeta: { fontSize: 14, opacity: 0.7 },
  step: { fontSize: 14, marginTop: 2 },
  rationale: { fontSize: 15, lineHeight: 22 },
  muted: { opacity: 0.6, textAlign: 'center', marginTop: 8 },
  error: { color: '#d64541', textAlign: 'center' },
  logout: { textAlign: 'center', opacity: 0.5, marginTop: 16 },
});
