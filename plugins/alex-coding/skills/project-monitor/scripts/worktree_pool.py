import argparse
from contextlib import contextmanager
import datetime
import fcntl
import json
from pathlib import Path
import shlex
import subprocess
import uuid

SCHEMA = 1
POOL_FILE = 'worktree-pool.json'
MAIN = 'main'


class PoolError(Exception):
    def __init__(self, message, status='refused', **detail):
        super().__init__(message)
        self.result = dict(status=status, reason=message, **detail)


def git(cwd, *args, check=True):
    result = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True, timeout=300)
    if check and result.returncode != 0:
        raise PoolError(f'git {" ".join(args)} failed: {(result.stderr or result.stdout).strip()[:300]}', status='error')
    return result.stdout.strip() if check else result


def worktrees(repo):
    records, current = [], {}
    for line in git(repo, 'worktree', 'list', '--porcelain').splitlines():
        if not line:
            if current:
                records.append(current)
            current = {}
            continue
        key, _, value = line.partition(' ')
        current[key] = value or True
    if current:
        records.append(current)
    return records


def common_dir(repo):
    return Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()


def primary_checkout(repo):
    return Path(worktrees(repo)[0]['worktree']).resolve()


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def empty_entry():
    return dict(holder=None, branch=None, pr=None, acquired_at=None)


