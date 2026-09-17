from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import test_postmerge_cleanup as fixtures

cleanup = fixtures.cleanup


class DisposableWorktreeTests(unittest.TestCase):
    git = fixtures.CleanupTests.git
    run_command = fixtures.CleanupTests.run_command
    clean = fixtures.CleanupTests.clean
    advance_remote = fixtures.CleanupTests.advance_remote
    squash_merge = fixtures.CleanupTests.squash_merge

    def setUp(self):
        fixtures.CleanupTests.setUp(self)
        self.target['cleanup']['lifecycle'] = 'disposable-v1'
        self.pr['base']['ref'] = 'main'

    def test_merged_worktree_is_removed_with_all_residual_files(self):
        self.git(self.checkout, 'config', 'core.excludesfile', str(self.root / 'ignore'))
        (self.root / 'ignore').write_text('node_modules/\n')
        (self.checkout / 'node_modules').mkdir()
        (self.checkout / 'node_modules/arbitrary.data').write_text('generated')
        (self.checkout / 'untracked.txt').write_text('discard')
        (self.checkout / 'staged.txt').write_text('discard')
        self.git(self.checkout, 'add', 'staged.txt')
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertFalse(self.checkout.exists())
        self.assertEqual(self.git(self.repo, 'rev-parse', 'origin/main'), self.head)
        self.assertNotIn('feature', self.git(self.repo, 'branch', '--format=%(refname:short)').split())

    def test_default_sync_overwrites_local_changes_and_collisions(self):
        tip = self.advance_remote()
        (self.repo / 'new-file').mkdir()
        (self.repo / 'new-file/cache').write_text('local collision')
        (self.repo / 'staged').write_text('discard')
        self.git(self.repo, 'add', 'staged')
        self.git(self.repo, 'commit', '-m', 'local default divergence')
        (self.repo / 'staged').write_text('local edit')
        (self.repo / '.semina').mkdir()
        (self.repo / '.semina/record').write_text('persistent project data')
        (self.repo / '.env').write_text('persistent configuration')
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)
        self.assertEqual((self.repo / 'new-file').read_text(), 'remote content')
        self.assertFalse((self.repo / 'staged').exists())
        self.assertEqual((self.repo / '.semina/record').read_text(), 'persistent project data')
        self.assertEqual((self.repo / '.env').read_text(), 'persistent configuration')
        self.assertFalse(self.checkout.exists())

    def test_sync_failure_does_not_block_deletion_and_can_be_retried(self):
        tip = self.advance_remote()
        original = cleanup._git

        def fail_fetch(path, *args):
            if args[0] == 'fetch':
                raise subprocess.CalledProcessError(1, args, stderr='offline')
            return original(path, *args)

        with patch.object(cleanup, '_git', side_effect=fail_fetch):
            result = self.clean()
        self.assertEqual(result['status'], 'partial', result)
        self.assertEqual(result['cleanup']['status'], 'cleaned')
        self.assertEqual(result['sync']['status'], 'failed')
        self.assertFalse(self.checkout.exists())
        self.assertNotEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)

    def test_squash_merge_does_not_require_original_head_ancestry(self):
        tip = self.squash_merge()
        (self.checkout / 'leftover').write_text('discard')
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertFalse(self.checkout.exists())
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)

    def test_completed_worktree_cwd_does_not_prevent_disposal(self):
        with patch.object(cleanup, '_process_cwds', return_value=[(42, self.checkout)]):
            result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertFalse(self.checkout.exists())

    def test_different_pr_base_never_authorizes_disposal(self):
        self.pr['base']['ref'] = 'release'
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_new_commits_after_merge_are_another_delivery(self):
        self.git(self.checkout, 'commit', '--allow-empty', '-m', 'next delivery')
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_unmerged_pr_is_never_disposed(self):
        self.pr['merged'] = False
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_creation_uses_the_synchronized_main_or_master(self):
        for default in ('main', 'master'):
            with self.subTest(default=default):
                if default == 'master':
                    self.git(self.repo, 'branch', '-m', 'main', 'master')
                    self.git(self.repo, 'push', 'origin', 'master')
                self.git(self.remote, 'symbolic-ref', 'HEAD', 'refs/heads/' + default)
                destination = self.root / ('new-' + default)
                created = cleanup.lifecycle.create_worktree(self.repo, destination, 'task-' + default)
                self.assertEqual(created['base_sha'], self.git(self.repo, 'rev-parse', default))
                self.assertEqual(self.git(destination, 'rev-parse', 'HEAD'), created['base_sha'])
                self.assertEqual(self.git(destination, 'status', '--porcelain'), '')

    def test_two_successive_deliveries_create_merge_sync_and_dispose(self):
        self.git(self.remote, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        writer = self.root / 'integration'
        self.git(self.root, 'clone', str(self.remote), str(writer))
        self.git(writer, 'config', 'user.name', 'Test')
        self.git(writer, 'config', 'user.email', 'test@example.invalid')
        for index in (1, 2):
            branch = f'delivery-{index}'
            destination = self.root / branch
            previous = self.git(self.repo, 'rev-parse', 'HEAD')
            created = cleanup.lifecycle.create_worktree(self.repo, destination, branch)
            self.assertEqual(created['base_sha'], previous)
            (destination / 'shared-source').write_text(f'delivery {index}')
            self.git(destination, 'add', 'shared-source')
            self.git(destination, 'commit', '-m', branch)
            self.head = self.git(destination, 'rev-parse', 'HEAD')
            self.git(destination, 'push', 'origin', branch)
            self.git(writer, 'fetch', 'origin', branch)
            self.git(writer, 'merge', '--squash', 'FETCH_HEAD')
            self.git(writer, 'commit', '-m', f'{branch} merged')
            self.git(writer, 'push', 'origin', 'main')
            merged = self.git(writer, 'rev-parse', 'HEAD')
            self.checkout = destination
            self.target.update(checkout=str(destination), head_branch=branch)
            self.pr['head'].update(sha=self.head, ref=branch)
            self.pr['merge_commit_sha'] = merged
            self.branch_info['name'] = branch
            (destination / 'shared-source').write_text('post-merge residue')
            (destination / 'untracked').write_text('discard')
            result = self.clean()
            self.assertEqual(result['status'], 'cleaned', result)
            self.assertFalse(destination.exists())
            self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), merged)
            self.assertEqual((self.repo / 'shared-source').read_text(), f'delivery {index}')

    def test_failed_fetch_never_creates_from_cached_default(self):
        self.git(self.remote, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        original = cleanup.lifecycle.git

        def fail_fetch(path, *args):
            if args[0] == 'fetch':
                raise subprocess.CalledProcessError(1, args)
            return original(path, *args)

        destination = self.root / 'must-not-exist'
        with patch.object(cleanup.lifecycle, 'git', side_effect=fail_fetch):
            with self.assertRaises(subprocess.CalledProcessError):
                cleanup.lifecycle.create_worktree(self.repo, destination, 'not-created')
        self.assertFalse(destination.exists())
        self.assertNotIn('not-created', self.git(self.repo, 'branch', '--format=%(refname:short)').split())

    def test_creation_rejects_nested_worktree_destinations(self):
        self.git(self.remote, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        for parent in (self.repo, self.checkout):
            with self.assertRaisesRegex(ValueError, 'inside another registered worktree'):
                cleanup.lifecycle.create_worktree(self.repo, parent / 'nested-task', 'nested-task')
            self.assertFalse((parent / 'nested-task').exists())

    def test_nested_delivery_is_never_deleted_with_its_parent(self):
        nested = self.checkout / 'another-delivery'
        self.git(self.repo, 'worktree', 'add', '-b', 'nested', str(nested))
        (nested / 'valuable').write_text('another task')
        result = self.clean()
        self.assertEqual(result['status'], 'preserved', result)
        self.assertEqual((nested / 'valuable').read_text(), 'another task')
        self.assertTrue(self.checkout.exists())

    def test_branch_switch_during_fetch_does_not_reset_another_branch(self):
        self.advance_remote()
        original = cleanup._git

        def switch_after_fetch(path, *args):
            value = original(path, *args)
            if args[0] == 'fetch':
                self.git(self.repo, 'switch', '-c', 'concurrent-work')
            return value

        before = self.git(self.repo, 'rev-parse', 'HEAD')
        with patch.object(cleanup, '_git', side_effect=switch_after_fetch):
            result = self.clean()
        self.assertEqual(result['sync']['status'], 'failed', result)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'concurrent-work'), before)
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'concurrent-work')
        self.assertFalse(self.checkout.exists())

    def test_index_lock_prevents_a_branch_switch_during_source_synchronization(self):
        tip = self.advance_remote()
        self.git(self.repo, 'branch', 'other')
        original = cleanup._git
        attempted = False

        def try_switch_in_critical_section(path, *args):
            nonlocal attempted
            if args[0] == 'update-ref' and args[1] == 'refs/heads/main':
                attempted = True
                with self.assertRaises(subprocess.CalledProcessError):
                    self.git(self.repo, 'switch', 'other')
            return original(path, *args)

        with patch.object(cleanup, '_git', side_effect=try_switch_in_critical_section):
            result = self.clean()
        self.assertTrue(attempted)
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)

    def test_killed_synchronization_recovers_its_owned_index_lock(self):
        tip = self.advance_remote()
        marker = self.root / 'interrupted-after-checkout'
        script = f'''
import importlib.util,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('lifecycle',{str(Path(cleanup.__file__).with_name('worktree_lifecycle.py'))!r})
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def pause(path,*args):
    if args[0]=='update-ref':
        Path({str(marker)!r}).write_text('ready')
        time.sleep(60)
    return module.git(path,*args)
module.synchronize(Path({str(self.repo)!r}),'origin','main',pause)
'''
        process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if marker.exists() or process.poll() is not None:
                    break
                time.sleep(.05)
            self.assertTrue(marker.exists())
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        self.assertTrue((self.repo / '.git/index.lock').exists())
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertFalse((self.repo / '.git/index.lock').exists())
        self.assertFalse(self.checkout.exists())
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)
        self.assertEqual(self.git(self.repo, 'status', '--porcelain'), '')

    def test_an_unowned_git_lock_is_preserved_and_reported(self):
        (self.repo / '.git/index.lock').write_bytes(b'Unrelated Git operation')
        result = self.clean()
        self.assertEqual(result['status'], 'partial', result)
        self.assertFalse(result['retryable'])
        self.assertEqual((self.repo / '.git/index.lock').read_bytes(), b'Unrelated Git operation')
        self.assertFalse(self.checkout.exists())
