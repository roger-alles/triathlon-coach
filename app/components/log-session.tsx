import { useState } from 'react';
import { ActivityIndicator, StyleSheet, TextInput, TouchableOpacity, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { PlanSession, logManualActivity } from '@/lib/api';

// "Ho he fet": registrar una sessió feta sense rellotge des de la targeta del
// dia. Els valors del pla venen preomplerts; el sync horari farà la resta
// (càrrega estimada, estat de la sessió) en menys d'una hora.

const LOGGABLE = new Set(['swim', 'bike', 'run']);
const SWIM_VENUES: [string, string][] = [
  ['open_water', 'Mar'],
  ['lap_swimming', 'Piscina'],
];

export default function LogSession({ session, dateISO }: { session: PlanSession; dateISO: string }) {
  const [open, setOpen] = useState(false);
  const [minutes, setMinutes] = useState(
    session.duration_sec_target != null ? String(Math.round(session.duration_sec_target / 60)) : ''
  );
  const [meters, setMeters] = useState(
    session.distance_m_target != null ? String(Math.round(session.distance_m_target)) : ''
  );
  const [venue, setVenue] = useState<string | null>(null);
  const [rpe, setRpe] = useState<number | null>(null);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (!LOGGABLE.has(session.sport) || session.status !== 'planned') return null;
  if (done) {
    return (
      <ThemedText style={styles.done}>
        Registrada. El coach ho veurà a la propera sincronització (menys d&apos;una hora).
      </ThemedText>
    );
  }
  if (!open) {
    return (
      <TouchableOpacity style={styles.openButton} onPress={() => setOpen(true)}>
        <ThemedText style={styles.openText}>Ho he fet</ThemedText>
      </TouchableOpacity>
    );
  }

  const durationSec = Math.round(Number(minutes) * 60);
  const canSave = Number.isFinite(durationSec) && durationSec > 0 && !busy;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const distance = meters.trim() ? Math.round(Number(meters)) : null;
      await logManualActivity({
        local_date: dateISO,
        sport: session.sport,
        ...(session.sport === 'swim' && venue ? { sub_sport: venue } : {}),
        duration_sec: durationSec,
        distance_m: Number.isFinite(distance as number) ? distance : null,
        perceived_effort: rpe,
        athlete_notes: notes.trim() || null,
        plan_session_id: session.id,
      });
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  return (
    <View style={styles.form}>
      <View style={styles.row}>
        <Field label="Minuts" value={minutes} onChange={setMinutes} />
        <Field label="Metres" value={meters} onChange={setMeters} />
      </View>
      {session.sport === 'swim' && (
        <View style={styles.chips}>
          {SWIM_VENUES.map(([v, label]) => (
            <Chip key={v} label={label} active={venue === v} onPress={() => setVenue(v)} />
          ))}
        </View>
      )}
      <ThemedText style={styles.label}>Esforç percebut (RPE 1-10)</ThemedText>
      <View style={styles.chips}>
        {Array.from({ length: 10 }, (_, i) => i + 1).map((v) => (
          <Chip key={v} label={String(v)} active={rpe === v} onPress={() => setRpe(v)} />
        ))}
      </View>
      <TextInput
        style={styles.notes}
        placeholder="Notes per al coach"
        placeholderTextColor="#8a8a8a"
        multiline
        value={notes}
        onChangeText={setNotes}
      />
      {error && <ThemedText style={styles.error}>{error}</ThemedText>}
      <View style={styles.row}>
        <TouchableOpacity style={styles.cancel} onPress={() => setOpen(false)} disabled={busy}>
          <ThemedText style={styles.cancelText}>Cancel·la</ThemedText>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.button, !canSave && { opacity: 0.4 }]} onPress={save} disabled={!canSave}>
          {busy ? <ActivityIndicator color="#fff" /> : <ThemedText style={styles.buttonText}>Registra</ThemedText>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <View style={styles.field}>
      <ThemedText style={styles.label}>{label}</ThemedText>
      <TextInput style={styles.input} keyboardType="numeric" value={value} onChangeText={onChange} />
    </View>
  );
}

function Chip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity style={[styles.chip, active && styles.chipActive]} onPress={onPress}>
      <ThemedText style={[styles.chipText, active && styles.chipTextActive]}>{label}</ThemedText>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  openButton: { alignSelf: 'flex-start', marginTop: 6, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, backgroundColor: 'rgba(127,127,127,0.15)' },
  openText: { fontSize: 13, fontWeight: '600' },
  done: { color: '#2e9e5b', fontSize: 13, marginTop: 6 },
  form: { gap: 8, marginTop: 8 },
  row: { flexDirection: 'row', gap: 10 },
  field: { flex: 1, gap: 4 },
  label: { fontSize: 12, opacity: 0.7 },
  input: { borderWidth: 1, borderColor: 'rgba(127,127,127,0.4)', borderRadius: 8, padding: 8, fontSize: 15, color: '#888' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 16, backgroundColor: 'rgba(127,127,127,0.12)' },
  chipActive: { backgroundColor: '#3b82c4' },
  chipText: { fontSize: 13 },
  chipTextActive: { color: '#fff', fontWeight: '700' },
  notes: { borderWidth: 1, borderColor: 'rgba(127,127,127,0.4)', borderRadius: 8, padding: 8, minHeight: 48, fontSize: 14, color: '#888', textAlignVertical: 'top' },
  error: { color: '#d64541' },
  button: { flex: 1, backgroundColor: '#1D3D47', borderRadius: 8, padding: 10, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '700' },
  cancel: { padding: 10, alignItems: 'center' },
  cancelText: { opacity: 0.6 },
});
