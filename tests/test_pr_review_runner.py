import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/review/scripts'
sys.path.insert(0, str(SCRIPTS))
import review_pr as runner
import pr_review_github as remote
import pr_review_runtime as runtime
import pr_review_state as core


def current(head='a' * 40, ci='pending', terminal=None):
    return {'head': head, 'base': 'b' * 40, 'ci': ci, 'ci_key': ci, 'events': [],
            'terminal': terminal, 'draft': False, 'checks': [], 'history': [],
            'pr': {'title': 'Example', 'body': 'Acceptance'}}


def result(outcome='approved'):
    return {'outcome': outcome, 'body': 'Reviewed behavior and its assertions.', 'comments': []}


class FakeGitHub:
    repository = 'owner/repo'

    def __init__(self):
        self.current = current()
        self.published = []
        self.fail = False

    def snapshot(self, author):
        return copy.deepcopy(self.current)

    def publish(self, state, pending):
        if self.fail:
            raise TimeoutError()
        self.published.append(copy.deepcopy(pending))
        return 'https://github.com/owner/repo/pull/1#review'


class PRReviewRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        self.state['acceptance'] = 'Review the accepted behavior.'
        self.github = FakeGitHub()
        self.calls = []
        self.addCleanup(patch.stopall)
        patch.object(runner, 'prepare_checkout').start()

    def execute(self, state, root, prompt, persist):
        self.calls.append(state['session'])
        state['session'] = 'one-pr-session'
        return result()

    def step(self):
        return runner.step(self.root, self.state, self.github, self.execute)

    def test_PRL_02_one_session_survives_approval_ci_and_new_head_then_exits_on_merge(self):
        self.step()
        self.assertEqual(len(self.calls), 1)
        self.step()
        for _ in range(3):
            self.assertTrue(self.step())
        self.assertEqual(len(self.calls), 1)
        self.github.current = current(ci='pass')
        self.step()
        self.step()
        self.assertEqual(self.state['rounds'], 1)
        self.github.current = current(head='c' * 40, ci='pass')
        self.step()
        self.step()
        self.assertEqual(self.calls, [None, 'one-pr-session', 'one-pr-session'])
        self.github.current['terminal'] = 'merged'
        self.assertFalse(self.step())
        self.assertEqual(self.state['phase'], 'merged')
        self.assertEqual(len(self.calls), 3)

    def test_PRL_04_publication_retry_reuses_result_without_model_replay(self):
        self.step()
        token = self.state['pending']['token']
        self.github.fail = True
        with self.assertRaises(TimeoutError):
            self.step()
        self.assertEqual(self.state['pending']['token'], token)
        self.assertEqual(self.state['phase'], 'reviewing')
        self.github.fail = False
        self.step()
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(self.state['pending'])

    def test_PRL_04_a_new_head_cannot_receive_an_old_approval(self):
        self.step()
        self.github.current = current(head='c' * 40)
        self.step()
        self.assertFalse(self.github.published)
        self.assertIsNone(self.state['pending'])
        self.step()
        self.assertEqual(len(self.calls), 2)

    def test_PRL_03_limit_handoff_is_published_before_the_runner_stops(self):
        self.state['rounds'] = 2
        self.step()
        self.assertEqual(self.state['pending']['checkpoint']['phase'], 'needs-user-attention')
        self.assertFalse(self.step())
        self.assertEqual(len(self.github.published), 1)
        self.assertFalse(self.calls)

    def test_PRL_04_interrupted_worker_produces_recoverable_handoff_without_replay(self):
        self.state['pending'] = {'stage': 'execution', 'token': 'lost', 'snapshot': current()}
        self.assertFalse(self.step())
        self.assertEqual(self.state['phase'], 'needs-user-attention')
        self.assertFalse(self.calls)

    def test_PRL_01_only_one_process_can_hold_a_pr_lock(self):
        with runner.lock(self.root, 'run.lock'):
            self.assertTrue(runner.running(self.root))
            with self.assertRaises(BlockingIOError):
                with runner.lock(self.root, 'run.lock'):
                    self.fail('duplicate owner acquired the PR')
        self.assertFalse(runner.running(self.root))

    def test_PRL_02_merge_during_execution_stops_without_publishing_a_handoff(self):
        def execute(state, root, prompt, persist):
            raise runtime.PRFinished('merged')
        self.assertFalse(runner.step(self.root, self.state, self.github, execute))
        self.assertEqual(self.state['phase'], 'merged')
        self.assertIsNone(self.state['pending'])
        self.assertFalse(self.github.published)


class PublicationTests(unittest.TestCase):
    def test_PRL_04_recovery_finds_posted_review_and_only_posts_missing_handoff(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        state['rounds'] = 2
        pending = runner.make_pending(state, current(), result('changes-requested'), 'batch')
        existing = {'kind': 'review', 'user': {'login': 'reviewer'}, 'html_url': 'review-url',
                    'body': core.encode_checkpoint(pending['checkpoint'])}
        github = remote.GitHub('owner/repo#1', 'reviewer')
        with patch.object(github, 'history', return_value=[existing]), patch.object(github, 'post') as post:
            self.assertEqual(github.publish(state, pending), 'review-url')
        self.assertEqual(post.call_count, 1)
        self.assertTrue(post.call_args.args[0].endswith('/issues/1/comments'))

    def test_PRL_04_identity_or_permission_failure_prevents_publication(self):
        github = remote.GitHub('owner/repo#1', 'reviewer')
        with patch.object(github, 'json', return_value={'login': 'author'}):
            with self.assertRaises(PermissionError):
                github.verify_writer('author')
        with patch.object(github, 'json', side_effect=[{'login': 'reviewer'}, {'permissions': {'push': False}}]):
            with self.assertRaises(PermissionError):
                github.verify_writer('author')

    def test_PRL_05_only_fixed_reviewers_checkpoint_can_restore_progress(self):
        github = remote.GitHub('owner/repo#1', 'reviewer')
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        body = core.encode_checkpoint(core.checkpoint(state, 'owned'))
        foreign = {'user': {'login': 'author'}, 'body': body}
        owned = {'user': {'login': 'reviewer'}, 'body': body}
        self.assertIsNone(github.latest_checkpoint([foreign]))
        self.assertEqual(github.latest_checkpoint([owned, foreign])[0]['token'], 'owned')


class RuntimeTests(unittest.TestCase):
    def test_PRL_06_codex_resume_keeps_read_only_permissions_and_exact_session(self):
        state = {'runtime': 'codex', 'executable': '/codex', 'session': 'one-session'}
        command = runtime.command(state, Path('/state'), Path('/state/result'))
        self.assertEqual(command[:4], ['/codex', 'exec', 'resume', 'one-session'])
        self.assertIn('sandbox_mode="read-only"', command)
        self.assertIn('approval_policy="never"', command)
        self.assertNotIn('--model', command)
        self.assertNotIn('--last', command)

    def test_PRL_06_claude_only_has_read_tools_and_resumes_exact_session(self):
        state = {'runtime': 'claude', 'executable': '/claude', 'session': 'one-session'}
        command = runtime.command(state, Path('/state'), Path('/state/result'))
        self.assertEqual(command[command.index('--tools') + 1], 'Read,Glob,Grep')
        self.assertEqual(command[-2:], ['--resume', 'one-session'])
        self.assertNotIn('--dangerously-skip-permissions', command)

    def test_PRL_06_missing_runtime_fails_before_launch(self):
        with patch.object(runtime.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError):
                runtime.preflight('codex')


if __name__ == '__main__':
    unittest.main()
