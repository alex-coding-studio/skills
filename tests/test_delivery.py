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
    def setUp(self):
        configured = patch.object(delivery.review, 'configured_runtime', return_value=None)
        configured.start()
        self.addCleanup(configured.stop)

    def test_review_runtime_prefers_the_argument_then_the_project_config_then_the_author(self):
        args = SimpleNamespace(pr='o/r#7', runtime='claude', review_runtime=None, reviewer='admin', max_rounds=3,
                               acceptance_file=None, complexity=None)
        def runtime(**changes):
            command = delivery.review_command(SimpleNamespace(**{**vars(args), **changes}))
            return command[command.index('--runtime') + 1]
        self.assertEqual(runtime(), 'claude')
        with patch.object(delivery.review, 'configured_runtime', return_value='codex'):
            self.assertEqual(runtime(), 'codex')
            self.assertEqual(runtime(review_runtime='claude'), 'claude')

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

    def test_coordinator_label_exempts_source_changes_and_start_only_registers_monitor(self):
        files = [{'filename': 'Sources/Owned.swift', 'status': 'removed', 'patch': '@@ -1 +0,0 @@\n-old'}]
        github = SimpleNamespace(number=7, base='repos/o/r')
        pull = {'head': {'sha': 'h'}, 'base': {'sha': 'b'}, 'labels': []}
        github.pull = lambda: pull
        github.json = lambda endpoint, paginate=False: files if paginate else {'content': ''}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(delivery.review.remote, 'GitHub', return_value=github), \
                patch.object(delivery, 'monitor_root', return_value=Path(directory)), \
                patch.object(delivery, 'monitor_live', return_value=True), \
                patch.object(delivery, 'invoke', return_value={}) as invoke:
            self.assertEqual(delivery.pin_check(SimpleNamespace(pr='o/r#7'))['status'], 'review-required')
            pull['labels'] = [{'name': 'ci-skip-approved'}]
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'o/r#7',
                '--checkout', directory, '--reviewer', 'reviewer'])
            result = delivery.start(args)
        self.assertEqual(result['status'], 'review-exempt')
        self.assertEqual(result['exemption'], 'coordinator-approved-mechanical')
        self.assertFalse(result['reviewer_active'])
        self.assertTrue(result['monitor_active'])
        self.assertEqual(invoke.call_count, 1)
        self.assertNotIn('review_pr.py', ' '.join(map(str, invoke.call_args.args[0])))

    def test_coordinator_label_does_not_start_a_second_monitor_for_an_active_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'state.json').write_text(json.dumps({'author_delivery': 'codex'}))
            args = delivery.parser().parse_args(['start', '--runtime', 'codex',
                '--session', '00000000-0000-0000-0000-000000000001', '--pr', 'o/r#7',
                '--checkout', directory, '--reviewer', 'reviewer'])
            with patch.object(delivery, 'pin_check', return_value={'status': 'review-exempt',
                    'exemption': 'coordinator-approved-mechanical'}), \
                    patch.object(delivery.review, 'state_root', return_value=root), \
                    patch.object(delivery.review, 'running', return_value=True), \
                    patch.object(delivery, 'start_monitor') as monitor:
                with self.assertRaisesRegex(ValueError, 'existing PR runner'):
                    delivery.start(args)
            monitor.assert_not_called()

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
                patch.object(delivery.review.remote.shared, 'ci_required', return_value=()), \
                patch.object(delivery, 'invoke', side_effect=lambda command, cwd=None: calls.append(command) or
                             {'headRefOid': head, 'statusCheckRollup': []}):
            with self.assertRaises(PermissionError):
                delivery.pin_merge(args)
        self.assertFalse(any('merge' in command for command in calls))


    def test_pin_merge_in_a_ci_project_refuses_when_a_required_check_is_missing(self):
        head = 'a' * 40
        github = SimpleNamespace(number=7, repository='o/r', base='repos/o/r')
        github.pull = lambda: {'state': 'open', 'draft': False, 'head': {'sha': head},
                               'mergeable': True, 'mergeable_state': 'clean'}
        github.json = lambda endpoint, paginate=False: {'permissions': {'push': True}}
        passed = {'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': 'SUCCESS'}
        rollup = [{**passed, 'name': 'ios-plan'}]
        calls = []
        with patch.object(delivery, 'pin_check', return_value={'status': 'review-exempt', 'head': head}), \
                patch.object(delivery.review.remote, 'GitHub', return_value=github), \
                patch.object(delivery.review.remote.shared, 'gh_command', return_value=['gh']), \
                patch.object(delivery.review.remote.shared, 'ci_required',
                             return_value=delivery.review.remote.shared.CI_REQUIRED_CHECKS), \
                patch.object(delivery, 'invoke', side_effect=lambda command, cwd=None: calls.append(command) or
                             {'headRefOid': head, 'statusCheckRollup': rollup}):
            with self.assertRaisesRegex(ValueError, 'checks are not passing'):
                delivery.pin_merge(SimpleNamespace(pr='o/r#7', expected_head=head, merge_method='merge'))
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


