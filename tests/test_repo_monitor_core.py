import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'repo_monitor_core',
    Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/review/scripts/repo_monitor_core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def row(**values):
    return dict(dict(number=1, url='https://example/pr/1', head='a', draft=False, ci='pending',
                     approved=False, reply=None), **values)


@contextlib.contextmanager
def watch(deliver=None, role=None, reviewer='reviewer'):
    delivered = []

    def default(message):
        delivered.append(message)
        return True

    with tempfile.TemporaryDirectory() as directory:
        subject = core.Watch('owner/repo', 'identity-one', reviewer, directory,
                             deliver or default, ['--identity', 'identity-one'], role=role)
        subject.delivered = delivered
        yield subject


class RoleSelectionTests(unittest.TestCase):
    def test_no_role_uses_plain_gh(self):
        self.assertEqual(core.gh_command(None), ['gh'])

    def test_a_role_prefixes_the_role_tool(self):
        with patch.object(core.shutil, 'which', return_value='/path/gh_as'):
            self.assertEqual(core.gh_command('admin'), ['/path/gh_as', 'admin'])

    def test_a_missing_role_tool_is_fatal_rather_than_falling_back(self):
        with patch.object(core.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError) as failure:
                core.gh_command('admin')
        self.assertIn('refusing to fall back', str(failure.exception))

    def test_the_role_reaches_every_github_read(self):
        with patch.object(core, 'gh_command', return_value=['gh_as', 'admin']) as selector, \
             patch.object(core.subprocess, 'run') as run:
            run.return_value.stdout = ''
            core.snapshot('owner/repo', 'reviewer', 'admin')
        selector.assert_called_once_with('admin')
        self.assertEqual(run.call_args[0][0][:2], ['gh_as', 'admin'])


class EventSelectionTests(unittest.TestCase):
    def test_ready_pull_requests_produce_events_and_drafts_stay_quiet(self):
        self.assertTrue(core.changes({}, {'1': row()}))
        self.assertFalse(core.changes({}, {'1': row(draft=True)}))
        self.assertTrue(core.changes({'1': row(draft=True)}, {'1': row()}))

    def test_a_queued_or_reviewing_claim_suppresses_every_other_event(self):
        for phase in core.CLAIMED:
            reviews = {'1': {'head': 'a', 'phase': phase}}
            self.assertFalse(core.changes({'1': row()}, {'1': row(ci='pass'), '2': row(number=2)}, reviews))
            self.assertFalse(core.changes({'1': row()}, {'1': row(head='b')}, reviews))

    def test_findings_and_completed_reviews_ignore_check_changes(self):
        for phase in ('changes-requested', 'done'):
            reviews = {'1': {'head': 'a', 'phase': phase}}
            for ci in ('pass', 'fail'):
                self.assertFalse(core.changes({'1': row()}, {'1': row(ci=ci)}, reviews))
            self.assertTrue(core.changes({'1': row(head='b')}, {'1': row(head='b')}, reviews))

    def test_only_waiting_checks_wake_on_a_changed_terminal_result(self):
        reviews = {'1': {'head': 'a', 'phase': 'waiting-ci', 'ci': 'fail'}}
        self.assertFalse(core.changes({}, {'1': row(ci='fail')}, reviews))
        self.assertFalse(core.changes({}, {'1': row(ci='pending')}, reviews))
        self.assertEqual(core.changes({}, {'1': row(ci='pass')}, reviews)[0]['reason'], 'ci-pass')

    def test_current_head_approval_stays_quiet(self):
        self.assertFalse(core.changes({}, {'1': row(approved=True)}))
        self.assertTrue(core.changes({}, {'1': row(approved=False)}))

    def test_approval_counts_only_for_the_configured_reviewer_and_exact_head(self):
        approve = [{'user': 'Reviewer', 'state': 'APPROVED', 'commit_id': 'a'}]
        self.assertTrue(core.approved_head(approve, 'a', 'reviewer'))
        self.assertFalse(core.approved_head(approve, 'b', 'reviewer'))
        self.assertFalse(core.approved_head(approve, 'a', 'someone'))
        self.assertFalse(core.approved_head(approve + [{'user': 'reviewer', 'state': 'CHANGES_REQUESTED', 'commit_id': 'a'}], 'a', 'reviewer'))


