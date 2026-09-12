import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/monitor/scripts/postmerge_cleanup.py'
spec = importlib.util.spec_from_file_location('postmerge_cleanup', MODULE)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


PROCESS_CWDS = cleanup._process_cwds


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'primary repo'
        self.remote = self.root / 'remote.git'
        self.git(self.root, 'init', '--bare', str(self.remote))
        self.git(self.root, 'init', '-b', 'main', str(self.repo))
        self.git(self.repo, 'config', 'user.name', 'Test')
        self.git(self.repo, 'config', 'user.email', 'test@example.com')
        self.git(self.repo, 'commit', '--allow-empty', '-m', 'base')
        self.git(self.repo, 'remote', 'add', 'origin', str(self.remote))
        self.git(self.repo, 'push', 'origin', 'main')
        self.checkout = self.root / 'owned worktree'
        self.git(self.repo, 'worktree', 'add', '-b', 'feature', str(self.checkout))
        self.git(self.checkout, 'commit', '--allow-empty', '-m', 'feature')
        self.head = self.git(self.checkout, 'rev-parse', 'HEAD')
        self.git(self.repo, 'merge', '--ff-only', 'feature')
        self.git(self.repo, 'push', 'origin', 'main')
        self.git(self.repo, 'remote', 'set-url', 'origin', 'https://github.com/example/repo.git')
        self.git(self.repo, 'config', 'url.' + str(self.remote) + '.insteadOf', 'https://github.com/example/repo.git')
        self.pr = {'merged': True, 'head': {'sha': self.head, 'ref': 'feature', 'repo': {'full_name': 'example/repo'}}, 'base': {'repo': {'full_name': 'example/repo'}}}
        self.target = {'repository': 'example/repo', 'number': 1, 'checkout': str(self.checkout), 'head_branch': 'feature', 'head_repository': 'example/repo', 'cleanup': {'owned': True, 'head_protected': False, 'common_dir': str(self.repo / '.git'), 'remote': 'origin', 'remote_url': str(self.remote), 'default_branch': 'main', 'default_checkout': str(self.repo)}}
        cwd_patch = patch.object(cleanup, '_process_cwds', return_value=[(123, self.root)])
        cwd_patch.start()
        self.addCleanup(cwd_patch.stop)
        self.repository_info = {'full_name': 'example/repo', 'default_branch': 'main'}
        self.branch_info = {'name': 'feature', 'protected': False}
        self.original = cleanup._run
        self.patcher = patch.object(cleanup, '_run', side_effect=self.run_command)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def git(self, cwd, *args):
        return subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True, check=True).stdout.strip()

    def run_command(self, args, cwd=None):
        if args[0] == 'gh':
            if '/pulls/' in args[-1]:
                return json.dumps(self.pr)
            if '/branches/' in args[-1]:
                info = dict(self.branch_info)
                info.setdefault('commit', {'sha': self.pr['head']['sha']})
                return json.dumps(info)
            return json.dumps(self.repository_info)
        if args[-3:] == ['remote', 'get-url', 'origin']:
            return 'https://github.com/example/repo.git'
        return self.original(args, cwd)

    def clean(self):
        self.target['cleanup']['remote_url'] = 'https://github.com/example/repo.git'
        return cleanup.cleanup_target(self.target, {'head': self.head})

    def test_linked_and_repeated_cleanup(self):
        self.assertEqual(self.clean()['status'], 'cleaned')
        self.assertFalse(self.checkout.exists())
        self.assertEqual(self.clean()['status'], 'cleaned')

    def test_linked_cleanup_removes_only_known_ios_generated_outputs(self):
        (self.checkout / 'project.yml').write_text('name: Example\n')
        (self.checkout / 'ExampleCore').mkdir()
        (self.checkout / 'ExampleCore/Package.swift').write_text('manifest')
        (self.checkout / '.gitignore').write_text('*.xcodeproj/\n.build/\n')
        self.git(self.checkout, 'add', '-A')
        self.git(self.checkout, 'commit', '-m', 'ios project')
        self.head = self.git(self.checkout, 'rev-parse', 'HEAD')
        self.pr['head']['sha'] = self.head
        self.git(self.repo, 'merge', '--ff-only', 'feature')
        self.git(self.repo, 'push', 'origin', 'main')
        for name in ['Example.xcodeproj/project.pbxproj', 'ExampleCore/.build/.lock']:
            path = self.checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('generated')
        self.assertEqual(self.clean()['status'], 'cleaned')
        self.assertFalse(self.checkout.exists())

    def test_untracked_preserved(self):
        (self.checkout / 'valuable').write_text('keep')
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_ignored_preserved(self):
        (self.repo / '.git/info/exclude').write_text('valuable\n')
        (self.checkout / 'valuable').write_text('keep')
        self.assertEqual(self.clean()['status'], 'preserved')

    def use_primary_checkout(self):
        self.git(self.repo, 'worktree', 'remove', str(self.checkout))
        self.git(self.repo, 'switch', 'feature')
        self.git(self.repo, 'branch', '-f', 'main', 'HEAD~1')
        self.target['checkout'] = str(self.repo)

    def test_primary_checkout_untracked_material_survives_cleanup(self):
        self.use_primary_checkout()
        (self.repo / 'valuable').write_text('keep')
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned')
        self.assertEqual((self.repo / 'valuable').read_text(), 'keep')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.head)
        self.assertEqual(self.git(self.repo, 'rev-parse', '--abbrev-ref', 'HEAD'), 'main')
        self.assertNotIn('feature', self.git(self.repo, 'branch', '--format=%(refname:short)').split())

    def test_primary_checkout_ignored_material_survives_cleanup(self):
        self.use_primary_checkout()
        (self.repo / '.git/info/exclude').write_text('valuable\n')
        (self.repo / 'valuable').write_text('keep')
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned')
        self.assertEqual((self.repo / 'valuable').read_text(), 'keep')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), self.head)

    def test_primary_checkout_tracked_modification_preserved(self):
        self.use_primary_checkout()
        self.git(self.repo, 'commit', '--allow-empty', '-m', 'tracked')
        self.git(self.repo, 'reset', '--soft', 'HEAD~1')
        (self.repo / 'tracked.txt').write_text('new')
        self.git(self.repo, 'add', 'tracked.txt')
        self.assertEqual(self.clean()['status'], 'preserved')

    def test_extra_commit_preserved(self):
        self.git(self.checkout, 'commit', '--allow-empty', '-m', 'extra')
        self.assertEqual(self.clean()['status'], 'preserved')

    def test_closed_unmerged_preserved(self):
        self.pr['merged'] = False
        self.assertEqual(self.clean()['status'], 'preserved')

    def test_wrong_repository_preserved(self):
        self.pr['head']['repo']['full_name'] = 'other/repo'
        self.assertEqual(self.clean()['status'], 'preserved')

    def test_missing_ownership_preserved(self):
        self.target['cleanup'] = {}
        self.assertEqual(self.clean()['status'], 'preserved')

    def test_locked_preserved(self):
        self.git(self.repo, 'worktree', 'lock', str(self.checkout))
        self.assertEqual(self.clean()['status'], 'preserved')

    def test_detached_preserved(self):
        self.git(self.checkout, 'switch', '--detach')
        self.assertEqual(self.clean()['status'], 'preserved')

    def squash_merge(self):
        base = self.git(self.repo, 'rev-parse', self.head + '^')
        squashed = self.git(self.repo, 'commit-tree', self.head + '^{tree}', '-p', base, '-m', 'Feature (#1)')
        if self.git(self.repo, 'branch', '--show-current') == 'main':
            self.git(self.repo, 'reset', '--hard', base)
        else:
            self.git(self.repo, 'branch', '-f', 'main', base)
        self.git(self.repo, 'push', '--force', 'origin', squashed + ':refs/heads/main')
        self.pr['merge_commit_sha'] = squashed
        return squashed

    def test_SQUASH_01_a_squash_merged_branch_is_cleaned_up(self):
        squashed = self.squash_merge()
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result['reason'])
        self.assertFalse(self.checkout.exists())
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), squashed)
        self.assertNotIn('feature', self.git(self.repo, 'branch', '--format=%(refname:short)').split())

    def test_SQUASH_02_a_merge_commit_outside_the_default_branch_preserves_the_work(self):
        self.squash_merge()
        self.pr['merge_commit_sha'] = self.git(self.repo, 'rev-parse', 'refs/heads/feature')
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())
        for reported in ('not-a-commit', 'HEAD', 'refs/remotes/origin/main'):
            self.pr['merge_commit_sha'] = reported
            self.assertEqual(self.clean()['status'], 'preserved', reported)
            self.assertTrue(self.checkout.exists(), reported)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'refs/heads/feature'), self.head)

    def test_SQUASH_03_work_beyond_the_squashed_head_is_still_preserved(self):
        self.squash_merge()
        self.git(self.checkout, 'commit', '--allow-empty', '-m', 'written after the merge')
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_SQUASH_04_a_squash_merged_branch_checked_out_in_the_primary_repository_is_cleaned_up(self):
        self.use_primary_checkout()
        squashed = self.squash_merge()
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result['reason'])
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), squashed)
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'main')
        self.assertNotIn('feature', self.git(self.repo, 'branch', '--format=%(refname:short)').split())

    def delete_flag(self):
        with patch.object(cleanup, '_git', wraps=cleanup._git) as git:
            self.assertEqual(self.clean()['status'], 'cleaned')
        return next(call.args for call in git.call_args_list if call.args[1] == 'branch')

    def test_SQUASH_05_a_branch_merged_into_the_default_branch_is_deleted_with_gits_own_merge_check(self):
        self.assertIn('-d', self.delete_flag())

    def test_SQUASH_06_only_the_squash_proof_drops_a_branch_git_still_calls_unmerged(self):
        self.squash_merge()
        self.assertIn('-D', self.delete_flag())

    def test_FORCE_01_a_head_branch_pushed_after_the_merge_preserves_the_work(self):
        self.squash_merge()
        self.git(self.checkout, 'commit', '--allow-empty', '-m', 'pushed after the merge')
        self.branch_info['commit'] = {'sha': self.git(self.checkout, 'rev-parse', 'HEAD')}
        self.git(self.checkout, 'reset', '--hard', self.head)
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())
        self.assertEqual(self.git(self.repo, 'rev-parse', 'refs/heads/feature'), self.head)

    def test_unproven_ancestry_preserved(self):
        base = self.git(self.repo, 'rev-parse', 'HEAD~1')
        self.git(self.remote, 'update-ref', 'refs/heads/main', base)
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_primary_divergence_preserved(self):
        self.git(self.repo, 'commit', '--allow-empty', '-m', 'local only')
        self.git(self.repo, 'worktree', 'remove', str(self.checkout))
        self.git(self.repo, 'switch', 'feature')
        self.target['checkout'] = str(self.repo)
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'feature')

    def test_active_descendant_cwd_preserved(self):
        with patch.object(cleanup, '_process_cwds', return_value=[(42, self.checkout / 'nested')]):
            result = self.clean()
        self.assertEqual(result['status'], 'preserved')
        self.assertIn('42', result['reason'])
        self.assertTrue(self.checkout.exists())

    def test_cwd_probe_failure_preserved(self):
        with patch.object(cleanup, '_process_cwds', side_effect=PermissionError('denied')):
            self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_index_flags_preserve_hidden_edits(self):
        for flag in ('--assume-unchanged', '--skip-worktree'):
            path = self.checkout / 'tracked'
            path.write_text('original')
            self.git(self.checkout, 'add', 'tracked')
            self.git(self.checkout, 'commit', '-m', 'tracked')
            self.git(self.checkout, 'update-index', flag, 'tracked')
            path.write_text('valuable edit')
            self.assertFalse(cleanup._clean(self.checkout))
            self.assertTrue(path.exists())
            self.git(self.checkout, 'update-index', '--no-assume-unchanged', 'tracked')
            self.git(self.checkout, 'update-index', '--no-skip-worktree', 'tracked')
            path.write_text('original')
            self.git(self.checkout, 'rm', 'tracked')
            self.git(self.checkout, 'commit', '-m', 'remove')

    def test_deleted_remote_head_cleanup(self):
        original = self.run_command
        def run(args, cwd=None):
            if args[0] == 'gh' and '/branches/' in args[-1]:
                raise subprocess.CalledProcessError(1, args, stderr='gh: Not Found (HTTP 404)')
            return original(args, cwd)
        with patch.object(cleanup, '_run', side_effect=run):
            self.assertEqual(self.clean()['status'], 'cleaned')

    def test_deleted_remote_head_unknown_registration_preserved(self):
        self.target['cleanup'].pop('head_protected')
        original = self.run_command
        def run(args, cwd=None):
            if args[0] == 'gh' and '/branches/' in args[-1]:
                raise subprocess.CalledProcessError(1, args, stderr='gh: Not Found (HTTP 404)')
            return original(args, cwd)
        with patch.object(cleanup, '_run', side_effect=run):
            self.assertEqual(self.clean()['status'], 'preserved')

    def advance_remote(self):
        writer = self.root / 'remote writer'
        self.git(self.root, 'clone', '--branch', 'main', str(self.remote), str(writer))
        self.git(writer, 'config', 'user.name', 'Test')
        self.git(writer, 'config', 'user.email', 'test@example.com')
        (writer / 'new-file').write_text('remote content')
        self.git(writer, 'add', 'new-file')
        self.git(writer, 'commit', '-m', 'remote advance')
        self.git(writer, 'push', 'origin', 'main')
        return self.git(writer, 'rev-parse', 'HEAD')

    def test_linked_cleanup_synchronizes_primary_tree(self):
        tip = self.advance_remote()
        self.assertNotEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)
        self.assertEqual(self.clean()['status'], 'cleaned')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)
        self.assertEqual((self.repo / 'new-file').read_text(), 'remote content')
        self.assertFalse(self.checkout.exists())
        self.assertNotIn('feature', self.git(self.repo, 'branch', '--list'))

    def test_absent_target_still_synchronizes_primary(self):
        self.assertEqual(self.clean()['status'], 'cleaned')
        tip = self.advance_remote()
        self.assertEqual(self.clean()['status'], 'cleaned')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)
        self.assertEqual((self.repo / 'new-file').read_text(), 'remote content')

    def test_nonconflicting_primary_untracked_material_survives_sync(self):
        (self.repo / 'valuable').write_text('keep')
        tip = self.advance_remote()
        self.assertEqual(self.clean()['status'], 'cleaned')
        self.assertEqual((self.repo / 'valuable').read_text(), 'keep')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)

    def test_conflicting_primary_untracked_material_blocks_sync(self):
        (self.repo / 'new-file').write_text('keep')
        self.advance_remote()
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertEqual((self.repo / 'new-file').read_text(), 'keep')
        self.assertTrue(self.checkout.exists())

    def test_tracked_primary_modification_blocks_sync(self):
        self.advance_remote()
        self.git(self.repo, 'pull', '--ff-only', 'origin', 'main')
        (self.repo / 'new-file').write_text('keep local edit')
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertEqual((self.repo / 'new-file').read_text(), 'keep local edit')
        self.assertTrue(self.checkout.exists())

    def test_unrelated_primary_branch_preserves(self):
        self.git(self.repo, 'switch', '-c', 'other-work')
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'other-work')

    def test_linked_cleanup_divergent_default_preserves(self):
        self.git(self.repo, 'commit', '--allow-empty', '-m', 'local work')
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_CWD_06_linked_cleanup_ignores_primary_cwd_only(self):
        with patch.object(cleanup, '_process_cwds', return_value=[(42, self.repo)]):
            self.assertEqual(self.clean()['status'], 'cleaned')
        self.assertFalse(self.checkout.exists())

    def test_promoted_default_preserved(self):
        self.repository_info['default_branch'] = 'feature'
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_protected_feature_preserved(self):
        self.branch_info['protected'] = True
        self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_missing_branch_protection_preserved(self):
        self.branch_info = {'name': 'feature'}
        self.assertEqual(self.clean()['status'], 'preserved')

    def test_fetch_does_not_prune_or_remap(self):
        with patch.object(cleanup, '_git', wraps=cleanup._git) as git:
            self.assertEqual(self.clean()['status'], 'cleaned')
            fetch = next(call.args for call in git.call_args_list if call.args[1] == 'fetch')
            self.assertIn('--no-prune', fetch)
            self.assertIn('--refmap=', fetch)

    def test_remote_credentials_rejected(self):
        for url in ('https://secret@github.com/example/repo.git',
                    'https://git:secret@github.com/example/repo.git',
                    'ssh://git:secret@github.com/example/repo.git',
                    'ssh://other@github.com/example/repo.git'):
            self.assertFalse(cleanup._matches_remote(url, 'example/repo'))
        self.assertTrue(cleanup._matches_remote('ssh://git@github.com/example/repo.git', 'example/repo'))

    def test_timeout_preserves(self):
        with patch.object(cleanup, '_run', side_effect=subprocess.TimeoutExpired('gh', 60)):
            self.assertEqual(self.clean()['status'], 'preserved')
        self.assertTrue(self.checkout.exists())

    def test_run_has_timeout(self):
        with patch.object(cleanup.subprocess, 'run') as run:
            run.return_value.stdout = ''
            self.original(['git', 'version'])
            self.assertEqual(run.call_args.kwargs['timeout'], 60)

    def test_case_insensitive_repository(self):
        self.target['repository'] = 'EXAMPLE/REPO'
        self.assertEqual(self.clean()['status'], 'cleaned')

    def test_CWD_01_primary_active_cwd_allows_safe_cleanup(self):
        self.git(self.repo, 'worktree', 'remove', str(self.checkout))
        self.git(self.repo, 'switch', 'feature')
        self.target['checkout'] = str(self.repo)
        with patch.object(cleanup, '_process_cwds', return_value=[(42, self.repo)]):
            self.assertEqual(self.clean()['status'], 'cleaned')
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'main')

    def test_CWD_02_same_tree_squash_does_not_rewrite_files_through_stale_main(self):
        self.use_primary_checkout()
        document = self.repo / 'delivered.txt'
        document.write_text('delivered content')
        self.git(self.repo, 'add', 'delivered.txt')
        self.git(self.repo, 'commit', '-m', 'delivered file')
        self.head = self.git(self.repo, 'rev-parse', 'HEAD')
        self.pr['head']['sha'] = self.head
        squashed = self.squash_merge()
        before = document.stat()
        result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), squashed)
        self.assertEqual(document.read_text(), 'delivered content')
        self.assertEqual(document.stat().st_ino, before.st_ino)
        self.assertEqual(document.stat().st_mtime_ns, before.st_mtime_ns)

    def test_CWD_03_primary_session_does_not_block_new_remote_content(self):
        self.use_primary_checkout()
        tip = self.advance_remote()
        with patch.object(cleanup, '_process_cwds', return_value=[(42, self.repo)]):
            result = self.clean()
        self.assertEqual(result['status'], 'cleaned', result)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)
        self.assertEqual((self.repo / 'new-file').read_text(), 'remote content')

    def test_CWD_04_busy_linked_worktree_is_preserved_after_primary_sync(self):
        tip = self.advance_remote()
        with patch.object(cleanup, '_process_cwds', return_value=[(42, self.checkout)]):
            result = self.clean()
        self.assertEqual(result['status'], 'preserved', result)
        self.assertIn('working directory', result['reason'])
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD'), tip)
        self.assertTrue(self.checkout.exists())
        self.assertIn('feature', self.git(self.repo, 'branch', '--format=%(refname:short)').split())

    def test_CWD_05_untracked_collision_preserves_branch_and_content(self):
        self.use_primary_checkout()
        self.advance_remote()
        before_main = self.git(self.repo, 'rev-parse', 'main')
        (self.repo / 'new-file').write_text('local content')
        with patch.object(cleanup, '_process_cwds', return_value=[(42, self.repo)]):
            result = self.clean()
        self.assertEqual(result['status'], 'preserved', result)
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'feature')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'main'), before_main)
        self.assertEqual((self.repo / 'new-file').read_text(), 'local content')

    def test_CWD_07_concurrent_default_commit_is_not_overwritten(self):
        self.use_primary_checkout()
        old_main = self.git(self.repo, 'rev-parse', 'main')
        concurrent = self.git(self.repo, 'commit-tree', old_main + '^{tree}', '-p', old_main, '-m', 'concurrent local work')
        original_git = cleanup._git
        injected = False

        def move_before_update(path, *args):
            nonlocal injected
            if not injected and args[0] in ('update-ref', 'switch'):
                injected = True
                self.git(self.repo, 'update-ref', 'refs/heads/main', concurrent, old_main)
            return original_git(path, *args)

        with patch.object(cleanup, '_git', side_effect=move_before_update):
            result = self.clean()
        self.assertTrue(injected)
        self.assertEqual(result['status'], 'preserved', result)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'main'), concurrent)
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'feature')
        self.assertIn('feature', self.git(self.repo, 'branch', '--format=%(refname:short)').split())

    def test_CWD_08_failed_switch_rollback_preserves_concurrent_default_update(self):
        self.use_primary_checkout()
        tip = self.advance_remote()
        self.git(self.repo, 'fetch', 'origin')
        concurrent = self.git(self.repo, 'commit-tree', tip + '^{tree}', '-p', tip, '-m', 'concurrent local work')
        (self.repo / 'new-file').write_text('local content')
        original_git = cleanup._git

        def move_before_failed_switch(path, *args):
            if args[0] == 'switch':
                self.git(self.repo, 'update-ref', 'refs/heads/main', concurrent, tip)
            return original_git(path, *args)

        with patch.object(cleanup, '_git', side_effect=move_before_failed_switch):
            result = self.clean()
        self.assertEqual(result['status'], 'preserved', result)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'main'), concurrent)
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'feature')
        self.assertEqual((self.repo / 'new-file').read_text(), 'local content')

    def test_macos_cwd_parser(self):
        with patch.object(cleanup, '_process_cwds', wraps=PROCESS_CWDS), patch.object(cleanup.sys, 'platform', 'darwin'), patch.object(cleanup, '_run', return_value='p42\0\nn/tmp/space dir\0\n'):
            self.assertEqual(cleanup._process_cwds(), [(42, Path('/tmp/space dir'))])

    def test_primary_cleanup(self):
        self.git(self.repo, 'worktree', 'remove', str(self.checkout))
        self.git(self.repo, 'switch', 'feature')
        self.target['checkout'] = str(self.repo)
        self.assertEqual(self.clean()['status'], 'cleaned')
        self.assertEqual(self.git(self.repo, 'branch', '--show-current'), 'main')
        self.assertTrue(self.repo.exists())
        self.assertEqual(self.clean()['status'], 'cleaned')


