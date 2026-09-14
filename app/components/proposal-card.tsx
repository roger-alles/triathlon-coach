import { useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, TouchableOpacity, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { BlockChange, Decision, Proposal, SessionChange, SessionRef, parseLocalISO } from '@/lib/api';
import { formatDuration, sportEmoji } from '@/lib/format';

// Una proposta del coach (un informe amb canvis al pla) i què en fa l'atleta.
// L'estat mana: 'proposed' → Aplica / Descarta; 'auto_applied' i 'applied' →
// Desfés; la resta, res. Una decisió pendent amaga els botons fins que el cron
// (cada 5 min) la resol; una de fallida ensenya l'error i els torna.

const WEEKDAY_SHORT = ['Dg', 'Dl', 'Dt', 'Dc', 'Dj', 'Dv', 'Ds'];
function shortDay(iso: string): string {
  const d = parseLocalISO(iso);
  return `${WEEKDAY_SHORT[d.getDay()]} ${d.getDate()}`;
}

const REPORT_LABEL: Record<string, string> = { daily: 'diari', weekly: 'setmanal', replan: 'petició', macro: 'macro' };
const DECIDING: Record<Decision['decision'], string> = { apply: 'Aplicant…', discard: 'Descartant…', undo: 'Desfent…' };

type BlockRef = { id: number; name: string | null; phase: string };

type Props = {
  proposal: Proposal;
  sessions: Map<number, SessionRef>;
  blocks?: Map<number, BlockRef>;
  decision?: Decision;
  applyMode: string;
  onDecide: (kind: Decision['decision']) => Promise<void>;
};

function ddmm(iso: string): string {
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
}

export default function ProposalCard({ proposal, sessions, blocks, decision, applyMode, onDecide }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inFlight = decision && (decision.status === 'pending' || decision.status === 'processing');
  const status = proposal.status;

  const decide = (kind: Decision['decision']) => {
    const go = async () => {
      setBusy(true);
      setError(null);
      try {
        await onDecide(kind);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
      setBusy(false);
    };
    if (kind === 'discard') return go();
    Alert.alert(
      kind === 'apply' ? 'Canviar el pla?' : 'Tornar enrere?',
      kind === 'apply'
        ? 'Les sessions afectades es substituiran per les que proposa el coach.'
        : "El pla tornarà a com estava abans d'aquest informe.",
      [
        { text: 'Cancel·la', style: 'cancel' },
        { text: kind === 'apply' ? 'Aplica' : 'Desfés', style: 'destructive', onPress: go },
      ]
    );
  };

  const statusLine =
    status === 'none' && applyMode === 'dry_run' ? "Mode prova · no s'aplica"
    : status === 'auto_applied' ? 'Aplicada automàticament'
    : status === 'applied' ? 'Aplicada'
    : status === 'proposed' ? 'Pendent de tu'
    : status === 'discarded' ? 'Descartada'
    : status === 'undone' ? 'Desfeta'
    : status === 'failed' ? "No s'ha pogut aplicar"
    : null;

  const created = new Date(proposal.createdAt);
  const when = `${String(created.getDate()).padStart(2, '0')}/${String(created.getMonth() + 1).padStart(2, '0')}`;

  return (
    <View style={styles.card}>
      <ThemedText style={styles.title}>
        Proposta del coach · {REPORT_LABEL[proposal.reportType] ?? proposal.reportType} · {when}
      </ThemedText>
      {statusLine && <ThemedText style={[styles.status, status === 'proposed' && styles.statusPending]}>{statusLine}</ThemedText>}

      {(proposal.blockChanges ?? []).map((b, i) => (
        <BlockRow key={`b${i}`} change={b} block={b.block_id != null ? blocks?.get(b.block_id) : undefined} />
      ))}
      {proposal.changes.map((c, i) => (
        <ChangeRow key={i} change={c} session={sessions.get(c.plan_session_id)} />
      ))}

      {proposal.classification && !proposal.classification.auto && proposal.classification.reasons.length > 0 &&
        (status === 'proposed' || status === 'none') && (
          <ThemedText style={styles.why}>{"Per què no s'aplica sola: "}{proposal.classification.reasons.join(' · ')}</ThemedText>
        )}

      {inFlight ? (
        <ThemedText style={styles.inFlight}>{DECIDING[decision!.decision]} (menys de 5 min)</ThemedText>
      ) : (
        <>
          {decision?.status === 'failed' && <ThemedText style={styles.error}>{decision.error ?? 'Ha fallat'}</ThemedText>}
          {error && <ThemedText style={styles.error}>{error}</ThemedText>}
          {busy ? (
            <ActivityIndicator />
          ) : status === 'proposed' ? (
            <View style={styles.row}>
              <TouchableOpacity style={styles.secondary} onPress={() => decide('discard')}>
                <ThemedText style={styles.secondaryText}>Descarta</ThemedText>
              </TouchableOpacity>
              <TouchableOpacity style={styles.primary} onPress={() => decide('apply')}>
                <ThemedText style={styles.primaryText}>Aplica</ThemedText>
              </TouchableOpacity>
            </View>
          ) : status === 'auto_applied' || status === 'applied' ? (
            <View style={styles.row}>
              <TouchableOpacity style={styles.secondary} onPress={() => decide('undo')}>
                <ThemedText style={styles.secondaryText}>Desfés</ThemedText>
              </TouchableOpacity>
            </View>
          ) : null}
        </>
      )}
    </View>
  );
}

function BlockRow({ change, block }: { change: BlockChange; block?: BlockRef }) {
  const nb = change.new_block ?? {};
  const name = block?.name ?? (change.block_id != null ? `Bloc #${change.block_id}` : nb.name ?? 'Bloc');
  const dates = nb.start_date && nb.end_date ? ` · ${ddmm(nb.start_date)} – ${ddmm(nb.end_date)}` : '';
  const hours = nb.target_weekly_hours != null ? ` · ${nb.target_weekly_hours} h/set` : '';
  const head =
    change.action === 'add' ? `+ ${nb.name ?? 'Bloc'}${dates}${hours}`
    : change.action === 'cancel' ? `× ${name}`
    : `~ ${name}${dates}${hours}`;
  return (
    <View style={styles.change}>
      <ThemedText style={styles.head}>{head}</ThemedText>
      {nb.intent ? <ThemedText style={styles.what}>{nb.intent}</ThemedText> : null}
      {change.reason ? <ThemedText style={styles.reason}>{change.reason}</ThemedText> : null}
    </View>
  );
}

function ChangeRow({ change, session }: { change: SessionChange; session?: SessionRef }) {
  const head = session
    ? `${sportEmoji(session.sport)} ${shortDay(session.local_date)} · ${session.title}`
    : `Sessió #${change.plan_session_id}`;
  const what =
    change.action === 'move' && change.new_date ? `→ ${shortDay(change.new_date)}`
    : change.action === 'cancel' ? 'cancel·lada'
    : change.new_session
      ? `→ ${change.new_session.title}${change.new_session.duration_sec_target != null ? ` · ${formatDuration(change.new_session.duration_sec_target)}` : ''}`
      : change.action;
  return (
    <View style={styles.change}>
      <ThemedText style={styles.head}>{head}</ThemedText>
      <ThemedText style={styles.what}>{what}</ThemedText>
      {change.reason ? <ThemedText style={styles.reason}>{change.reason}</ThemedText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: 'rgba(59,130,196,0.12)', borderRadius: 12, padding: 14, gap: 8 },
  title: { fontSize: 13, fontWeight: '700', opacity: 0.8 },
  status: { fontSize: 13, fontWeight: '600', opacity: 0.8 },
  statusPending: { color: '#e6a817', opacity: 1 },
  change: { gap: 1 },
  head: { fontSize: 14, fontWeight: '600' },
  what: { fontSize: 14, marginLeft: 12 },
  reason: { fontSize: 13, opacity: 0.7, fontStyle: 'italic', marginLeft: 12 },
  why: { fontSize: 12, opacity: 0.7 },
  inFlight: { fontSize: 13, fontStyle: 'italic', opacity: 0.8 },
  error: { color: '#d64541', fontSize: 13 },
  row: { flexDirection: 'row', gap: 10, justifyContent: 'flex-end' },
  primary: { backgroundColor: '#1D3D47', borderRadius: 8, paddingVertical: 8, paddingHorizontal: 16 },
  primaryText: { color: '#fff', fontWeight: '700' },
  secondary: { borderRadius: 8, paddingVertical: 8, paddingHorizontal: 12 },
  secondaryText: { opacity: 0.7, fontWeight: '600' },
});
