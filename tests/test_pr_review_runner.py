import contextlib
import copy
import io
import os
from types import SimpleNamespace
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

    def publish(self, state, pending, patch=''):
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
        self.fingerprints = {}
        patch.object(runner, 'own_diff_fingerprint', side_effect=lambda root, value: self.fingerprints.get(
            value['head'], 'e' * 39 + value['head'][0])).start()

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
        self.assertEqual(self.calls, [None, 'one-pr-session'])
        self.github.current['terminal'] = 'merged'
        self.assertFalse(self.step())
        self.assertEqual(self.state['phase'], 'merged')
        self.assertEqual(len(self.calls), 2)

    def approve_at_round_limit(self):
        self.state['rounds'] = 1
        self.github.current = current(ci='pass')
        self.fingerprints = {'a' * 40: '1' * 40, 'c' * 40: '1' * 40}
        self.step()
        self.step()
        self.assertEqual(self.state['rounds'], 2)

    def test_merging_main_without_changing_own_diff_reuses_approval_without_model_or_round(self):
        self.approve_at_round_limit()
        self.github.current = current(head='c' * 40, ci='pending')
        self.step()
        self.step()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.state['rounds'], 2)
        reused = self.github.published[-1]
        self.assertEqual(reused['checkpoint']['head'], 'c' * 40)
        self.assertIn('a' * 40, reused['result']['body'])
        self.assertEqual(self.state['review_phase'], 'waiting-ci')
        restored = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        core.restore(restored, reused['checkpoint'])
        self.assertEqual(restored['approved_fingerprint'], '1' * 40)

    def test_changed_own_diff_after_approval_gets_an_independent_review(self):
        self.approve_at_round_limit()
        self.fingerprints['c' * 40] = '2' * 40
        self.github.current = current(head='c' * 40, ci='pass')
        self.step()
        self.step()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.github.published[-1]['checkpoint']['phase'], 'needs-user-attention')

    def test_new_feedback_with_an_unchanged_own_diff_is_still_reviewed(self):
        self.approve_at_round_limit()
        self.github.current = current(head='c' * 40, ci='pass')
        self.github.current['events'] = [{'key': 'human', 'kind': 'conversation', 'id': 9, 'url': 'u'}]
        self.step()
        self.step()
        self.assertEqual(self.github.published[-1]['checkpoint']['phase'], 'needs-user-attention')

    def test_base_move_with_unchanged_own_diff_is_settled_without_publication(self):
        self.approve_at_round_limit()
        self.github.current = current(ci='pass')
        self.github.current['base'] = 'd' * 40
        self.step()
        self.assertEqual(len(self.github.published), 1)
        self.assertEqual(self.state['base'], 'd' * 40)
        self.assertIsNone(self.state['pending'])

    def test_base_move_does_not_swallow_a_new_ci_failure(self):
        self.approve_at_round_limit()
        self.github.current = current(ci='fail')
        self.github.current['base'] = 'd' * 40
        self.step()
        self.step()
        self.assertEqual(len(self.calls), 2)

    def test_merged_pr_discards_its_review_checkout_and_keeps_state(self):
        self.step()
        (self.root / 'checkout/.git').mkdir(parents=True)
        self.github.current['terminal'] = 'merged'
        self.assertFalse(self.step())
        self.assertFalse((self.root / 'checkout').exists())
        self.assertEqual(json.loads((self.root / 'state.json').read_text())['phase'], 'merged')

    def test_successful_ci_reuses_published_review_without_model_or_publication(self):
        self.step()
        self.step()
        self.github.current = current(ci='pass')
        self.step()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.github.published), 1)
        self.assertEqual(self.state['ci'], 'pass')
        self.assertIsNone(self.state['pending'])

    def test_waiting_ci_without_any_reported_checks_is_recorded_as_approved(self):
        self.github.current = current(ci='none')
        self.execute = lambda state, root, prompt, persist: result('waiting-ci')
        self.step()
        self.step()
        self.assertEqual(self.github.published[0]['checkpoint']['phase'], 'approved')
        self.assertEqual(self.state['phase'], 'approved')
        self.assertEqual(self.state['review_phase'], 'approved')
        self.assertEqual(self.state['ci'], 'none')

    def test_checks_appearing_after_a_no_check_approval_still_wake_the_reviewer_on_failure(self):
        self.github.current = current(ci='none')
        self.step()
        self.step()
        self.github.current = current(ci='fail')
        self.step()
        self.assertEqual(len(self.calls), 2)

    def test_waiting_ci_with_observed_pending_checks_keeps_its_ci_gate(self):
        self.execute = lambda state, root, prompt, persist: result('waiting-ci')
        self.step()
        self.step()
        self.assertEqual(self.github.published[0]['checkpoint']['phase'], 'waiting-ci')
        self.assertEqual(self.state['phase'], 'waiting-ci')

    def test_failed_ci_still_reaches_independent_reviewer(self):
        self.step()
        self.step()
        self.github.current = current(ci='fail')
        self.step()
        self.assertEqual(len(self.calls), 2)

    def test_continuation_keeps_acceptance_accessible_without_repeating_it(self):
        self.state.update(session='existing', head='a' * 40, base='b' * 40)
        self.state['acceptance'] = 'Authoritative scope ' * 100
        with patch.object(runner, 'git', return_value='incremental diff'):
            prompt = runner.prompt_for(self.root, self.state, current(head='c' * 40), 'head')
        context = json.loads((self.root / 'context.json').read_text())
        self.assertNotIn('acceptance', context)
        self.assertNotIn('body', context)
        self.assertEqual((self.root / 'acceptance.md').read_text(), self.state['acceptance'])
        self.assertEqual((self.root / 'continuation.patch').read_text(), 'incremental diff')
        self.assertIn('continuation.patch', prompt)
        self.assertIn('current.patch', prompt)

    def test_without_an_acceptance_file_the_reviewer_reads_the_current_pr_description(self):
        self.state['acceptance'] = None
        runner.prompt_for(self.root, self.state, current(), 'head')
        self.assertEqual((self.root / 'acceptance.md').read_text(), 'Acceptance')
        edited = current()
        edited['pr']['body'] = 'Updated checks at the new head'
        runner.prompt_for(self.root, self.state, edited, 'feedback')
        self.assertEqual((self.root / 'acceptance.md').read_text(), 'Updated checks at the new head')

    def test_continuation_prompt_names_the_event_instead_of_repeating_instructions(self):
        worker = (Path(runner.__file__).resolve().parents[1] / 'references/worker.md').read_text()
        self.assertIn(worker, runner.prompt_for(self.root, self.state, current(), 'head'))
        self.state.update(session='existing', head='a' * 40, base='b' * 40)
        prompt = runner.prompt_for(self.root, self.state, current(ci='fail'), 'ci')
        self.assertNotIn(worker, prompt)
        self.assertIn('`ci` event', prompt)
        self.assertIn('context.json', prompt)

    def test_base_change_uses_full_patch_on_continuation(self):
        self.state.update(session='existing', head='a' * 40, base='d' * 40)
        prompt = runner.prompt_for(self.root, self.state, current(head='c' * 40), 'head')
        self.assertNotIn('continuation.patch', prompt)
        self.assertIn('current.patch', prompt)

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

    def test_PRL_05_unseen_feedback_before_checkpoint_publication_is_included(self):
        checkpoint = {'kind': 'review', 'id': 10, 'user': {'login': 'reviewer'},
                      'body': core.encode_checkpoint(core.checkpoint(self.state, 'previous'))}
        for body in ['Edited an older comment with a new question.', 'Reply posted while the reviewer was running.']:
            with self.subTest(body=body):
                comment = {'kind': 'conversation', 'id': 1, 'body': body, 'user': {'login': 'author'}}
                snapshot = current()
                snapshot['history'] = [comment, checkpoint]
                snapshot['events'] = [{'key': 'unseen-version', 'kind': 'conversation', 'id': 1}]
                runner.prompt_for(self.root, self.state, snapshot, 'feedback')
                context = json.loads((self.root / 'context.json').read_text())
                self.assertEqual(context['new_feedback'], [comment])

    def test_PRL_03_feedback_on_approved_head_does_not_consume_another_code_round(self):
        self.state['rounds'] = 2
        core.settle(self.state, current(), 'approved', [])
        self.github.current['events'] = [{'key': 'reply', 'kind': 'conversation', 'id': 2}]
        self.step()
        self.step()
        self.assertEqual(self.state['phase'], 'approved')
        self.assertEqual(self.state['rounds'], 2)
        self.assertEqual(len(self.calls), 1)

    def test_PRL_03_unresolved_same_head_reassessment_reaches_the_limit(self):
        self.state['rounds'] = 1
        core.settle(self.state, current(), 'changes-requested', [])
        self.github.current['events'] = [{'key': 'reply', 'kind': 'conversation', 'id': 2}]
        def execute(state, root, prompt, persist):
            return result('changes-requested')
        runner.step(self.root, self.state, self.github, execute)
        self.assertFalse(runner.step(self.root, self.state, self.github, execute))
        self.assertEqual(self.state['phase'], 'needs-user-attention')
        self.assertEqual(self.state['rounds'], 2)

    def test_check_results_on_a_head_with_requested_changes_do_not_repeat_the_review(self):
        self.execute = lambda state, root, prompt, persist: (self.calls.append(1), result('changes-requested'))[1]
        self.step()
        self.step()
        self.github.current = current(ci='fail')
        self.github.current['ci_events'] = ['merge-workflow-run']
        self.step()
        self.github.current = current(ci='pass')
        self.github.current['ci_events'] = ['merge-workflow-run', 'tests-rerun']
        self.step()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.github.published), 1)
        self.assertEqual(self.state['phase'], 'changes-requested')
        self.assertEqual(self.state['rounds'], 1)
        self.assertEqual(self.state['ci'], 'pass')
        self.assertIsNone(self.state['pending'])
        self.github.current = current(head='c' * 40, ci='pass')
        self.step()
        self.assertEqual(len(self.calls), 2)


