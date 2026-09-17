import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import uuid


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], capture_output=True,
                          text=True, check=True, timeout=60).stdout.strip()


class UnownedIndexLock(FileExistsError):
    pass


@contextmanager
def owned_index_lock(index):
    lock = index.with_name(index.name + '.lock')
    if lock.exists():
        try:
            data = json.loads(lock.read_text())
            token = data['token']
            if data.get('owner') != 'alex-coding-disposable-v1' or not re.fullmatch(r'[0-9a-f]{32}', token):
                raise ValueError('Unrecognized owner')
            owner = index.with_name('task-sync-' + token + '.owner')
            if not lock.samefile(owner):
                raise ValueError('Ownership inode does not match')
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
            raise UnownedIndexLock('An unrelated Git index lock was preserved; synchronization needs attention') from error
        lock.unlink()
        owner.unlink()
        for suffix in ('.index', '.index.lock'):
            index.with_name('task-sync-' + token + suffix).unlink(missing_ok=True)
    token = uuid.uuid4().hex
    owner = index.with_name('task-sync-' + token + '.owner')
    temporary = index.with_name('task-sync-' + token + '.index')
    with owner.open('x') as file:
        json.dump(dict(owner='alex-coding-disposable-v1', token=token), file)
        file.flush()
        os.fsync(file.fileno())
    acquired = False
    try:
        os.link(owner, lock)
        acquired = True
        yield temporary
    finally:
        if acquired and lock.exists() and lock.samefile(owner):
            lock.unlink()
        owner.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


def synchronize(primary, remote, default, run_git=None, lock_fd=None):
    run_git = run_git or git
    if lock_fd is None:
        common = Path(run_git(primary, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
        with (common / 'author-monitor-cleanup.lock').open('a') as repository_lock:
            fcntl.flock(repository_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return synchronize(primary, remote, default, run_git, repository_lock.fileno())
    if run_git(primary, 'symbolic-ref', '--short', 'HEAD') != default:
        raise ValueError('The primary checkout must be on the remote default branch')
    reference = f'refs/remotes/{remote}/{default}'
    run_git(primary, 'fetch', '--no-prune', '--no-tags', '--refmap=', remote,
            f'+refs/heads/{default}:{reference}')
    commit = run_git(primary, 'rev-parse', '--verify', reference + '^{commit}')
    index = Path(run_git(primary, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))
    with owned_index_lock(index) as temporary:
        if run_git(primary, 'symbolic-ref', '--short', 'HEAD') != default:
            raise ValueError('The primary branch changed during fetch')
        previous = run_git(primary, 'rev-parse', 'HEAD')
        environment = dict(os.environ, GIT_INDEX_FILE=str(temporary))
        for args in [('read-tree', previous), ('read-tree', '--reset', '-u', '--no-sparse-checkout', commit)]:
            subprocess.run(['git', '-C', str(primary), *args], env=environment, pass_fds=(lock_fd,),
                           capture_output=True, text=True, check=True, timeout=60)
        run_git(primary, 'update-ref', f'refs/heads/{default}', commit, previous)
        temporary.replace(index)
    if (run_git(primary, 'rev-parse', 'HEAD') != commit
            or run_git(primary, 'status', '--porcelain', '--untracked-files=no')):
        raise RuntimeError('Default checkout did not match the fetched commit')
    return commit


def create_worktree(repository, destination, branch, remote='origin'):
    repository = Path(repository).resolve()
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('The destination already exists')
    common = Path(git(repository, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    with (common / 'author-monitor-cleanup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        paths = [Path(value.removeprefix('worktree ')).resolve()
                 for value in git(repository, 'worktree', 'list', '--porcelain', '-z').split('\0')
                 if value.startswith('worktree ')]
        destination = destination.resolve()
        if any(destination == path or path in destination.parents or destination in path.parents for path in paths):
            raise ValueError('Task worktrees must not contain or be inside another registered worktree')
        primary = paths[0]
        head = git(repository, 'ls-remote', '--symref', remote, 'HEAD')
        match = re.search(r'^ref: refs/heads/(.+)\tHEAD$', head, re.MULTILINE)
        if not match:
            raise ValueError('Could not resolve the remote default branch')
        default = match[1]
        git(repository, 'check-ref-format', '--branch', branch)
        if branch == default:
            raise ValueError('A task branch must differ from the default branch')
        commit = synchronize(primary, remote, default, lock_fd=lock.fileno())
        git(primary, 'worktree', 'add', '-b', branch, str(destination), commit)
        return dict(path=str(destination.resolve()), branch=branch, base_sha=commit,
                    default_branch=default, default_checkout=str(primary))


def main():
    parser = argparse.ArgumentParser(description='Create a disposable task worktree from the synchronized default checkout')
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--branch', required=True)
    parser.add_argument('--remote', default='origin')
    args = parser.parse_args()
    print(json.dumps(create_worktree(args.repository, args.destination, args.branch, args.remote)))


if __name__ == '__main__':
    main()