if __name__ == '__main__':
    unittest.main()


class IgnoredFilesTests(unittest.TestCase):
    def repository(self, directory):
        path = Path(directory)
        run = lambda *a: subprocess.run(['git', '-C', str(path), *a], capture_output=True, text=True, check=True)
        run('init', '-q', '-b', 'main')
        run('config', 'user.email', 't@example.com')
        run('config', 'user.name', 'Test')
        (path / '.gitignore').write_text('__pycache__/\n*.log\n')
        (path / 'kept.txt').write_text('kept')
        run('add', '-A')
        run('commit', '-qm', 'base')
        return path

    def test_regenerable_caches_no_longer_block_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.repository(directory)
            (path / '__pycache__').mkdir()
            (path / '__pycache__' / 'x.pyc').write_bytes(b'\x00')
            self.assertTrue(cleanup._clean(path))
            self.assertEqual(cleanup._dirty(path), [])

    def test_any_other_ignored_file_still_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.repository(directory)
            (path / 'run.log').write_text('noise')
            self.assertFalse(cleanup._clean(path))
            self.assertTrue(any('run.log' in line for line in cleanup._dirty(path)))

    def test_a_modified_tracked_file_still_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.repository(directory)
            (path / 'kept.txt').write_text('changed')
            self.assertFalse(cleanup._clean(path))
            self.assertTrue(any('kept.txt' in line for line in cleanup._dirty(path)))

    def test_an_untracked_file_still_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.repository(directory)
            (path / 'new.txt').write_text('new')
            self.assertFalse(cleanup._clean(path))
            self.assertTrue(any('new.txt' in line for line in cleanup._dirty(path)))

    def test_a_similarly_named_ignored_directory_still_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.repository(directory)
            (path / '.gitignore').write_text('__pycache__/\n*.log\nmy__pycache__/\n')
            subprocess.run(['git', '-C', str(path), 'commit', '-aqm', 'ignore'], check=True)
            (path / 'my__pycache__').mkdir()
            (path / 'my__pycache__' / 'private.env').write_text('SECRET=1')
            self.assertFalse(cleanup._clean(path))
            self.assertTrue(any('my__pycache__' in line for line in cleanup._dirty(path)))

    def test_a_tracked_cache_named_file_still_blocks_when_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.repository(directory)
            (path / 'fixture.pyc').write_bytes(b'\x00')
            subprocess.run(['git', '-C', str(path), 'add', '-f', 'fixture.pyc'], check=True)
            subprocess.run(['git', '-C', str(path), 'commit', '-qm', 'tracked cache'], check=True)
            (path / 'fixture.pyc').write_bytes(b'\x01')
            self.assertFalse(cleanup._clean(path))
            self.assertTrue(any('fixture.pyc' in line for line in cleanup._dirty(path)))

    def test_an_untracked_cache_that_is_not_ignored_still_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.repository(directory)
            (path / '.gitignore').write_text('*.log\n')
            subprocess.run(['git', '-C', str(path), 'commit', '-aqm', 'narrow ignore'], check=True)
            (path / '__pycache__').mkdir()
            (path / '__pycache__' / 'x.pyc').write_bytes(b'\x00')
            self.assertFalse(cleanup._clean(path))