class PublicationTests(unittest.TestCase):
    def test_skipped_workflow_runs_are_not_check_results_for_the_reviewer(self):
        tests = {'__typename': 'CheckRun', 'name': 'tests', 'status': 'COMPLETED', 'conclusion': 'SUCCESS'}
        merge = {'__typename': 'CheckRun', 'name': 'merge', 'status': 'COMPLETED', 'conclusion': 'SKIPPED'}
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        def snapshot(checks):
            return {**current(), **remote.check_summary(checks)}
        core.settle(state, snapshot([tests]), 'approved', [])
        self.assertIsNone(core.next_event(state, snapshot([tests, merge, {**merge, 'startedAt': 'later'}])))
        self.assertEqual(snapshot([merge])['ci'], 'none')
        self.assertEqual(snapshot([merge, tests])['ci'], 'pass')

    def test_PRL_02_failed_check_with_pending_churn_does_not_change_terminal_fingerprint(self):
        failed = {'__typename': 'CheckRun', 'name': 'tests', 'status': 'COMPLETED', 'conclusion': 'FAILURE'}
        queued = {'__typename': 'CheckRun', 'name': 'build', 'status': 'QUEUED', 'conclusion': None}
        running = {**queued, 'status': 'IN_PROGRESS'}
        passed = {**queued, 'status': 'COMPLETED', 'conclusion': 'SUCCESS'}
        self.assertEqual(remote.terminal_check_key([failed, queued]), remote.terminal_check_key([failed, running]))
        self.assertNotEqual(remote.terminal_check_key([failed, running]), remote.terminal_check_key([failed, passed]))

    def test_PRL_02_failed_status_rerun_only_wakes_for_its_new_terminal_result(self):
        failed = {'__typename': 'CheckRun', 'name': 'tests', 'status': 'COMPLETED', 'conclusion': 'FAILURE'}
        status = {'__typename': 'StatusContext', 'context': 'build', 'state': 'FAILURE'}
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        def snapshot(checks):
            snapshot = current(ci=remote.shared.checks_state(checks))
            snapshot['ci_key'] = remote.terminal_check_key(checks)
            snapshot['ci_events'] = remote.terminal_check_events(checks)
            return snapshot
        core.settle(state, snapshot([failed, status]), 'waiting-ci', [])
        self.assertIsNone(core.next_event(state, snapshot([failed, {**status, 'state': 'PENDING'}])))
        self.assertEqual(core.next_event(state, snapshot([failed, {**status, 'state': 'SUCCESS'}])), 'ci')

    def test_PRL_04_recovery_reuses_posted_attention_review_without_reposting(self):
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 2)
        state['rounds'] = 2
        pending = runner.make_pending(state, current(), result('changes-requested'), 'batch')
        existing = {'kind': 'review', 'user': {'login': 'reviewer'}, 'html_url': 'review-url',
                    'body': core.encode_checkpoint(pending['checkpoint'])}
        github = remote.GitHub('owner/repo#1', 'reviewer')
        with patch.object(github, 'history', return_value=[existing]), patch.object(github, 'post') as post:
            self.assertEqual(github.publish(state, pending), 'review-url')
        post.assert_not_called()

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
        self.assertEqual(command[command.index('--model') + 1], 'gpt-5.6-sol')
        self.assertIn('model_reasoning_effort="high"', command)
        self.assertNotIn('--last', command)

    def test_PRL_06_claude_only_has_read_tools_and_resumes_exact_session(self):
        state = {'runtime': 'claude', 'executable': '/claude', 'session': 'one-session'}
        command = runtime.command(state, Path('/state'), Path('/state/result'))
        self.assertEqual(command[command.index('--tools') + 1], 'Read,Glob,Grep')
        self.assertEqual(command[-2:], ['--resume', 'one-session'])
        self.assertNotIn('--dangerously-skip-permissions', command)
        self.assertEqual(command[command.index('--model') + 1], 'claude-opus-5')
        self.assertEqual(command[command.index('--effort') + 1], 'high')

    def test_new_sessions_use_the_same_review_models_as_resumes(self):
        for name, model in [('codex', 'gpt-6.1-sol'), ('claude', 'claude-opus-5-5')]:
            state = {'runtime': name, 'executable': '/' + name, 'session': None, 'next_session': 'new',
                     'model': model}
            initial = runtime.command(state, Path('/state'), Path('/state/result'))
            state['session'] = 'same-session'
            resumed = runtime.command(state, Path('/state'), Path('/state/result'))
            self.assertEqual(initial[initial.index('--model') + 1], model)
            self.assertEqual(resumed[resumed.index('--model') + 1], model)

    def test_existing_review_without_a_model_pin_keeps_the_previous_policy(self):
        for name, model in [('codex', 'gpt-5.6-sol'), ('claude', 'claude-opus-5')]:
            state = {'runtime': name, 'executable': '/' + name, 'session': 'old-session'}
            command = runtime.command(state, Path('/state'), Path('/state/result'))
            self.assertEqual(command[command.index('--model') + 1], model)

    def test_deterministic_reviews_use_lower_models_with_explicit_max_exception(self):
        for name, model in [('codex', 'gpt-6-luna'), ('claude', 'claude-sonnet-5-5')]:
            self.assertEqual(runtime.review_settings(name, 'deterministic'), {'model': model, 'effort': 'max'})
            state = {'runtime': name, 'executable': '/' + name, 'session': 'existing',
                     'complexity': 'deterministic', 'model': model}
            command = runtime.command(state, Path('/state'), Path('/state/result'))
            self.assertEqual(command[command.index('--model') + 1], model)
            self.assertIn('model_reasoning_effort="max"' if name == 'codex' else 'max', command)

    def test_deterministic_claude_review_pinned_before_upgrade_keeps_its_model(self):
        state = {'runtime': 'claude', 'executable': '/claude', 'session': 'existing',
                 'complexity': 'deterministic', 'model': 'claude-sonnet-5'}
        command = runtime.command(state, Path('/state'), Path('/state/result'))
        self.assertEqual(command[command.index('--model') + 1], 'claude-sonnet-5')

    def test_codex_review_pinned_to_gpt_6_sol_keeps_its_model(self):
        state = {'runtime': 'codex', 'executable': '/codex', 'session': 'existing',
                 'complexity': 'high', 'model': 'gpt-6-sol'}
        command = runtime.command(state, Path('/state'), Path('/state/result'))
        self.assertEqual(command[command.index('--model') + 1], 'gpt-6-sol')

    def test_regular_review_effort_is_bounded_at_high(self):
        for name, model in [('codex', 'gpt-6.1-sol'), ('claude', 'claude-opus-5-5')]:
            for effort in ['low', 'medium', 'high']:
                self.assertEqual(runtime.review_settings(name, effort), {'model': model, 'effort': effort})
            with self.assertRaises(ValueError):
                runtime.review_settings(name, 'max')

    def test_PRL_06_missing_runtime_fails_before_launch(self):
        with patch.object(runtime.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError):
                runtime.preflight('codex')

    def test_PRL_06_claude_can_read_the_supplied_inputs_outside_its_checkout(self):
        state = {'runtime': 'claude', 'executable': '/claude', 'session': 'one-session'}
        command = runtime.command(state, Path('/state'), Path('/state/result'))
        self.assertIn('--add-dir', command)
        self.assertEqual(command[command.index('--add-dir') + 1], '/state')




class OnePullRequestRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'alex-coding/review/pr'
        self.root.mkdir(parents=True)
        self.addCleanup(os.chdir, os.getcwd())
        state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 3)
        state.update(interval=10, acceptance='scope')
        self.state = state
        self.addCleanup(patch.stopall)
        patch.object(runner.remote, 'GitHub').start()
        patch.object(runner.time, 'sleep').start()

    def author(self, runtime='claude', remote=None):
        self.state['author_delivery'] = {'runtime': runtime, 'session': 'session-one', 'remote': remote}
        runner.save(self.root, self.state)

    def test_author_delivery_continues_after_review_ends_until_its_cleanup_finishes(self):
        self.author(remote='unix:///tmp/owner.sock')
        polls = []
        with patch.object(runner, 'step', return_value=False) as step, \
                patch.object(runner, 'author_poll', side_effect=lambda store, module: polls.append(1) or len(polls) == 3):
            runner.run(self.root, 'owner/repo#1')
        self.assertEqual(len(polls), 3)
        self.assertEqual(step.call_count, 3)

    def test_runner_without_author_delivery_stops_with_its_review(self):
        runner.save(self.root, self.state)
        with patch.object(runner, 'step', return_value=False), patch.object(runner, 'author_poll') as poll:
            runner.run(self.root, 'owner/repo#1')
        poll.assert_not_called()

    def test_claude_stdout_delivery_keeps_runner_status_off_stdout(self):
        self.author()
        output = io.StringIO()
        with patch.object(runner, 'step', return_value=False), \
                patch.object(runner, 'author_poll', return_value=True), contextlib.redirect_stdout(output):
            runner.run(self.root, 'owner/repo#1')
        self.assertEqual(output.getvalue(), '')
        self.assertIn('Reviewer started', (self.root / 'monitor.log').read_text())

    def test_claude_stdout_delivery_is_not_detached(self):
        self.author()
        with patch.object(runner.subprocess, 'Popen') as popen:
            state = runner.launch(self.root, 'owner/repo#1')
        popen.assert_not_called()
        self.assertIn("review_pr.py run --pr 'owner/repo#1' --state-base ", runner.run_command(self.root, state['pr']))

    def test_author_ledger_lives_inside_the_pr_state_directory(self):
        self.author(remote='unix:///tmp/owner.sock')
        store, module = runner.author_store(self.root, self.state)
        self.assertEqual(store.root, (self.root / 'author').resolve())
        self.assertEqual(store.runtime.delivery_name, 'session')
        self.assertTrue(store.runtime.state_delivery)

    def test_author_delivery_is_registered_once_and_cannot_be_rerouted(self):
        runner.save(self.root, self.state)
        args = SimpleNamespace(author_runtime='claude', author_session='session-one', session_remote=None,
                               checkout=Path(self.temp.name), slot=None, codex='codex')
        registered = []
        real = runner.author_store

        def author_store(root, state):
            store, module = real(root, state)
            store.register = lambda checkout=None: registered.append((store.root, checkout))
            return store, module

        with patch.object(runner, 'author_store', side_effect=author_store):
            runner.attach_author(args, self.root, self.state)
            runner.attach_author(args, self.root, self.state)
            args.author_session = 'session-two'
            with self.assertRaisesRegex(ValueError, 'refusing reroute'):
                runner.attach_author(args, self.root, self.state)
        self.assertEqual(registered[0], ((self.root / 'author').resolve(), str(Path(self.temp.name).resolve())))
        self.assertEqual(runner.read(self.root, 'owner/repo#1')['author_delivery']['session'], 'session-one')

    def test_repeated_start_with_the_same_author_keeps_the_running_reviewers_progress(self):
        self.author()
        stale = runner.read(self.root, 'owner/repo#1')
        self.state['rounds'] = 2
        runner.save(self.root, self.state)
        args = SimpleNamespace(author_runtime='claude', author_session='session-one', session_remote=None,
                               checkout=Path(self.temp.name), slot=None, codex='codex')
        with patch.object(runner, 'author_store') as store:
            runner.attach_author(args, self.root, stale)
        store.assert_not_called()
        self.assertEqual(runner.read(self.root, 'owner/repo#1')['rounds'], 2)

    def test_author_delivery_cannot_be_added_to_a_running_reviewer(self):
        runner.save(self.root, self.state)
        args = SimpleNamespace(author_runtime='claude', author_session='session-one', session_remote=None,
                               checkout=Path(self.temp.name), slot=None, codex='codex')
        with patch.object(runner, 'running', return_value=True), patch.object(runner, 'author_store') as store, \
                self.assertRaisesRegex(ValueError, 'already running'):
            runner.attach_author(args, self.root, self.state)
        store.assert_not_called()
        self.assertNotIn('author_delivery', runner.read(self.root, 'owner/repo#1'))

    def test_a_pool_slot_is_released_by_the_project_store_instead_of_disposed(self):
        runner.save(self.root, self.state)
        args = SimpleNamespace(author_runtime='claude', author_session='session-one', session_remote=None,
                               checkout=None, slot=Path(self.temp.name), codex='codex')
        registered = []
        real = runner.author_store

        def author_store(root, state):
            store, module = real(root, state)
            store.register_slot = lambda slot: registered.append(slot)
            store.register = lambda checkout=None: self.fail('a pool slot must not be registered as disposable')
            return store, module

        with patch.object(runner, 'author_store', side_effect=author_store):
            runner.attach_author(args, self.root, self.state)
        self.assertEqual(registered, [Path(self.temp.name)])
        store, module = runner.author_store(self.root, self.state)
        self.assertEqual(type(store).__name__, 'ProjectStore')
        self.assertTrue(store.delivers_state)
        self.assertEqual(self.state['author_delivery']['slot'], str(Path(self.temp.name).resolve()))

    def test_a_codex_worker_in_a_pool_slot_gets_queue_delivery_and_slot_release(self):
        runner.save(self.root, self.state)
        args = SimpleNamespace(author_runtime='codex', author_session='00000000-0000-0000-0000-000000000001',
                               session_remote=None, checkout=None, slot=Path(self.temp.name), codex='codex')
        registered = []
        real = runner.author_store

        def author_store(root, state):
            store, module = real(root, state)
            store.register_slot = lambda slot: registered.append(slot)
            return store, module

        with patch.object(runner.shutil, 'which', return_value='/bin/codex'), \
                patch.object(runner.subprocess, 'run'), \
                patch.object(runner, 'author_store', side_effect=author_store):
            runner.attach_author(args, self.root, self.state)
        self.assertEqual(registered, [Path(self.temp.name)])
        store, module = runner.author_store(self.root, self.state)
        self.assertEqual(type(store).__name__, 'ProjectStore')
        self.assertEqual(store.runtime.delivery_name, 'queued')
        self.assertEqual(store.runtime.identity_arguments, ['--thread', '00000000-0000-0000-0000-000000000001'])
        self.assertTrue(store.runtime.may_clean({}))
        self.assertFalse(store.runtime.foreground_cleanup)


