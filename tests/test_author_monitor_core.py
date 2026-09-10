import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/monitor/scripts'
spec = importlib.util.spec_from_file_location('author_monitor_core', ROOT / 'author_monitor_core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

NAME = 'owner/repo#1'


class FakeRuntime:
    role = 'bot'
    marker = 'From Test 🤖'
    delivery_name = 'test'
    state_keys = ('identity', 'name')

    def __init__(self, accept=True, clean=True):
        self.script = '/scripts/monitor.py'
        self.identity_arguments = ['--identity', 'identity-one']
        self.delivered = []
        self.reported = []
        self.accept = accept
        self.clean = clean

    def deliver(self, message):
        if not self.accept:
            return False
        self.delivered.append(message)
        return True

    def may_clean(self, target):
        return self.clean

    def report(self, root, failures):
        self.reported.append(list(failures))


def result(*events, terminal=None, head='a', ci='pending', version='pending'):
    return dict(events=list(events), terminal=terminal, head=head, ci=ci, ci_version=version, url='https://example/pr')


def notice(identifier):
    return core.event('conversation', identifier, 'version1', 'https://example/comment')


def ending(outcome='merged'):
    return core.event('terminal', 1, [outcome, None, 'now'], 'https://example/pr', outcome=outcome, head='a')


@contextlib.contextmanager
def store(name=NAME, identity='identity-one', runtime=None):
    with tempfile.TemporaryDirectory() as directory:
        yield core.Store(directory, identity, name, runtime or FakeRuntime())


def enrol(subject, checkout=None):
    repository, number = core.parse_target(subject.name)
    with subject.locked() as data:
        data['target'] = dict(repository=repository, number=number, author='bot', checkout=checkout,
                              head_branch='work', head_repository=repository, cleanup=dict(owned=bool(checkout)),
                              cleanup_result=None, events={}, stopped=False, terminal=None, ci=None, ci_version=None)
    return subject


class DecisionTests(unittest.TestCase):
    def test_a_acknowledging_the_last_terminal_event_stops_the_monitor(self):
        with store() as subject:
            enrol(subject).apply(result(notice(1), ending('closed'), terminal='closed'))
            subject.deliver()
            self.assertFalse(subject.read()['target']['stopped'])
            subject.acknowledge(subject.read()['batch']['token'])
            self.assertTrue(subject.read()['target']['stopped'])

    def test_b_a_stored_target_that_does_not_match_the_bound_pull_request_is_refused(self):
        with store() as subject:
            enrol(subject)
            with subject.locked() as data:
                data['target']['number'] = 999
            with self.assertRaises(ValueError) as failure:
                subject.read()
        self.assertIn('stored target does not match', str(failure.exception))

    def test_c_only_https_github_pull_request_urls_are_accepted(self):
        self.assertEqual(core.parse_target('https://github.com/Owner/Repo/pull/12'), ('owner/repo', 12))
        self.assertEqual(core.parse_target('Owner/Repo#12'), ('owner/repo', 12))
        for bad in ('http://github.com/o/r/pull/1', 'https://example.com/o/r/pull/1', 'owner/repo'):
            with self.assertRaises(ValueError):
                core.parse_target(bad)

    def test_d_diagnostics_are_handed_to_the_runtime_rather_than_printed_by_the_core(self):
        runtime = FakeRuntime()
        with store(runtime=runtime) as subject:
            enrol(subject)
            with patch.object(core, 'snapshot', side_effect=RuntimeError('offline')), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                core.poll(subject)
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(len(runtime.reported), 1)
            self.assertIn('poll failed', runtime.reported[0][0])

    def test_e_running_without_a_registered_pull_request_raises(self):
        with store() as subject:
            with self.assertRaises(ValueError) as failure:
                core.poll(subject)
        self.assertIn('register this pull request', str(failure.exception))

    def test_f_a_second_runner_exits_with_an_explanation(self):
        with store() as subject:
            enrol(subject)
            with core.runner_lock(subject):
                rival = core.Store(subject.root, subject.identity, subject.name, FakeRuntime())
                with self.assertRaises(SystemExit) as refusal:
                    with core.runner_lock(rival):
                        pass
        self.assertIn('already followed by a live monitor', str(refusal.exception))

    def test_g_event_rows_carry_no_repeated_pull_request_name(self):
        with store() as subject:
            runtime = subject.runtime
            enrol(subject).apply(result(notice(1), notice(2)))
            subject.deliver()
            body = runtime.delivered[0]
            rows = [line for line in body.splitlines() if line.startswith('conversation id=')]
            self.assertEqual(len(rows), 2)
            self.assertEqual(body.count(NAME), 2)

    def test_h_the_acknowledgement_line_precedes_the_event_rows(self):
        with store() as subject:
            runtime = subject.runtime
            enrol(subject).apply(result(*[notice(i) for i in range(3)]))
            subject.deliver()
            lines = runtime.delivered[0].splitlines()
            token = subject.read()['batch']['token']
            ack = [i for i, line in enumerate(lines) if 'ack --token ' + token in line][0]
            rows = [i for i, line in enumerate(lines) if line.startswith('conversation id=')]
            self.assertLess(ack, min(rows))

    def test_i_a_manual_claim_stores_its_keys_as_a_list(self):
        with store() as subject:
            enrol(subject).apply(result(notice(1), notice(2)))
            keys = tuple(subject.read()['target']['events'])[:1]
            subject.claim(keys)
            self.assertEqual(subject.read()['batch']['events'], list(keys))


class RoleTests(unittest.TestCase):
    def test_a_role_prefixes_the_role_tool_and_a_missing_tool_is_fatal(self):
        with patch.object(core.shutil, 'which', return_value='/path/gh_as'):
            self.assertEqual(core.gh_command('bot'), ['/path/gh_as', 'bot'])
        with patch.object(core.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError):
                core.gh_command('bot')

    def test_the_role_reaches_github_reads(self):
        with patch.object(core, 'gh_command', return_value=['gh_as', 'bot']), \
             patch.object(core.subprocess, 'run') as run:
            run.return_value.stdout = json.dumps([])
            core.gh_json('endpoint', 'bot')
        self.assertEqual(run.call_args[0][0][:3], ['gh_as', 'bot', 'api'])

    def test_run_refuses_before_the_banner_when_the_role_tool_is_missing(self):
        with store() as subject:
            enrol(subject)
            with patch.object(core.shutil, 'which', return_value=None), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(RuntimeError):
                    core.run(subject, 45, once=True)
            self.assertEqual(output.getvalue(), '')
            self.assertFalse((subject.root / 'run.pid').exists())


class DeliveryTests(unittest.TestCase):
    def test_a_refused_delivery_leaves_every_event_pending(self):
        runtime = FakeRuntime(accept=False)
        with store(runtime=runtime) as subject:
            enrol(subject).apply(result(notice(1)))
            self.assertFalse(subject.deliver())
            self.assertEqual([e['status'] for e in subject.read()['target']['events'].values()], ['pending'])
            self.assertIsNone(subject.read()['batch'])

    def test_no_second_batch_while_one_is_outstanding(self):
        with store() as subject:
            enrol(subject).apply(result(notice(1)))
            self.assertTrue(subject.deliver())
            subject.apply(result(notice(1), notice(2)))
            self.assertFalse(subject.deliver())
            self.assertEqual(sorted(e['status'] for e in subject.read()['target']['events'].values()), ['delivered', 'pending'])

    def test_the_batch_is_bounded_and_the_remainder_stays_pending(self):
        with store() as subject:
            enrol(subject).apply(result(*[notice(i) for i in range(core.BATCH_LIMIT + 5)]))
            subject.deliver()
            self.assertEqual(len(subject.read()['batch']['events']), core.BATCH_LIMIT)

    def test_the_acknowledgement_command_carries_the_runtime_identity(self):
        with store() as subject:
            enrol(subject).apply(result(notice(1)))
            subject.deliver()
            token = subject.read()['batch']['token']
            command = shlex.split(subject.runtime.delivered[0].split('Run: ', 1)[1].split('\n', 1)[0])
        self.assertEqual(command[command.index('--identity') + 1], 'identity-one')
        self.assertEqual(command[command.index('--pr') + 1], NAME)
        self.assertEqual(command[command.index('--token') + 1], token)


class TerminalTests(unittest.TestCase):
    def test_successful_cleanup_settles_every_event_and_stops(self):
        with store() as subject:
            enrol(subject, checkout='/tmp/owned')
            with patch.object(core, 'cleanup_target', return_value=dict(status='cleaned')):
                subject.apply(result(notice(1), ending(), terminal='merged'))
            target = subject.read()['target']
            self.assertTrue(target['stopped'])
            self.assertEqual({e['status'] for e in target['events'].values()}, {'settled'})

    def test_a_runtime_that_refuses_cleanup_defers_it(self):
        runtime = FakeRuntime(clean=False)
        with store(runtime=runtime) as subject:
            enrol(subject, checkout='/tmp/owned')
            with patch.object(core, 'cleanup_target') as helper:
                subject.apply(result(ending(), terminal='merged'))
            helper.assert_not_called()
            self.assertIsNone(subject.read()['target']['cleanup_result'])

    def test_preserved_cleanup_keeps_the_terminal_event_pending_with_its_reason(self):
        with store() as subject:
            enrol(subject, checkout='/tmp/owned')
            with patch.object(core, 'cleanup_target', return_value=dict(status='preserved', reason='dirty')):
                subject.apply(result(ending(), terminal='merged'))
            terminal = [e for e in subject.read()['target']['events'].values() if e['kind'] == 'terminal'][0]
            self.assertEqual(terminal['status'], 'pending')
            self.assertEqual(terminal['cleanup']['reason'], 'dirty')

    def test_a_raising_cleanup_helper_is_recorded_once_and_not_retried(self):
        with store() as subject:
            enrol(subject, checkout='/tmp/owned')
            with patch.object(core, 'cleanup_target', side_effect=OSError('busy')) as helper:
                subject.apply(result(ending(), terminal='merged'))
                subject.apply(result(ending(), terminal='merged'))
            self.assertEqual(helper.call_count, 1)
            self.assertEqual(subject.read()['target']['cleanup_result']['status'], 'error')

    def test_completion_refuses_a_pull_request_that_is_not_merged(self):
        with store() as subject:
            enrol(subject, checkout='/tmp/owned')
            with patch.object(core, 'snapshot', return_value=result(terminal=None)):
                with self.assertRaises(ValueError):
                    subject.complete()

    def test_completion_refuses_while_a_batch_is_unacknowledged(self):
        with store() as subject:
            enrol(subject, checkout='/tmp/owned').apply(result(notice(1)))
            subject.deliver()
            with self.assertRaises(ValueError):
                subject.complete()


class IdentityTests(unittest.TestCase):
    def test_state_from_another_owner_or_pull_request_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            enrol(core.Store(directory, 'identity-one', NAME, FakeRuntime()))
            with self.assertRaises(ValueError):
                core.Store(directory, 'identity-two', NAME, FakeRuntime()).read()
            with self.assertRaises(ValueError):
                core.Store(directory, 'identity-one', 'owner/repo#2', FakeRuntime()).read()

    def test_each_pull_request_gets_its_own_directory_under_either_naming(self):
        self.assertNotEqual(core.hashed_slug('owner/repo#1'), core.hashed_slug('owner/repo#2'))
        self.assertTrue(core.hashed_slug('owner/repo#1').startswith('pr-'))
        self.assertEqual(core.readable_slug('owner/repo#1'), 'owner__repo__1')
        self.assertNotEqual(core.readable_slug('owner/repo#1'), core.readable_slug('owner/repo#2'))

    def test_self_echo_needs_the_fixed_author_and_a_robot_marker(self):
        for user, body, ignored in [('BOT', 'From Claude 🤖', True), ('bot', '🤖', True),
                                    ('bot', 'human', False), ('reviewer', 'From Codex 🤖', False)]:
            self.assertEqual(core.self_echo(dict(user={'login': user}, body=body), 'Bot'), ignored)

    def test_registration_is_idempotent_and_the_author_is_immutable(self):
        pr = dict(user={'login': 'bot'}, head={'sha': 'head', 'ref': 'work', 'repo': {'full_name': 'owner/repo'}})
        with store() as subject, patch.object(core, 'gh_json', return_value=pr):
            self.assertTrue(subject.register())
            self.assertFalse(subject.register())
            with self.assertRaises(ValueError):
                subject.register(author='someone-else')


class ContinuousIntegrationTests(unittest.TestCase):
    def test_first_all_green_result_is_quiet_but_a_failure_is_an_event(self):
        with store() as subject:
            enrol(subject).apply(result(ci='pass', version='green'))
            self.assertEqual(subject.read()['target']['events'], {})
            subject.apply(result(ci='fail', version='red'))
            self.assertEqual([e['kind'] for e in subject.read()['target']['events'].values()], ['ci'])

    def test_rollup_collapses_to_one_verdict(self):
        self.assertEqual(core.checks_state([]), 'none')
        self.assertEqual(core.checks_state([{'status': 'IN_PROGRESS'}, {'status': 'COMPLETED', 'conclusion': 'FAILURE'}]), 'fail')
        self.assertEqual(core.checks_state([{'status': 'COMPLETED', 'conclusion': 'SKIPPED'}, {'status': 'QUEUED'}]), 'pending')


if __name__ == '__main__':
    unittest.main()


class ForegroundCompletionTests(unittest.TestCase):
    def test_MQ_03_merged_feedback_can_queue_without_background_cleanup(self):
        runtime = FakeRuntime(clean=False)
        runtime.foreground_cleanup = True
        with store(runtime=runtime) as subject:
            enrol(subject, checkout='/work')
            with patch.object(core, 'cleanup_target') as cleanup:
                subject.apply(result(ending(), terminal='merged'))
                self.assertTrue(subject.deliver())
            cleanup.assert_not_called()
            self.assertIsNone(subject.read()['target']['cleanup_result'])
            self.assertIn('complete', runtime.delivered[0])
            self.assertIsNotNone(subject.read()['batch'])

    def test_MQ_02_queue_failure_leaves_events_pending_for_retry(self):
        runtime = FakeRuntime()
        with store(runtime=runtime) as subject:
            enrol(subject).apply(result(notice(1)))
            with patch.object(runtime, 'deliver', side_effect=OSError('queue unavailable')):
                with self.assertRaises(OSError):
                    subject.deliver()
            self.assertIsNone(subject.read()['batch'])
            self.assertEqual(next(iter(subject.read()['target']['events'].values()))['status'], 'pending')
            self.assertTrue(subject.deliver())
            self.assertFalse(subject.deliver())
            self.assertEqual(len(runtime.delivered), 1)


class QueuedCompletionDrainTests(unittest.TestCase):
    def test_MQ_02_completion_waits_for_all_pending_feedback(self):
        runtime = FakeRuntime(clean=False)
        runtime.foreground_cleanup = True
        with store(runtime=runtime) as subject:
            enrol(subject, checkout='/work')
            current = result(*(notice(i) for i in range(core.BATCH_LIMIT + 1)), ending(), terminal='merged')
            subject.apply(current)
            subject.deliver()
            self.assertNotIn('run the protected foreground completion', runtime.delivered[0])
            subject.acknowledge(subject.read()['batch']['token'])
            with patch.object(core, 'snapshot', return_value=current), patch.object(core, 'cleanup_target') as cleanup:
                outcome = subject.complete()
            self.assertEqual(outcome['status'], 'pending-feedback')
            cleanup.assert_not_called()
            self.assertTrue(subject.deliver())
            self.assertIn('run the protected foreground completion', runtime.delivered[-1])

    def test_MQ_02_new_feedback_found_at_completion_is_retained(self):
        runtime = FakeRuntime(clean=False)
        runtime.foreground_cleanup = True
        with store(runtime=runtime) as subject:
            enrol(subject, checkout='/work').apply(result(ending(), terminal='merged'))
            subject.deliver()
            subject.acknowledge(subject.read()['batch']['token'])
            with patch.object(core, 'snapshot', return_value=result(ending(), notice(9), terminal='merged')), \
                 patch.object(core, 'cleanup_target') as cleanup:
                self.assertEqual(subject.complete()['status'], 'pending-feedback')
            cleanup.assert_not_called()
            self.assertFalse(subject.read()['target']['stopped'])
            self.assertTrue(subject.deliver())
