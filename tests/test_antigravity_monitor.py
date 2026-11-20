import contextlib
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/alex-coding/skills/monitor/scripts'
PROJECT_SCRIPTS = ROOT / 'plugins/alex-coding/skills/project-monitor/scripts'


def load(name, directory=SCRIPTS):
    spec = importlib.util.spec_from_file_location(name, directory / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


antigravity = load('antigravity_pr_monitor')
reply = load('antigravity_reply')
cleanup = load('postmerge_cleanup')
project_monitor = load('project_pr_monitor', PROJECT_SCRIPTS)
SESSION = 'a08f0871-e684-4b6f-bda5-d2e95d5f9f76'
PR = 'owner/repo#42'


def register_disposable(store, checkout='/tmp/task-wt'):
    with store.locked() as data:
        data['target'] = dict(
            repository='owner/repo', number=42, author='bot', checkout=checkout,
            head_branch='feat/demo', head_repository='owner/repo',
            cleanup={'owned': True, 'lifecycle': 'disposable-v1'},
            cleanup_result=None, events={}, stopped=False, terminal=None, ci=None, ci_version=None,
        )


def write_runner_state(runner, **overrides):
    data = {
        'schema': 1, 'pr': PR, 'phase': 'reviewing',
        'author_delivery': {'runtime': 'antigravity', 'session': SESSION, 'remote': None, 'slot': None},
    }
    data.update(overrides)
    (runner / 'state.json').write_text(json.dumps(data))


def make_snapshot(events, terminal=None, head='a' * 40, ci='pass', summary=None):
    return dict(
        events=list(events), terminal=terminal, head=head, ci=ci, ci_version=head + ':' + ci,
        url='https://github.com/owner/repo/pull/42', pr={},
        summary=summary or dict(head=head, ci=ci, failing=[], reviews=[], threads=[]),
    )


class OutboxDeliveryTests(unittest.TestCase):
    def test_deliver_appends_monotonic_jsonl_records_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            self.assertTrue(runtime.deliver('first state'))
            self.assertTrue(runtime.deliver('second state\nwith newline'))
            records = antigravity.read_outbox(root)
            self.assertEqual([item['seq'] for item in records], [1, 2])
            self.assertEqual(records[0]['text'], 'first state')
            self.assertEqual(records[1]['text'], 'second state\nwith newline')
            self.assertTrue(records[0]['created_at'].endswith('Z'))

    def test_truncated_outbox_tail_recovers_on_next_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = json.dumps({'seq': 1, 'created_at': '2026-11-20T00:00:00Z', 'text': 'first'})
            (root / 'outbox.jsonl').write_text(valid + '\n{"seq": 2, "text": "truncated')
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            self.assertTrue(runtime.deliver('retried feedback'))
            records = antigravity.read_outbox(root)
            self.assertEqual([item['seq'] for item in records], [1, 2])
            self.assertEqual(records[1]['text'], 'retried feedback')

    def test_may_clean_is_true_only_for_disposable_worktrees(self):
        runtime = antigravity.Runtime(SESSION, antigravity.__file__)
        self.assertTrue(runtime.may_clean({'cleanup': {'lifecycle': 'disposable-v1'}}))
        self.assertFalse(runtime.may_clean({'cleanup': {'owned': True}}))
        self.assertFalse(runtime.may_clean({'checkout': '/tmp/x'}))

    def test_self_echo_ignores_antigravity_marker_for_fixed_author_only(self):
        self.assertTrue(antigravity.core.self_echo(
            {'user': {'login': 'Cunqi-Bot'}, 'body': 'Reason\n\nFrom Antigravity 🤖'}, 'cunqi-bot'))
        self.assertFalse(antigravity.core.self_echo(
            {'user': {'login': 'cunqi-bot'}, 'body': 'Human reply without marker'}, 'cunqi-bot'))
        self.assertFalse(antigravity.core.self_echo(
            {'user': {'login': 'reviewer'}, 'body': 'Review\n\nFrom Antigravity 🤖'}, 'cunqi-bot'))


class WaitSubcommandTests(unittest.TestCase):
    def test_coalescing_preserves_earlier_human_conversation_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'author'
            runner = Path(directory) / 'runner'
            root.mkdir()
            runner.mkdir()
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            store = antigravity.core.Store(root, SESSION, PR, runtime)
            register_disposable(store)
            write_runner_state(runner)
            comment = antigravity.core.event(
                'conversation', 99, ['t1', None, None, 'Please rename this flag'],
                'https://github.com/owner/repo/pull/42#issuecomment-99', user='alex',
            )
            store.apply(make_snapshot([comment], head='1' * 40, ci='pending'))
            self.assertTrue(store.deliver())
            store.apply(make_snapshot([comment], head='1' * 40, ci='fail',
                                      summary=dict(head='1' * 40, ci='fail', failing=['tests'], reviews=[], threads=[])))
            self.assertTrue(store.deliver())
            code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code, 0)
            self.assertIn('2 outbox updates coalesced (seq 1..2)', output)
            self.assertIn('https://github.com/owner/repo/pull/42#issuecomment-99', output)
            self.assertIn('conversation id=99 user=alex', output)
            self.assertIn('["tests"]', output)
            self.assertIn('wait --runner-dir', output)
            self.assertEqual(antigravity.read_cursor(root), 2)

    def test_stale_feedback_is_not_marked_terminal_before_terminal_record_is_enqueued(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            store = antigravity.core.Store(root, SESSION, PR, runtime)
            register_disposable(store)
            write_runner_state(runner)
            review_event = antigravity.core.event(
                'review', 101, ['t1', 't1', 'CHANGES_REQUESTED', 'fix'],
                'https://github.com/owner/repo/pull/42#pullrequestreview-101',
                user='reviewer', review_state='CHANGES_REQUESTED',
            )
            store.apply(make_snapshot([review_event], head='1' * 40, ci='pass'))
            self.assertTrue(store.deliver())

            terminal_event = antigravity.core.event(
                'terminal', 42, ['merged', 't2', 't2'],
                'https://github.com/owner/repo/pull/42', outcome='merged', head='2' * 40,
            )
            cleaned = {'status': 'cleaned', 'reason': 'Default synchronized and task worktree disposed'}
            with patch.object(antigravity.core, 'cleanup_target', return_value=cleaned):
                store.apply(make_snapshot([review_event, terminal_event], terminal='merged', head='2' * 40, ci='pass'))

            code, first_output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code, 0)
            self.assertIn('pullrequestreview-101', first_output)
            self.assertIn('resume waiting', first_output)
            self.assertNotIn('no further waiting is needed', first_output)
            self.assertEqual(antigravity.read_cursor(root), 1)

            self.assertTrue(store.deliver())
            code, second_output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code, 0)
            self.assertIn('"status": "cleaned"', second_output)
            self.assertIn('no further waiting is needed', second_output)
            self.assertNotIn('resume waiting', second_output)
            self.assertEqual(antigravity.read_cursor(root), 2)

    def test_live_wake_on_feedback_then_merged_disposable_cleanup_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            store = antigravity.core.Store(root, SESSION, PR, runtime)
            register_disposable(store)
            write_runner_state(runner)
            lock_handle = (runner / 'run.lock').open('a')
            fcntl.flock(lock_handle, fcntl.LOCK_EX)
            self.addCleanup(lock_handle.close)

            review_event = antigravity.core.event(
                'review', 101, ['2026-11-20T00:00:00Z', '2026-11-20T00:00:00Z', 'CHANGES_REQUESTED', 'fix bug'],
                'https://github.com/owner/repo/pull/42#pullrequestreview-101',
                user='reviewer', review_state='CHANGES_REQUESTED',
            )
            feedback_snap = make_snapshot(
                [review_event], head='1' * 40, ci='fail',
                summary=dict(
                    head='1' * 40, ci='fail', failing=['unit-tests'],
                    reviews=[{'user': 'reviewer', 'state': 'CHANGES_REQUESTED', 'url': review_event['url']}],
                    threads=[],
                ),
            )

            def push_feedback():
                time.sleep(0.2)
                store.apply(feedback_snap)
                store.deliver()

            thread = threading.Thread(target=push_feedback)
            thread.start()
            code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1, timeout=5.0)
            thread.join(timeout=5)
            self.assertEqual(code, 0)
            self.assertIn('CHANGES_REQUESTED', output)
            self.assertIn('unit-tests', output)
            self.assertIn('wait --runner-dir', output)
            self.assertEqual(antigravity.read_cursor(root), 1)

            cleanup_outcome = {
                'status': 'cleaned',
                'reason': 'Default synchronized and task worktree disposed',
                'actions': ['Reset default checkout to the fetched remote commit', 'Removed disposable worktree including all residual files'],
                'sync': {'status': 'synced', 'commit': '9' * 40},
                'cleanup': {'status': 'cleaned'},
            }
            terminal_event = antigravity.core.event(
                'terminal', 42, ['merged', '2026-11-20T00:05:00Z', '2026-11-20T00:05:00Z'],
                'https://github.com/owner/repo/pull/42', outcome='merged', head='2' * 40,
            )
            merged_snap = make_snapshot([review_event, terminal_event], terminal='merged', head='2' * 40, ci='pass')

            def merge_and_clean():
                time.sleep(0.2)
                with patch.object(antigravity.core, 'cleanup_target', return_value=cleanup_outcome):
                    store.apply(merged_snap)
                    self.assertTrue(store.deliver())
                self.assertTrue(store.read()['target']['stopped'])
                write_runner_state(runner, phase='merged')
                fcntl.flock(lock_handle, fcntl.LOCK_UN)

            thread = threading.Thread(target=merge_and_clean)
            thread.start()
            code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1, timeout=5.0)
            thread.join(timeout=5)
            self.assertEqual(code, 0)
            self.assertIn('"status": "cleaned"', output)
            self.assertIn('9' * 40, output)
            self.assertIn('no further waiting is needed', output)
            self.assertNotIn('resume waiting', output)
            self.assertEqual(antigravity.read_cursor(root), 2)

    def test_non_retryable_partial_cleanup_stops_runner_and_exits_2_with_result(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            store = antigravity.core.Store(root, SESSION, PR, runtime)
            register_disposable(store)
            write_runner_state(runner, phase='merged')
            terminal_event = antigravity.core.event(
                'terminal', 42, ['merged', 't', 't'],
                'https://github.com/owner/repo/pull/42', outcome='merged', head='a' * 40,
            )
            partial = {
                'status': 'partial',
                'reason': 'Unrelated Git index lock preserved',
                'retryable': False,
                'sync': {'status': 'failed', 'retryable': False},
                'cleanup': {'status': 'cleaned'},
            }
            with patch.object(antigravity.core, 'cleanup_target', return_value=partial):
                store.apply(make_snapshot([terminal_event], terminal='merged'))
            self.assertTrue(store.deliver())
            self.assertTrue(store.read()['target']['stopped'])
            self.assertTrue(antigravity.core.runner_done(store, store.read()))

            code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code, 2)
            self.assertIn('"status": "partial"', output)
            self.assertIn('"retryable": false', output)
            self.assertNotIn('resume waiting', output)

            with (runner / 'run.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                code2, output2 = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1, timeout=2.0)
            self.assertEqual(code2, 2)
            self.assertIn('"status": "partial"', output2)

    def test_retryable_partial_cleanup_keeps_waiting_until_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            store = antigravity.core.Store(root, SESSION, PR, runtime)
            register_disposable(store)
            write_runner_state(runner, phase='merged')
            terminal_event = antigravity.core.event(
                'terminal', 42, ['merged', 't', 't'],
                'https://github.com/owner/repo/pull/42', outcome='merged', head='a' * 40,
            )
            retryable = {'status': 'partial', 'reason': 'Another lifecycle operation holds the repository lock', 'retryable': True}
            cleaned = {'status': 'cleaned', 'reason': 'Default synchronized and task worktree disposed'}
            with patch.object(antigravity.core, 'cleanup_target', return_value=retryable):
                store.apply(make_snapshot([terminal_event], terminal='merged'))
            self.assertFalse(store.deliver())
            self.assertFalse(antigravity.core.runner_done(store, store.read()))

            lock_handle = (runner / 'run.lock').open('a')
            fcntl.flock(lock_handle, fcntl.LOCK_EX)
            self.addCleanup(lock_handle.close)

            def finish_retry():
                time.sleep(0.25)
                with patch.object(antigravity.core, 'cleanup_target', return_value=cleaned):
                    store.apply(make_snapshot([terminal_event], terminal='merged'))
                self.assertTrue(store.deliver())
                fcntl.flock(lock_handle, fcntl.LOCK_UN)

            thread = threading.Thread(target=finish_retry)
            thread.start()
            code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1, timeout=5.0)
            thread.join(timeout=5)
            self.assertEqual(code, 0)
            self.assertIn('"status": "cleaned"', output)
            self.assertIn('no further waiting is needed', output)

    def test_preserved_merged_cleanup_exits_2_with_actual_cleanup_result(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            store = antigravity.core.Store(root, SESSION, PR, runtime)
            register_disposable(store)
            write_runner_state(runner, phase='merged')
            terminal_event = antigravity.core.event(
                'terminal', 42, ['merged', 't', 't'],
                'https://github.com/owner/repo/pull/42', outcome='merged', head='a' * 40,
            )
            preserved = {'status': 'preserved', 'reason': 'Local branch has work beyond the final PR head'}
            with patch.object(antigravity.core, 'cleanup_target', return_value=preserved):
                store.apply(make_snapshot([terminal_event], terminal='merged'))
            self.assertTrue(store.deliver())

            code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code, 2)
            self.assertIn('"status": "preserved"', output)
            self.assertIn('Local branch has work beyond the final PR head', output)

            code2, output2 = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code2, 2)
            self.assertIn('"status": "preserved"', output2)

    def test_stale_session_cannot_consume_outbox_or_advance_cursor_after_takeover(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            runtime = antigravity.Runtime('session-new', antigravity.__file__, root)
            store = antigravity.core.Store(root, 'session-new', PR, runtime)
            register_disposable(store)
            write_runner_state(runner, author_delivery={'runtime': 'antigravity', 'session': 'session-new', 'remote': None, 'slot': None})
            antigravity.append_outbox(root, 'feedback for session-new')

            code, output = antigravity.wait_for_event(root, 'session-old', PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code, 2)
            self.assertIn('ownership-lost', output)
            self.assertEqual(antigravity.read_cursor(root), 0)

            code_new, output_new = antigravity.wait_for_event(root, 'session-new', PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code_new, 0)
            self.assertIn('feedback for session-new', output_new)
            self.assertEqual(antigravity.read_cursor(root), 1)

    def test_duplicate_concurrent_wait_fails_fast(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            write_runner_state(runner)
            with (runner / 'run.lock').open('a') as run_lock:
                fcntl.flock(run_lock, fcntl.LOCK_EX)
                with subprocess.Popen(
                    [sys.executable, str(SCRIPTS / 'antigravity_pr_monitor.py'),
                     '--session', SESSION, '--pr', PR, '--state-dir', str(root),
                     'wait', '--runner-dir', str(runner), '--interval', '0.1', '--timeout', '5'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                ) as first:
                    try:
                        deadline = time.monotonic() + 3
                        while not antigravity.lock_held(root / 'wait.lock') and time.monotonic() < deadline:
                            time.sleep(0.05)
                        self.assertTrue(antigravity.lock_held(root / 'wait.lock'))
                        duplicate = subprocess.run(
                            [sys.executable, str(SCRIPTS / 'antigravity_pr_monitor.py'),
                             '--session', SESSION, '--pr', PR, '--state-dir', str(root),
                             'wait', '--runner-dir', str(runner), '--interval', '0.1'],
                            capture_output=True, text=True, timeout=5,
                        )
                        self.assertNotEqual(duplicate.returncode, 0)
                        self.assertIn('already has an active waiter', duplicate.stderr)
                    finally:
                        first.terminate()
                        first.wait(timeout=5)

    def test_stopped_non_terminal_runner_exits_2_with_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            write_runner_state(
                runner, phase='error', last_error='RuntimeError',
                last_transport_error='TimeoutError', rounds=1, round_limit=3,
            )
            code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code, 2)
            self.assertIn('runner-inactive', output)
            self.assertIn('TimeoutError', output)
            self.assertIn('RuntimeError', output)

    def test_errored_live_runner_wakes_immediately_with_exit_2(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            write_runner_state(runner, phase='error', last_transport_error='CalledProcessError')
            with (runner / 'run.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1, timeout=5.0)
            self.assertEqual(code, 2)
            self.assertIn('runner-inactive', output)
            self.assertIn('CalledProcessError', output)

    def test_stopped_terminal_runner_without_unread_prints_terminal_summary_and_exits_0(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            store = antigravity.core.Store(root, SESSION, PR, antigravity.Runtime(SESSION, antigravity.__file__, root))
            with store.locked() as data:
                data['target'] = dict(
                    repository='owner/repo', number=42, author='bot', terminal='merged', stopped=True,
                    cleanup={'owned': True, 'lifecycle': 'disposable-v1'},
                    cleanup_result={'status': 'cleaned', 'reason': 'Default synchronized and task worktree disposed'},
                    events={},
                )
            write_runner_state(runner, phase='merged')
            code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1)
            self.assertEqual(code, 0)
            self.assertIn('reached terminal state: merged', output)
            self.assertIn('"status": "cleaned"', output)

    def test_timeout_exits_3_when_runner_stays_live_without_events(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / 'runner'
            root = runner / 'author'
            root.mkdir(parents=True)
            write_runner_state(runner, phase='reviewing')
            with (runner / 'run.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                code, output = antigravity.wait_for_event(root, SESSION, PR, runner_dir=runner, interval=0.1, timeout=0.25)
            self.assertEqual(code, 3)
            self.assertIn('timed out', output)
            self.assertIn('wait --runner-dir', output)

    def test_non_disposable_merged_target_delivers_foreground_complete_without_stalling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'author'
            runtime = antigravity.Runtime(SESSION, antigravity.__file__, root)
            store = antigravity.core.Store(root, SESSION, PR, runtime)
            with store.locked() as data:
                data['target'] = dict(
                    repository='owner/repo', number=42, author='bot', checkout=None,
                    head_branch='feat/demo', head_repository='owner/repo', cleanup=None,
                    cleanup_result=None, events={}, stopped=False, terminal=None, ci=None, ci_version=None,
                )
            terminal_event = antigravity.core.event(
                'terminal', 42, ['merged', 't', 't'], 'https://github.com/owner/repo/pull/42',
                outcome='merged', head='a' * 40,
            )
            store.apply(make_snapshot([terminal_event], terminal='merged'))
            self.assertTrue(store.deliver())
            self.assertTrue(store.read()['target']['stopped'])
            self.assertTrue(antigravity.core.runner_done(store, store.read()))
            unread = antigravity.unread_outbox(root)
            self.assertEqual(len(unread), 1)
            self.assertIn('complete', unread[0]['text'])


class RoleAwareCleanupTests(unittest.TestCase):
    def test_cleanup_binding_and_postmerge_verification_use_explicit_bot_role(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            primary = root / 'repo'
            subprocess.run(['git', 'init', '-q', '-b', 'main', str(primary)], check=True)
            subprocess.run(['git', '-C', str(primary), 'config', 'user.name', 'Test'], check=True)
            subprocess.run(['git', '-C', str(primary), 'config', 'user.email', 'test@example.invalid'], check=True)
            subprocess.run(['git', '-C', str(primary), 'commit', '-q', '--allow-empty', '-m', 'base'], check=True)
            subprocess.run(['git', '-C', str(primary), 'remote', 'add', 'origin', 'https://github.com/owner/repo.git'], check=True)
            worktree = root / 'wt'
            subprocess.run(['git', '-C', str(primary), 'worktree', 'add', '-q', '-b', 'feat', str(worktree)], check=True)
            head = subprocess.run(['git', '-C', str(worktree), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
            pr = {'user': {'login': 'bot'}, 'merged': True, 'head': {'ref': 'feat', 'sha': head, 'repo': {'full_name': 'owner/repo'}},
                  'base': {'ref': 'main', 'repo': {'full_name': 'owner/repo'}}}
            gh_calls = []
            original_run = cleanup._run

            def fake_run(args, cwd=None):
                if args[0] == '/bin/gh_as':
                    gh_calls.append(args)
                    if '/pulls/' in args[-1]:
                        return json.dumps(pr)
                    if '/branches/' in args[-1]:
                        return json.dumps({'name': 'feat', 'protected': False, 'commit': {'sha': head}})
                    return json.dumps({'full_name': 'owner/repo', 'default_branch': 'main'})
                if args[0] == 'gh':
                    self.fail('bare gh called when explicit bot role was required')
                return original_run(args, cwd)

            with patch.object(cleanup.shutil, 'which', return_value='/bin/gh_as'), \
                    patch.object(cleanup, '_run', side_effect=fake_run):
                bound = cleanup.bind_cleanup(worktree, 'owner/repo', pr, role='bot')
            self.assertTrue(bound['owned'])
            self.assertEqual(bound['lifecycle'], 'disposable-v1')
            self.assertTrue(gh_calls)
            self.assertTrue(all(call[:3] == ['/bin/gh_as', 'bot', 'api'] for call in gh_calls))

            target = {'repository': 'owner/repo', 'number': 42, 'checkout': str(worktree),
                      'head_branch': 'feat', 'head_repository': 'owner/repo', 'cleanup': bound}
            with patch.object(cleanup.shutil, 'which', return_value=None):
                missing = cleanup.cleanup_target(target, {'head': head}, role='bot')
            self.assertEqual(missing['status'], 'preserved')
            self.assertIn('gh_as was not found', missing['reason'])

    def test_store_register_and_cleanup_pass_runtime_bot_role(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'author'
            store = antigravity.core.Store(root, SESSION, PR, antigravity.Runtime(SESSION, antigravity.__file__, root))
            pr = {'user': {'login': 'bot'}, 'head': {'ref': 'feat', 'sha': 'a' * 40, 'repo': {'full_name': 'owner/repo'}}}
            fake_cleanup_mod = type('FakeCleanup', (), {})()
            captured = {}

            def fake_bind(checkout, repository, pull, role=None):
                captured['bind_role'] = role
                return {'owned': True, 'lifecycle': 'disposable-v1'}

            fake_cleanup_mod.bind_cleanup = fake_bind
            with patch.object(antigravity.core, 'gh_json', return_value=pr), \
                    patch.object(antigravity.core, 'cleanup_module', return_value=fake_cleanup_mod):
                self.assertTrue(store.register(checkout='/tmp/owned-wt'))
            self.assertEqual(captured['bind_role'], 'bot')

            def fake_cleanup_target(target, current, role=None):
                captured['cleanup_role'] = role
                return {'status': 'cleaned'}

            terminal = antigravity.core.event('terminal', 42, ['merged', 't', 't'], 'url', outcome='merged', head='a' * 40)
            with patch.object(antigravity.core, 'cleanup_target', side_effect=fake_cleanup_target):
                store.apply(make_snapshot([terminal], terminal='merged'))
            self.assertEqual(captured['cleanup_role'], 'bot')


class AntigravityReplyTests(unittest.TestCase):
    def test_marked_body_appends_marker_once_and_rejects_empty_text(self):
        self.assertEqual(reply.marked_body('Looks good.'), 'Looks good.\n\nFrom Antigravity 🤖')
        self.assertEqual(reply.marked_body('Already marked\n\nFrom Antigravity 🤖\n'),
                         'Already marked\n\nFrom Antigravity 🤖')
        with self.assertRaises(ValueError):
            reply.marked_body('   \n')

    def test_reply_uses_gh_as_bot_for_checks_and_post_and_refuses_missing_gh_as(self):
        with patch.object(reply.shutil, 'which', return_value=None), \
                patch.object(reply.subprocess, 'run') as sub:
            with self.assertRaisesRegex(RuntimeError, 'gh_as'):
                reply.reply('owner/repo', 42, 'bot', 'hello')
        sub.assert_not_called()

        with self.assertRaises(ValueError):
            reply.reply('bad repo', 1, 'bot', 'hi')
        with self.assertRaises(ValueError):
            reply.reply('owner/repo', 0, 'bot', 'hi')

        responses = [
            json.dumps({'user': {'login': 'bot'}, 'url': 'https://api.github.com/repos/owner/repo/pulls/42'}),
            json.dumps({'pull_request_url': 'https://api.github.com/repos/owner/repo/pulls/42'}),
            'true\n',
            'bot\n',
            json.dumps({'html_url': 'https://github.com/owner/repo/pull/42#discussion_r9'}),
        ]
        commands = []

        def fake_subprocess(cmd, **kwargs):
            commands.append((cmd, kwargs.get('input')))
            return subprocess.CompletedProcess(cmd, 0, responses.pop(0), '')

        with patch.object(reply.shutil, 'which', return_value='/bin/gh_as'), \
                patch.object(reply.subprocess, 'run', side_effect=fake_subprocess):
            url = reply.reply('owner/repo', 42, 'bot', 'Disagree because X', inline_comment=9)
        self.assertEqual(url, 'https://github.com/owner/repo/pull/42#discussion_r9')
        self.assertEqual(len(commands), 5)
        self.assertTrue(all(cmd[:2] == ['/bin/gh_as', 'bot'] for cmd, _ in commands))
        post_cmd, post_input = commands[-1]
        self.assertIn('repos/owner/repo/pulls/42/comments/9/replies', post_cmd)
        self.assertTrue(json.loads(post_input)['body'].endswith('From Antigravity 🤖'))

    def test_reply_refuses_mismatched_author_or_foreign_inline_comment(self):
        with patch.object(reply, 'run', side_effect=[json.dumps({'user': {'login': 'other'}, 'url': 'u'})]):
            with self.assertRaises(PermissionError):
                reply.reply('owner/repo', 42, 'bot', 'hello')
        with patch.object(reply, 'run', side_effect=[
            json.dumps({'user': {'login': 'bot'}, 'url': 'https://api.github.com/repos/owner/repo/pulls/42'}),
            json.dumps({'pull_request_url': 'https://api.github.com/repos/owner/repo/pulls/99'}),
        ]):
            with self.assertRaises(ValueError):
                reply.reply('owner/repo', 42, 'bot', 'hello', inline_comment=5)


class AntigravitySlotRuntimeTests(unittest.TestCase):
    def test_project_monitor_slot_runtime_delivers_to_outbox_and_carries_antigravity_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rt = project_monitor.slot_runtime('antigravity', SESSION, project_monitor.__file__, outbox_root=root)
            self.assertEqual(rt.delivery_name, 'outbox')
            self.assertEqual(rt.identity_arguments, ['--runtime', 'antigravity', '--session', SESSION])
            self.assertTrue(rt.may_clean({}))
            self.assertFalse(rt.foreground_cleanup)
            self.assertTrue(rt.deliver('slot feedback'))
            self.assertEqual(antigravity.read_outbox(root)[0]['text'], 'slot feedback')


if __name__ == '__main__':
    unittest.main()
