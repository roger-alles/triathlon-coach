import { useCallback, useEffect, useState } from 'react';
import {ActivityIndicator, Alert, StyleSheet, Switch, TextInput, TouchableOpacity, View} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import FormScrollView from '@/components/form-scroll-view';
import { ThemedText } from '@/components/themed-text';
import { Athlete, AthleteProfile, getAthlete, getSetting, setSetting, updateAthleteProfile } from '@/lib/api';
import { supabase } from '@/lib/supabase';

// "Jo": el que el coach ha de saber de mi i no ve de Garmin. S'edita
// athlete.profile.constraints i .notes; la resta del perfil (salut, marques
// conegudes...) es conserva tal qual. També hi viu l'interruptor del coach.

const DAYS: [string, string][] = [
  ['monday', 'Dl'], ['tuesday', 'Dt'], ['wednesday', 'Dc'], ['thursday', 'Dj'],
  ['friday', 'Dv'], ['saturday', 'Ds'], ['sunday', 'Dg'],
];
const ALL_DAYS = DAYS.map(([d]) => d);

export default function Jo() {
  const [athlete, setAthlete] = useState<Athlete | null>(null);
  const [restDay, setRestDay] = useState<string | null>(null);
  const [hours, setHours] = useState('');
  const [available, setAvailable] = useState<string[]>(ALL_DAYS);
  const [pool, setPool] = useState('');
  const [gym, setGym] = useState(false);
  const [notes, setNotes] = useState('');
  const [applyMode, setApplyMode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const insets = useSafeAreaInsets();

  const load = useCallback(async () => {
    try {
      const a = await getAthlete();
      setAthlete(a);
      const c = a?.profile?.constraints ?? {};
      setRestDay(c.fixed_rest_day ?? null);
      setHours(c.weekly_hours_ceiling == null ? '' : String(c.weekly_hours_ceiling));
      setAvailable(c.available_days && c.available_days.length > 0 ? c.available_days : ALL_DAYS);
      setPool(c.pool_availability ?? '');
      setGym(!!c.gym);
      setNotes(a?.profile?.notes ?? '');
      setApplyMode((await getSetting('coach_apply_mode')) ?? 'dry_run');
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    // load() només fa setState després d'un await (no és síncron).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const hoursNum = hours.trim() === '' ? null : Number(hours);
  const hoursOk = hoursNum == null || (Number.isFinite(hoursNum) && hoursNum > 0);

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const prev: AthleteProfile = athlete?.profile ?? {};
      const profile: AthleteProfile = {
        ...prev,
        constraints: {
          ...(prev.constraints ?? {}),
          fixed_rest_day: restDay,
          weekly_hours_ceiling: hoursNum,
          available_days: available.length === ALL_DAYS.length ? [] : ALL_DAYS.filter((d) => available.includes(d)),
          pool_availability: pool.trim() || null,
          gym,
        },
        notes: notes.trim() || null,
      };
      await updateAthleteProfile(profile);
      setAthlete((a) => (a ? { ...a, profile } : a));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  const toggleAvailable = (d: string) =>
    setAvailable((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));

  const toggleApplyMode = (on: boolean) => {
    const write = async (mode: 'dry_run' | 'hybrid') => {
      const before = applyMode;
      setApplyMode(mode);
      try {
        await setSetting('coach_apply_mode', mode);
      } catch (e) {
        setApplyMode(before);
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    if (!on) return write('dry_run');
    Alert.alert(
      'Activar el mode híbrid?',
      'El coach aplicarà sol els canvis petits (com a molt 2 sessions, 3 dies, mai una clau, mai més càrrega) i et demanarà permís per a la resta. Tot es pot desfer des d’Avui el mateix dia.',
      [
        { text: 'Cancel·la', style: 'cancel' },
        { text: 'Activa', style: 'default', onPress: () => write('hybrid') },
      ]
    );
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <FormScrollView style={styles.container} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8 }]}>
      <ThemedText style={styles.title}>{athlete?.name ?? 'Jo'}</ThemedText>
      {athlete?.max_hr != null && <ThemedText style={styles.meta}>FC màx {athlete.max_hr}</ThemedText>}
      {error && <ThemedText style={styles.error}>{error}</ThemedText>}

      <ThemedText style={styles.sectionTitle}>Disponibilitat</ThemedText>
      <View style={styles.card}>
        <ThemedText style={styles.label}>Dia de descans fix</ThemedText>
        <View style={styles.chips}>
          {DAYS.map(([d, label]) => (
            <Chip key={d} label={label} a11y={`Descans ${label}`} active={restDay === d} onPress={() => setRestDay(d)} />
          ))}
          <Chip label="Cap" a11y="Descans Cap" active={restDay == null} onPress={() => setRestDay(null)} />
        </View>
        <Field label="Hores màximes per setmana" value={hours} onChange={setHours} numeric placeholder="8" />
        {!hoursOk && <ThemedText style={styles.error}>Un nombre d’hores, o buit.</ThemedText>}
        <ThemedText style={styles.label}>Dies disponibles</ThemedText>
        <View style={styles.chips}>
          {DAYS.map(([d, label]) => (
            <Chip key={d} label={label} a11y={`Disponible ${label}`} active={available.includes(d)} onPress={() => toggleAvailable(d)} />
          ))}
        </View>
        <Field label="Piscina" value={pool} onChange={setPool} placeholder="quan i on pots nedar" />
        <View style={styles.switchRow}>
          <ThemedText style={styles.switchLabel}>Gimnàs</ThemedText>
          <Switch accessibilityLabel="gimnàs" value={gym} onValueChange={setGym} />
        </View>
      </View>

      <ThemedText style={styles.sectionTitle}>Notes per al coach</ThemedText>
      <View style={styles.card}>
        <Field label="Notes per al coach" hideLabel value={notes} onChange={setNotes} multiline placeholder="Salut, vacances, el que el coach ha de saber" />
        <View style={styles.row}>
          {saved && <ThemedText style={styles.saved}>Desat</ThemedText>}
          <TouchableOpacity style={[styles.button, (!hoursOk || busy) && { opacity: 0.4 }]} onPress={save} disabled={!hoursOk || busy}>
            {busy ? <ActivityIndicator color="#fff" /> : <ThemedText style={styles.buttonText}>Desa</ThemedText>}
          </TouchableOpacity>
        </View>
      </View>

      <ThemedText style={styles.sectionTitle}>Coach</ThemedText>
      <View style={styles.card}>
        <View style={styles.switchRow}>
          <ThemedText style={styles.switchLabel}>El coach aplica els canvis (mode híbrid)</ThemedText>
          <Switch accessibilityLabel="mode híbrid" value={applyMode === 'hybrid'} onValueChange={toggleApplyMode} />
        </View>
        <ThemedText style={styles.switchHelp}>
          {applyMode === 'hybrid'
            ? 'Mode híbrid: els canvis petits s’apliquen sols; els grans esperen el teu Aplica a Avui.'
            : 'Mode prova: el coach proposa i ho veus a Avui, però no toca el pla.'}
        </ThemedText>
      </View>

      <TouchableOpacity onPress={() => supabase.auth.signOut()}>
        <ThemedText style={styles.logout}>Surt</ThemedText>
      </TouchableOpacity>
    </FormScrollView>
  );
}

function Field({
  label, value, onChange, placeholder, numeric = false, multiline = false, hideLabel = false,
}: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
  numeric?: boolean; multiline?: boolean; hideLabel?: boolean;
}) {
  return (
    <View style={styles.field}>
      {!hideLabel && <ThemedText style={styles.label}>{label}</ThemedText>}
      <TextInput
        style={[styles.input, multiline && styles.multiline]}
        accessibilityLabel={label}
        keyboardType={numeric ? 'numeric' : 'default'}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor="#8a8a8a"
        multiline={multiline}
      />
    </View>
  );
}

function Chip({ label, a11y, active, onPress }: { label: string; a11y: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity
      style={[styles.chip, active && styles.chipActive]}
      onPress={onPress}
      accessibilityLabel={a11y}
      accessibilityState={{ selected: active }}>
      <ThemedText style={[styles.chipText, active && styles.chipTextActive]}>{label}</ThemedText>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, gap: 12, paddingBottom: 48 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  title: { fontSize: 22, fontWeight: '800' },
  meta: { fontSize: 13, opacity: 0.7 },
  card: { backgroundColor: 'rgba(127,127,127,0.1)', borderRadius: 12, padding: 14, gap: 8 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 4 },
  row: { flexDirection: 'row', gap: 10, alignItems: 'center', justifyContent: 'flex-end' },
  field: { gap: 4 },
  label: { fontSize: 12, opacity: 0.7 },
  input: { borderWidth: 1, borderColor: 'rgba(127,127,127,0.4)', borderRadius: 8, padding: 8, fontSize: 15, color: '#888' },
  multiline: { minHeight: 64, textAlignVertical: 'top' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 16, backgroundColor: 'rgba(127,127,127,0.12)' },
  chipActive: { backgroundColor: '#3b82c4' },
  chipText: { fontSize: 13 },
  chipTextActive: { color: '#fff', fontWeight: '700' },
  error: { color: '#d64541' },
  saved: { color: '#2e9e5b', fontWeight: '600' },
  button: { backgroundColor: '#1D3D47', borderRadius: 8, paddingVertical: 10, paddingHorizontal: 24, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '700' },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  switchLabel: { flex: 1, fontSize: 14, fontWeight: '600' },
  switchHelp: { fontSize: 12, opacity: 0.7 },
  logout: { textAlign: 'center', opacity: 0.5, marginTop: 16 },
});
