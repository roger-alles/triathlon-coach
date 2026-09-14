import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import LogSession from '@/components/log-session';
import ProposalCard from '@/components/proposal-card';
import { ThemedText } from '@/components/themed-text';

import {
  AthleteAnswer,
  DailyReport,
  Decision,
  PlanSession,
  Proposal,
  SessionRef,
  getAnswers,
  getBlocks,
  getDecisions,
  getLatestDailyReport,
  getOpenProposals,
  getSessionsByIds,
  getSessionsForDay,
  getSetting,
  localDateISO,
  sendAnswer,
  sendDecision,
} from '@/lib/api';
import { formatDateCa, formatDuration, formatSegment, formatStep, sportEmoji, sportLabel, verdictColor } from '@/lib/format';

const VERDICT_LABEL: Record<string, string> = { green: 'VERD', amber: 'ÀMBAR', red: 'VERMELL' };

function previewLabel(report: DailyReport): string {
  const [y, m, d] = report.windowStart.split('-').map(Number);
  const day = formatDateCa(new Date(y, m - 1, d));
  return report.kind === 'preview_tomorrow'
    ? `Preview per a demà, ${day.toLowerCase()} · el semàfor definitiu arriba al matí`
    : `Preview d'ahir al vespre per a avui · l'informe del matí arriba amb el son`;
}

