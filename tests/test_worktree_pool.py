import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/project-monitor/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pool = load('worktree_pool')
monitor = load('project_pr_monitor')


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                          capture_output=True, text=True, check=True).stdout.strip()


class PoolFixture(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.remote = self.root / 'remote.git'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(self.remote)], check=True)
        self.primary = self.root / 'App'
        subprocess.run(['git', 'clone', '-q', str(self.remote), str(self.primary)], check=True, capture_output=True)
        (self.primary / 'README').write_text('base\n')
        git(self.primary, 'add', 'README')
        git(self.primary, 'commit', '-qm', 'base')
        git(self.primary, 'push', '-q', 'origin', 'main')
        self.slots = []
        for name in ('slot-1', 'slot-2'):
            path = self.root / 'worktrees' / name
            git(self.primary, 'worktree', 'add', '-q', '--detach', str(path), 'origin/main')
            self.slots.append(path)
        pool.init(self.primary, default='main')
        for path in self.slots:
            pool.add_slot(self.primary, path)

    def tearDown(self):
        self.directory.cleanup()

    def advance_remote(self, name='upstream'):
        other = self.root / ('other-' + name)
        subprocess.run(['git', 'clone', '-q', str(self.remote), str(other)], check=True, capture_output=True)
        (other / name).write_text(name)
        git(other, 'add', name)
        git(other, 'commit', '-qm', name)
        git(other, 'push', '-q', 'origin', 'main')
        return git(other, 'rev-parse', 'HEAD')

    def commit_in(self, path, name):
        (path / name).write_text(name)
        git(path, 'add', name)
        git(path, 'commit', '-qm', name)
        return git(path, 'rev-parse', 'HEAD')


