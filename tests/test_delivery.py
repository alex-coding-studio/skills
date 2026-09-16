import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/implement/scripts/delivery.py'
spec = importlib.util.spec_from_file_location('delivery', PATH)
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class DeliveryTests(unittest.TestCase):
    def evidence(self):
        state = {'head': 'a' * 40, 'base': 'b' * 40, 'phase': 'approved', 'pending': None,
                 'reviewer': 'reviewer', 'seen': ['handled']}
        snapshot = {'head': state['head'], 'base': state['base'], 'ci': 'pass',
                    'draft': False, 'terminal': None, 'events': [{'key': 'handled'}],
                    'pr': {'mergeable': True, 'mergeable_state': 'clean'},
                    'history': [{'kind': 'review', 'id': 1, 'state': 'APPROVED',
                                 'commit_id': state['head'], 'user': {'login': 'reviewer'}}]}
        return state, snapshot

    def test_merge_refuses_new_head_pending_checks_and_unhandled_feedback(self):
        for field, value in [('head', 'c' * 40), ('ci', 'pending'), ('events', [{'key': 'new'}]),
                             ('draft', True), ('base', 'd' * 40)]:
            state, snapshot = self.evidence()
            snapshot[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                delivery.verify_merge(state, snapshot, 'a' * 40, 'author')

    def test_merge_requires_current_independent_approval_and_no_blocking_review(self):
        for row in [{'id': 2, 'state': 'DISMISSED', 'user': {'login': 'reviewer'}},
                    {'id': 3, 'state': 'CHANGES_REQUESTED', 'user': {'login': 'other'}}]:
            state, snapshot = self.evidence()
            snapshot['history'].append({'kind': 'review', **row})
            with self.assertRaises(ValueError):
                delivery.verify_merge(state, snapshot, 'a' * 40, 'author')

    def test_merge_accepts_passing_evidence_but_rejects_author_as_reviewer(self):
        state, snapshot = self.evidence()
        delivery.verify_merge(state, snapshot, 'a' * 40, 'author')
        with self.assertRaises(ValueError):
            delivery.verify_merge(state, snapshot, 'a' * 40, 'reviewer')

    def test_waiting_ci_requires_positive_check_evidence(self):
        state, snapshot = self.evidence()
        state['phase'] = 'waiting-ci'
        snapshot['ci'] = 'none'
        with self.assertRaises(ValueError):
            delivery.verify_merge(state, snapshot, 'a' * 40, 'author')
        snapshot['ci'] = 'pass'
        delivery.verify_merge(state, snapshot, 'a' * 40, 'author')
        state['phase'] = 'approved'
        snapshot['ci'] = 'none'
        delivery.verify_merge(state, snapshot, 'a' * 40, 'author')

    def test_claude_start_requires_native_monitor_without_launching_shell_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'claude', '--session', 'existing',
                '--pr', 'owner/repo#1', '--checkout', directory, '--acceptance-file', __file__,
                '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'invoke', return_value={}), \
                    patch.object(delivery, 'monitor_live', return_value=False), \
                    patch.object(delivery.subprocess, 'Popen') as popen:
                result = delivery.start(args)
            self.assertEqual(result['status'], 'native-monitor-required')
            self.assertFalse(result['reviewer_active'])
            self.assertIn('claude_pr_monitor.py', result['monitor_command'])
            popen.assert_not_called()

    def test_existing_monitor_is_reused_before_starting_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'owner/repo#1',
                '--checkout', directory, '--acceptance-file', __file__, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'invoke', return_value={'active': True, 'phase': 'starting'}) as invoke, \
                    patch.object(delivery, 'monitor_live', return_value=True), \
                    patch.object(delivery.subprocess, 'Popen') as popen:
                result = delivery.start(args)
            self.assertEqual(result['status'], 'started')
            self.assertTrue(result['reviewer_active'])
            self.assertEqual(invoke.call_count, 2)
            popen.assert_not_called()

    def test_finish_rechecks_base_and_uses_matching_head_before_protected_completion(self):
        state, snapshot = self.evidence()
        args = delivery.parser().parse_args(['finish', '--runtime', 'claude', '--session', 'existing',
            '--pr', 'owner/repo#1', '--expected-head', state['head'], '--merge-method', 'squash', '--feedback-settled'])
        fresh = {'head': {'sha': state['head']}, 'base': {'sha': state['base']}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                patch.object(delivery.review, 'read', return_value=state), \
                patch.object(delivery.review.remote, 'GitHub') as remote, \
                patch.object(delivery.review.remote.shared, 'gh_command', return_value=['gh_as', 'admin']), \
                patch.object(delivery, 'invoke', side_effect=[{'target': {'author': 'author'}}, '']) as invoke, \
                patch.object(delivery.os, 'chdir'), \
                patch.object(delivery.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps({'status': 'cleaned'}))):
            remote.return_value.snapshot.return_value = snapshot
            remote.return_value.pull.side_effect = [fresh, {'merged': True}]
            remote.return_value.number = 1
            remote.return_value.repository = 'owner/repo'
            result = delivery.finish(args)
            command = invoke.call_args_list[1].args[0]
            self.assertIn('--match-head-commit', command)
            self.assertEqual(command[-1], state['head'])
            self.assertNotIn('--admin', command)
            remote.return_value.verify_writer.assert_called_once_with('author')
            self.assertTrue(result['complete'])

    def test_finish_stops_if_base_changes_after_review_snapshot(self):
        state, snapshot = self.evidence()
        args = delivery.parser().parse_args(['finish', '--runtime', 'claude', '--session', 'existing',
            '--pr', 'owner/repo#1', '--expected-head', state['head'], '--merge-method', 'squash', '--feedback-settled'])
        with patch.object(delivery.review, 'read', return_value=state), \
                patch.object(delivery.review.remote, 'GitHub') as remote, \
                patch.object(delivery, 'invoke', return_value={'target': {'author': 'author'}}) as invoke:
            remote.return_value.snapshot.return_value = snapshot
            remote.return_value.pull.return_value = {'head': {'sha': state['head']}, 'base': {'sha': 'c' * 40}}
            with self.assertRaises(ValueError):
                delivery.finish(args)
            self.assertEqual(invoke.call_count, 1)

    def test_open_reconciles_an_existing_pr_instead_of_creating_a_duplicate(self):
        args = delivery.parser().parse_args(['open', '--runtime', 'claude', '--session', 'existing',
            '--repository', 'owner/repo', '--checkout', '/checkout', '--title', 'Fix',
            '--body-file', __file__, '--acceptance-file', __file__, '--reviewer', 'reviewer'])
        responses = [{'login': 'author'}, {'default_branch': 'main', 'permissions': {'push': True}},
                     {'object': {'sha': 'a' * 40}},
                     [{'number': 1, 'author': {'login': 'author'}, 'headRefOid': 'a' * 40}]]
        with patch.object(delivery.review.remote.shared, 'gh_command', return_value=['gh_as', 'bot']), \
                patch.object(delivery.review, 'git', side_effect=['work', 'a' * 40, '']), \
                patch.object(delivery, 'invoke', side_effect=responses) as invoke, \
                patch.object(delivery, 'start', return_value={'status': 'started'}):
            delivery.open_pr(args)
            self.assertEqual(args.pr, 'owner/repo#1')
            self.assertFalse(any('create' in call.args[0] for call in invoke.call_args_list))


if __name__ == '__main__':
    unittest.main()
