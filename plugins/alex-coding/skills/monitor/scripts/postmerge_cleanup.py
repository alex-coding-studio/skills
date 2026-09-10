import fcntl
import json
import os
import re
import sys
from pathlib import Path
import subprocess
from urllib.parse import quote, urlparse


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


def _generated_project_files(path, tracked):
    spec = path / 'project.yml'
    if 'project.yml' not in tracked or spec.is_symlink():
        return set()
    text = spec.read_text()
    name = re.search(r'^name: ([A-Za-z][A-Za-z0-9_-]*)\s*$', text, re.MULTILINE)
    if not name:
        return set()
    project = name.group(1)
    schemes = {project}
    section = re.search(r'^schemes:\s*\n((?:[ \t].*\n|\n)*)', text, re.MULTILINE)
    if section:
        schemes.update(re.findall(r'^  ([A-Za-z][A-Za-z0-9 _-]*):\s*$', section.group(1), re.MULTILINE))
    prefix = project + '.xcodeproj/'
    return {prefix + 'project.pbxproj', prefix + 'project.xcworkspace/contents.xcworkspacedata',
            *(prefix + 'xcshareddata/xcschemes/' + name + '.xcscheme' for name in schemes)}


def _dependency_safe(root, dependency, bare=False):
    try:
        if dependency.is_symlink() or not dependency.resolve().is_relative_to(root.resolve()):
            return False
        if bare:
            return _git(dependency, 'rev-parse', '--is-bare-repository') == 'true'
        if Path(_git(dependency, 'rev-parse', '--show-toplevel')).resolve() != dependency.resolve():
            return False
        if not Path(_git(dependency, 'rev-parse', '--absolute-git-dir')).resolve().is_relative_to(root.resolve()):
            return False
        if _git(dependency, 'status', '--porcelain', '--untracked-files=all', '--ignored'):
            return False
        entries = _git(dependency, 'ls-files', '-v', '-z').split('\0')
        if any(e and (e[0].islower() or e[0] == 'S') for e in entries):
            return False
        return bool(_git(dependency, 'for-each-ref', '--contains', 'HEAD', '--format=%(refname)', 'refs/remotes'))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def _regenerable(line, path=None, tracked=None, generated=None, memo=None):
    if memo is None:
        memo = {}
    if line[:2] != '!!':
        return False
    entry = line[3:]
    parts = [part for part in entry.split('/') if part]
    if not parts:
        return False
    if path is not None and not (path / entry).resolve().is_relative_to(path.resolve()):
        return False
    if parts[-1].endswith(('.pyc', '.pyo')) or any(part in REGENERABLE for part in parts):
        return True
    if entry in (generated or set()):
        return True
    if '.build' not in parts or tracked is None:
        return False
    index = parts.index('.build')
    manifest = '/'.join([*parts[:index], 'Package.swift'])
    if manifest not in tracked or (path / manifest).is_symlink() or index + 1 >= len(parts):
        return False
    rest = parts[index + 1:]
    if len(rest) == 1 and rest[0] in {'.lock', 'build.db', 'workspace-state.json', 'debug.yaml', 'release.yaml', 'plugin-tools.yaml', 'debug', 'release'}:
        return True
    if rest[0] in {'checkouts', 'repositories'}:
        container = path.joinpath(*parts[:index + 2])
        dependencies = [container / rest[1]] if len(rest) > 1 else list(container.iterdir())
        for dep in dependencies:
            key = (str(dep), rest[0])
            if key not in memo:
                memo[key] = _dependency_safe(path, dep, rest[0] == 'repositories')
            if not memo[key]:
                return False
        return True
    if rest[0] in {'artifacts', 'plugins'}:
        return True
    return bool(re.fullmatch(r'(?:arm64|aarch64|x86_64)-(?:apple|unknown)-[a-z0-9-]+', rest[0]) and len(rest) > 1 and rest[1] in {'debug', 'release'})


