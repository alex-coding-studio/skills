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
        added = {'filename': 'docs/NEW.md', 'status': 'added', 'patch': '@@ -0,0 +1 @@\n+# New'}
        self.assertEqual(delivery.exempt_kinds([added, {'filename': 'README.txt', 'status': 'removed',
                                                        'patch': '@@ -1 +0,0 @@\n-old'},
                                                {'filename': 'docs/B.md', 'previous_filename': 'docs/A.md',
                                                 'status': 'renamed', 'changes': 0}]), {'text'})
        self.assertEqual(delivery.exempt_kinds([resolved, added]), {'pin', 'text'})
        for files in [[], [{**resolved, 'status': 'added'}],
                      [{'filename': 'data.bin.txt', 'status': 'added', 'changes': 0}],
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
        doc = {'filename': 'docs/A.md', 'status': 'modified', 'patch': '@@ -1 +1 @@\n-a\n+b'}
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

    def test_claude_stdout_delivery_returns_the_single_runner_for_the_monitor_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'claude', '--session', 'existing',
                '--pr', 'owner/repo#1', '--checkout', directory, '--acceptance-file', __file__,
                '--reviewer', 'reviewer', '--review-runtime', 'codex'])
            runner = "python3 review_pr.py run --pr 'owner/repo#1' --state-base /state"
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery, 'invoke', return_value={'active': False, 'monitor_command': runner}) as invoke, \
                    patch.object(delivery.subprocess, 'Popen') as popen:
                result = delivery.start(args)
            self.assertEqual(result['status'], 'native-monitor-required')
            self.assertEqual(result['monitor_command'], runner)
            command = invoke.call_args.args[0]
            self.assertIn('review_pr.py', command[1])
            self.assertEqual(command[command.index('--runtime') + 1], 'codex')
            self.assertEqual(command[command.index('--author-runtime') + 1], 'claude')
            self.assertEqual(invoke.call_count, 1)
            popen.assert_not_called()

    def test_reviewer_started_without_author_delivery_keeps_the_standalone_monitor(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'owner/repo#1',
                '--checkout', directory, '--acceptance-file', __file__, '--reviewer', 'reviewer'])
            review_root = Path(directory) / 'review'
            review_root.mkdir()
            (review_root / 'state.json').write_text(json.dumps({'schema': 1, 'pr': 'owner/repo#1'}))
            with patch.object(delivery, 'monitor_root', return_value=Path(directory) / 'monitor'), \
                    patch.object(delivery.review, 'state_root', return_value=review_root), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery, 'start_monitor', return_value={'status': 'started'}) as legacy, \
                    patch.object(delivery, 'invoke') as invoke:
                delivery.start(args)
            legacy.assert_called_once()
            invoke.assert_not_called()

    def test_new_pr_starts_one_runner_that_also_delivers_author_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'owner/repo#1',
                '--checkout', directory, '--acceptance-file', __file__, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery, 'invoke', return_value={'active': True, 'phase': 'starting'}) as invoke, \
                    patch.object(delivery.subprocess, 'Popen') as popen:
                result = delivery.start(args)
            self.assertEqual(result['status'], 'started')
            self.assertTrue(result['monitor_active'])
            self.assertEqual(invoke.call_count, 1)
            self.assertIn('--author-session', invoke.call_args.args[0])
            popen.assert_not_called()

    def test_reviewer_uses_the_pr_description_when_no_acceptance_file_is_given(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'owner/repo#1',
                '--checkout', directory, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery, 'invoke', return_value={'active': True}) as invoke:
                self.assertEqual(delivery.start(args)['status'], 'started')
            self.assertNotIn('--acceptance-file', invoke.call_args.args[0])

    def test_a_pool_slot_starts_the_single_runner_with_its_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'claude', '--session', 'existing',
                '--pr', 'owner/repo#1', '--slot', directory, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery, 'invoke', return_value={'active': True}) as invoke:
                delivery.start(args)
            command = invoke.call_args.args[0]
            self.assertEqual(command[command.index('--slot') + 1], str(Path(directory).resolve()))
            self.assertNotIn('--checkout', command)

    def test_a_codex_worker_in_a_pool_slot_starts_the_single_runner_with_queue_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'owner/repo#1',
                '--slot', directory, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery, 'invoke', return_value={'active': True}) as invoke:
                self.assertEqual(delivery.start(args)['status'], 'started')
            command = invoke.call_args.args[0]
            self.assertEqual(command[command.index('--author-runtime') + 1], 'codex')
            self.assertEqual(command[command.index('--slot') + 1], str(Path(directory).resolve()))

    def test_takeover_is_passed_to_the_runner_only_when_declared(self):
        with tempfile.TemporaryDirectory() as directory:
            for extra, expected in (([], False), (['--takeover'], True)):
                args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                    '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'owner/repo#1',
                    '--slot', directory, '--reviewer', 'reviewer', *extra])
                with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                        patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                        patch.object(delivery, 'invoke', return_value={'active': True}) as invoke:
                    delivery.start(args)
                self.assertEqual('--takeover' in invoke.call_args.args[0], expected)

    def test_an_exempt_pool_slot_registers_the_project_monitor_with_its_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            args = delivery.parser().parse_args(['start', '--runtime', 'claude', '--session', 'existing',
                '--pr', 'owner/repo#1', '--slot', directory, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-exempt', 'head': 'h'}), \
                    patch.object(delivery, 'monitor_live', return_value=True), \
                    patch.object(delivery, 'invoke', return_value={}) as invoke:
                result = delivery.start(args)
            registration = invoke.call_args_list[0].args[0]
            self.assertEqual(result['status'], 'review-exempt')
            self.assertIn('project_pr_monitor.py', registration[1])
            self.assertEqual(registration[registration.index('--slot') + 1], str(Path(directory).resolve()))

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
                    patch.object(delivery, 'pin_check', return_value={'status': 'review-required'}), \
                    patch.object(delivery, 'invoke', return_value={}), \
                    patch.object(delivery.subprocess, 'Popen'), \
                    self.assertRaisesRegex(ValueError, 'refusing reroute'):
                delivery.start(args)

    def test_legacy_registered_monitor_is_reused_before_starting_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'state.json').write_text(json.dumps({'target': {}}))
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
