import fcntl
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
import subprocess
from urllib.parse import quote, urlparse

_spec = importlib.util.spec_from_file_location('worktree_lifecycle', Path(__file__).with_name('worktree_lifecycle.py'))
lifecycle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lifecycle)


def _run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True, timeout=60).stdout.strip()


def _git(path, *args):
    return _run(['git', '-C', str(path), *args])


def _result(status, reason, actions=None):
    return {'status': status, 'reason': reason, 'actions': actions or []}


def _worktrees(path):
    return [dict(line.split(' ', 1) if ' ' in line else (line, True)
                 for line in record.splitlines())
            for record in _git(path, 'worktree', 'list', '--porcelain').split('\n\n') if record]


REGENERABLE = frozenset({'__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache'})


def _regenerable(line):
    if line[:2] != '!!':
        return False
    parts = [part for part in line[3:].split('/') if part]
    generated = {'.build', '.swiftpm', 'build', 'DerivedData', 'ci-artifacts', 'xcuserdata'}
    return bool(parts) and (
        parts[-1] == '.DS_Store'
        or parts[-1].endswith(('.pyc', '.pyo', '.xcuserstate'))
        or any(part in REGENERABLE or part in generated or part.endswith(('.xcodeproj', '.xcresult')) for part in parts)
    )


def _dirty(path, tracked_only=False):
    path = Path(path)
    entries = _git(path, 'ls-files', '-v', '-z').split('\0')
    if any(entry and (entry[0].islower() or entry[0] == 'S') for entry in entries):
        return ['assume-unchanged or skip-worktree entries']
    status = _git(path, 'status', '--porcelain', '-z', '--untracked-files=all', '--ignored').split('\0')
    if tracked_only:
        return [line for line in status if line and line[:2] not in {'!!', '??'}]
    return [line for line in status if line and not _regenerable(line)]


def _clean(path):
    return not _dirty(path)


def _owned_dirty(checkout, primary):
    return _dirty(checkout, tracked_only=checkout == primary)


