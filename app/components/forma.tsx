import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Line, Polyline } from 'react-native-svg';

import { ThemedText } from '@/components/themed-text';
import { TouchableOpacity } from 'react-native';
import { FormDay, getFormSeries, localDateISO } from '@/lib/api';
import { extent, polylinePoints } from '@/lib/chart';

const DAYS_SHOWN = 90;
const CHART_HEIGHT = 180;

const COLORS = { ctl: '#3b82c4', atl: '#e6a817', tsb: '#2e9e5b' };

export default function Forma() {
  const [series, setSeries] = useState<FormDay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [rangeDays, setRangeDays] = useState(30);
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();

  const load = useCallback(async () => {
    setError(null);
    try {
      const since = new Date();
      since.setDate(since.getDate() - DAYS_SHOWN);
      setSeries(await getFormSeries(localDateISO(since)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
    setRefreshing(false);
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

  const today = series.at(-1);
  const shown = series.slice(-rangeDays);
  const chartWidth = width - 32;
  const { min, max } = shown.length
    ? extent([shown.map((d) => d.ctl), shown.map((d) => d.atl), shown.map((d) => d.tsb)], 0.05)
    : { min: 0, max: 1 };
  const zeroY = CHART_HEIGHT - ((0 - min) / (max - min || 1)) * CHART_HEIGHT;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
      }>
      {error && <ThemedText style={styles.error}>{error}</ThemedText>}

      {!error && series.length === 0 && (
        <ThemedText style={styles.muted}>Encara no hi ha dades de forma.</ThemedText>
      )}

      {today && (
        <View style={styles.numbers}>
          <Metric label="Forma" sub="CTL" value={today.ctl} color={COLORS.ctl} />
          <Metric label="Fatiga" sub="ATL" value={today.atl} color={COLORS.atl} />
          <Metric label="Frescor" sub="TSB" value={today.tsb} color={COLORS.tsb} />
        </View>
      )}

      {series.length > 1 && (
        <View style={styles.rangeRow}>
          {[7, 30, 90].map((d) => (
            <TouchableOpacity
              key={d}
              style={[styles.rangeButton, rangeDays === d && styles.rangeActive]}
              onPress={() => setRangeDays(d)}>
              <ThemedText style={[styles.rangeText, rangeDays === d && styles.rangeTextActive]}>
                {d} dies
              </ThemedText>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {shown.length > 1 && (
        <View>
          <Svg width={chartWidth} height={CHART_HEIGHT}>
            <Line x1={0} y1={zeroY} x2={chartWidth} y2={zeroY} stroke="#8a8a8a" strokeWidth={1} strokeDasharray="4 4" />
            <Polyline
              points={polylinePoints(shown.map((d) => d.ctl), chartWidth, CHART_HEIGHT, min, max)}
              fill="none" stroke={COLORS.ctl} strokeWidth={2}
            />
            <Polyline
              points={polylinePoints(shown.map((d) => d.atl), chartWidth, CHART_HEIGHT, min, max)}
              fill="none" stroke={COLORS.atl} strokeWidth={2}
            />
            <Polyline
              points={polylinePoints(shown.map((d) => d.tsb), chartWidth, CHART_HEIGHT, min, max)}
              fill="none" stroke={COLORS.tsb} strokeWidth={2.5}
            />
          </Svg>
          <ThemedText style={styles.axis}>
            {shown[0].local_date.slice(5)} → {shown.at(-1)!.local_date.slice(5)} · la línia de punts és el zero de frescor
          </ThemedText>
        </View>
      )}

      <View style={styles.card}>
        <ThemedText style={styles.explain}>
          <ThemedText style={[styles.explain, { color: COLORS.ctl, fontWeight: '700' }]}>Forma (CTL)</ThemedText>
          {': el fons que has construït (mitjana de càrrega de 42 dies). Puja lent, baixa lent.\n'}
          <ThemedText style={[styles.explain, { color: COLORS.atl, fontWeight: '700' }]}>Fatiga (ATL)</ThemedText>
          {': el cansament recent (mitjana de 7 dies). Puja i baixa ràpid.\n'}
          <ThemedText style={[styles.explain, { color: COLORS.tsb, fontWeight: '700' }]}>Frescor (TSB)</ThemedText>
          {': forma menys fatiga. Negatiu = entrenant fort; prop de zero o positiu = a punt per rendir. El dia de la cursa la vols en positiu.'}
        </ThemedText>
      </View>
    </ScrollView>
  );
}

function Metric({ label, sub, value, color }: { label: string; sub: string; value: number; color: string }) {
  return (
    <View style={styles.metric}>
      <ThemedText style={[styles.metricValue, { color }]}>{value}</ThemedText>
      <ThemedText style={styles.metricLabel}>{label}</ThemedText>
      <ThemedText style={styles.metricSub}>{sub}</ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, gap: 16, paddingBottom: 48 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  numbers: { flexDirection: 'row', justifyContent: 'space-around' },
  metric: { alignItems: 'center' },
  metricValue: { fontSize: 32, lineHeight: 40, fontWeight: '800' },
  rangeRow: { flexDirection: 'row', justifyContent: 'center', gap: 8 },
  rangeButton: { paddingVertical: 6, paddingHorizontal: 14, borderRadius: 16, backgroundColor: 'rgba(127,127,127,0.12)' },
  rangeActive: { backgroundColor: '#3b82c4' },
  rangeText: { fontSize: 13 },
  rangeTextActive: { color: '#fff', fontWeight: '700' },
  metricLabel: { fontSize: 14, fontWeight: '600' },
  metricSub: { fontSize: 11, opacity: 0.5 },
  axis: { fontSize: 11, opacity: 0.5, textAlign: 'center', marginTop: 4 },
  card: { backgroundColor: 'rgba(127,127,127,0.1)', borderRadius: 12, padding: 14 },
  explain: { fontSize: 14, lineHeight: 21 },
  muted: { opacity: 0.6, textAlign: 'center', marginTop: 8 },
  error: { color: '#d64541', textAlign: 'center' },
});