def _dirty(path, tracked_only=False):
    path = Path(path)
    entries = _git(path, 'ls-files', '-v', '-z').split('\0')
    if any(entry and (entry[0].islower() or entry[0] == 'S') for entry in entries):
        return ['assume-unchanged or skip-worktree entries']
    tracked = {entry[2:] for entry in entries if entry}
    status = _git(path, 'status', '--porcelain', '-z', '--untracked-files=all', '--ignored').split('\0')
    if tracked_only:
        return [line for line in status if line and line[:2] not in {'!!', '??'}]
    generated = _generated_project_files(path, tracked)
    memo = {}
    return [line for line in status if line and not _regenerable(line, path, tracked, generated, memo)]


def _clean(path):
    return not _dirty(path)


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
        branch_info = {'name': branch, 'protected': False}
    if branch_info.get('name') != branch or branch_info.get('protected') is not False:
        return _result('preserved', 'PR head branch is protected or its protection cannot be verified')
    head = pr['head']['sha']
    if (pr['head']['ref'] != branch or pr['head']['repo']['full_name'].casefold() != repository.casefold()
            or pr['base']['repo']['full_name'].casefold() != repository.casefold() or snapshot.get('head') != head):
        return _result('preserved', 'PR identity or final head changed')
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
        return _locked(target, metadata, checkout, primary, common, branch, default, remote, head, actions)


def _locked(target, metadata, checkout, primary, common, branch, default, remote, head, actions):
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
        if Path(_git(checkout, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve() != common or not _clean(checkout):
            return _result('preserved', 'Checkout identity changed or contains modified, untracked, or ignored files: ' + '; '.join(_dirty(checkout)[:5]))
        cwd = Path.cwd().resolve()
        if checkout != primary and (cwd == checkout or checkout in cwd.parents):
            return _result('preserved', 'Cleanup process is running inside the owned worktree')
    elif checkout.exists():
        return _result('preserved', 'Checkout path exists but is not registered as a worktree')
    _git(primary, 'fetch', '--no-prune', '--no-tags', '--refmap=', remote, f'refs/heads/{default}:refs/remotes/{remote}/{default}')
    ancestry = subprocess.run(['git', '-C', str(primary), 'merge-base', '--is-ancestor', head, f'refs/remotes/{remote}/{default}'], capture_output=True, timeout=60)
    if ancestry.returncode != 0:
        return _result('preserved', 'Final PR head ancestry is not proven; squash or rebase cleanup requires review')
    if owned and (not _clean(checkout) or _git(checkout, 'rev-parse', 'HEAD') != head):
        return _result('preserved', 'Checkout changed during verification')
    if owned:
        occupied = _active_cwd(checkout)
        if occupied:
            return _result('preserved', occupied)
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
    occupied = _active_cwd(primary)
    if occupied:
        return _result('preserved', occupied, actions)
    default_ancestry = subprocess.run(['git', '-C', str(primary), 'merge-base', '--is-ancestor', f'refs/heads/{default}', f'refs/remotes/{remote}/{default}'], capture_output=True, timeout=60)
    if default_ancestry.returncode != 0:
        return _result('preserved', 'Local default branch cannot fast-forward safely', actions)
    if primary_record.get('branch') != f'refs/heads/{default}':
        _git(primary, 'switch', '--no-overwrite-ignore', default)
        actions.append('Switched primary checkout to default branch')
    _git(primary, 'merge', '--ff-only', '--no-overwrite-ignore', f'refs/remotes/{remote}/{default}')
    actions.append('Fast-forwarded default branch')
    if (_git(primary, 'rev-parse', 'HEAD') != _git(primary, 'rev-parse', f'refs/remotes/{remote}/{default}')
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
        _git(primary, 'branch', '-d', '--', branch)
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
    return {'owned': True, 'head_protected': branch_info['protected'], 'common_dir': str(common), 'remote': remote, 'remote_url': url,
            'default_branch': default, 'default_checkout': str(primary)}


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