class TakeoverTests(unittest.TestCase):
    OLD = '00000000-0000-0000-0000-000000000001'
    NEW = '00000000-0000-0000-0000-000000000002'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'review'
        self.root.mkdir()
        self.slot = Path(self.temp.name) / 'slot'
        self.slot.mkdir()
        self.state = core.initial_state('owner/repo#1', 'reviewer', 'author', 'codex', 3)
        self.state.update(rounds=2, approved_fingerprint='f' * 40, approved_head='a' * 40,
                          seen=['review:1'], last_review_url='https://github.com/owner/repo/pull/1#r',
                          phase='error', pid=None, worker_pid=None,
                          author_delivery={'runtime': 'codex', 'session': self.OLD, 'remote': None,
                                           'slot': None, 'executable': '/bin/codex'})
        runner.save(self.root, self.state)
        (self.root / 'author').mkdir()
        (self.root / 'author/state.json').write_text(json.dumps({
            'schema': runner.author_adapter({'runtime': 'codex'}).core.SCHEMA, 'thread': self.OLD,
            'pr': 'owner/repo#1', 'batch': None, 'target': {
                'repository': 'owner/repo', 'number': 1, 'author': 'bot', 'checkout': '/old/worktree',
                'cleanup': {'owned': True, 'lifecycle': 'disposable-v1'}, 'cleanup_result': None,
                'events': {'review:1': {'kind': 'review', 'status': 'handled'}}, 'stopped': False,
                'terminal': None, 'ci': None, 'ci_version': None}}))
        self.addCleanup(patch.stopall)
        patch.object(runner.shutil, 'which', return_value='/bin/codex').start()
        patch.object(runner.subprocess, 'run').start()
        self.registered = []
        real = self.real = runner.author_store

        def author_store(root, state):
            store, module = real(root, state)
            store.register_slot = lambda slot: self.registered.append(slot)
            return store, module

        patch.object(runner, 'author_store', side_effect=author_store).start()

    def args(self, takeover=True):
        return SimpleNamespace(author_runtime='codex', author_session=self.NEW, session_remote=None,
                               checkout=None, slot=self.slot, codex='codex', takeover=takeover)

    def test_a_new_session_cannot_take_over_without_declaring_it(self):
        with self.assertRaisesRegex(ValueError, '--takeover'):
            runner.attach_author(self.args(takeover=False), self.root, self.state)
        self.assertEqual(runner.read(self.root, 'owner/repo#1')['author_delivery']['session'], self.OLD)

    def test_takeover_is_refused_while_the_previous_runner_holds_its_lock(self):
        with patch.object(runner, 'running', return_value=True), self.assertRaisesRegex(ValueError, 'still alive'):
            runner.attach_author(self.args(), self.root, self.state)
        self.assertEqual(runner.read(self.root, 'owner/repo#1')['author_delivery']['session'], self.OLD)

    def test_takeover_is_refused_while_the_previous_process_is_alive(self):
        self.state['pid'] = os.getpid()
        runner.save(self.root, self.state)
        with self.assertRaisesRegex(ValueError, 'still alive'):
            runner.attach_author(self.args(), self.root, self.state)
        self.assertEqual(json.loads((self.root / 'author/state.json').read_text())['thread'], self.OLD)

    def test_a_failed_registration_leaves_the_previous_owner_so_a_corrected_takeover_succeeds(self):
        def refuse(slot):
            raise ValueError('slot is not held; acquire it before binding a PR')

        with patch.object(runner, 'author_store', side_effect=lambda root, state: self.refusing(root, state, refuse)), \
                self.assertRaisesRegex(ValueError, 'not held'):
            runner.attach_author(self.args(), self.root, self.state)
        self.assertEqual(json.loads((self.root / 'author/state.json').read_text())['thread'], self.OLD)
        self.assertEqual(runner.read(self.root, 'owner/repo#1')['author_delivery']['session'], self.OLD)
        runner.attach_author(self.args(), self.root, runner.read(self.root, 'owner/repo#1'))
        self.assertEqual(json.loads((self.root / 'author/state.json').read_text())['thread'], self.NEW)

    def refusing(self, root, state, register_slot):
        store, module = self.real(root, state)
        store.register_slot = register_slot
        return store, module

    def test_the_same_session_moving_to_another_checkout_needs_a_declared_takeover(self):
        moved = Path(self.temp.name) / 'moved'
        args = SimpleNamespace(author_runtime='codex', author_session=self.OLD, session_remote=None,
                               checkout=moved, slot=None, codex='codex', takeover=False)
        with self.assertRaisesRegex(ValueError, '--takeover'):
            runner.attach_author(args, self.root, self.state)
        registered = []

        def author_store(root, state):
            store, module = self.real(root, state)
            store.register = lambda checkout=None: registered.append(checkout)
            return store, module

        args.takeover = True
        with patch.object(runner, 'author_store', side_effect=author_store):
            runner.attach_author(args, self.root, self.state)
        self.assertEqual(registered, [str(moved.resolve())])
        self.assertIsNone(json.loads((self.root / 'author/state.json').read_text())['target'].get('checkout'))
        self.assertEqual(runner.read(self.root, 'owner/repo#1')['author_delivery']['checkout'], str(moved.resolve()))

    def test_takeover_rebinds_the_ledger_and_keeps_rounds_findings_and_fingerprint(self):
        runner.attach_author(self.args(), self.root, self.state)
        state = runner.read(self.root, 'owner/repo#1')
        self.assertEqual(state['author_delivery']['session'], self.NEW)
        self.assertEqual(state['author_delivery']['slot'], str(self.slot.resolve()))
        self.assertEqual((state['rounds'], state['approved_fingerprint'], state['seen'], state['last_review_url']),
                         (2, 'f' * 40, ['review:1'], 'https://github.com/owner/repo/pull/1#r'))
        self.assertEqual(state['phase'], 'starting')
        self.assertEqual(state['takeovers'][0]['from']['session'], self.OLD)
        ledger = json.loads((self.root / 'author/state.json').read_text())
        self.assertEqual(ledger['thread'], self.NEW)
        self.assertEqual(ledger['target']['events'], {'review:1': {'kind': 'review', 'status': 'handled'}})
        self.assertIsNone(ledger['target'].get('checkout'))
        self.assertIsNone(ledger['target'].get('cleanup'))
        self.assertEqual(ledger['target']['takeovers'][0]['to']['session'], self.NEW)
        self.assertEqual(self.registered, [self.slot])
        store, module = runner.author_store(self.root, state)
        self.assertEqual(store.read()['target']['events'], ledger['target']['events'])


