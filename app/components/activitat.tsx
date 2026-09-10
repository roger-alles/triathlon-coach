import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ActivityDetail, getActivity, updateActivitySubjective } from '@/lib/api';
import { formatDateCa, formatDuration, sportEmoji, sportLabel } from '@/lib/format';

const FEELINGS: [number, string][] = [
  [1, 'Fatal'],
  [2, 'Fluix'],
  [3, 'Normal'],
  [4, 'Bé'],
  [5, 'Genial'],
];

export default function Activitat({ id }: { id: number }) {
  const [activity, setActivity] = useState<ActivityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rpe, setRpe] = useState<number | null>(null);
  const [feeling, setFeeling] = useState<number | null>(null);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getActivity(id)
      .then((a) => {
        setActivity(a);
        if (a) {
          setRpe(a.perceived_effort);
          setFeeling(a.feeling);
          setNotes(a.athlete_notes ?? '');
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  const save = useCallback(async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await updateActivitySubjective(id, {
        perceived_effort: rpe,
        feeling,
        athlete_notes: notes.trim() || null,
      });
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setSaving(false);
  }, [id, rpe, feeling, notes]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  if (!activity) {
    return (
      <View style={styles.center}>
        <ThemedText>{error ?? 'Activitat no trobada.'}</ThemedText>
      </View>
    );
  }

  const [y, m, d] = activity.local_date.split('-').map(Number);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <ThemedText style={styles.title}>
        {sportEmoji(activity.sport)} {sportLabel(activity.sport)} · {formatDateCa(new Date(y, m - 1, d))}
      </ThemedText>

      <View style={styles.card}>
        {activity.duration_sec != null && <Row label="Durada" value={formatDuration(activity.duration_sec)} />}
        {activity.distance_m != null && (
          <Row label="Distància" value={`${(activity.distance_m / 1000).toFixed(1)} km`} />
        )}
        {activity.avg_hr != null && <Row label="FC mitjana" value={`${activity.avg_hr} ppm`} />}
        {activity.max_hr != null && <Row label="FC màxima" value={`${activity.max_hr} ppm`} />}
        {activity.elevation_gain_m != null && <Row label="Desnivell" value={`${Math.round(activity.elevation_gain_m)} m`} />}
        {activity.load != null && <Row label="Càrrega" value={`${Math.round(Number(activity.load))}`} />}
      </View>

      <ThemedText style={styles.sectionTitle}>Com ha anat? (el coach ho llegeix)</ThemedText>

      <ThemedText style={styles.fieldLabel}>Esforç percebut (RPE 1-10)</ThemedText>
      <View style={styles.chips}>
        {Array.from({ length: 10 }, (_, i) => i + 1).map((v) => (
          <TouchableOpacity
            key={v}
            style={[styles.chip, rpe === v && styles.chipActive]}
            onPress={() => setRpe(v)}>
            <ThemedText style={[styles.chipText, rpe === v && styles.chipTextActive]}>{v}</ThemedText>
          </TouchableOpacity>
        ))}
      </View>

      <ThemedText style={styles.fieldLabel}>Sensacions</ThemedText>
      <View style={styles.chips}>
        {FEELINGS.map(([v, label]) => (
          <TouchableOpacity
            key={v}
            style={[styles.chip, feeling === v && styles.chipActive]}
            onPress={() => setFeeling(v)}>
            <ThemedText style={[styles.chipText, feeling === v && styles.chipTextActive]}>{label}</ThemedText>
          </TouchableOpacity>
        ))}
      </View>

      <TextInput
        style={styles.notes}
        placeholder="Notes per al coach (genoll, son, calor…)"
        placeholderTextColor="#8a8a8a"
        multiline
        value={notes}
        onChangeText={(t) => { setNotes(t); setSaved(false); }}
      />

      {error && <ThemedText style={styles.error}>{error}</ThemedText>}
      {saved && <ThemedText style={styles.saved}>Desat. El coach ho veurà al pròxim informe.</ThemedText>}

      <TouchableOpacity style={styles.button} onPress={save} disabled={saving}>
        {saving ? <ActivityIndicator color="#fff" /> : <ThemedText style={styles.buttonText}>Desa</ThemedText>}
      </TouchableOpacity>
    </ScrollView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <ThemedText style={styles.rowLabel}>{label}</ThemedText>
      <ThemedText style={styles.rowValue}>{value}</ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, gap: 10, paddingBottom: 48 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  title: { fontSize: 20, fontWeight: '800', lineHeight: 26 },
  card: { backgroundColor: 'rgba(127,127,127,0.1)', borderRadius: 12, padding: 14, gap: 6 },
  row: { flexDirection: 'row', justifyContent: 'space-between' },
  rowLabel: { opacity: 0.7 },
  rowValue: { fontWeight: '600' },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 8 },
  fieldLabel: { fontSize: 13, opacity: 0.7 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 18,
    backgroundColor: 'rgba(127,127,127,0.12)',
  },
  chipActive: { backgroundColor: '#3b82c4' },
  chipText: { fontSize: 14 },
  chipTextActive: { color: '#fff', fontWeight: '700' },
  notes: {
    borderWidth: 1,
    borderColor: 'rgba(127,127,127,0.4)',
    borderRadius: 10,
    padding: 12,
    minHeight: 80,
    fontSize: 15,
    color: '#888',
    textAlignVertical: 'top',
  },
  button: { backgroundColor: '#1D3D47', borderRadius: 10, padding: 14, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '700' },
  error: { color: '#d64541' },
  saved: { color: '#2e9e5b' },
});