class PendingCIMergeTests(unittest.TestCase):
    def setUp(self):
        self.head = 'a' * 40
        self.args = SimpleNamespace(pr='o/r#7', expected_head=self.head, merge_method='merge', allow_pending_ci=True)
        self.pull = {'state': 'open', 'draft': False, 'head': {'sha': self.head, 'ref': 'work',
                     'repo': {'full_name': 'o/r'}}, 'mergeable': True, 'mergeable_state': 'clean',
                     'labels': [{'name': 'ci-skip-approved'}]}
        self.checks = [{'__typename': 'CheckRun', 'name': 'tests', 'status': 'IN_PROGRESS', 'conclusion': None}]
        self.runs = [{'id': 1, 'head_sha': self.head, 'head_branch': 'work',
                      'head_repository': {'full_name': 'o/r'}, 'status': 'in_progress'}]
        self.calls = []
        self.permission = True
        self.exemption = 'review-exempt'
        self.revoke_label = False
        self.coordinator_exemption = False
        self.cancel_fails = False
        self.extra_page = []

    def merge(self):
        github = SimpleNamespace(number=7, repository='o/r', base='repos/o/r', pull=lambda: self.pull.copy(),
                                 json=lambda endpoint, paginate=False: {'permissions': {'push': self.permission}})

        def invoke(command, cwd=None):
            self.calls.append(command)
            if 'view' in command:
                if self.revoke_label:
                    self.pull['labels'] = []
                return {'headRefOid': self.head, 'statusCheckRollup': self.checks}
            if 'merge' in command:
                self.pull['merged'] = True
                return ''
            if any('/cancel' in str(value) for value in command):
                if self.cancel_fails:
                    raise delivery.subprocess.CalledProcessError(1, command, stderr='HTTP 403')
                return {}
            if any('/actions/runs' in str(value) for value in command):
                return [{'workflow_runs': self.runs}, {'workflow_runs': self.extra_page}]
            raise AssertionError(command)

        with patch.object(delivery, 'pin_check', return_value={'status': self.exemption, 'head': self.head,
                    **({'exemption': 'coordinator-approved-mechanical'} if self.coordinator_exemption else {})}), \
                patch.object(delivery.review.remote, 'GitHub', return_value=github), \
                patch.object(delivery.review.remote.shared, 'gh_command', return_value=['gh_as', 'admin']), \
                patch.object(delivery.review.remote.shared, 'ci_required', return_value=()), \
                patch.object(delivery, 'invoke', side_effect=invoke):
            return delivery.pin_merge(self.args)

    def test_source_exemption_requires_the_flag_even_when_ci_has_passed(self):
        self.coordinator_exemption = True
        self.args.allow_pending_ci = False
        self.checks = [{'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': 'SUCCESS'}]
        with self.assertRaisesRegex(ValueError, '--allow-pending-ci'):
            self.merge()
        self.assertFalse(any('merge' in command for command in self.calls))

    def test_coordinator_mechanical_merge_audits_exemption_label_head_and_cancellations(self):
        self.coordinator_exemption = True
        result = self.merge()
        self.assertEqual(result['exemption'], 'coordinator-approved-mechanical')
        self.assertEqual(result['approval_label'], 'ci-skip-approved')
        self.assertEqual(result['head'], self.head)
        self.assertIn('协调者批准的机械改动：免独立审查、未等 CI', result['message'])
        self.assertEqual(result['cancel_requested_run_ids'], [1])

    def test_unsuccessful_completed_checks_block_even_without_another_pending_check(self):
        self.coordinator_exemption = True
        for conclusion in ('FAILURE', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED'):
            with self.subTest(conclusion=conclusion):
                self.checks = [{'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': conclusion}]
                with self.assertRaisesRegex(ValueError, 'checks are not passing'):
                    self.merge()
        self.assertFalse(any('merge' in command for command in self.calls))

    def test_coordinator_label_is_rechecked_even_after_successful_checks(self):
        self.coordinator_exemption = True
        self.revoke_label = True
        self.checks = [{'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': 'SUCCESS'}]
        with self.assertRaisesRegex(ValueError, 'approval label or expected ready head changed'):
            self.merge()
        self.assertFalse(any('merge' in command for command in self.calls))

    def test_pending_requires_both_the_flag_and_coordinator_label(self):
        for flag, labels in ((False, [{'name': 'ci-skip-approved'}]), (True, []), (False, [])):
            with self.subTest(flag=flag, labels=labels):
                self.args.allow_pending_ci = flag
                self.pull['labels'] = labels
                with self.assertRaisesRegex(ValueError, 'checks are not passing'):
                    self.merge()
                self.assertFalse(any('merge' in command for command in self.calls))

    def test_every_unsuccessful_terminal_check_still_blocks_the_override(self):
        for conclusion in ('FAILURE', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED', None):
            with self.subTest(conclusion=conclusion):
                self.checks = [self.checks[0], {'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': conclusion}]
                with self.assertRaisesRegex(ValueError, 'checks are not passing'):
                    self.merge()
        for state in ('FAILURE', 'ERROR'):
            with self.subTest(state=state):
                self.checks = [self.checks[0], {'__typename': 'StatusContext', 'state': state}]
                with self.assertRaisesRegex(ValueError, 'checks are not passing'):
                    self.merge()
        self.assertFalse(any('merge' in command for command in self.calls))

    def test_skipped_and_neutral_checks_do_not_block_a_coordinator_merge(self):
        for conclusion in ('SKIPPED', 'NEUTRAL'):
            for pending in (False, True):
                with self.subTest(conclusion=conclusion, pending=pending):
                    self.pull['merged'] = False
                    self.checks = ([{'__typename': 'CheckRun', 'name': 'build', 'status': 'QUEUED'}] if pending else [])
                    self.checks.append({'__typename': 'CheckRun', 'name': 'label-job',
                                        'status': 'COMPLETED', 'conclusion': conclusion})
                    self.assertEqual(self.merge()['status'], 'merged')

    def test_superseded_cancelled_check_does_not_block_but_latest_failure_does(self):
        old = {'__typename': 'CheckRun', 'name': 'lint', 'startedAt': '1',
               'status': 'COMPLETED', 'conclusion': 'CANCELLED'}
        self.checks = [{**old, 'startedAt': '2', 'conclusion': 'SUCCESS'}, old]
        self.assertEqual(self.merge()['status'], 'merged')
        self.pull['merged'] = False
        self.checks.append({**old, 'startedAt': '3', 'conclusion': 'FAILURE'})
        with self.assertRaisesRegex(ValueError, 'checks are not passing'):
            self.merge()

    def test_new_failed_run_blocks_merge_when_old_success_started_later(self):
        old = {'__typename': 'CheckRun', 'name': 'lint', 'status': 'COMPLETED', 'conclusion': 'SUCCESS',
               'startedAt': '2026-11-07T10:03:00Z',
               'detailsUrl': 'https://github.com/o/r/actions/runs/100/job/1000'}
        new = {**old, 'conclusion': 'FAILURE', 'startedAt': '2026-11-07T10:01:00Z',
               'detailsUrl': 'https://github.com/o/r/actions/runs/101/job/1001'}
        self.checks = [new, old]
        with self.assertRaisesRegex(ValueError, 'checks are not passing'):
            self.merge()
        self.assertFalse(any('merge' in command for command in self.calls))

    def test_pending_override_merges_then_cancels_only_its_exact_head_branch_and_repository(self):
        self.runs += [{**self.runs[0], 'id': 2, 'head_sha': 'b' * 40},
                      {**self.runs[0], 'id': 3, 'head_branch': 'other'},
                      {**self.runs[0], 'id': 4, 'head_repository': {'full_name': 'fork/r'}},
                      {**self.runs[0], 'id': 5, 'status': 'completed'}]
        self.extra_page = [{**self.runs[0], 'id': 6, 'status': 'queued'}]
        result = self.merge()
        self.assertEqual(result['status'], 'merged')
        self.assertTrue(result['merged_without_waiting_for_ci'])
        self.assertEqual(result['cancel_requested_run_ids'], [1, 6])
        self.assertIn('未等 CI 合并', result['message'])
        commands = [' '.join(command) for command in self.calls]
        cancelled = [command for command in commands if '/cancel' in command]
        self.assertEqual(len(cancelled), 2)
        self.assertIn('/actions/runs/1/cancel', cancelled[0])
        self.assertLess(next(index for index, command in enumerate(commands) if 'pr merge' in command),
                        next(index for index, command in enumerate(commands) if '/cancel' in command))

    def test_revoked_label_prevents_a_merge_after_the_checks_are_read(self):
        self.revoke_label = True
        with self.assertRaisesRegex(ValueError, 'approval label or expected ready head changed'):
            self.merge()
        self.assertFalse(any('merge' in command for command in self.calls))

    def test_cancellation_failure_keeps_the_confirmed_merge_and_failed_run_in_the_receipt(self):
        self.cancel_fails = True
        result = self.merge()
        self.assertEqual(result['status'], 'merged')
        self.assertEqual(result['cancel_requested_run_ids'], [])
        self.assertEqual(result['cancel_errors'][0]['run_id'], 1)
        self.assertTrue(self.pull['merged'])

    def test_pending_status_and_queued_checks_are_allowed_but_unknown_states_are_not(self):
        self.assertEqual(delivery.mechanical_ci_state([{'__typename': 'StatusContext', 'state': 'PENDING'}]), 'pending')
        self.assertEqual(delivery.mechanical_ci_state([{'__typename': 'CheckRun', 'status': 'QUEUED'}]), 'pending')
        self.assertEqual(delivery.mechanical_ci_state([{'__typename': 'CheckRun', 'status': 'UNKNOWN'}]), 'fail')
        self.assertEqual(delivery.mechanical_ci_state([]), 'pass')

    def test_pending_override_preserves_exemption_head_and_permission_guards(self):
        for field, value, error in (('exemption', 'review-required', ValueError), ('permission', False, PermissionError)):
            with self.subTest(field=field):
                previous = getattr(self, field)
                setattr(self, field, value)
                with self.assertRaises(error):
                    self.merge()
                setattr(self, field, previous)
        self.args.expected_head = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'expected ready head'):
            self.merge()
        self.assertFalse(any('merge' in command for command in self.calls))

    def test_flag_is_explicit_and_normal_success_keeps_the_existing_receipt(self):
        self.assertFalse(delivery.parser().parse_args(['pin-merge']).allow_pending_ci)
        self.assertTrue(delivery.parser().parse_args(['pin-merge', '--allow-pending-ci']).allow_pending_ci)
        for action in ('open', 'start', 'pin-check'):
            with self.subTest(action=action), patch.object(delivery.sys, 'argv', ['delivery.py', action, '--allow-pending-ci']), \
                    patch('builtins.print') as printed, patch.object(delivery, 'invoke') as invoke:
                with self.assertRaises(SystemExit) as exited:
                    delivery.main()
                self.assertEqual(exited.exception.code, 1)
                self.assertIn('only available for pin-merge', printed.call_args.args[0])
                invoke.assert_not_called()
        self.args.allow_pending_ci = False
        self.checks = [{'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': 'SUCCESS'}]
        self.assertEqual(self.merge(), {'status': 'merged', 'head': self.head})



if __name__ == '__main__':
    unittest.main()
