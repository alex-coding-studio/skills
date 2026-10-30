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

    def test_pin_only_accepts_lockfiles_and_version_lines_only(self):
        resolved = {'filename': 'App.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved',
                    'status': 'modified', 'patch': '@@ -1 +1 @@\n-"revision" : "a"\n+"revision" : "b"'}
        version = {'filename': 'project.yml', 'status': 'modified',
                   'patch': '@@ -3,3 +3,3 @@\n     settings:\n-    MARKETING_VERSION: "1.4"\n+    MARKETING_VERSION: "1.4.1"'}
        self.assertEqual(delivery.exempt_kinds([resolved]), {'pin'})
        self.assertEqual(delivery.exempt_kinds([resolved, version]), {'pin'})
        self.assertTrue(delivery.exempt_kinds([{'filename': 'App.xcodeproj/project.pbxproj', 'status': 'modified',
                                            'patch': '@@ -1 +1 @@\n-\t\t\t\tMARKETING_VERSION = 1.4;\n'
                                                     '+\t\t\t\tMARKETING_VERSION = 1.4.1;'}]))
        self.assertEqual(delivery.exempt_kinds([{'filename': 'docs/NEW.md', 'status': 'added'},
                                                {'filename': 'README.txt', 'status': 'removed'}]), {'text'})
        self.assertEqual(delivery.exempt_kinds([resolved, {'filename': 'docs/NEW.md', 'status': 'added'}]),
                         {'pin', 'text'})
        for files in [[], [{**resolved, 'status': 'added'}],
                      [{'filename': 'Sources/Notes.md', 'previous_filename': 'Sources/Notes.swift', 'status': 'renamed'}],
                      [{'filename': 'docs/acceptance.html', 'status': 'modified', 'patch': '@@ -1 +1 @@\n-a\n+b'}],
                      [{**version, 'patch': version['patch'] + '\n+    url: https://example.com/new'}],
                      [{**version, 'patch': None}],
                      [{'filename': 'Sources/App.swift', 'status': 'modified', 'patch': '@@ -1 +1 @@\n-    version = 1\n+    version = 2'}]]:
            with self.subTest(files=files):
                self.assertEqual(delivery.exempt_kinds(files), set())

    def test_exemption_needs_base_branch_declaration_covering_every_kind(self):
        self.assertEqual(delivery.declared_exemptions('scheme=App\nreview_exempt="pin text"\n'), {'pin', 'text'})
        self.assertEqual(delivery.declared_exemptions('review_exempt=pin\n'), {'pin'})
        self.assertEqual(delivery.declared_exemptions('scheme=App\n'), set())
        resolved = {'filename': 'Package.resolved', 'status': 'modified', 'patch': ''}
        doc = {'filename': 'docs/A.md', 'status': 'modified'}
        for files, config, expected in [
                ([resolved], 'review_exempt=pin', 'review-exempt'),
                ([resolved, doc], 'review_exempt=pin', 'review-required'),
                ([doc], None, 'review-required')]:
            github = SimpleNamespace(number=7, base='repos/o/r')
            github.pull = lambda: {'head': {'sha': 'h'}, 'base': {'sha': 'b'}}

            def respond(endpoint, paginate=False, files=files, config=config):
                if paginate:
                    return files
                self.assertIn('ref=b', endpoint)
                if config is None:
                    raise delivery.subprocess.CalledProcessError(1, 'gh')
                return {'content': delivery.base64.b64encode(config.encode()).decode()}
            github.json = respond
            with self.subTest(expected=expected, config=config), \
                    patch.object(delivery.review.remote, 'GitHub', return_value=github):
                self.assertEqual(delivery.pin_check(SimpleNamespace(pr='o/r#7'))['status'], expected)

    def test_pin_merge_refuses_without_push_permission(self):
        head = 'a' * 40
        github = SimpleNamespace(number=7, repository='o/r', base='repos/o/r')
        github.pull = lambda: {'state': 'open', 'draft': False, 'head': {'sha': head},
                               'mergeable': True, 'mergeable_state': 'clean'}
        github.json = lambda endpoint, paginate=False: {'permissions': {'push': False}}
        args = SimpleNamespace(pr='o/r#7', expected_head=head, merge_method='merge')
        calls = []
        with patch.object(delivery, 'pin_check', return_value={'status': 'review-exempt', 'head': head}), \
                patch.object(delivery.review.remote, 'GitHub', return_value=github), \
                patch.object(delivery.review.remote.shared, 'gh_command', return_value=['gh']), \
                patch.object(delivery, 'invoke', side_effect=lambda command, cwd=None: calls.append(command) or
                             {'headRefOid': head, 'statusCheckRollup': []}):
            with self.assertRaises(PermissionError):
                delivery.pin_merge(args)
        self.assertFalse(any('merge' in command for command in calls))

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

    def test_waiting_ci_recorded_without_any_checks_merges_like_an_approval(self):
        state, snapshot = self.evidence()
        state.update(phase='waiting-ci', ci='none')
        snapshot['ci'] = 'none'
        delivery.verify_merge(state, snapshot, 'a' * 40, 'author')
        for ci in ('pending', 'fail'):
            snapshot['ci'] = ci
            with self.subTest(ci=ci), self.assertRaises(ValueError):
                delivery.verify_merge(state, snapshot, 'a' * 40, 'author')

    def test_waiting_ci_recorded_with_observed_checks_still_requires_passing_checks(self):
        state, snapshot = self.evidence()
        for recorded in ('pending', 'fail'):
            state.update(phase='waiting-ci', ci=recorded)
            snapshot['ci'] = 'none'
            with self.subTest(recorded=recorded), self.assertRaises(ValueError):
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

    def test_claude_start_launches_its_own_listener_once_a_session_endpoint_is_bound(self):
        endpoint = 'unix:///tmp/semina-claude-test/control.sock'
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'state.json').write_text(json.dumps({'target': {'session_remote': endpoint}}))
            args = delivery.parser().parse_args(['start', '--runtime', 'claude', '--session', 'existing',
                '--pr', 'owner/repo#1', '--checkout', directory, '--acceptance-file', __file__,
                '--reviewer', 'reviewer', '--session-remote', endpoint])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'invoke', return_value={'active': True, 'phase': 'starting'}) as invoke, \
                    patch.object(delivery, 'monitor_live', side_effect=[False, True]), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery.subprocess, 'Popen') as popen:
                result = delivery.start(args)
            self.assertEqual(result['status'], 'started')
            self.assertTrue(result['monitor_active'])
            popen.assert_called_once()
            self.assertNotIn('--session-remote', invoke.call_args_list[0].args[0])

    def test_claude_start_refuses_a_session_endpoint_that_differs_from_the_bound_one(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'state.json').write_text(
                json.dumps({'target': {'session_remote': 'unix:///tmp/one/control.sock'}}))
            args = delivery.parser().parse_args(['start', '--runtime', 'claude', '--session', 'existing',
                '--pr', 'owner/repo#1', '--checkout', directory, '--acceptance-file', __file__,
                '--reviewer', 'reviewer', '--session-remote', 'unix:///tmp/two/control.sock'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'invoke', return_value={}), \
                    patch.object(delivery.subprocess, 'Popen'), \
                    self.assertRaisesRegex(ValueError, 'refusing reroute'):
                delivery.start(args)

    def test_existing_monitor_is_reused_before_starting_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'owner/repo#1',
                '--checkout', directory, '--acceptance-file', __file__, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'invoke', return_value={'active': True, 'phase': 'starting'}) as invoke, \
                    patch.object(delivery, 'monitor_live', return_value=True), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery.subprocess, 'Popen') as popen:
                result = delivery.start(args)
            self.assertEqual(result['status'], 'started')
            self.assertTrue(result['reviewer_active'])
            self.assertEqual(invoke.call_count, 2)
            popen.assert_not_called()

    def test_declared_exemption_registers_monitor_without_starting_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'owner/repo#1',
                '--checkout', directory, '--acceptance-file', __file__, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'invoke', return_value={}) as invoke, \
                    patch.object(delivery, 'monitor_live', return_value=True), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-exempt', 'head': 'h'}):
                result = delivery.start(args)
            self.assertEqual(result['status'], 'review-exempt')
            self.assertFalse(result['reviewer_active'])
            self.assertEqual(invoke.call_count, 1)
            self.assertNotIn('review_pr.py', ' '.join(map(str, invoke.call_args.args[0])))

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
