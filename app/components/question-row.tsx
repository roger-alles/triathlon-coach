import { useState } from 'react';
import { StyleSheet, TextInput, TouchableOpacity, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';

// Una pregunta del coach amb la caixa de resposta (o la resposta ja donada).
// La fan servir Avui (informe diari) i la targeta de proposta (setmanal, macro).
export default function QuestionRow({
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
  step: { fontSize: 14, marginTop: 2 },
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