class ReconciliationTests(unittest.TestCase):
    def test_a_closed_pull_request_releases_its_claim(self):
        reviews = {'1': {'head': 'a', 'phase': 'reviewing'}}
        core.reconcile_reviews(reviews, {})
        self.assertEqual(reviews['1']['phase'], 'done')

    def test_waiting_checks_are_released_only_once_they_pass(self):
        reviews = {'1': {'head': 'a', 'phase': 'waiting-ci', 'ci': 'pending'}}
        core.reconcile_reviews(reviews, {'1': row(approved=True, ci='pending')})
        self.assertEqual(reviews['1']['phase'], 'waiting-ci')
        core.reconcile_reviews(reviews, {'1': row(approved=True, ci='pass')})
        self.assertEqual(reviews['1']['phase'], 'done')


class MessageTests(unittest.TestCase):
    def test_acknowledgement_instructions_precede_the_pull_request_rows(self):
        message = core.build_message('owner/repo', [row(reason='new-pr-or-head')], 'CMD')
        self.assertLess(message.index('--phase reviewing'), message.index('https://example/pr/1'))

    def test_the_publication_rule_is_present(self):
        message = core.build_message('owner/repo', [row(reason='new-pr-or-head')], 'CMD')
        self.assertIn('Publish the head-bound formal review', message)
        self.assertIn('If publication fails, retain the reviewing claim', message)

    def test_every_dispatched_pull_request_is_listed(self):
        message = core.build_message('owner/repo', [row(reason='new-pr-or-head'), row(number=2, url='https://example/pr/2', head='b', ci='fail', reason='ci-fail')], 'CMD')
        self.assertIn('https://example/pr/1 head=a event=new-pr-or-head ci=pending', message)
        self.assertIn('https://example/pr/2 head=b event=ci-fail ci=fail', message)

    def test_the_acknowledgement_command_carries_the_watch_identity_and_state(self):
        with watch() as subject:
            command = core.ack_command('/scripts/monitor.py', subject)
        self.assertIn('owner/repo', command)
        self.assertIn('--identity identity-one', command)
        self.assertIn('--state-dir', command)


class DispatchTests(unittest.TestCase):
    def test_a_delivered_batch_claims_every_pull_request_as_queued(self):
        with watch() as subject:
            reviews = {}
            self.assertTrue(core.dispatch(subject, '/scripts/monitor.py', [row(reason='new-pr-or-head')], reviews))
            self.assertEqual({k: reviews['1'][k] for k in ('head', 'phase', 'ci')},
                         {'head': 'a', 'phase': 'queued', 'ci': 'pending'})
            self.assertEqual(json.loads((subject.root / 'reviews.json').read_text()), reviews)
            self.assertEqual(len(subject.delivered), 1)

    def test_a_refused_delivery_claims_nothing(self):
        with watch(deliver=lambda message: False) as subject:
            reviews = {}
            self.assertFalse(core.dispatch(subject, '/scripts/monitor.py', [row(reason='new-pr-or-head')], reviews))
            self.assertEqual(reviews, {})
            self.assertFalse((subject.root / 'reviews.json').exists())

    def test_the_whole_batch_reaches_delivery_as_one_message(self):
        with watch() as subject:
            core.dispatch(subject, '/scripts/monitor.py', [row(reason='new-pr-or-head'), row(number=2, url='https://example/pr/2', reason='ci-fail')], {})
            self.assertEqual(len(subject.delivered), 1)
            self.assertEqual(subject.delivered[0].count('https://example/pr/'), 2)


class AcknowledgementTests(unittest.TestCase):
    def test_recording_a_phase_persists_it_for_the_next_poll(self):
        with watch() as subject, contextlib.redirect_stdout(io.StringIO()):
            core.acknowledge(subject.root, 1, 'a' * 40, 'changes-requested', None)
            stored = core.read_reviews(subject.root)
        self.assertEqual({k: stored['1'][k] for k in ('head', 'phase', 'ci')},
                         {'head': 'a' * 40, 'phase': 'changes-requested', 'ci': None})
        self.assertIn('claimed', stored['1'])
        self.assertFalse(core.changes({}, {'1': row(head='a' * 40, ci='fail')}, stored))