class WorktreePoolTests(PoolFixture):
    def test_slots_are_locked_so_generic_worktree_cleanup_leaves_them(self):
        listing = git(self.primary, 'worktree', 'list', '--porcelain')
        self.assertEqual(listing.count('locked worktree pool slot'), 2)

    def test_acquire_branches_from_the_latest_remote_default_and_fills_slots_in_order(self):
        tip = self.advance_remote()
        first = pool.acquire(self.primary, 'thread-a', 'feature-a')
        second = pool.acquire(self.primary, 'thread-b', 'feature-b')
        self.assertEqual(first['path'], str(self.slots[0]))
        self.assertEqual(second['path'], str(self.slots[1]))
        self.assertEqual(git(self.slots[0], 'rev-parse', 'HEAD'), tip)
        self.assertEqual(git(self.slots[0], 'branch', '--show-current'), 'feature-a')

    def test_a_full_pool_reports_busy_with_its_holders(self):
        pool.acquire(self.primary, 'thread-a', 'feature-a')
        pool.acquire(self.primary, 'thread-b', 'feature-b')
        with self.assertRaises(pool.PoolError) as caught:
            pool.acquire(self.primary, 'thread-c', 'feature-c')
        self.assertEqual(caught.exception.result['status'], 'busy')
        self.assertEqual(set(caught.exception.result['holders'].values()), {'thread-a', 'thread-b'})

    def test_the_same_holder_and_branch_reacquire_their_slot(self):
        first = pool.acquire(self.primary, 'thread-a', 'feature-a')
        again = pool.acquire(self.primary, 'thread-a', 'feature-a')
        self.assertEqual(again['path'], first['path'])
        self.assertTrue(again['reused'])

    def test_a_slot_with_leftover_untracked_files_is_not_handed_out(self):
        (self.slots[0] / 'leftover.log').write_text('earlier task')
        with self.assertRaises(pool.PoolError):
            pool.acquire(self.primary, 'thread-a', 'feature-a', slot=self.slots[0])

    def test_acquire_stops_build_processes_left_running_in_the_slot(self):
        tool = self.root / 'bin' / 'xcodebuild'
        tool.parent.mkdir()
        tool.write_text('#!/bin/bash\nsleep 300 &\nwait\n')
        tool.chmod(0o755)
        stray = subprocess.Popen([str(tool), '-derivedDataPath', str(self.slots[0] / 'build')])
        bystander = subprocess.Popen(['/bin/bash', '-c', 'sleep 300', str(self.slots[0] / 'shell')])
        self.addCleanup(bystander.kill)
        deadline = time.monotonic() + 10
        while not any('sleep 300' in item['command'] for item in pool.slot_processes(self.slots[0])):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.1)
        child = next(item['pid'] for item in pool.slot_processes(self.slots[0]) if item['pid'] != stray.pid)
        result = pool.acquire(self.primary, 'thread-a', 'feature-a', self.slots[0])
        self.assertIn(stray.pid, [item['pid'] for item in result['stopped_processes']])
        self.assertIsNotNone(stray.wait(timeout=5))
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)
        self.assertIsNone(bystander.poll())

    def test_only_build_tools_naming_this_slot_exactly_are_selected(self):
        slot, derived = '/work/slot-1', '/tmp/build-slot-1'
        cases = {
            '/usr/bin/xcodebuild -packagePath /work/slot-1': True,
            '/usr/bin/xcodebuild -derivedDataPath /tmp/build-slot-1/Build': True,
            '/usr/bin/python3 /infra/test-watchdog.py --idle 30 -- swift test --package-path /work/slot-1/Core': True,
            '/usr/bin/vim xcodebuild /work/slot-1/notes': False,
            '/usr/bin/xcodebuild -derivedDataPath /tmp/build-slot-10': False,
            '/usr/bin/xcodebuild -packagePath /work/slot-10': False,
        }
        for command, expected in cases.items():
            self.assertEqual(pool.slot_command(command, [slot, derived]), expected, command)

    def test_release_after_merge_detaches_the_slot_deletes_the_branch_and_frees_it(self):
        pool.acquire(self.primary, 'thread-a', 'feature-a')
        head = self.commit_in(self.slots[0], 'work')
        pool.bind(self.slots[0], self.slots[0], 'o/r#1')
        tip = self.advance_remote('squashed')
        result = pool.release(self.slots[0], self.slots[0], pr='o/r#1', expect_head=head)
        self.assertEqual(result['status'], 'released')
        self.assertTrue(result['branch_deleted'])
        self.assertTrue(self.slots[0].exists())
        self.assertEqual(git(self.slots[0], 'rev-parse', 'HEAD'), tip)
        self.assertEqual(git(self.slots[0], 'branch', '--show-current'), '')
        self.assertEqual(pool.status(self.primary)['free'], sorted(str(p) for p in self.slots))

    def test_release_keeps_a_local_branch_with_commits_beyond_the_pr_head(self):
        pool.acquire(self.primary, 'thread-a', 'feature-a')
        head = self.commit_in(self.slots[0], 'work')
        self.commit_in(self.slots[0], 'unpushed')
        result = pool.release(self.slots[0], self.slots[0], holder='thread-a', expect_head=head)
        self.assertFalse(result['branch_deleted'])
        self.assertIn('feature-a', git(self.primary, 'branch', '--format=%(refname:short)').split())

    def test_release_refuses_uncommitted_changes_and_keeps_the_slot_held(self):
        pool.acquire(self.primary, 'thread-a', 'feature-a')
        (self.slots[0] / 'README').write_text('edited')
        with self.assertRaises(pool.PoolError) as caught:
            pool.release(self.slots[0], self.slots[0], holder='thread-a')
        self.assertEqual(caught.exception.result['status'], 'preserved')
        self.assertNotIn(str(self.slots[0]), pool.status(self.primary)['free'])

    def test_release_needs_the_holder_or_the_bound_pr(self):
        pool.acquire(self.primary, 'thread-a', 'feature-a')
        with self.assertRaises(pool.PoolError):
            pool.release(self.slots[0], self.slots[0], holder='thread-b')

    def test_sync_main_fast_forwards_a_clean_primary_and_leaves_untracked_files(self):
        tip = self.advance_remote()
        (self.primary / 'draft.png').write_text('owner file')
        result = pool.sync_main(self.primary)
        self.assertEqual(result['status'], 'synced')
        self.assertEqual(git(self.primary, 'rev-parse', 'HEAD'), tip)
        self.assertTrue((self.primary / 'draft.png').exists())

    def test_sync_main_skips_a_primary_with_uncommitted_changes(self):
        before = git(self.primary, 'rev-parse', 'HEAD')
        self.advance_remote()
        (self.primary / 'README').write_text('owner edit')
        result = pool.sync_main(self.primary)
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(git(self.primary, 'rev-parse', 'HEAD'), before)
        self.assertEqual((self.primary / 'README').read_text(), 'owner edit')

    def test_main_serves_as_overflow_and_sync_skips_it_until_released(self):
        pool.acquire(self.primary, 'thread-a', 'feature-a')
        pool.acquire(self.primary, 'thread-b', 'feature-b')
        overflow = pool.acquire(self.primary, 'thread-c', 'feature-c', main=True)
        self.assertEqual(overflow['slot'], 'main')
        self.assertEqual(pool.sync_main(self.primary)['status'], 'skipped')
        head = self.commit_in(self.primary, 'urgent')
        tip = self.advance_remote()
        result = pool.release(self.primary, self.primary, holder='thread-c', expect_head=head)
        self.assertEqual(result['main_sync'], 'synced')
        self.assertEqual(git(self.primary, 'branch', '--show-current'), 'main')
        self.assertEqual(git(self.primary, 'rev-parse', 'HEAD'), tip)

    def test_sync_main_runs_prepare_and_starts_warm_only_when_main_moved(self):
        pool.init(self.primary, prepare='true', warm='true')
        self.assertNotIn('warm', pool.sync_main(self.primary))
        self.advance_remote()
        result = pool.sync_main(self.primary)
        self.assertEqual(result['prepare']['exit'], 0)
        self.assertIn('pid', result['warm'])


