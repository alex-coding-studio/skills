import argparse
import fcntl
import json
from pathlib import Path
import re
import subprocess


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], capture_output=True,
                          text=True, check=True, timeout=60).stdout.strip()


def synchronize(primary, remote, default, run_git=None):
    run_git = run_git or git
    if run_git(primary, 'symbolic-ref', '--short', 'HEAD') != default:
        raise ValueError('The primary checkout must be on the remote default branch')
    reference = f'refs/remotes/{remote}/{default}'
    run_git(primary, 'fetch', '--no-prune', '--no-tags', '--refmap=', remote,
            f'+refs/heads/{default}:{reference}')
    commit = run_git(primary, 'rev-parse', '--verify', reference + '^{commit}')
    flagged = run_git(primary, 'ls-files', '-v', '-z').split('\0')
    for entry in flagged:
        if entry and (entry[0].islower() or entry[0] == 'S'):
            run_git(primary, 'update-index', '--no-assume-unchanged', '--no-skip-worktree', '--', entry[2:])
    run_git(primary, 'reset', '--hard', commit)
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
        records = git(repository, 'worktree', 'list', '--porcelain').split('\n\n')
        primary = Path(records[0].splitlines()[0].removeprefix('worktree ')).resolve()
        head = git(repository, 'ls-remote', '--symref', remote, 'HEAD')
        match = re.search(r'^ref: refs/heads/(.+)\tHEAD$', head, re.MULTILINE)
        if not match:
            raise ValueError('Could not resolve the remote default branch')
        default = match[1]
        git(repository, 'check-ref-format', '--branch', branch)
        if branch == default:
            raise ValueError('A task branch must differ from the default branch')
        commit = synchronize(primary, remote, default)
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