class IOSGeneratedFilesTests(unittest.TestCase):
    repository = IgnoredFilesTests.repository

    def ios_repository(self, directory):
        path = self.repository(directory)
        (path / 'project.yml').write_text('name: Example\nschemes:\n  Example Demo:\n    build: {}\n')
        (path / 'ExampleCore').mkdir()
        (path / 'ExampleCore/Package.swift').write_text('package manifest')
        (path / '.gitignore').write_text('*.xcodeproj/\n.build/\n*.log\n')
        subprocess.run(['git', '-C', str(path), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(path), 'commit', '-qm', 'ios inputs'], check=True)
        return path

    def add_file(self, path, name):
        file = path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('generated')

    def test_known_xcodegen_and_swiftpm_outputs_are_regenerable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.ios_repository(directory)
            for name in ['Example.xcodeproj/project.pbxproj', 'Example.xcodeproj/project.xcworkspace/contents.xcworkspacedata', 'Example.xcodeproj/xcshareddata/xcschemes/Example Demo.xcscheme', 'ExampleCore/.build/.lock', 'ExampleCore/.build/plugin-tools.yaml', 'ExampleCore/.build/arm64-apple-macosx/debug/Example.o']:
                self.add_file(path, name)
            self.assertTrue(cleanup._clean(path), cleanup._dirty(path))

    def test_unknown_generated_bundle_contents_remain_protected(self):
        for name in ['private.log']:
            with tempfile.TemporaryDirectory() as directory:
                path = self.ios_repository(directory)
                self.add_file(path, name)
                self.assertFalse(cleanup._clean(path), name)

    def test_ignored_build_directory_is_disposable_without_inspecting_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.ios_repository(directory)
            for name in ['ExampleCore/.build/notes.txt', 'Other/.build/.lock', 'ExampleCore/.build/checkouts/Dependency/Source.swift', 'Example.xcodeproj/xcshareddata/xcschemes/Example Demo.xcscheme']:
                self.add_file(path, name)
            self.assertTrue(cleanup._clean(path), cleanup._dirty(path))

    def test_modified_tracked_build_file_is_still_a_local_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.ios_repository(directory)
            self.add_file(path, 'ExampleCore/.build/tracked.txt')
            subprocess.run(['git', '-C', str(path), 'add', '-f', 'ExampleCore/.build/tracked.txt'], check=True)
            subprocess.run(['git', '-C', str(path), 'commit', '-qm', 'tracked fixture'], check=True)
            (path / 'ExampleCore/.build/tracked.txt').write_text('modified')
            self.assertFalse(cleanup._clean(path))