class ProjectMonitorTests(PoolFixture):
    def store(self):
        root = self.root / 'state'
        store = monitor.ProjectStore(root, 'session', 'o/r#1', monitor.claude.Runtime('session', monitor.__file__))
        pool.acquire(self.primary, 'thread-a', 'feature-a')
        self.head = self.commit_in(self.slots[0], 'work')
        with patch.object(monitor.core, 'gh_json', return_value=dict(user=dict(login='bot'), head=dict(ref='feature-a'))):
            store.register_slot(self.slots[0])
        return store

    def terminal(self, outcome):
        event = monitor.core.event('terminal', 1, [outcome, 't', 't'], 'url', outcome=outcome, head=self.head)
        return dict(events=[event], terminal=outcome, head=self.head, ci=None, ci_version=None, url='url', pr={})

    def test_a_merged_pr_releases_its_slot_syncs_main_and_tells_the_thread(self):
        store = self.store()
        self.advance_remote('squashed')
        store.apply(self.terminal('merged'))
        target = store.read()['target']
        self.assertEqual(target['cleanup_result']['status'], 'released')
        self.assertEqual(target['cleanup_result']['main']['status'], 'synced')
        self.assertTrue(self.slots[0].exists())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(store.deliver())
        self.assertIn('alex-coding:project-monitor', output.getvalue())
        self.assertIn('Tell the project coordinator this slot is free', output.getvalue())
        self.assertIsNone(store.read()['batch'])

    def test_a_closed_pr_also_releases_its_slot(self):
        store = self.store()
        store.apply(self.terminal('closed'))
        self.assertEqual(store.read()['target']['cleanup_result']['status'], 'released')
        self.assertIn(str(self.slots[0]), pool.status(self.primary)['free'])

    def test_feedback_and_the_release_reach_the_thread_without_any_acknowledgement(self):
        store = self.store()
        event = monitor.core.event('conversation', 1, 'v1', 'url')
        with store.locked() as data:
            data['target']['events'][event['key']] = dict(event, status='pending')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(store.deliver())
        self.assertIsNone(store.read()['batch'])
        self.assertNotIn(' ack ', output.getvalue())
        store.apply(self.terminal('closed'))
        self.assertEqual(store.read()['target']['cleanup_result']['status'], 'released')
        self.assertIn(str(self.slots[0]), pool.status(self.primary)['free'])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(store.deliver())
        self.assertIn('Tell the project coordinator this slot is free', output.getvalue())
        with patch.object(monitor.core, 'snapshot') as snapshot:
            self.assertTrue(monitor.core.poll(store))
        snapshot.assert_not_called()

    def test_a_failed_release_is_reported_and_complete_retries_it(self):
        store = self.store()
        (self.slots[0] / 'README').write_text('uncommitted')
        store.apply(self.terminal('merged'))
        self.assertEqual(store.read()['target']['cleanup_result']['status'], 'preserved')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            store.deliver()
        self.assertIn('complete', output.getvalue())
        git(self.slots[0], 'checkout', 'README')
        with patch.object(monitor.core, 'snapshot', return_value=self.terminal('merged')):
            self.assertEqual(store.complete()['status'], 'released')


