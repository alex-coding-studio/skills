import argparse
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time
import uuid

_spec = importlib.util.spec_from_file_location('author_monitor_core', Path(__file__).with_name('author_monitor_core.py'))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


def _utc_now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, OSError, ValueError):
        return None


def read_cursor(root):
    data = _read_json(Path(root) / 'cursor.json')
    if not isinstance(data, dict):
        return 0
    value = data.get('last_seq', 0)
    return int(value) if isinstance(value, int) and value >= 0 else 0


def write_cursor(root, seq):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / ('cursor.' + uuid.uuid4().hex + '.tmp')
    payload = json.dumps({'last_seq': int(seq), 'updated_at': _utc_now()}, ensure_ascii=False) + '\n'
    with temporary.open('w', encoding='utf-8') as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(root / 'cursor.json')


def _parse_outbox(path):
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and isinstance(item.get('seq'), int) and isinstance(item.get('text'), str):
            records.append(item)
    records.sort(key=lambda item: item['seq'])
    return records


def append_outbox(root, message):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'outbox.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        outbox = root / 'outbox.jsonl'
        existing = _parse_outbox(outbox)
        next_seq = (existing[-1]['seq'] + 1) if existing else 1
        record = {'seq': next_seq, 'created_at': _utc_now(), 'text': message}
        line = json.dumps(record, ensure_ascii=False) + '\n'
        with outbox.open('a', encoding='utf-8') as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return record


