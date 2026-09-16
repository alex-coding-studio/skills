import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/review/scripts/pr_review_state.py'
spec = importlib.util.spec_from_file_location('pr_review_state', SCRIPT)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def snapshot(head='a' * 40, ci='pending', events=None, terminal=None):
    return {'head': head, 'base': 'b' * 40, 'ci': ci, 'ci_key': ci,
            'events': events or [], 'terminal': terminal, 'draft': False}


class PRReviewStateTests(unittest.TestCase):
    def test_PRL_02_approval_waits_for_merge_without_idle_model_calls(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        current = snapshot()
        self.assertEqual(core.next_event(state, current), 'head')
        core.settle(state, current, 'approved', ['event-one'])
        self.assertIsNone(core.next_event(state, current))
        self.assertEqual(state['phase'], 'approved')
        self.assertEqual(core.next_event(state, snapshot(ci='pass')), 'ci')
        self.assertEqual(core.next_event(state, snapshot(terminal='merged')), 'merged')

    def test_PRL_02_new_head_after_approval_returns_to_same_reviewer(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        state['session'] = 'review-session'
        core.settle(state, snapshot(), 'approved', [])
        self.assertEqual(core.next_event(state, snapshot(head='c' * 40)), 'head')
        self.assertEqual(state['session'], 'review-session')

    def test_PRL_02_pending_check_churn_and_repeated_events_are_quiet(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        core.settle(state, snapshot(), 'waiting-ci', ['one'])
        current = snapshot(events=[{'key': 'one'}])
        current['ci_key'] = 'another-pending-check'
        self.assertIsNone(core.next_event(state, current))
        self.assertEqual(core.next_event(state, snapshot(events=[{'key': 'two'}])), 'feedback')

    def test_PRL_03_recovery_keeps_rounds_and_attention_does_not_auto_resume(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        state['rounds'] = 2
        state['phase'] = 'needs-user-attention'
        state['head'] = 'a' * 40
        checkpoint = core.checkpoint(state, 'handoff-one')
        restored = core.initial_state('owner/repo#1', 'reviewer', 'author', 'claude', 2)
        core.restore(restored, checkpoint)
        self.assertEqual(restored['rounds'], 2)
        self.assertIsNone(core.next_event(restored, snapshot(head='c' * 40)))
        self.assertIsNone(restored['session'])

    def test_PRL_04_settling_a_snapshot_preserves_later_feedback(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        core.settle(state, snapshot(), 'changes-requested', ['old'])
        self.assertEqual(core.next_event(state, snapshot(events=[{'key': 'old'}, {'key': 'later'}])), 'feedback')

    def test_PRL_03_changes_after_last_allowed_round_require_attention(self):
        self.assertEqual(core.disposition('changes-requested', 2, 2), 'needs-user-attention')
        self.assertEqual(core.disposition('approved', 2, 2), 'approved')

    def test_PRL_05_wrong_pr_or_invalid_checkpoint_cannot_restore_progress(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        other = core.initial_state('owner/repo#2', 'reviewer', 'author', 'codex', 2)
        with self.assertRaises(ValueError):
            core.restore(state, core.checkpoint(other, 'wrong'))


if __name__ == '__main__':
    unittest.main()