export default function Avui() {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [sessions, setSessions] = useState<PlanSession[]>([]);
  const [answers, setAnswers] = useState<AthleteAnswer[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [refs, setRefs] = useState<Map<number, SessionRef>>(new Map());
  const [blockRefs, setBlockRefs] = useState<Map<number, { id: number; name: string | null; phase: string }>>(new Map());
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [applyMode, setApplyMode] = useState('dry_run');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const insets = useSafeAreaInsets();

  const load = useCallback(async () => {
    setError(null);
    try {
      const today = localDateISO();
      const [r, s, open, mode] = await Promise.all([
        getLatestDailyReport(today), getSessionsForDay(today), getOpenProposals(today), getSetting('coach_apply_mode'),
      ]);
      setReport(r);
      setSessions(s);
      setApplyMode(mode ?? 'dry_run');
      // la proposta de l'informe d'avui primer; després les obertes d'altres informes
      const all = [...(r?.proposal ? [r.proposal] : []), ...open.filter((p) => p.id !== r?.proposal?.id)];
      setProposals(all);
      const ids = all.flatMap((p) => p.changes.map((c) => c.plan_session_id));
      const needsBlocks = all.some((p) => (p.blockChanges ?? []).length > 0);
      const [answersNow, refsNow, decisionsNow, blocksNow] = await Promise.all([
        r ? getAnswers(r.id) : Promise.resolve([]),
        getSessionsByIds(ids),
        getDecisions(all.map((p) => p.id)),
        needsBlocks ? getBlocks() : Promise.resolve([]),
      ]);
      setAnswers(answersNow);
      setRefs(refsNow);
      setDecisions(decisionsNow);
      setBlockRefs(new Map(blocksNow.map((b) => [b.id, { id: b.id, name: b.name, phase: b.phase }])));
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
          {report.kind !== 'today' && (
            <Text style={styles.bannerPreview}>{previewLabel(report)}</Text>
          )}
          <Text style={styles.bannerVerdict}>{VERDICT_LABEL[report.verdict] ?? report.verdict}</Text>
          <Text style={styles.bannerSummary}>{report.summary}</Text>
        </View>
      ) : (
        !error && <ThemedText style={styles.muted}>Encara no hi ha informe del coach.</ThemedText>
      )}

      {proposals.map((p) => (
        <ProposalCard
          key={p.id}
          proposal={p}
          sessions={refs}
          blocks={blockRefs}
          decision={decisions.find((d) => d.report_id === p.id)}
          applyMode={applyMode}
          onDecide={async (kind) => {
            await sendDecision(p.id, kind);
            await load();
          }}
        />
      ))}

      {sessions.map((s, i) => (
        <View key={s.id} style={styles.card}>
          <ThemedText style={styles.cardTitle}>
            {sessions.length > 1 ? `Sessió d'avui (${i + 1} de ${sessions.length})` : "Sessió d'avui"}
          </ThemedText>
          <ThemedText style={styles.cardMeta}>
            {sportEmoji(s.sport)} {sportLabel(s.sport)}
            {s.duration_sec_target != null && ` · ${formatDuration(s.duration_sec_target)}`}
            {` · ${s.title}`}
            {s.is_test && ' · TEST'}
          </ThemedText>
          {(s.structure?.steps ?? []).map((step, i) => (
            <ThemedText key={`s${i}`} style={styles.step}>
              {formatStep(step)}
            </ThemedText>
          ))}
          {(s.structure?.segments ?? []).map((seg, i) => (
            <ThemedText key={`g${i}`} style={styles.step}>
              {formatSegment(seg)}
            </ThemedText>
          ))}
          <LogSession session={s} dateISO={localDateISO()} />
        </View>
      ))}

      {report && (
        <>
          <ThemedText style={styles.rationale}>{report.rationale}</ThemedText>
          {report.questions.length > 0 && (
            <View style={styles.card}>
              <ThemedText style={styles.cardTitle}>El coach et pregunta</ThemedText>
              {report.questions.map((q, i) => (
                <QuestionRow
                  key={i}
                  question={q}
                  existing={answers.find((a) => a.question === q)?.answer}
                  onSend={async (text) => {
                    await sendAnswer(report.id, q, text);
                    setAnswers((prev) => [...prev, { id: -prev.length - 1, question: q, answer: text }]);
                  }}
                />
              ))}
            </View>
          )}
        </>
      )}

    </ScrollView>
  );
}

function QuestionRow({
  question,
  existing,
  onSend,
}: {
  question: string;
  existing?: string;
  onSend: (text: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  return (
    <View style={styles.questionRow}>
      <ThemedText style={styles.step}>· {question}</ThemedText>
      {existing ? (
        <ThemedText style={styles.answerDone}>Tu: {existing}</ThemedText>
      ) : (
        <View style={styles.answerRow}>
          <TextInput
            style={styles.answerInput}
            placeholder="Respon al coach…"
            placeholderTextColor="#8a8a8a"
            value={draft}
            onChangeText={setDraft}
            multiline
          />
          <TouchableOpacity
            style={[styles.answerButton, !draft.trim() && { opacity: 0.4 }]}
            disabled={busy || !draft.trim()}
            onPress={async () => {
              setBusy(true);
              setRowError(null);
              try {
                await onSend(draft.trim());
              } catch (e) {
                setRowError(e instanceof Error ? e.message : String(e));
              }
              setBusy(false);
            }}>
            <ThemedText style={styles.answerButtonText}>{busy ? '…' : 'Envia'}</ThemedText>
          </TouchableOpacity>
        </View>
      )}
      {rowError && <ThemedText style={styles.error}>{rowError}</ThemedText>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, gap: 12, paddingBottom: 48 },
  date: { fontSize: 22, fontWeight: '800' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  banner: { borderRadius: 12, padding: 16 },
  bannerPreview: { color: '#fff', opacity: 0.85, fontSize: 12, marginBottom: 6 },
  bannerVerdict: { color: '#fff', fontWeight: '800', fontSize: 13, letterSpacing: 2 },
  bannerSummary: { color: '#fff', fontSize: 17, fontWeight: '600', marginTop: 6 },
  card: { backgroundColor: 'rgba(127,127,127,0.1)', borderRadius: 12, padding: 14, gap: 4 },
  cardTitle: { fontSize: 16, fontWeight: '700' },
  cardMeta: { fontSize: 14, opacity: 0.7 },
  step: { fontSize: 14, marginTop: 2 },
  rationale: { fontSize: 15, lineHeight: 22 },
  muted: { opacity: 0.6, textAlign: 'center', marginTop: 8 },
  error: { color: '#d64541', textAlign: 'center' },
  questionRow: { gap: 6 },
  answerRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-end' },
  answerInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: 'rgba(127,127,127,0.4)',
    borderRadius: 10,
    padding: 10,
    fontSize: 14,
    color: '#888',
    minHeight: 40,
  },
  answerButton: {
    backgroundColor: '#1D3D47',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  answerButtonText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  answerDone: { fontSize: 14, fontStyle: 'italic', color: '#2e9e5b' },
});
