import { useState } from 'react';
import { ActivityIndicator, StyleSheet, TextInput, TouchableOpacity, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { PlanSession, localDateISO, logManualActivity } from '@/lib/api';
import { distance, formatDuration, sportLabel } from '@/lib/format';

// "Ho he fet": registrar una sessió feta sense rellotge, des d'Avui o des de
// Setmana (dies passats, sessions perdudes). Els valors del pla venen
// preomplerts; el dia es pot canviar (la sessió del dimecres feta el dijous);
// el sync horari farà la resta (càrrega estimada, estat de la sessió).
//
// Un 'multisport' es registra per trams (natació / bici / cursa, dels
// segments del pla); un 'brick' com la cursa del brick (la bici del dia ja
// arriba de Garmin). Cada tram és una activitat lligada a la mateixa sessió.

const LOGGABLE = new Set(['swim', 'bike', 'run']);
const OPEN_STATUSES = new Set(['planned', 'partial', 'missed']);
const SWIM_VENUES: [string, string][] = [
  ['open_water', 'Mar'],
  ['lap_swimming', 'Piscina'],
];

type Leg = {
  sport: string;
  label: string; // '' per a una sessió simple; 'natació 800 m' per a un tram
  duration_sec_target: number | null;
  distance_m_target: number | null;
  venue: string | null;
};

export function legsFor(session: PlanSession): Leg[] {
  if (session.sport === 'multisport') {
    return (session.structure?.segments ?? [])
      .filter((seg) => LOGGABLE.has(seg.sport))
      .map((seg) => {
        const size =
          seg.distance_m != null ? ` ${distance(seg.distance_m)}`
          : seg.duration_sec != null ? ` ${formatDuration(seg.duration_sec)}`
          : '';
        return {
          sport: seg.sport,
          label: `${sportLabel(seg.sport).toLowerCase()}${size}`,
          duration_sec_target: seg.duration_sec ?? null,
          distance_m_target: seg.distance_m ?? null,
          venue: seg.venue ?? null,
        };
      });
  }
  if (session.sport === 'brick') {
    return [{ sport: 'run', label: 'cursa del brick', duration_sec_target: session.duration_sec_target,
              distance_m_target: null, venue: null }];
  }
  if (LOGGABLE.has(session.sport)) {
    return [{ sport: session.sport, label: '', duration_sec_target: session.duration_sec_target,
              distance_m_target: session.distance_m_target, venue: null }];
  }
  return [];
}

type Props = {
  session: PlanSession;
  dateISO: string;
  logged?: Set<string>; // esports d'aquesta sessió que ja tenen activitat
  onSaved?: () => void;
};

export default function LogSession({ session, dateISO, logged, onSaved }: Props) {
  const [done, setDone] = useState<Set<string>>(new Set());
  const [openSport, setOpenSport] = useState<string | null>(null);

  if (!OPEN_STATUSES.has(session.status)) return null;
  const legs = legsFor(session).filter((l) => !logged?.has(l.sport));
  if (legs.length === 0) return null;
  const multi = legs.length > 1 || legs[0].label !== '';

  return (
    <View style={styles.legs}>
      {legs.map((leg) =>
        done.has(leg.sport) ? (
          <ThemedText key={leg.sport} style={styles.done}>
            Registrada{multi ? ` ${sportLabel(leg.sport).toLowerCase()}` : ''}. El coach ho veurà a la
            propera sincronització (menys d&apos;una hora).
          </ThemedText>
        ) : openSport === leg.sport ? (
          <LegForm
            key={leg.sport}
            leg={leg}
            sessionId={session.id}
            dateISO={dateISO}
            onCancel={() => setOpenSport(null)}
            onSaved={() => {
              setDone((prev) => new Set(prev).add(leg.sport));
              setOpenSport(null);
              onSaved?.();
            }}
          />
        ) : (
          <TouchableOpacity key={leg.sport} style={styles.openButton} onPress={() => setOpenSport(leg.sport)}>
            <ThemedText style={styles.openText}>Ho he fet{leg.label && ` · ${leg.label}`}</ThemedText>
          </TouchableOpacity>
        )
      )}
    </View>
  );
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function LegForm({
  leg, sessionId, dateISO, onCancel, onSaved,
}: { leg: Leg; sessionId: number; dateISO: string; onCancel: () => void; onSaved: () => void }) {
  const [day, setDay] = useState(dateISO);
  const [minutes, setMinutes] = useState(
    leg.duration_sec_target != null ? String(Math.round(leg.duration_sec_target / 60)) : ''
  );
  const [meters, setMeters] = useState(
    leg.distance_m_target != null ? String(Math.round(leg.distance_m_target)) : ''
  );
  const [venue, setVenue] = useState<string | null>(leg.venue);
  const [rpe, setRpe] = useState<number | null>(null);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const durationSec = Math.round(Number(minutes) * 60);
  const dayOk = ISO_DAY.test(day) && day <= localDateISO();
  const canSave = Number.isFinite(durationSec) && durationSec > 0 && dayOk && !busy;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const dist = meters.trim() ? Math.round(Number(meters)) : null;
      await logManualActivity({
        local_date: day,
        sport: leg.sport,
        ...(leg.sport === 'swim' && venue ? { sub_sport: venue } : {}),
        duration_sec: durationSec,
        distance_m: Number.isFinite(dist as number) ? dist : null,
        perceived_effort: rpe,
        athlete_notes: notes.trim() || null,
        plan_session_id: sessionId,
      });
      onSaved();
      return;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  return (
    <View style={styles.form}>
      {leg.label !== '' && <ThemedText style={styles.legTitle}>{leg.label}</ThemedText>}
      <View style={styles.row}>
        <Field label="Dia" value={day} onChange={setDay} keyboard="numbers-and-punctuation" />
        <View style={styles.todayWrap}>
          <Chip label="Avui" active={day === localDateISO()} onPress={() => setDay(localDateISO())} />
        </View>
      </View>
      {!dayOk && <ThemedText style={styles.error}>Dia en format AAAA-MM-DD, no posterior a avui.</ThemedText>}
      <View style={styles.row}>
        <Field label="Minuts" value={minutes} onChange={setMinutes} />
        <Field label="Metres" value={meters} onChange={setMeters} />
      </View>
      {leg.sport === 'swim' && (
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
        <TouchableOpacity style={styles.cancel} onPress={onCancel} disabled={busy}>
          <ThemedText style={styles.cancelText}>Cancel·la</ThemedText>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.button, !canSave && { opacity: 0.4 }]} onPress={save} disabled={!canSave}>
          {busy ? <ActivityIndicator color="#fff" /> : <ThemedText style={styles.buttonText}>Registra</ThemedText>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

function Field({
  label, value, onChange, keyboard = 'numeric',
}: { label: string; value: string; onChange: (v: string) => void; keyboard?: 'numeric' | 'numbers-and-punctuation' }) {
  return (
    <View style={styles.field}>
      <ThemedText style={styles.label}>{label}</ThemedText>
      <TextInput style={styles.input} accessibilityLabel={label} keyboardType={keyboard} value={value} onChangeText={onChange} />
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
  legs: { gap: 6, marginTop: 6 },
  openButton: { alignSelf: 'flex-start', paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, backgroundColor: 'rgba(127,127,127,0.15)' },
  openText: { fontSize: 13, fontWeight: '600' },
  done: { color: '#2e9e5b', fontSize: 13 },
  form: { gap: 8, marginTop: 2 },
  legTitle: { fontSize: 13, fontWeight: '700' },
  row: { flexDirection: 'row', gap: 10, alignItems: 'flex-end' },
  todayWrap: { paddingBottom: 6 },
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
