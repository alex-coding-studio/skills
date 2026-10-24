import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
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

    def test_a_closed_pr_also_releases_its_slot(self):
        store = self.store()
        store.apply(self.terminal('closed'))
        self.assertEqual(store.read()['target']['cleanup_result']['status'], 'released')
        self.assertIn(str(self.slots[0]), pool.status(self.primary)['free'])

    def test_closed_pr_waits_for_active_feedback_then_releases_its_slot(self):
        store = self.store()
        event = monitor.core.event('conversation', 1, 'v1', 'url')
        with store.locked() as data:
            data['target']['events'][event['key']] = dict(event, status='pending')
        with contextlib.redirect_stdout(io.StringIO()):
            store.deliver()
        token = store.read()['batch']['token']
        store.apply(self.terminal('closed'))
        with patch.object(monitor.core, 'snapshot') as snapshot:
            self.assertFalse(monitor.core.poll(store))
        snapshot.assert_not_called()
        with patch.object(monitor.core, 'snapshot', return_value=self.terminal('closed')) as snapshot, \
             contextlib.redirect_stdout(io.StringIO()):
            store.acknowledge(token)
        snapshot.assert_called_once()
        self.assertEqual(store.read()['target']['cleanup_result']['status'], 'released')
        self.assertIn(str(self.slots[0]), pool.status(self.primary)['free'])
        self.assertIsNotNone(store.read()['batch'])
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


if __name__ == '__main__':
    unittest.main()