class OwnDiffFingerprintTests(unittest.TestCase):
    def test_merging_the_base_keeps_the_fingerprint_until_own_files_change(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checkout = root / 'checkout'
            checkout.mkdir()

            def git(*arguments):
                return subprocess.run(['git', '-C', str(checkout), '-c', 'user.name=t', '-c', 'user.email=t@t',
                                       *arguments], capture_output=True, text=True, check=True).stdout.strip()

            def commit(name, text):
                (checkout / name).write_text(text)
                git('add', name)
                git('commit', '-qm', name)
                return git('rev-parse', 'HEAD')

            git('init', '-q', '-b', 'main')
            base = commit('shared.txt', 'one')
            git('switch', '-qc', 'work')
            approved = commit('own.txt', 'feature')
            git('switch', '-q', 'main')
            main = commit('other.txt', 'main moved')
            git('switch', '-q', 'work')
            git('merge', '-q', '--no-edit', 'main')
            merged = git('rev-parse', 'HEAD')
            first = runner.own_diff_fingerprint(root, {'base': base, 'head': approved})
            self.assertEqual(runner.own_diff_fingerprint(root, {'base': main, 'head': merged}), first)
            changed = commit('own.txt', 'feature v2')
            self.assertNotEqual(runner.own_diff_fingerprint(root, {'base': main, 'head': changed}), first)

if __name__ == '__main__':
    unittest.main()
