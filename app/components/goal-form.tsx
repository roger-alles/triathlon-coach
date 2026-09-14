import { useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, TextInput, TouchableOpacity, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Goal, GoalInput, abandonGoal, upsertGoal } from '@/lib/api';
import { formatClock, parseClock } from '@/lib/format';

// Alta i edició d'un objectiu. El perfil (distàncies per segment) es construeix
// com el de Fornells (profile.segments) perquè el coach i el validador (R13)
// hi treballin igual. En editar es conserva la resta del perfil (temps
// objectiu, protocol de cursa...) que l'app no edita.

const DISCIPLINES: [Goal['discipline'], string][] = [
  ['triathlon', 'Triatló'],
  ['run', 'Cursa'],
  ['bike', 'Bici'],
  ['swim', 'Natació'],
  ['ultra_endurance', 'Ultra'],
];
const PRIORITIES: Goal['priority'][] = ['A', 'B', 'C'];
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

type Props = { goal?: Goal; onDone: () => void; onCancel: () => void };

function segmentOf(goal: Goal | undefined, sport: string): number | null {
  const seg = (goal?.profile?.segments ?? []).find((s: any) => s.sport === sport);
  return seg?.distance_m ?? null;
}
const km = (m: number | null) => (m == null ? '' : String(m / 1000));
const meters = (m: number | null) => (m == null ? '' : String(m));

// Temps objectiu: profile.target_times_sec.{clau} és [prudent, objectiu, gran dia];
// l'app només edita l'objectiu (índex 1, el que llegeixen el coach i R8).
type Times = Record<string, any>;
const TIME_KEYS = ['swim', 'bike', 'run'] as const;
function targetOf(goal: Goal | undefined, key: string): string {
  const arr = goal?.profile?.target_times_sec?.[key];
  const sec = Array.isArray(arr) ? arr[1] : null;
  return sec == null ? '' : formatClock(sec);
}
const mid = (t: Times, key: string): number | null => (Array.isArray(t[key]) && t[key][1] != null ? Number(t[key][1]) : null);