class IdentityTests(unittest.TestCase):
    def test_state_bound_to_another_identity_is_refused(self):
        with watch() as subject:
            subject.bind_identity('session', lambda message: self.fail(message))
            rival = core.Watch('owner/repo', 'identity-two', 'reviewer', subject.root,
                               subject.deliver, [], role=None)
            errors = []
            rival.bind_identity('session', errors.append)
        self.assertEqual(len(errors), 1)
        self.assertIn('different repository', errors[0])

    def test_each_repository_and_identity_gets_its_own_default_directory(self):
        first = core.default_root('NOT_SET', '.claude', 'owner/repo', 'one')
        second = core.default_root('NOT_SET', '.claude', 'owner/repo', 'two')
        other = core.default_root('NOT_SET', '.claude', 'owner/other', 'one')
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertEqual(first.parent, second.parent)


class ChecksTests(unittest.TestCase):
    def test_rollup_collapses_to_one_verdict(self):
        self.assertEqual(core.checks_state([]), 'none')
        self.assertEqual(core.checks_state([{'status': 'COMPLETED', 'conclusion': 'SUCCESS'}]), 'pass')
        self.assertEqual(core.checks_state([{'status': 'COMPLETED', 'conclusion': 'FAILURE'}]), 'fail')
        self.assertEqual(core.checks_state([{'status': 'IN_PROGRESS'}, {'status': 'COMPLETED', 'conclusion': 'FAILURE'}]), 'pending')
        self.assertEqual(core.checks_state([{'__typename': 'StatusContext', 'state': 'ERROR'}]), 'fail')


class HealthTests(unittest.TestCase):
    def test_repeated_identical_failures_notify_once_and_recovery_notifies_once(self):
        with watch() as subject:
            health = core.Health()
            with contextlib.redirect_stdout(io.StringIO()) as failing:
                for _ in range(3):
                    subject.note('poll/delivery failed: OSError; retry next cycle')
                    health.observe(subject, 'poll/delivery failed: OSError; retry next cycle')
            self.assertEqual(failing.getvalue().count('poll/delivery failed'), 1)
            self.assertEqual((subject.root / 'monitor.log').read_text().count('poll/delivery failed'), 3)
            with contextlib.redirect_stdout(io.StringIO()) as recovered:
                health.observe(subject, None)
            self.assertIn('monitor recovered', recovered.getvalue())


class PollTests(unittest.TestCase):
    def test_a_failing_snapshot_is_logged_and_the_old_state_is_retained(self):
        with watch() as subject:
            old = {'1': row()}
            with patch.object(core, 'snapshot', side_effect=RuntimeError('offline')), \
                 contextlib.redirect_stdout(io.StringIO()):
                result = core.poll(subject, '/scripts/monitor.py', old, core.Health())
            self.assertEqual(result, old)
            self.assertIn('poll/delivery failed', (subject.root / 'monitor.log').read_text())

    def test_a_refused_delivery_does_not_advance_the_baseline(self):
        with watch(deliver=lambda message: False) as subject:
            with patch.object(core, 'snapshot', return_value={'1': row()}), \
                 contextlib.redirect_stdout(io.StringIO()):
                result = core.poll(subject, '/scripts/monitor.py', None, core.Health())
            self.assertEqual(result, {})

    def test_a_delivered_batch_advances_the_baseline_and_claims_the_pull_request(self):
        with watch() as subject:
            with patch.object(core, 'snapshot', return_value={'1': row()}), \
                 contextlib.redirect_stdout(io.StringIO()):
                result = core.poll(subject, '/scripts/monitor.py', None, core.Health())
            self.assertIn('1', result)
            self.assertEqual(core.read_reviews(subject.root)['1']['phase'], 'queued')


if __name__ == '__main__':
    unittest.main()


class StartupPreflightTests(unittest.TestCase):
    def test_run_refuses_before_the_banner_when_the_role_tool_is_missing(self):
        with watch(role='admin') as subject, patch.object(core.shutil, 'which', return_value=None), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(RuntimeError):
                core.run(subject, '/scripts/monitor.py', 'started', once=True)
        self.assertEqual(output.getvalue(), '')
        self.assertFalse((subject.root / 'watch.pid').exists())

    def test_run_starts_when_the_role_tool_is_present(self):
        with watch(role='admin') as subject, patch.object(core.shutil, 'which', return_value='/path/gh_as'), \
             patch.object(core, 'snapshot', return_value={}), contextlib.redirect_stdout(io.StringIO()) as output:
            core.run(subject, '/scripts/monitor.py', 'started', once=True)
        self.assertIn('started', output.getvalue())


