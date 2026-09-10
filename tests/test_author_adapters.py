import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/monitor/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


claude = load('claude_pr_monitor')
codex = load('codex_pr_monitor')
THREAD = '12345678-1234-1234-1234-123456789abc'


class RoleTests(unittest.TestCase):
    def test_both_runtimes_read_github_as_the_bot(self):
        self.assertEqual(claude.Runtime.role, 'bot')
        self.assertEqual(codex.Runtime.role, 'bot')

    def test_each_runtime_carries_its_own_marker_and_delivery_name(self):
        self.assertEqual(claude.Runtime.marker, 'From Claude 🤖')
        self.assertEqual(codex.Runtime.marker, 'From Codex 🤖')
        self.assertEqual(claude.Runtime.delivery_name, 'stdout')
        self.assertEqual(codex.Runtime.delivery_name, 'queue')


class ClaudeDeliveryTests(unittest.TestCase):
    def test_delivery_prints_and_reports_success(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(claude.Runtime('session-one', '/s.py').deliver('batch'))
        self.assertIn('batch', output.getvalue())

    def test_cleanup_is_never_deferred(self):
        self.assertTrue(claude.Runtime('session-one', '/s.py').may_clean({'checkout': '/tmp/x'}))

    def test_repeated_failures_notify_once_and_recovery_notifies_once(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = claude.Runtime('session-one', '/s.py')
            with contextlib.redirect_stdout(io.StringIO()) as failing:
                for _ in range(3):
                    runtime.report(Path(directory), ['owner/repo#1: poll failed (OSError); retained for retry'])
            self.assertEqual(failing.getvalue().count('poll failed'), 1)
            self.assertEqual((Path(directory) / 'monitor.log').read_text().count('poll failed'), 3)
            with contextlib.redirect_stdout(io.StringIO()) as recovered:
                runtime.report(Path(directory), [])
            self.assertIn('monitor recovered', recovered.getvalue())


class CodexDeliveryTests(unittest.TestCase):
    def test_a_busy_desktop_refuses_delivery_without_queueing(self):
        runtime = codex.Runtime(THREAD, '/s.py', '/path/codex')
        with patch.object(codex.transport, 'desktop_is_idle', return_value=False), \
             patch.object(codex.transport, 'queue_message') as queue:
            self.assertFalse(runtime.deliver('batch'))
        queue.assert_not_called()

    def test_an_idle_desktop_queues_the_batch(self):
        runtime = codex.Runtime(THREAD, '/s.py', '/path/codex')
        with patch.object(codex.transport, 'desktop_is_idle', return_value=True), \
             patch.object(codex.transport, 'queue_message') as queue:
            self.assertTrue(runtime.deliver('batch'))
        queue.assert_called_once_with('/path/codex', THREAD, 'batch')

    def test_cleanup_waits_for_an_idle_desktop_when_a_checkout_is_bound(self):
        runtime = codex.Runtime(THREAD, '/s.py')
        with patch.object(codex.transport, 'desktop_is_idle', return_value=False):
            self.assertFalse(runtime.may_clean({'checkout': '/tmp/x'}))
            self.assertTrue(runtime.may_clean({'checkout': None}))

    def test_every_failure_is_reported_because_stdout_is_a_log_file(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = codex.Runtime(THREAD, '/s.py')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                for _ in range(3):
                    runtime.report(Path(directory), ['owner/repo#1: poll failed (OSError); retained for retry'])
            self.assertEqual(output.getvalue().count('poll failed'), 3)
            self.assertEqual((Path(directory) / 'monitor.log').read_text().count('poll failed'), 3)


class QueuedDeliveryTests(unittest.TestCase):
    def test_MQ_01_unavailable_desktop_does_not_block_queued_feedback(self):
        runtime = codex.Runtime(THREAD, '/s.py', '/codex', delivery='queued')
        with patch.object(codex.transport, 'desktop_is_idle', side_effect=TimeoutError), \
             patch.object(codex.transport, 'queue_message') as queue:
            self.assertTrue(runtime.deliver('feedback'))
        queue.assert_called_once_with('/codex', THREAD, 'feedback')

    def test_MQ_03_queued_mode_never_runs_background_cleanup(self):
        runtime = codex.Runtime(THREAD, '/s.py', '/codex', delivery='queued')
        with patch.object(codex.transport, 'desktop_is_idle', side_effect=TimeoutError):
            self.assertFalse(runtime.may_clean({'checkout': '/work'}))
            self.assertFalse(runtime.may_clean({'checkout': None}))

    def test_MQ_01_queued_startup_does_not_require_a_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = codex.Runtime(THREAD, '/s.py')
            store = codex.core.Store(directory, THREAD, 'owner/repo#1', runtime)
            with store.locked() as data:
                data['target'] = dict(repository='owner/repo', number=1)
            argv = ['s.py', '--thread', THREAD, '--pr', 'owner/repo#1',
                    '--state-dir', directory, 'run', '--delivery', 'queued', '--once']
            with patch.object(sys, 'argv', argv), \
                 patch.object(codex.shutil, 'which', return_value='/codex'), \
                 patch.object(codex.subprocess, 'run'), \
                 patch.object(codex.transport, 'desktop_is_idle', side_effect=TimeoutError), \
                 patch.object(codex.core, 'run') as run:
                codex.main()
            self.assertEqual(run.call_args.args[0].runtime.delivery_name, 'queued')


class MigrationTests(unittest.TestCase):
    def legacy(self, directory, **overrides):
        state = dict(schema=1, thread=THREAD, targets={'owner/repo#1': dict(
            repository='owner/repo', number=1, author='bot', checkout=None, head_branch='w',
            head_repository='owner/repo', cleanup=None, cleanup_result=None, events={}, stopped=False,
            terminal=None, ci=None, ci_version=None)}, batch=None)
        state.update(overrides)
        (Path(directory) / 'state.json').write_text(json.dumps(state))
        return Path(directory)

    def store(self, directory):
        return codex.core.Store(directory, THREAD, 'owner/repo#1', codex.Runtime(THREAD, '/s.py'))

    def test_migration_moves_the_target_and_preserves_the_source(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            self.legacy(source)
            subject = self.store(destination)
            codex.migrate_legacy(subject, source)
            self.assertEqual(subject.read()['target']['number'], 1)
            self.assertIn('owner/repo#1', json.loads((Path(source) / 'state.json').read_text())['targets'])

    def test_migration_refuses_an_unacknowledged_legacy_batch(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            self.legacy(source, batch={'token': 'x', 'events': {}})
            with self.assertRaises(ValueError):
                codex.migrate_legacy(self.store(destination), source)

    def test_migration_refuses_delivered_events(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            path = self.legacy(source)
            state = json.loads((path / 'state.json').read_text())
            state['targets']['owner/repo#1']['events'] = {'k': {'status': 'delivered'}}
            (path / 'state.json').write_text(json.dumps(state))
            with self.assertRaises(ValueError):
                codex.migrate_legacy(self.store(destination), source)

    def test_migration_refuses_to_overwrite_existing_destination_state(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            self.legacy(source)
            subject = self.store(destination)
            codex.migrate_legacy(subject, source)
            with self.assertRaises(ValueError):
                codex.migrate_legacy(subject, source)

    def test_registration_is_guarded_while_legacy_state_still_holds_the_pull_request(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as destination:
            self.legacy(source)
            with self.assertRaises(ValueError):
                codex.guard_legacy(self.store(destination), source)


class EntrypointTests(unittest.TestCase):
    def test_claude_refuses_a_malformed_session(self):
        with tempfile.TemporaryDirectory() as directory:
            argv = ['s.py', '--session', 'has space', '--pr', 'owner/repo#1', '--state-dir', directory, 'status']
            with patch.object(sys, 'argv', argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                claude.main()

    def test_codex_refuses_a_malformed_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            argv = ['s.py', '--thread', 'not-a-uuid', '--pr', 'owner/repo#1', '--state-dir', directory, 'status']
            with patch.object(sys, 'argv', argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                codex.main()

    def test_both_refuse_a_malformed_pull_request_target(self):
        for module, identity in ((claude, ['--session', 'session-one']), (codex, ['--thread', THREAD])):
            with tempfile.TemporaryDirectory() as directory:
                argv = ['s.py', *identity, '--pr', 'owner/repo', '--state-dir', directory, 'status']
                with patch.object(sys, 'argv', argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                    module.main()


if __name__ == '__main__':
    unittest.main()


class ShippedStateCompatibilityTests(unittest.TestCase):
    def shipped(self, directory, keys, identity, name):
        owner_key, target_key = keys
        (Path(directory) / 'state.json').write_text(json.dumps({
            'schema': 2, owner_key: identity, target_key: name,
            'target': dict(repository='owner/repo', number=1, author='bot', checkout=None, head_branch='w',
                           head_repository='owner/repo', cleanup=None, cleanup_result=None,
                           events={'k': dict(key='k', kind='conversation', id=1, url='u', status='delivered')},
                           stopped=False, terminal=None, ci=None, ci_version=None),
            'batch': {'token': 'live-token', 'events': ['k'], 'delivery': 'x'}}))
        return Path(directory)

    def test_a_shipped_claude_state_stays_readable_with_its_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            self.shipped(directory, ('session', 'name'), 'session-one', 'owner/repo#1')
            store = claude.core.Store(directory, 'session-one', 'owner/repo#1',
                                      claude.Runtime('session-one', '/s.py'))
            data = store.read()
        self.assertEqual(data['batch']['token'], 'live-token')
        self.assertEqual(data['target']['events']['k']['status'], 'delivered')

    def test_a_shipped_codex_state_stays_readable_with_its_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            self.shipped(directory, ('thread', 'pr'), THREAD, 'owner/repo#1')
            store = codex.core.Store(directory, THREAD, 'owner/repo#1', codex.Runtime(THREAD, '/s.py'))
            data = store.read()
        self.assertEqual(data['batch']['token'], 'live-token')

    def test_neither_runtime_reads_the_other_state_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            self.shipped(directory, ('thread', 'pr'), 'session-one', 'owner/repo#1')
            store = claude.core.Store(directory, 'session-one', 'owner/repo#1',
                                      claude.Runtime('session-one', '/s.py'))
            with self.assertRaises(ValueError):
                store.read()

    def test_the_shipped_default_directories_are_unchanged(self):
        self.assertEqual(claude.core.readable_slug('owner/repo#1'), 'owner__repo__1')
        self.assertTrue(codex.core.hashed_slug('owner/repo#1').startswith('pr-'))