def cleanup_target(target, snapshot):
    actions = []
    try:
        return _cleanup(target, snapshot, actions)
    except (OSError, TypeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        return _result('preserved', f'Cleanup could not be verified: {error}', actions)


def _cleanup(target, snapshot, actions):
    metadata = target.get('cleanup') or {}
    required = ('common_dir', 'remote', 'remote_url', 'default_branch', 'default_checkout')
    if metadata.get('owned') is not True or not all(metadata.get(key) for key in required):
        return _result('preserved', 'Explicit task ownership metadata is missing')
    repository = target['repository']
    number = int(target['number'])
    checkout = Path(target['checkout']).resolve()
    primary = Path(metadata['default_checkout']).resolve()
    common = Path(metadata['common_dir']).resolve()
    branch = target['head_branch']
    default = metadata['default_branch']
    remote = metadata['remote']
    if branch == default or branch in ('main', 'master', 'develop', 'development', 'release') or branch.startswith('release/'):
        return _result('preserved', 'Default or protected branch cannot be cleaned')
    if (target.get('head_repository') or '').casefold() != repository.casefold():
        return _result('preserved', 'Fork or mismatched head repository cannot be cleaned')
    pr = json.loads(_run(['gh', 'api', f'repos/{repository}/pulls/{number}']))
    if not pr.get('merged'):
        return _result('preserved', 'PR is not freshly verified as merged')
    head = pr['head']['sha']
    repository_info = json.loads(_run(['gh', 'api', f'repos/{repository}']))
    if (repository_info['full_name'].casefold() != repository.casefold()
            or repository_info['default_branch'] != default):
        return _result('preserved', 'Repository identity or default branch changed since registration')
    try:
        branch_info = json.loads(_run(['gh', 'api', f'repos/{repository}/branches/{quote(branch, safe="")}']))
    except subprocess.CalledProcessError as error:
        if 'HTTP 404' not in (error.stderr or '') or metadata.get('head_protected') is not False:
            return _result('preserved', 'Current branch protection is unknown')
        if _git(primary, 'ls-remote', '--heads', metadata['remote_url'], f'refs/heads/{branch}'):
            return _result('preserved', 'Remote head still exists but protection could not be read')
        branch_info = {'name': branch, 'protected': False, 'commit': {'sha': head}}
    if branch_info.get('name') != branch or branch_info.get('protected') is not False:
        return _result('preserved', 'PR head branch is protected or its protection cannot be verified')
    if (branch_info.get('commit') or {}).get('sha') != head:
        return _result('preserved', 'Remote head branch carries work the merged PR head does not')
    if (pr['head']['ref'] != branch or pr['head']['repo']['full_name'].casefold() != repository.casefold()
            or pr['base']['repo']['full_name'].casefold() != repository.casefold() or snapshot.get('head') != head):
        return _result('preserved', 'PR identity or final head changed')
    if metadata.get('lifecycle') == 'disposable-v1' and pr['base'].get('ref') != default:
        return _result('preserved', 'The PR did not merge into the registered default branch')
    if not primary.is_dir() or not common.is_dir():
        return _result('preserved', 'Registered repository no longer exists')
    actual_common = Path(_git(primary, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    if actual_common != common or _git(primary, 'remote', 'get-url', remote) != metadata['remote_url']:
        return _result('preserved', 'Repository identity changed')
    if not _matches_remote(metadata['remote_url'], repository):
        return _result('preserved', 'Remote URL does not match PR repository')
    with (common / 'author-monitor-cleanup.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return _result('preserved', 'Another cleanup holds the repository lock')
        if metadata.get('lifecycle') == 'disposable-v1':
            return _disposable(checkout, primary, common, branch, default, remote, head, actions, lock.fileno())
        return _locked(target, metadata, checkout, primary, common, branch, default, remote, head, pr.get('merge_commit_sha'), actions)


def _disposable(checkout, primary, common, branch, default, remote, head, actions, lock_fd):
    if checkout == primary:
        return _result('preserved', 'A disposable worktree cannot be the primary checkout')
    records = _worktrees(primary)
    owned = next((record for record in records if Path(record['worktree']).resolve() == checkout), None)
    if any(checkout in Path(record['worktree']).resolve().parents for record in records):
        return _result('preserved', 'Another registered worktree is nested inside this task directory')
    reference = f'refs/heads/{branch}'
    exists = subprocess.run(['git', '-C', str(primary), 'show-ref', '--verify', '--quiet', reference], capture_output=True, timeout=60).returncode == 0
    if exists and _git(primary, 'rev-parse', reference) != head:
        return _result('preserved', 'Local branch has work beyond the final PR head')
    if any(record.get('branch') == reference and Path(record['worktree']).resolve() != checkout for record in records):
        return _result('preserved', 'Branch is occupied by a different worktree')
    if owned:
        if 'locked' in owned or owned.get('branch') != reference:
            return _result('preserved', 'Worktree identity or lock changed')
        if checkout.exists() and (Path(_git(checkout, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve() != common
                                  or _git(checkout, 'rev-parse', 'HEAD') != head):
            return _result('preserved', 'Worktree repository or final head changed')
    elif checkout.exists():
        return _result('preserved', 'The checkout path exists without its worktree registration')
    try:
        commit = lifecycle.synchronize(primary, remote, default, _git, lock_fd)
        sync = dict(status='synced', commit=commit)
        actions.append('Reset default checkout to the fetched remote commit')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sync = dict(status='failed', reason=str(error), retryable=not isinstance(error, lifecycle.UnownedIndexLock))
    try:
        if owned:
            current_records = _worktrees(primary)
            if any(checkout in Path(record['worktree']).resolve().parents for record in current_records):
                raise ValueError('Another worktree was nested inside the task before disposal')
            current = next((record for record in current_records if Path(record['worktree']).resolve() == checkout), None)
            if not current or 'locked' in current or current.get('branch') != reference:
                raise ValueError('Worktree identity changed before disposal')
            if exists and _git(primary, 'rev-parse', reference) != head:
                raise ValueError('Branch changed before disposal')
            _git(primary, 'worktree', 'remove', '--force', str(checkout))
            actions.append('Removed disposable worktree including all residual files')
        if exists:
            _git(primary, 'update-ref', '-d', reference, head)
            actions.append('Deleted the final merged task branch')
        disposal = dict(status='cleaned')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        disposal = dict(status='failed', reason=str(error))
    complete = sync['status'] == 'synced' and disposal['status'] == 'cleaned'
    result = _result('cleaned' if complete else 'partial',
                     'Default synchronized and task worktree disposed' if complete else 'Synchronization and disposal have separate results; retry the failed operation', actions)
    result.update(sync=sync, cleanup=disposal)
    result['retryable'] = sync.get('retryable', True)
    return result


def _on_default(path, remote, default, commit):
    return subprocess.run(['git', '-C', str(path), 'merge-base', '--is-ancestor', commit, f'refs/remotes/{remote}/{default}'],
                          capture_output=True, timeout=60).returncode == 0


def _reached_default(primary, remote, default, head, merge_commit, actions):
    if _on_default(primary, remote, default, head):
        return 'ancestor'
    if not isinstance(merge_commit, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', merge_commit):
        return None
    if not _on_default(primary, remote, default, merge_commit):
        return None
    actions.append('Verified the squash or rebase merge commit on the default branch')
    return 'merge commit'


def _locked(target, metadata, checkout, primary, common, branch, default, remote, head, merge_commit, actions):
    records = _worktrees(primary)
    owned = next((record for record in records if Path(record['worktree']).resolve() == checkout), None)
    exists = subprocess.run(['git', '-C', str(primary), 'show-ref', '--verify', '--quiet', f'refs/heads/{branch}'], capture_output=True, timeout=60).returncode == 0
    if exists and _git(primary, 'rev-parse', f'refs/heads/{branch}') != head:
        return _result('preserved', 'Local branch has work beyond the final PR head')
    occupants = [record for record in records if record.get('branch') == f'refs/heads/{branch}']
    if any(Path(record['worktree']).resolve() != checkout for record in occupants):
        return _result('preserved', 'Branch is occupied by another worktree')
    if owned:
        if owned.get('locked') or 'locked' in owned or owned.get('prunable'):
            return _result('preserved', 'Owned worktree is locked or prunable')
        if owned.get('branch') != f'refs/heads/{branch}':
            if checkout == primary and owned.get('branch') == f'refs/heads/{default}' and not exists:
                owned = None
            else:
                return _result('preserved', 'Checkout is detached or on a different branch')
        if Path(_git(checkout, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve() != common or _owned_dirty(checkout, primary):
            return _result('preserved', 'Checkout identity changed or contains changes cleanup would have to move through: ' + '; '.join(_owned_dirty(checkout, primary)[:5]))
        cwd = Path.cwd().resolve()
        if checkout != primary and (cwd == checkout or checkout in cwd.parents):
            return _result('preserved', 'Cleanup process is running inside the owned worktree')
    elif checkout.exists():
        return _result('preserved', 'Checkout path exists but is not registered as a worktree')
    _git(primary, 'fetch', '--no-prune', '--no-tags', '--refmap=', remote, f'refs/heads/{default}:refs/remotes/{remote}/{default}')
    reached = _reached_default(primary, remote, default, head, merge_commit, actions)
    if not reached:
        return _result('preserved', 'Final PR head is not on the default branch and no merge commit proves it landed there')
    if owned and (_owned_dirty(checkout, primary) or _git(checkout, 'rev-parse', 'HEAD') != head):
        return _result('preserved', 'Checkout changed during verification')
    current_records = _worktrees(primary)
    primary_record = next((record for record in current_records if Path(record['worktree']).resolve() == primary), None)
    if not primary_record or 'locked' in primary_record or 'prunable' in primary_record:
        return _result('preserved', 'Primary checkout is missing, locked, or prunable', actions)
    allowed = {f'refs/heads/{default}'}
    if checkout == primary:
        allowed.add(f'refs/heads/{branch}')
    if primary_record.get('branch') not in allowed:
        return _result('preserved', 'Primary checkout is detached or on an unrelated branch', actions)
    if any(record.get('branch') == f'refs/heads/{default}' and Path(record['worktree']).resolve() != primary for record in current_records):
        return _result('preserved', 'Default branch is occupied elsewhere', actions)
    if _dirty(primary, tracked_only=True):
        return _result('preserved', 'Primary checkout contains local files, changes, or hidden index flags', actions)
    default_ref = f'refs/heads/{default}'
    previous_default = _git(primary, 'rev-parse', default_ref)
    remote_default = _git(primary, 'rev-parse', f'refs/remotes/{remote}/{default}')
    default_ancestry = subprocess.run(['git', '-C', str(primary), 'merge-base', '--is-ancestor', previous_default, remote_default], capture_output=True, timeout=60)
    if default_ancestry.returncode != 0:
        return _result('preserved', 'Local default branch cannot fast-forward safely', actions)
    if primary_record.get('branch') != f'refs/heads/{default}':
        _git(primary, 'update-ref', default_ref, remote_default, previous_default)
        try:
            _git(primary, 'switch', '--no-overwrite-ignore', default)
        except (OSError, subprocess.SubprocessError):
            _git(primary, 'update-ref', default_ref, previous_default, remote_default)
            raise
        actions.append('Switched primary checkout directly to the verified remote default')
    else:
        _git(primary, 'merge', '--ff-only', '--no-overwrite-ignore', remote_default)
        actions.append('Fast-forwarded default branch')
    if (_git(primary, 'rev-parse', 'HEAD') != remote_default
            or _dirty(primary, tracked_only=True)):
        return _result('preserved', 'Default checkout synchronization could not be verified', actions)
    if owned and checkout != primary:
        refreshed = next((record for record in _worktrees(primary) if Path(record['worktree']).resolve() == checkout), None)
        if (not refreshed or 'locked' in refreshed or 'prunable' in refreshed
                or refreshed.get('branch') != f'refs/heads/{branch}'
                or not _clean(checkout) or _git(checkout, 'rev-parse', 'HEAD') != head):
            return _result('preserved', 'Owned checkout changed after default synchronization', actions)
        occupied = _active_cwd(checkout)
        if occupied:
            return _result('preserved', occupied, actions)
        _git(primary, 'worktree', 'remove', str(checkout))
        actions.append('Removed owned clean worktree')
    if exists:
        if _git(primary, 'rev-parse', f'refs/heads/{branch}') != head:
            return _result('preserved', 'Owned branch changed before deletion', actions)
        _git(primary, 'branch', '-d' if reached == 'ancestor' else '-D', '--', branch)
        actions.append('Deleted merged local branch')
    return _result('cleaned', 'Owned local PR state cleaned', actions)


def bind_cleanup(checkout, repository, pr):
    path = Path(checkout).resolve()
    if Path(_git(path, 'rev-parse', '--show-toplevel')).resolve() != path:
        raise ValueError('Checkout must name the repository root')
    if _git(path, 'symbolic-ref', '--short', 'HEAD') != pr['head']['ref'] or pr['head']['repo']['full_name'].casefold() != repository.casefold():
        raise ValueError('Checkout branch must match the PR head repository and branch')
    common = Path(_git(path, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    records = _worktrees(path)
    primary = Path(records[0]['worktree']).resolve()
    matches = []
    for remote in _git(path, 'remote').splitlines():
        url = _git(path, 'remote', 'get-url', remote)
        if _matches_remote(url, repository):
            matches.append((remote, url))
    if len(matches) != 1:
        raise ValueError('Exactly one remote must match the PR repository')
    remote, url = matches[0]
    info = json.loads(_run(['gh', 'api', f'repos/{repository}']))
    if info['full_name'].casefold() != repository.casefold():
        raise ValueError('Repository API identity does not match')
    default = info['default_branch']
    branch_info = json.loads(_run(['gh', 'api', f'repos/{repository}/branches/{quote(pr["head"]["ref"], safe="")}']))
    if branch_info.get('name') != pr['head']['ref'] or not isinstance(branch_info.get('protected'), bool):
        raise ValueError('Branch protection could not be captured')
    result = {'owned': True, 'head_protected': branch_info['protected'], 'common_dir': str(common), 'remote': remote, 'remote_url': url,
              'default_branch': default, 'default_checkout': str(primary)}
    if path != primary:
        result['lifecycle'] = 'disposable-v1'
    return result


def _matches_remote(url, repository):
    if url.startswith('git@github.com:'):
        return url.removeprefix('git@github.com:').rstrip('/').removesuffix('.git').casefold() == repository.casefold()
    parsed = urlparse(url)
    credentials_valid = ((parsed.scheme == 'https' and parsed.username is None)
                         or (parsed.scheme == 'ssh' and parsed.username in (None, 'git')))
    return (credentials_valid and parsed.password is None and parsed.hostname == 'github.com'
            and parsed.path.strip('/').removesuffix('.git').casefold() == repository.casefold())


def _process_cwds():
    if sys.platform == 'darwin':
        output = _run(['lsof', '-a', '-u', str(os.getuid()), '-d', 'cwd', '-F0pn'])
        pid = None
        entries = []
        for field in output.split('\0'):
            field = field.lstrip('\n')
            if field.startswith('p'):
                pid = int(field[1:])
            elif field.startswith('n'):
                if pid is None or not field[1:].startswith('/'):
                    raise ValueError('Process cwd listing is incomplete')
                entries.append((pid, Path(field[1:])))
        if not entries:
            raise ValueError('Process cwd listing is empty')
        return entries
    if sys.platform.startswith('linux'):
        entries = []
        for directory in Path('/proc').iterdir():
            if not directory.name.isdigit():
                continue
            try:
                if directory.stat().st_uid == os.getuid():
                    entries.append((int(directory.name), (directory / 'cwd').resolve(strict=True)))
            except FileNotFoundError:
                if directory.exists():
                    raise ValueError('Process cwd could not be read')
        if not entries:
            raise ValueError('Process cwd listing is empty')
        return entries
    raise ValueError('Process cwd inspection is unavailable on this platform')


def _active_cwd(checkout):
    try:
        entries = _process_cwds()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return f'Active checkout use could not be verified: {error}'
    for pid, cwd in entries:
        path = cwd.resolve()
        if path == checkout or checkout in path.parents:
            return f'Checkout is the working directory of process {pid}'
    return None