class Pool:
    def __init__(self, repo):
        self.common = common_dir(Path(repo).expanduser().resolve())
        self.primary = primary_checkout(self.common)
        self.path = self.common / POOL_FILE

    @contextmanager
    def locked(self, create=False):
        with (self.common / 'worktree-pool.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists():
                data = json.loads(self.path.read_text())
                if data.get('schema') != SCHEMA:
                    raise PoolError('worktree pool uses an unsupported schema')
            elif create:
                data = dict(schema=SCHEMA, remote='origin', default=None, prepare=None, warm=None,
                            slots={}, main=empty_entry())
            else:
                raise PoolError('this repository has no worktree pool; run init first')
            yield data
            temporary = self.common / ('worktree-pool.' + uuid.uuid4().hex + '.tmp')
            temporary.write_text(json.dumps(data, indent=2))
            temporary.replace(self.path)

    def resolve(self, data, path):
        path = Path(path).expanduser().resolve()
        if path == self.primary:
            return MAIN, data['main']
        entry = data['slots'].get(str(path))
        if entry is None:
            raise PoolError(f'{path} is not a slot of this pool')
        return str(path), entry

    def checkout(self, key):
        return self.primary if key == MAIN else Path(key)


def tracked_changes(path):
    return git(path, 'status', '--porcelain', '--untracked-files=no').splitlines()


def untracked_files(path):
    return [line[3:] for line in git(path, 'status', '--porcelain').splitlines() if line.startswith('??')]


def current_branch(path):
    result = git(path, 'symbolic-ref', '-q', '--short', 'HEAD', check=False)
    return result.stdout.strip() or None


def fetch_default(data, path):
    git(path, 'fetch', '--no-tags', data['remote'],
        f'refs/heads/{data["default"]}:refs/remotes/{data["remote"]}/{data["default"]}')
    return f'{data["remote"]}/{data["default"]}'


def run_hook(command, cwd):
    if not command:
        return None
    result = subprocess.run(shlex.split(command), cwd=cwd, capture_output=True, text=True, timeout=600)
    return dict(command=command, exit=result.returncode,
                output=(result.stdout + result.stderr).strip()[-500:])


def start_warm(pool, data):
    if not data.get('warm'):
        return None
    log = pool.common / 'worktree-pool-warm.log'
    with log.open('a') as handle:
        handle.write(f'{now()} warm: {data["warm"]}\n')
        handle.flush()
        process = subprocess.Popen(shlex.split(data['warm']), cwd=pool.primary, stdout=handle, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
    return dict(command=data['warm'], pid=process.pid, log=str(log))


def init(repo, remote=None, default=None, prepare=None, warm=None):
    pool = Pool(repo)
    with pool.locked(create=True) as data:
        if remote:
            data['remote'] = remote
        if default:
            data['default'] = default
        if not data['default']:
            head = git(pool.primary, 'symbolic-ref', '--short', f'refs/remotes/{data["remote"]}/HEAD', check=False).stdout.strip()
            data['default'] = head.split('/', 1)[1] if '/' in head else 'main'
        if prepare is not None:
            data['prepare'] = prepare or None
        if warm is not None:
            data['warm'] = warm or None
        return dict(status='ready', primary=str(pool.primary), remote=data['remote'], default=data['default'],
                    prepare=data['prepare'], warm=data['warm'], slots=sorted(data['slots']))


def add_slot(repo, slot):
    pool = Pool(repo)
    path = Path(slot).expanduser().resolve()
    if path == pool.primary:
        raise PoolError('the primary checkout is the pool main, not a slot')
    record = next((r for r in worktrees(pool.primary) if Path(r['worktree']).resolve() == path), None)
    if record is None:
        raise PoolError(f'{path} is not a registered worktree of this repository')
    with pool.locked() as data:
        data['slots'].setdefault(str(path), empty_entry())
    if 'locked' not in record:
        git(pool.primary, 'worktree', 'lock', '--reason', 'worktree pool slot', str(path))
    return dict(status='added', slot=str(path))


def remove_slot(repo, slot):
    pool = Pool(repo)
    with pool.locked() as data:
        key, entry = pool.resolve(data, slot)
        if key == MAIN:
            raise PoolError('the pool main cannot be removed')
        if entry['holder']:
            raise PoolError(f'{key} is held by {entry["holder"]}; release it first')
        del data['slots'][key]
    git(pool.primary, 'worktree', 'unlock', key, check=False)
    return dict(status='removed', slot=key)


def status(repo):
    pool = Pool(repo)
    with pool.locked() as data:
        rows = []
        for key, entry in [(MAIN, data['main'])] + sorted(data['slots'].items()):
            path = pool.checkout(key)
            exists = path.exists()
            rows.append(dict(entry, slot=key, path=str(path), exists=exists,
                             checked_out=current_branch(path) if exists else None,
                             tracked_changes=len(tracked_changes(path)) if exists else None))
        free = [row['slot'] for row in rows if row['slot'] != MAIN and not row['holder']]
        return dict(status='ok', default=data['default'], free=free, slots=rows)


def acquire(repo, holder, branch, slot=None, main=False):
    pool = Pool(repo)
    with pool.locked() as data:
        for key, entry in [(MAIN, data['main'])] + list(data['slots'].items()):
            if entry['holder'] == holder and entry['branch'] == branch:
                return dict(status='acquired', slot=key, path=str(pool.checkout(key)), branch=branch, reused=True)
        if main:
            key, entry = MAIN, data['main']
        elif slot:
            key, entry = pool.resolve(data, slot)
        else:
            free = [k for k, e in sorted(data['slots'].items()) if not e['holder']]
            if not free:
                raise PoolError('every slot is held', status='busy',
                                holders={k: e['holder'] for k, e in data['slots'].items()},
                                main_holder=data['main']['holder'])
            key, entry = free[0], data['slots'][free[0]]
        if entry['holder']:
            raise PoolError(f'{key} is held by {entry["holder"]}', status='busy')
        path = pool.checkout(key)
        if key == MAIN and current_branch(path) != data['default']:
            raise PoolError(f'the pool main is not on {data["default"]}')
        if tracked_changes(path):
            raise PoolError(f'{path} has uncommitted changes', changes=tracked_changes(path)[:20])
        if key != MAIN and untracked_files(path):
            raise PoolError(f'{path} has untracked files left by an earlier task', untracked=untracked_files(path)[:20])
        if git(path, 'show-ref', '--verify', '--quiet', f'refs/heads/{branch}', check=False).returncode == 0:
            raise PoolError(f'branch {branch} already exists')
        base = fetch_default(data, path)
        git(path, 'switch', '--no-track', '-c', branch, base)
        entry.update(holder=holder, branch=branch, pr=None, acquired_at=now())
        prepare = data.get('prepare')
    return dict(status='acquired', slot=key, path=str(path), branch=branch, base=git(path, 'rev-parse', 'HEAD'),
                prepare=run_hook(prepare, path))


def bind(repo, slot, pr, holder=None):
    pool = Pool(repo)
    with pool.locked() as data:
        key, entry = pool.resolve(data, slot)
        if not entry['holder']:
            raise PoolError(f'{key} is not held; acquire it before binding a PR')
        if holder and entry['holder'] != holder:
            raise PoolError(f'{key} is held by {entry["holder"]}, not {holder}')
        if entry['pr'] not in (None, pr):
            raise PoolError(f'{key} is already bound to {entry["pr"]}')
        entry['pr'] = pr
        return dict(status='bound', slot=key, pr=pr, holder=entry['holder'], branch=entry['branch'])


def release(repo, slot, holder=None, pr=None, expect_head=None):
    pool = Pool(repo)
    with pool.locked() as data:
        key, entry = pool.resolve(data, slot)
        if not entry['holder']:
            return dict(status='released', slot=key, reason='slot was already free')
        if not (holder and entry['holder'] == holder) and not (pr and entry['pr'] == pr):
            raise PoolError(f'{key} is held by {entry["holder"]} for {entry["pr"]}; name its holder or PR')
        path = pool.checkout(key)
        changes = tracked_changes(path)
        if changes:
            raise PoolError(f'{path} has uncommitted changes; commit or discard them before release', status='preserved',
                            changes=changes[:20])
        branch = entry['branch']
        base = fetch_default(data, path)
        result = dict(status='released', slot=key, path=str(path), branch=branch)
        if key == MAIN:
            git(path, 'switch', data['default'])
            merged = git(path, 'merge', '--ff-only', base, check=False)
            result['main_sync'] = 'synced' if merged.returncode == 0 else 'diverged'
        else:
            git(path, 'switch', '--detach', base)
        if branch and git(path, 'show-ref', '--verify', '--quiet', f'refs/heads/{branch}', check=False).returncode == 0:
            local = git(path, 'rev-parse', f'refs/heads/{branch}')
            pushed = git(path, 'rev-parse', '-q', '--verify', f'refs/remotes/{data["remote"]}/{branch}', check=False).stdout.strip()
            landed = git(path, 'merge-base', '--is-ancestor', local, base, check=False).returncode == 0
            if local in (expect_head, pushed) or landed:
                git(path, 'branch', '-D', branch)
                result['branch_deleted'] = True
            else:
                result['branch_deleted'] = False
                result['kept_branch_reason'] = 'local branch has commits that are not on the PR head or the remote'
        result['untracked'] = untracked_files(path)[:20]
        if key == MAIN:
            data['main'] = empty_entry()
        else:
            data['slots'][key] = empty_entry()
        return result


def sync_main(repo):
    pool = Pool(repo)
    with pool.locked() as data:
        path = pool.primary
        if data['main']['holder']:
            return dict(status='skipped', reason=f'the pool main is held by {data["main"]["holder"]}')
        if current_branch(path) != data['default']:
            return dict(status='skipped', reason=f'the pool main is not on {data["default"]}')
        if tracked_changes(path):
            return dict(status='skipped', reason='the pool main has uncommitted changes', changes=tracked_changes(path)[:20])
        base = fetch_default(data, path)
        before = git(path, 'rev-parse', 'HEAD')
        merged = git(path, 'merge', '--ff-only', base, check=False)
        if merged.returncode != 0:
            return dict(status='skipped', reason='the pool main cannot fast-forward: ' + merged.stderr.strip()[:300])
        after = git(path, 'rev-parse', 'HEAD')
        result = dict(status='synced', before=before, after=after)
        if before != after:
            result['prepare'] = run_hook(data.get('prepare'), path)
            result['warm'] = start_warm(pool, data)
        return result


def main():
    parser = argparse.ArgumentParser(description='A fixed pool of long-lived worktree slots plus the primary checkout as the pool main')
    parser.add_argument('--repo', type=Path, default=Path.cwd(), help='Any checkout of the repository')
    commands = parser.add_subparsers(dest='command', required=True)
    setup = commands.add_parser('init')
    setup.add_argument('--remote')
    setup.add_argument('--default')
    setup.add_argument('--prepare', help='Command run in a checkout after it moves to a new base; empty clears it')
    setup.add_argument('--warm', help='Background command run in the pool main after it syncs; empty clears it')
    for name in ('add-slot', 'remove-slot'):
        commands.add_parser(name).add_argument('--slot', type=Path, required=True)
    commands.add_parser('status')
    take = commands.add_parser('acquire')
    take.add_argument('--holder', required=True)
    take.add_argument('--branch', required=True)
    where = take.add_mutually_exclusive_group()
    where.add_argument('--slot', type=Path)
    where.add_argument('--main', action='store_true')
    attach = commands.add_parser('bind')
    attach.add_argument('--slot', type=Path, required=True)
    attach.add_argument('--pr', required=True)
    attach.add_argument('--holder')
    give = commands.add_parser('release')
    give.add_argument('--slot', type=Path, required=True)
    give.add_argument('--holder')
    give.add_argument('--pr')
    give.add_argument('--expect-head')
    commands.add_parser('sync-main')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            result = init(args.repo, args.remote, args.default, args.prepare, args.warm)
        elif args.command == 'add-slot':
            result = add_slot(args.repo, args.slot)
        elif args.command == 'remove-slot':
            result = remove_slot(args.repo, args.slot)
        elif args.command == 'status':
            result = status(args.repo)
        elif args.command == 'acquire':
            result = acquire(args.repo, args.holder, args.branch, args.slot, args.main)
        elif args.command == 'bind':
            result = bind(args.repo, args.slot, args.pr, args.holder)
        elif args.command == 'release':
            result = release(args.repo, args.slot, args.holder, args.pr, args.expect_head)
        else:
            result = sync_main(args.repo)
    except PoolError as error:
        print(json.dumps(error.result, indent=2, ensure_ascii=False))
        raise SystemExit(3 if error.result['status'] == 'busy' else 1)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