def read_outbox(root, after_seq=0):
    root = Path(root).expanduser().resolve()
    outbox = root / 'outbox.jsonl'
    if not outbox.exists():
        return []
    with (root / 'outbox.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        records = _parse_outbox(outbox)
    return [item for item in records if item['seq'] > after_seq]


def unread_outbox(root):
    root = Path(root).expanduser().resolve()
    return read_outbox(root, read_cursor(root))


def lock_held(path):
    path = Path(path)
    if not path.exists():
        return False
    try:
        with path.open('r') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
            return False
    except FileNotFoundError:
        return False


def build_wait_command(script, session, pr, state_dir=None, runner_dir=None):
    command = [sys.executable, str(Path(script).resolve()), '--session', session, '--pr', core.canonical(pr)]
    if state_dir is not None:
        command += ['--state-dir', str(Path(state_dir).expanduser().resolve())]
    command.append('wait')
    if runner_dir is not None:
        command += ['--runner-dir', str(Path(runner_dir).expanduser().resolve())]
    return shlex.join(command)


class Runtime:
    role = 'bot'
    state_delivery = True
    deliver_cleaned_terminal = True
    marker = 'From Antigravity 🤖'
    delivery_name = 'outbox'
    state_keys = ('session', 'pr')

    def __init__(self, session, script, outbox_root=None):
        self.session = session
        self.script = script
        self.outbox_root = Path(outbox_root).expanduser().resolve() if outbox_root is not None else None
        self.foreground_cleanup = True

    @property
    def identity_arguments(self):
        return ['--session', self.session]

    def deliver(self, message):
        if self.outbox_root is None:
            raise ValueError('outbox_root is required for Antigravity outbox delivery')
        append_outbox(self.outbox_root, message)
        return True

    def may_clean(self, target):
        return (target.get('cleanup') or {}).get('lifecycle') == 'disposable-v1'

    def report(self, root, failures):
        for line in failures:
            core.note(root, line)
            print(line, flush=True)


@contextmanager
def wait_lock(root, name):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'wait.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f'{name} already has an active waiter; refusing duplicate wait')
        yield lock


def _is_settled_terminal(target):
    terminal = (target or {}).get('terminal')
    if terminal not in ('merged', 'closed'):
        return False
    if core.disposable_target(target or {}) and terminal == 'merged':
        status = ((target or {}).get('cleanup_result') or {}).get('status')
        if status in (None, 'partial', 'interrupted', 'error'):
            return False
    return True


def _format_delivery(unread, author_state, next_cmd):
    latest = unread[-1]
    parts = [latest['text']]
    if len(unread) > 1:
        parts.append(
            f"Note: {len(unread)} outbox updates coalesced (seq {unread[0]['seq']}..{latest['seq']}); "
            'showing the latest full state.'
        )
    target = (author_state or {}).get('target') or {}
    cleanup_result = target.get('cleanup_result')
    if _is_settled_terminal(target):
        if cleanup_result is not None:
            parts.append(
                f"Terminal outcome: {target.get('terminal')}; cleanup_result="
                + json.dumps(cleanup_result, ensure_ascii=False)
            )
        parts.append('PR reached terminal state; no further waiting is needed.')
    else:
        parts.append('After handling this update, resume waiting in the background with:\n' + next_cmd)
    return '\n\n'.join(parts)


def _format_terminal_summary(name, author_state, runner_state):
    target = (author_state or {}).get('target') or {}
    terminal = target.get('terminal') or (runner_state or {}).get('phase')
    cleanup_result = target.get('cleanup_result')
    lines = [f'{name} reached terminal state: {terminal}.']
    if cleanup_result is not None:
        lines.append('cleanup_result=' + json.dumps(cleanup_result, ensure_ascii=False))
    else:
        lines.append('cleanup_result=null')
    lines.append('The PR runner has stopped; no further waiting is needed.')
    return '\n'.join(lines)


def _format_inactive_diagnostic(name, root, runner_dir, active, author_state, runner_state):
    target = (author_state or {}).get('target') or {}
    detail = {
        'active': active,
        'state_directory': str(runner_dir or root),
        'log': str((runner_dir or root) / 'monitor.log'),
    }
    if runner_state:
        for key in ('phase', 'last_error', 'last_transport_error', 'rounds', 'round_limit', 'last_review_url'):
            if runner_state.get(key) is not None:
                detail[key] = runner_state.get(key)
    if target:
        detail['author_stopped'] = target.get('stopped')
        detail['author_terminal'] = target.get('terminal')
        if target.get('cleanup_result') is not None:
            detail['cleanup_result'] = target.get('cleanup_result')
    return (
        f'{name} runner-inactive: the PR runner is not healthy or stopped before reaching a terminal state.\n'
        + json.dumps(detail, indent=2, ensure_ascii=False)
    )


def wait_for_event(root, session, name, runner_dir=None, interval=1.0, timeout=0.0, script=__file__):
    root = Path(root).expanduser().resolve()
    runner_dir = Path(runner_dir).expanduser().resolve() if runner_dir is not None else None
    lock_path = (runner_dir / 'run.lock') if runner_dir is not None else (root / 'run.lock')
    next_cmd = build_wait_command(script, session, name, state_dir=root, runner_dir=runner_dir)
    deadline = (time.monotonic() + timeout) if timeout > 0 else None
    with wait_lock(root, name):
        while True:
            last_seq = read_cursor(root)
            unread = read_outbox(root, last_seq)
            if unread:
                write_cursor(root, unread[-1]['seq'])
                author_state = _read_json(root / 'state.json')
                return 0, _format_delivery(unread, author_state, next_cmd)
            live = lock_held(lock_path)
            runner_state = _read_json(runner_dir / 'state.json') if runner_dir is not None else None
            errored = bool(runner_state and runner_state.get('phase') == 'error')
            if not live or errored:
                unread = read_outbox(root, last_seq)
                if unread:
                    write_cursor(root, unread[-1]['seq'])
                    author_state = _read_json(root / 'state.json')
                    return 0, _format_delivery(unread, author_state, next_cmd)
                author_state = _read_json(root / 'state.json')
                target = (author_state or {}).get('target')
                settled = _is_settled_terminal(target) if target is not None else (
                    (runner_state or {}).get('phase') in ('merged', 'closed')
                )
                if not live and settled:
                    return 0, _format_terminal_summary(name, author_state, runner_state)
                return 2, _format_inactive_diagnostic(name, root, runner_dir, live, author_state, runner_state)
            if deadline is not None and time.monotonic() >= deadline:
                return 3, (
                    f'{name} wait timed out after {timeout}s with no new events; runner is still active.\n'
                    'Resume waiting in the background with:\n' + next_cmd
                )
            remaining = (deadline - time.monotonic()) if deadline is not None else interval
            time.sleep(min(interval, max(0.0, remaining)))


def main():
    parser = argparse.ArgumentParser(description='One named PR author feedback listener per pull request, delivered to an Antigravity session through a local outbox')
    parser.add_argument('--session', required=True)
    parser.add_argument('--pr', required=True, help='owner/repo#number or a pull request URL')
    parser.add_argument('--state-dir', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    register = commands.add_parser('register')
    register.add_argument('--author')
    register.add_argument('--checkout', type=Path)
    commands.add_parser('status')
    commands.add_parser('complete')
    commands.add_parser('reopen')
    ack = commands.add_parser('ack')
    ack.add_argument('--token', required=True)
    claim = commands.add_parser('claim')
    claim.add_argument('--events', nargs='+', required=True)
    run = commands.add_parser('run')
    run.add_argument('--interval', type=int, default=45)
    run.add_argument('--once', action='store_true')
    wait = commands.add_parser('wait')
    wait.add_argument('--runner-dir', type=Path)
    wait.add_argument('--interval', type=float, default=1.0)
    wait.add_argument('--timeout', type=float, default=0.0)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', args.session):
        parser.error('--session must be a stable identifier of letters, digits, dot, underscore or hyphen')
    try:
        name = core.canonical(args.pr)
    except ValueError as error:
        parser.error(str(error))
    base = os.environ.get('ANTIGRAVITY_HOME') or str(Path.home() / '.gemini' / 'antigravity')
    owner = Path(base) / 'state' / 'author-pr-monitor' / args.session
    root = (args.state_dir or owner / core.readable_slug(name)).expanduser().resolve()
    if args.command == 'wait':
        if args.interval < 0.1:
            parser.error('interval must be at least 0.1 seconds')
        if args.timeout < 0:
            parser.error('timeout must be nonnegative')
        root.mkdir(parents=True, exist_ok=True)
        os.chdir(root)
        code, message = wait_for_event(
            root, args.session, name, runner_dir=args.runner_dir,
            interval=args.interval, timeout=args.timeout, script=__file__,
        )
        print(message, flush=True)
        raise SystemExit(code)
    store = core.Store(root, args.session, name, Runtime(args.session, __file__, root))
    if args.command == 'register':
        print('registered' if store.register(args.author, args.checkout) else 'already registered')
    elif args.command == 'complete':
        os.chdir(store.root)
        outcome = store.complete()
        print(json.dumps(outcome, indent=2))
        if outcome.get('status') != 'cleaned':
            raise SystemExit(1)
    elif args.command == 'status':
        print(json.dumps(store.read(), indent=2))
    elif args.command == 'reopen':
        store.reopen()
    elif args.command == 'ack':
        print(store.acknowledge(args.token))
    elif args.command == 'claim':
        print(store.claim(args.events))
    else:
        if args.interval < 10:
            parser.error('interval must be at least 10 seconds')
        if store.read()['target'] is None:
            parser.error('register this pull request before running')
        core.run(store, args.interval, args.once)


if __name__ == '__main__':
    main()