class CodexProjectMonitorTests(ProjectMonitorTests):
    THREAD = '00000000-0000-0000-0000-000000000001'

    def setUp(self):
        super().setUp()
        self.queued = []
        patcher = patch.object(monitor.codex.transport, 'queue_message',
                               side_effect=lambda executable, thread, message: self.queued.append(message))
        patcher.start()
        self.addCleanup(patcher.stop)

    def store(self):
        root = self.root / 'state'
        runtime = monitor.slot_runtime('codex', self.THREAD, monitor.__file__, executable='/bin/codex')
        store = monitor.ProjectStore(root, self.THREAD, 'o/r#1', runtime)
        pool.acquire(self.primary, 'thread-a', 'feature-a')
        self.head = self.commit_in(self.slots[0], 'work')
        with patch.object(monitor.core, 'gh_json', return_value=dict(user=dict(login='bot'), head=dict(ref='feature-a'))):
            store.register_slot(self.slots[0])
        return store

    def delivered(self, store):
        before = len(self.queued)
        self.assertTrue(store.deliver())
        self.assertEqual(len(self.queued), before + 1)
        return self.queued[-1]

    def test_a_merged_pr_releases_its_slot_syncs_main_and_tells_the_thread(self):
        store = self.store()
        self.advance_remote('squashed')
        store.apply(self.terminal('merged'))
        target = store.read()['target']
        self.assertEqual(target['cleanup_result']['status'], 'released')
        self.assertEqual(target['cleanup_result']['main']['status'], 'synced')
        self.assertTrue(self.slots[0].exists())
        message = self.delivered(store)
        self.assertIn('alex-coding:project-monitor', message)
        self.assertIn('Tell the project coordinator this slot is free', message)
        self.assertIsNone(store.read()['batch'])

    def test_feedback_and_the_release_reach_the_thread_without_any_acknowledgement(self):
        store = self.store()
        event = monitor.core.event('conversation', 1, 'v1', 'url')
        with store.locked() as data:
            data['target']['events'][event['key']] = dict(event, status='pending')
        self.assertNotIn(' ack ', self.delivered(store))
        self.assertIsNone(store.read()['batch'])
        store.apply(self.terminal('closed'))
        self.assertEqual(store.read()['target']['cleanup_result']['status'], 'released')
        self.assertIn(str(self.slots[0]), pool.status(self.primary)['free'])
        self.assertIn('Tell the project coordinator this slot is free', self.delivered(store))

    def test_a_failed_release_is_reported_and_complete_retries_it(self):
        store = self.store()
        (self.slots[0] / 'README').write_text('uncommitted')
        store.apply(self.terminal('merged'))
        self.assertEqual(store.read()['target']['cleanup_result']['status'], 'preserved')
        message = self.delivered(store)
        self.assertIn('--thread ' + self.THREAD, message)
        self.assertIn('tell the project coordinator', message)
        store.apply(self.terminal('merged'))
        self.assertEqual(store.read()['target']['cleanup_result']['status'], 'preserved')
        self.assertNotIn(str(self.slots[0]), pool.status(self.primary)['free'])
        git(self.slots[0], 'checkout', 'README')
        with patch.object(monitor.core, 'snapshot', return_value=self.terminal('merged')):
            self.assertEqual(store.complete()['status'], 'released')


if __name__ == '__main__':
    unittest.main()