class AuthorReplyTests(unittest.TestCase):
    def held(self, phase='changes-requested', claimed='2026-01-01T00:00:00Z', **extra):
        return {'1': dict({'head': 'a', 'phase': phase, 'ci': None, 'claimed': claimed}, **extra)}

    def test_a_reply_after_the_claim_wakes_a_held_review(self):
        events = core.changes({}, {'1': row(reply='2026-01-01T00:00:01Z')}, self.held())
        self.assertEqual(events[0]['reason'], 'author-reply')

    def test_a_reply_from_before_the_claim_stays_quiet(self):
        self.assertFalse(core.changes({}, {'1': row(reply='2025-12-31T23:59:59Z')}, self.held()))

    def test_no_reply_stays_quiet(self):
        self.assertFalse(core.changes({}, {'1': row()}, self.held()))

    def test_a_waiting_ci_claim_also_wakes_on_a_reply(self):
        events = core.changes({}, {'1': row(reply='2026-01-01T00:00:01Z', ci='pending')},
                              self.held('waiting-ci', ci='pending'))
        self.assertEqual(events[0]['reason'], 'author-reply')

    def test_a_queued_or_reviewing_claim_still_suppresses_replies(self):
        for phase in core.CLAIMED:
            self.assertFalse(core.changes({}, {'1': row(reply='2026-01-01T00:00:01Z')}, self.held(phase)))

    def test_a_done_claim_is_not_woken_by_a_reply(self):
        self.assertFalse(core.changes({}, {'1': row(reply='2026-01-01T00:00:01Z', approved=True)}, self.held('done')))

    def test_the_reviewers_own_comments_are_never_collected(self):
        rows = ['{"user": "Reviewer", "at": "2026-01-02T00:00:00Z"}', '{"user": "author", "at": "2026-01-01T00:00:00Z"}']
        with patch.object(core.subprocess, 'run') as run:
            run.return_value.stdout = '\n'.join(rows)
            newest = core.latest_reply('owner/repo', 1, 'reviewer', ['gh'])
        self.assertEqual(newest, '2026-01-01T00:00:00Z')

    def test_both_comment_endpoints_are_read(self):
        with patch.object(core.subprocess, 'run') as run:
            run.return_value.stdout = ''
            core.latest_reply('owner/repo', 1, 'reviewer', ['gh'])
        endpoints = [call[0][0][3] for call in run.call_args_list]
        self.assertTrue(any('/issues/1/comments' in e for e in endpoints))
        self.assertTrue(any('/pulls/1/comments' in e for e in endpoints))

    def test_a_claim_records_when_it_was_made(self):
        with watch() as subject, contextlib.redirect_stdout(io.StringIO()):
            core.acknowledge(subject.root, 1, 'a' * 40, 'changes-requested', None)
            self.assertIn('claimed', core.read_reviews(subject.root)['1'])
            reviews = {}
            core.dispatch(subject, '/s.py', [row(reason='new-pr-or-head')], reviews)
            self.assertIn('claimed', reviews['1'])

    def test_a_reply_between_publication_and_the_final_acknowledgement_survives(self):
        with watch() as subject, contextlib.redirect_stdout(io.StringIO()), \
             patch.object(core, 'now', side_effect=['2026-01-01T19:00:00Z', '2026-01-01T19:02:00Z']):
            core.acknowledge(subject.root, 1, 'a', 'reviewing', None)
            core.acknowledge(subject.root, 1, 'a', 'changes-requested', None)
            stored = core.read_reviews(subject.root)
        self.assertEqual(stored['1']['claimed'], '2026-01-01T19:00:00Z')
        events = core.changes({}, {'1': row(reply='2026-01-01T19:01:59Z')}, stored)
        self.assertEqual(events[0]['reason'], 'author-reply')

    def test_a_new_head_starts_a_fresh_claim_window(self):
        with watch() as subject, contextlib.redirect_stdout(io.StringIO()), \
             patch.object(core, 'now', side_effect=['2026-01-01T19:00:00Z', '2026-01-01T19:05:00Z']):
            core.acknowledge(subject.root, 1, 'a', 'changes-requested', None)
            core.acknowledge(subject.root, 1, 'b', 'reviewing', None)
            stored = core.read_reviews(subject.root)
        self.assertEqual(stored['1']['claimed'], '2026-01-01T19:05:00Z')
