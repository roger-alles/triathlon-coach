import { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, TextInput, TouchableOpacity, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { getWeekRequest, requestWeekRedesign, WeekRequest } from '@/lib/api';

// Mentre el coach hi treballa (cron cada 5 min + 1-2 min de model), la targeta
// es refresca sola; quan respon, la setmana es torna a carregar.
const POLL_MS = 20000;

const inFlight = (r: WeekRequest | null) => r?.status === 'pending' || r?.status === 'processing';

// "Demana canvis" de la pestanya Setmana: l'atleta escriu què vol i el coach
// redissenya d'avui a diumenge. No hi ha proposta a aprovar: s'aplica sola.
export default function WeekRequestBox({
  weekStart,
  onApplied,
}: {
  weekStart: string;
  onApplied: () => void;
}) {
  const [request, setRequest] = useState<WeekRequest | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wasInFlight = useRef(false);

  const load = useCallback(async () => {
    try {
      const r = await getWeekRequest(weekStart);
      setRequest(r);
      if (wasInFlight.current && r?.status === 'answered') onApplied();
      wasInFlight.current = inFlight(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [weekStart, onApplied]);

  useEffect(() => {
    wasInFlight.current = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const waiting = inFlight(request);
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [waiting, load]);

  const send = async () => {
    const text = draft.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      await requestWeekRedesign(weekStart, text);
      setDraft('');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  return (
    <View style={styles.card}>
      <ThemedText style={styles.title}>Demana canvis a la setmana</ThemedText>

      {request && (
        <View style={styles.last}>
          <ThemedText style={styles.asked}>Has demanat: «{request.text}»</ThemedText>
          {request.status === 'pending' && (
            <ThemedText style={styles.pending}>Enviada · el coach s&apos;hi posarà en uns minuts</ThemedText>
          )}
          {request.status === 'processing' && (
            <ThemedText style={styles.pending}>El coach està redissenyant la setmana…</ThemedText>
          )}
          {request.status === 'answered' && (
            <>
              <ThemedText style={styles.done}>Fet{request.summary ? `: ${request.summary}` : ''}</ThemedText>
              {request.rationale && <ThemedText style={styles.rationale}>{request.rationale}</ThemedText>}
            </>
          )}
          {request.status === 'failed' && (
            <ThemedText style={styles.error}>No s&apos;ha pogut: {request.error ?? 'error desconegut'}</ThemedText>
          )}
        </View>
      )}

      <View style={styles.row}>
        <TextInput
          style={styles.input}
          placeholder="Què vols canviar? (p. ex. dijous no puc)"
          placeholderTextColor="#8a8a8a"
          value={draft}
          onChangeText={setDraft}
          editable={!waiting}
          multiline
          maxLength={1000}
        />
        <TouchableOpacity
          style={[styles.button, (waiting || busy || !draft.trim()) && { opacity: 0.4 }]}
          accessibilityRole="button"
          disabled={waiting || busy || !draft.trim()}
          onPress={send}>
          <ThemedText style={styles.buttonText}>{busy ? '…' : 'Demana'}</ThemedText>
        </TouchableOpacity>
      </View>
      {error && <ThemedText style={styles.error}>{error}</ThemedText>}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: 12, padding: 12, gap: 8, backgroundColor: 'rgba(127,127,127,0.08)' },
  title: { fontSize: 15, fontWeight: '700' },
  last: { gap: 4 },
  asked: { fontSize: 13, opacity: 0.8, fontStyle: 'italic' },
  pending: { fontSize: 13, fontWeight: '600', color: '#e6a817' },
  done: { fontSize: 14, fontWeight: '600', color: '#2e9e5b' },
  rationale: { fontSize: 13, opacity: 0.75 },
  row: { flexDirection: 'row', gap: 8, alignItems: 'flex-end' },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: 'rgba(127,127,127,0.4)',
    borderRadius: 10,
    padding: 10,
    fontSize: 14,
    color: '#888',
    minHeight: 40,
  },
  button: { backgroundColor: '#1D3D47', borderRadius: 10, paddingVertical: 10, paddingHorizontal: 16 },
  buttonText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  error: { color: '#d64541', fontSize: 13 },
});
