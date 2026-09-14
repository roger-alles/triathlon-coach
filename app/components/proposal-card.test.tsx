jest.mock('@/lib/supabase', () => ({ supabase: {} }));
import { render, screen, userEvent, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import ProposalCard from './proposal-card';

const sessions = new Map([
  [43, { id: 43, local_date: '2026-09-10', sport: 'swim', title: 'Ritme de cursa amb orientació', status: 'planned' }],
  [44, { id: 44, local_date: '2026-09-11', sport: 'run', title: 'Rodatge amb progressius', status: 'planned' }],
  [46, { id: 46, local_date: '2026-09-13', sport: 'run', title: 'Recuperació', status: 'planned' }],
]);

const proposal = {
  id: 27,
  createdAt: '2026-09-10T19:32:04Z',
  reportType: 'daily',
  status: 'proposed' as const,
  classification: { auto: false, reasons: ['toca una sessió clau'] },
  changes: [
    { plan_session_id: 43, action: 'move' as const, new_date: '2026-09-11', reason: 'no es pot saltar' },
    { plan_session_id: 44, action: 'modify' as const, reason: 'guardar cames', new_session: { sport: 'run', title: 'Rodatge 25 min', duration_sec_target: 1500 } },
    { plan_session_id: 46, action: 'cancel' as const, reason: 'sobra' },
  ],
};

beforeEach(() => {
  jest.restoreAllMocks();
  jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons) => {
    buttons?.find((b) => b.style !== 'cancel')?.onPress?.();
  });
});

test('pinta el diff: dia i títol actual, i què canvia, amb la raó', async () => {
  await render(<ProposalCard proposal={proposal} sessions={sessions} applyMode="hybrid" onDecide={jest.fn()} />);
  expect(screen.getByText(/Proposta del coach/)).toBeOnTheScreen();
  expect(screen.getByText(/Dj 10 · Ritme de cursa amb orientació/)).toBeOnTheScreen();
  expect(screen.getByText(/→ Dv 11/)).toBeOnTheScreen();
  expect(screen.getByText(/Dv 11 · Rodatge amb progressius/)).toBeOnTheScreen();
  expect(screen.getByText(/→ Rodatge 25 min · 25 min/)).toBeOnTheScreen();
  expect(screen.getByText(/Dg 13 · Recuperació/)).toBeOnTheScreen();
  expect(screen.getByText(/cancel·lada/)).toBeOnTheScreen();
  expect(screen.getByText(/no es pot saltar/)).toBeOnTheScreen();
  expect(screen.getByText(/Per què no s'aplica sola: toca una sessió clau/)).toBeOnTheScreen();
});

test('proposta pendent: Aplica (amb confirmació) i Descarta', async () => {
  const onDecide = jest.fn().mockResolvedValue(undefined);
  await render(<ProposalCard proposal={proposal} sessions={sessions} applyMode="hybrid" onDecide={onDecide} />);
  const user = userEvent.setup();
  await user.press(screen.getByText('Aplica'));
  await waitFor(() => expect(onDecide).toHaveBeenCalledWith('apply'));
  expect(Alert.alert).toHaveBeenCalled();
  await user.press(screen.getByText('Descarta'));
  await waitFor(() => expect(onDecide).toHaveBeenCalledWith('discard'));
});

test('aplicada automàticament: ho diu i ofereix Desfés', async () => {
  const onDecide = jest.fn().mockResolvedValue(undefined);
  await render(<ProposalCard proposal={{ ...proposal, status: 'auto_applied', classification: { auto: true, reasons: [] } }} sessions={sessions} applyMode="hybrid" onDecide={onDecide} />);
  expect(screen.getByText(/Aplicada automàticament/)).toBeOnTheScreen();
  expect(screen.queryByText('Aplica')).toBeNull();
  const user = userEvent.setup();
  await user.press(screen.getByText('Desfés'));
  await waitFor(() => expect(onDecide).toHaveBeenCalledWith('undo'));
});

test('en mode prova: etiqueta i cap botó', async () => {
  await render(<ProposalCard proposal={{ ...proposal, status: 'none' }} sessions={sessions} applyMode="dry_run" onDecide={jest.fn()} />);
  expect(screen.getByText(/Mode prova/)).toBeOnTheScreen();
  expect(screen.queryByText('Aplica')).toBeNull();
  expect(screen.queryByText('Desfés')).toBeNull();
});

test('decisió en curs: "Aplicant…" i sense botons; fallida: error i botons de nou', async () => {
  const pending = { id: 1, report_id: 27, decision: 'apply' as const, status: 'pending' as const, error: null, created_at: '2026-09-14T10:00:00Z' };
  const { rerender } = await render(<ProposalCard proposal={proposal} sessions={sessions} decision={pending} applyMode="hybrid" onDecide={jest.fn()} />);
  expect(screen.getByText(/Aplicant…/)).toBeOnTheScreen();
  expect(screen.queryByText('Aplica')).toBeNull();
  const failed = { ...pending, status: 'failed' as const, error: 'proposta caducada: la sessió 43 ja no és planned' };
  await rerender(<ProposalCard proposal={proposal} sessions={sessions} decision={failed} applyMode="hybrid" onDecide={jest.fn()} />);
  expect(screen.getByText(/proposta caducada/)).toBeOnTheScreen();
  expect(screen.getByText('Aplica')).toBeOnTheScreen();
});

test('una sessió que no es troba surt pel seu id, no peta', async () => {
  await render(<ProposalCard proposal={{ ...proposal, changes: [{ plan_session_id: 99, action: 'cancel', reason: 'x' }] }} sessions={new Map()} applyMode="hybrid" onDecide={jest.fn()} />);
  expect(screen.getByText(/Sessió #99/)).toBeOnTheScreen();
});