export default function GoalForm({ goal, onDone, onCancel }: Props) {
  const [name, setName] = useState(goal?.name ?? '');
  const [discipline, setDiscipline] = useState<Goal['discipline']>(goal?.discipline ?? 'triathlon');
  const [date, setDate] = useState(goal?.event_date ?? '');
  const [priority, setPriority] = useState<Goal['priority']>(goal?.priority ?? 'A');
  const [swimM, setSwimM] = useState(meters(segmentOf(goal, 'swim')));
  const [bikeKm, setBikeKm] = useState(km(segmentOf(goal, 'bike')));
  const [runKm, setRunKm] = useState(km(segmentOf(goal, 'run')));
  const [notes, setNotes] = useState(goal?.notes ?? '');
  const [times, setTimes] = useState<Record<string, string>>({
    swim: targetOf(goal, 'swim'), bike: targetOf(goal, 'bike'), run: targetOf(goal, 'run'), total: targetOf(goal, 'total'),
  });
  const [days, setDays] = useState(goal?.profile?.days == null ? '' : String(goal.profile.days));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dateOk = date === '' || ISO_DAY.test(date);
  const timeKeys = discipline === 'triathlon' ? TIME_KEYS : (['total'] as const);
  const timesOk = timeKeys.every((k) => times[k].trim() === '' || parseClock(times[k]) != null);
  const canSave = name.trim() !== '' && dateOk && timesOk && !busy;
  const setTime = (k: string) => (v: string) => setTimes((prev) => ({ ...prev, [k]: v }));

  const buildSegments = () => {
    const num = (v: string) => (v.trim() === '' ? null : Number(v));
    const segs: { sport: string; distance_m: number }[] = [];
    const push = (sport: string, m: number | null) => {
      if (m != null && Number.isFinite(m) && m > 0) segs.push({ sport, distance_m: Math.round(m) });
    };
    if (discipline === 'triathlon') {
      push('swim', num(swimM));
      push('bike', num(bikeKm) == null ? null : Number(bikeKm) * 1000);
      push('run', num(runKm) == null ? null : Number(runKm) * 1000);
    } else if (discipline === 'swim') {
      push('swim', num(swimM));
    } else {
      // run, bike, ultra: una sola distància en km
      const sport = discipline === 'ultra_endurance' ? 'bike' : discipline;
      push(sport, num(runKm) == null ? null : Number(runKm) * 1000);
    }
    return segs;
  };

  // Només es reescriu una clau si el text ha canviat respecte del preomplert:
  // un objectiu amb tres escenaris (Fornells) no en perd cap per obrir i desar.
  const buildTimes = (): Times | undefined => {
    const prev: Times = goal?.profile?.target_times_sec ?? {};
    const out: Times = { ...prev };
    let changed = false;
    for (const k of timeKeys) {
      const text = times[k].trim();
      if (text === targetOf(goal, k)) continue;
      changed = true;
      if (text === '') delete out[k];
      else out[k] = [null, parseClock(text), null];
    }
    if (!changed) return Object.keys(out).length ? out : undefined;
    if (discipline === 'triathlon') {
      const parts = ['swim', 't1', 'bike', 't2', 'run'].map((k) => mid(out, k));
      const sum = parts.reduce((acc: number, v) => acc + (v ?? 0), 0);
      if (parts.some((v) => v != null)) out.total = [null, sum, null];
      else delete out.total;
    }
    return Object.keys(out).length ? out : undefined;
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const profile: Record<string, any> = { ...(goal?.profile ?? {}), segments: buildSegments() };
      delete profile.target_times_sec;
      delete profile.days;
      const targetTimes = buildTimes();
      if (targetTimes) profile.target_times_sec = targetTimes;
      if (discipline === 'ultra_endurance' && days.trim() !== '' && Number.isFinite(Number(days)) && Number(days) > 0) {
        profile.days = Math.round(Number(days));
      }
      const input: GoalInput = {
        ...(goal ? { id: goal.id } : {}),
        name: name.trim(),
        discipline,
        event_date: date === '' ? null : date,
        priority,
        notes: notes.trim() || null,
        profile,
      };
      await upsertGoal(input);
      setBusy(false);
      onDone();
      return;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  const abandon = () => {
    if (!goal) return;
    Alert.alert('Abandonar objectiu?', `"${goal.name}" deixarà de comptar per al coach. No s'esborra res.`, [
      { text: 'Cancel·la', style: 'cancel' },
      {
        text: 'Abandona',
        style: 'destructive',
        onPress: async () => {
          try {
            await abandonGoal(goal.id);
            onDone();
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.form}>
      <ThemedText style={styles.title}>{goal ? 'Edita l’objectiu' : 'Nou objectiu'}</ThemedText>
      <Field label="Nom" value={name} onChange={setName} placeholder="Artiem Half Menorca" />
      <ThemedText style={styles.label}>Disciplina</ThemedText>
      <View style={styles.chips}>
        {DISCIPLINES.map(([d, label]) => (
          <Chip key={d} label={label} active={discipline === d} onPress={() => setDiscipline(d)} />
        ))}
      </View>
      <View style={styles.row}>
        <Field label="Data" value={date} onChange={setDate} placeholder="AAAA-MM-DD (o buit)" keyboard="numbers-and-punctuation" />
        <View style={styles.priority}>
          <ThemedText style={styles.label}>Prioritat</ThemedText>
          <View style={styles.chips}>
            {PRIORITIES.map((p) => (
              <Chip key={p} label={p} active={priority === p} onPress={() => setPriority(p)} />
            ))}
          </View>
        </View>
      </View>
      {!dateOk && <ThemedText style={styles.error}>Data en format AAAA-MM-DD, o deixa-la buida.</ThemedText>}
      {discipline === 'triathlon' ? (
        <View style={styles.row}>
          <Field label="Natació (m)" value={swimM} onChange={setSwimM} />
          <Field label="Bici (km)" value={bikeKm} onChange={setBikeKm} />
          <Field label="Cursa (km)" value={runKm} onChange={setRunKm} />
        </View>
      ) : discipline === 'swim' ? (
        <Field label="Distància (m)" value={swimM} onChange={setSwimM} />
      ) : (
        <Field label="Distància (km)" value={runKm} onChange={setRunKm} />
      )}
      {discipline === 'triathlon' ? (
        <View style={styles.row}>
          <Field label="Natació (h:mm:ss)" value={times.swim} onChange={setTime('swim')} keyboard="numbers-and-punctuation" />
          <Field label="Bici (h:mm:ss)" value={times.bike} onChange={setTime('bike')} keyboard="numbers-and-punctuation" />
          <Field label="Córrer (h:mm:ss)" value={times.run} onChange={setTime('run')} keyboard="numbers-and-punctuation" />
        </View>
      ) : discipline === 'ultra_endurance' ? (
        <Field label="Dies" value={days} onChange={setDays} keyboard="numeric" placeholder="en quants dies" />
      ) : (
        <Field label="Temps objectiu (h:mm:ss)" value={times.total} onChange={setTime('total')} keyboard="numbers-and-punctuation" placeholder="36:30" />
      )}
      {!timesOk && <ThemedText style={styles.error}>Temps en format h:mm:ss o mm:ss.</ThemedText>}
      <Field label="Notes" value={notes} onChange={setNotes} multiline placeholder="Per al coach: context, límits, què vols" />
      {error && <ThemedText style={styles.error}>{error}</ThemedText>}
      <View style={styles.row}>
        <TouchableOpacity style={styles.cancel} onPress={onCancel} disabled={busy}>
          <ThemedText style={styles.cancelText}>Cancel·la</ThemedText>
        </TouchableOpacity>
        {goal && (
          <TouchableOpacity style={styles.cancel} onPress={abandon} disabled={busy}>
            <ThemedText style={styles.abandonText}>Abandona</ThemedText>
          </TouchableOpacity>
        )}
        <TouchableOpacity style={[styles.button, !canSave && { opacity: 0.4 }]} onPress={save} disabled={!canSave}>
          {busy ? <ActivityIndicator color="#fff" /> : <ThemedText style={styles.buttonText}>Desa</ThemedText>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

function Field({
  label, value, onChange, placeholder, keyboard = 'default', multiline = false,
}: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
  keyboard?: 'default' | 'numeric' | 'numbers-and-punctuation'; multiline?: boolean;
}) {
  const numeric = /\((m|km)\)$/.test(label);
  return (
    <View style={styles.field}>
      <ThemedText style={styles.label}>{label}</ThemedText>
      <TextInput
        style={[styles.input, multiline && styles.multiline]}
        accessibilityLabel={label}
        keyboardType={numeric ? 'numeric' : keyboard}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor="#8a8a8a"
        multiline={multiline}
      />
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
  form: { gap: 10 },
  title: { fontSize: 18, fontWeight: '800' },
  row: { flexDirection: 'row', gap: 10, alignItems: 'flex-end' },
  priority: { gap: 4 },
  field: { flex: 1, gap: 4 },
  label: { fontSize: 12, opacity: 0.7 },
  input: { borderWidth: 1, borderColor: 'rgba(127,127,127,0.4)', borderRadius: 8, padding: 8, fontSize: 15, color: '#888' },
  multiline: { minHeight: 64, textAlignVertical: 'top' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 16, backgroundColor: 'rgba(127,127,127,0.12)' },
  chipActive: { backgroundColor: '#3b82c4' },
  chipText: { fontSize: 13 },
  chipTextActive: { color: '#fff', fontWeight: '700' },
  error: { color: '#d64541' },
  button: { flex: 1, backgroundColor: '#1D3D47', borderRadius: 8, padding: 10, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '700' },
  cancel: { padding: 10, alignItems: 'center' },
  cancelText: { opacity: 0.6 },
  abandonText: { color: '#d64541' },
});
