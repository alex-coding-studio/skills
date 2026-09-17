import contextlib
import copy
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/review/scripts'
sys.path.insert(0, str(SCRIPTS))
import review_pr as runner
import pr_review_github as remote
import pr_review_state as core


def snapshot():
    return {'head': 'a' * 40, 'base': 'b' * 40, 'ci': 'none', 'ci_key': 'none',
            'events': [], 'terminal': None, 'draft': False, 'checks': [], 'history': [],
            'pr': {'title': 'Example', 'body': 'Acceptance'}}


class FreshReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = runner.state_root('owner/repo#1', self.base)
        self.root.mkdir(parents=True)
        self.decision = self.base / 'decision.md'
        self.decision.write_text('同意重新发起一轮独立 review。\n')
        self.state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        self.state.update(rounds=1, phase='error', session='old-session',
                          acceptance='Review the accepted behavior.', pid=12345)
        result = {'outcome': 'changes-requested', 'body': 'An unresolved finding.', 'comments': []}
        self.state['pending'] = runner.make_pending(self.state, snapshot(), result, 'old-token')
        runner.save(self.root, self.state)
        self.github = Mock()
        self.github.pull.return_value = {'state': 'open', 'merged': False, 'user': {'login': 'author'}}
        self.github.history.return_value = []
        self.github.latest_checkpoint.return_value = None
        self.addCleanup(patch.stopall)
        patch.object(runner.remote, 'GitHub', return_value=self.github).start()
        self.preflight = patch.object(runner.runtime, 'preflight', return_value='/runtime').start()
        self.running_patch = patch.object(runner, 'running', return_value=False)
        self.running = self.running_patch.start()
        self.launch = patch.object(runner, 'launch', side_effect=runner.read).start()

    def continue_review(self, *extra):
        arguments = ['review_pr.py', 'continue', '--pr', self.state['pr'],
                     '--state-base', str(self.base), '--decision-file', str(self.decision), *extra]
        with patch.object(sys, 'argv', arguments), contextlib.redirect_stdout(io.StringIO()):
            runner.main()
        return runner.read(self.root, self.state['pr'])

    def test_failed_publication_does_not_block_user_authorized_fresh_review(self):
        state = self.continue_review('--additional-rounds', '0')
        self.assertIsNone(state['pending'])
        self.assertIsNone(state['session'])
        self.assertEqual((state['rounds'], state['round_limit']), (1, 2))
        self.assertEqual(state['decision'], self.decision.read_text())
        self.github.publish.assert_not_called()
        calls = []
        current = snapshot()
        github = Mock(repository='owner/repo')
        github.snapshot.return_value = current
        def execute(state, root, prompt, persist):
            calls.append(state['session'])
            self.assertIn('previous_review', prompt)
            previous = json.loads((root / state['previous_review']).read_text())
            self.assertEqual(previous, self.state)
            return {'outcome': 'changes-requested', 'body': 'The finding is still unresolved.', 'comments': []}
        with patch.object(runner, 'prepare_checkout'):
            runner.step(self.root, state, github, execute)
        self.assertEqual(calls, [None])
        self.assertEqual(state['rounds'], 2)
        self.assertNotEqual(state['pending']['token'], 'old-token')
        self.assertEqual(state['pending']['result']['outcome'], 'changes-requested')

    def test_fresh_request_preserves_interrupted_execution_without_replaying_it(self):
        self.state.update(phase='reviewing', pending={'stage': 'execution', 'token': 'interrupted',
                                                   'snapshot': snapshot()})
        runner.save(self.root, self.state)
        state = self.continue_review()
        previous = json.loads((self.root / state['previous_review']).read_text())
        self.assertEqual(previous['pending']['stage'], 'execution')
        self.assertIsNone(state['pending'])
        self.assertEqual(state['round_limit'], 3)

    def test_settled_approval_can_be_reassessed_without_reusing_approval(self):
        self.state.update(phase='approved', review_phase='approved', pending=None,
                          head='a' * 40, base='b' * 40, last_review_url='old-approval')
        runner.save(self.root, self.state)
        state = self.continue_review()
        self.assertEqual(state['phase'], 'starting')
        self.assertIsNone(state['head'])
        self.assertIsNone(state.get('last_review_url'))
        self.assertIsNone(state['review_phase'])

    def test_missing_decision_or_failed_preflight_preserves_previous_request(self):
        before = (self.root / 'state.json').read_bytes()
        self.decision.write_text(' ')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.continue_review()
        self.assertEqual((self.root / 'state.json').read_bytes(), before)
        self.decision.write_text('重新评审')
        self.preflight.side_effect = RuntimeError('runtime unavailable')
        with self.assertRaisesRegex(RuntimeError, 'runtime unavailable'):
            self.continue_review()
        self.assertEqual((self.root / 'state.json').read_bytes(), before)
        self.launch.assert_not_called()

    def test_closed_or_merged_pr_preserves_previous_request(self):
        before = (self.root / 'state.json').read_bytes()
        for merged in [False, True]:
            self.github.pull.return_value.update(state='closed', merged=merged)
            with self.subTest(merged=merged), self.assertRaisesRegex(ValueError, 'open PR'):
                self.continue_review()
        self.assertEqual((self.root / 'state.json').read_bytes(), before)
        self.launch.assert_not_called()

    def test_active_owned_runner_is_stopped_before_a_fresh_request(self):
        self.running.side_effect = [True, False, False]
        command = f'python /installed/review_pr.py run --pr owner/repo#1 --state-base {self.root.parents[2]}'
        with patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, command)), \
                patch.object(runner.os, 'kill') as kill:
            state = self.continue_review()
        kill.assert_called_once_with(12345, signal.SIGTERM)
        self.assertIsNone(state['pending'])
        self.launch.assert_called_once()

    def test_unrelated_active_process_is_never_stopped(self):
        self.running.return_value = True
        before = (self.root / 'state.json').read_bytes()
        with patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'unrelated')), \
                patch.object(runner.os, 'kill') as kill, self.assertRaisesRegex(RuntimeError, 'ownership'):
            self.continue_review()
        kill.assert_not_called()
        self.assertEqual((self.root / 'state.json').read_bytes(), before)

    def test_real_owned_process_releases_its_lock_before_replacement(self):
        self.running_patch.stop()
        script = self.base / 'review_pr.py'
        script.write_text(
            'import fcntl, json, os, pathlib, sys, time\n'
            f'root = pathlib.Path({str(self.root)!r})\n'
            'with (root / "run.lock").open("a") as handle:\n'
            '    fcntl.flock(handle, fcntl.LOCK_EX)\n'
            '    state = json.loads((root / "state.json").read_text())\n'
            '    state["pid"] = os.getpid()\n'
            '    (root / "state.json").write_text(json.dumps(state))\n'
            '    print("ready", flush=True)\n'
            '    time.sleep(30)\n')
        process = subprocess.Popen([sys.executable, str(script), 'run', '--pr', self.state['pr'],
                                    '--state-base', str(self.root.parents[2])], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        try:
            deadline = time.monotonic() + 5
            while runner.read(self.root, self.state['pr']).get('pid') != process.pid:
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail('fixture runner did not acquire its lock')
                time.sleep(0.01)
            self.continue_review()
            process.wait(timeout=5)
            self.assertFalse(runner.running(self.root))
            self.assertEqual(runner.read(self.root, self.state['pr'])['phase'], 'starting')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()


class InlinePublicationTests(unittest.TestCase):
    def test_renamed_and_deleted_files_use_the_review_diff_path(self):
        patch_text = ('diff --git a/old.py b/new.py\n--- a/old.py\n+++ b/new.py\n'
                      '@@ -1 +1 @@\n-old\n+new\n'
                      'diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n'
                      '@@ -3 +0,0 @@\n-removed\n')
        locations = remote.inline_locations(patch_text)
        self.assertIn(('new.py', 'LEFT', 1), locations)
        self.assertIn(('new.py', 'RIGHT', 1), locations)
        self.assertIn(('gone.py', 'LEFT', 3), locations)
        self.assertNotIn(('old.py', 'LEFT', 1), locations)
        self.assertNotIn(('gone.py', 'RIGHT', 0), locations)

    def test_invalid_positions_move_to_body_without_changing_the_verdict(self):
        patch_text = ('diff --git a/tests/access.test.ts b/tests/access.test.ts\n'
                      '--- a/tests/access.test.ts\n+++ b/tests/access.test.ts\n'
                      '@@ -195,2 +198,2 @@\n existing\n-old\n+new\n')
        for outcome, event in [('approved', 'APPROVE'), ('changes-requested', 'REQUEST_CHANGES')]:
            state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
            comments = [{'path': 'tests/access.test.ts', 'line': line, 'side': side, 'body': body}
                        for line, side, body in [(85, 'RIGHT', 'Misnumbered finding'),
                                                 (199, 'RIGHT', 'New line finding'),
                                                 (196, 'LEFT', 'Deleted line finding'),
                                                 (199, 'LEFT', 'Wrong side finding'),
                                                 (195, 'LEFT', 'Context on wrong side'),
                                                 (198, 'RIGHT', 'Context finding')]]
            pending = runner.make_pending(state, snapshot(), {'outcome': outcome, 'body': 'Review',
                                                              'comments': comments}, 'token')
            original = copy.deepcopy(pending)
            github = remote.GitHub(state['pr'], state['reviewer'])
            with self.subTest(outcome=outcome), patch.object(github, 'history', return_value=[]), \
                    patch.object(github, 'post', return_value={'html_url': 'review'}) as post:
                github.publish(state, pending, patch_text)
            payload = post.call_args.args[1]
            self.assertEqual(payload['event'], event)
            self.assertEqual([item['body'].split('\n')[0] for item in payload['comments']],
                             ['New line finding', 'Deleted line finding', 'Context finding'])
            self.assertIn('Misnumbered finding', payload['body'])
            self.assertIn('Wrong side finding', payload['body'])
            self.assertIn('Context on wrong side', payload['body'])
            self.assertEqual(pending, original)

    def test_unavailable_diff_preserves_finding_in_body(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        comment = {'path': 'file.py', 'line': 1, 'side': 'RIGHT', 'body': 'Keep this finding'}
        pending = runner.make_pending(state, snapshot(), {'outcome': 'approved', 'body': 'Review',
                                                          'comments': [comment]}, 'token')
        github = remote.GitHub(state['pr'], state['reviewer'])
        with patch.object(github, 'history', return_value=[]), \
                patch.object(github, 'post', return_value={'html_url': 'review'}) as post:
            github.publish(state, pending)
        payload = post.call_args.args[1]
        self.assertEqual(payload['comments'], [])
        self.assertIn(comment['body'], payload['body'])


if __name__ == '__main__':
    unittest.main()
