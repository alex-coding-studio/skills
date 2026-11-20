import argparse
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid

_spec = importlib.util.spec_from_file_location('author_monitor_core', Path(__file__).with_name('author_monitor_core.py'))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


class _OwnershipLost(RuntimeError):
    pass


def _utc_now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError, OSError, ValueError):
        return None


def _atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_cursor(root):
    data = _read_json(Path(root) / 'cursor.json')
    if not isinstance(data, dict):
        return 0
    value = data.get('last_seq', 0)
    return int(value) if isinstance(value, int) and value >= 0 else 0


def write_cursor(root, seq):
    payload = json.dumps({'last_seq': int(seq), 'updated_at': _utc_now()}, ensure_ascii=False) + '\n'
    _atomic_write_text(Path(root) / 'cursor.json', payload)


def _parse_outbox(path):
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
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


def append_outbox(root, message, terminal=None, cleanup_result=None, disposable=None, pool_slot=None, has_checkout=None):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'outbox.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        outbox = root / 'outbox.jsonl'
        existing = _parse_outbox(outbox)
        next_seq = (existing[-1]['seq'] + 1) if existing else 1
        record = {'seq': next_seq, 'created_at': _utc_now(), 'text': message}
        if terminal is not None:
            record['terminal'] = terminal
        if cleanup_result is not None:
            record['cleanup_result'] = cleanup_result
        if disposable is not None:
            record['disposable'] = bool(disposable)
        if pool_slot is not None:
            record['pool_slot'] = bool(pool_slot)
        if has_checkout is not None:
            record['has_checkout'] = bool(has_checkout)
        existing.append(record)
        content = ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in existing)
        _atomic_write_text(outbox, content)
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


def _message_has_terminal_event(message):
    lines = message.splitlines()
    marker = 'New since the last delivery:'
    if marker in lines:
        lines = lines[lines.index(marker) + 1:]
    return any(line.startswith('terminal id=') for line in lines)


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
        if _message_has_terminal_event(message):
            state = _read_json(self.outbox_root / 'state.json') or {}
            target = state.get('target') or {}
            append_outbox(
                self.outbox_root,
                message,
                terminal=target.get('terminal'),
                cleanup_result=target.get('cleanup_result'),
                disposable=core.disposable_target(target),
                pool_slot=bool(target.get('pool_slot')),
                has_checkout=bool(target.get('checkout')),
            )
        else:
            append_outbox(self.outbox_root, message)
        return True

    def may_clean(self, target):
        return (target.get('cleanup') or {}).get('lifecycle') == 'disposable-v1'

    def report(self, root, failures):
        for line in failures:
            core.note(root, line)
            print(line, flush=True)


def _ownership_mismatch(root, session, name, runner_dir=None, expected_takeovers=None):
    author_state = _read_json(Path(root) / 'state.json')
    if author_state is not None:
        if author_state.get('session') != session or not core.same_pr(author_state.get('pr'), name):
            return (f"author state is bound to another session or runtime "
                    f"(pr={author_state.get('pr')!r}, session={author_state.get('session')!r})")
        if expected_takeovers is not None:
            current_takeovers = len(((author_state.get('target') or {}).get('takeovers')) or [])
            if current_takeovers != expected_takeovers:
                return f'author state was taken over (takeovers={current_takeovers}, expected={expected_takeovers})'
    if runner_dir is not None:
        runner_state = _read_json(Path(runner_dir) / 'state.json')
        if runner_state is not None:
            ad = runner_state.get('author_delivery') or {}
            if (ad.get('runtime') != 'antigravity' or ad.get('session') != session
                    or not core.same_pr(runner_state.get('pr'), name)):
                return (f"runner author_delivery is bound to "
                        f"{ad.get('runtime')!r}:{ad.get('session')!r} for {runner_state.get('pr')!r}")
    return None


def invalidate_waiter(root, timeout=2.0):
    root = Path(root).expanduser().resolve()
    owner = _read_json(root / 'wait.owner.json')
    pid = owner.get('pid') if isinstance(owner, dict) else None
    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid() or not lock_held(root / 'wait.lock'):
        return False
    process = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True, timeout=10)
    cmdline = process.stdout.strip()
    if process.returncode != 0 or 'antigravity_pr_monitor.py' not in cmdline or 'wait' not in cmdline or str(root) not in cmdline:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + timeout
    while lock_held(root / 'wait.lock') and time.monotonic() < deadline:
        time.sleep(0.05)
    return not lock_held(root / 'wait.lock')


@contextmanager
def wait_lock(root, session, name, runner_dir=None, supersede_timeout=3.0):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    mismatch = _ownership_mismatch(root, session, name, runner_dir)
    if mismatch:
        raise _OwnershipLost(mismatch)
    owner_file = root / 'wait.owner.json'
    with (root / 'wait.lock').open('a') as lock:
        deadline = time.monotonic() + supersede_timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                holder = _read_json(owner_file)
                superseded = isinstance(holder, dict) and holder.get('session') not in (None, session)
                if not superseded or time.monotonic() >= deadline:
                    raise SystemExit(f'{name} already has an active waiter; refusing duplicate wait')
                mismatch = _ownership_mismatch(root, session, name, runner_dir)
                if mismatch:
                    raise _OwnershipLost(mismatch)
                time.sleep(0.05)
        _atomic_write_text(owner_file, json.dumps({'pid': os.getpid(), 'session': session, 'pr': name}) + '\n')
        try:
            yield lock
        finally:
            holder = _read_json(owner_file)
            if isinstance(holder, dict) and holder.get('pid') == os.getpid():
                owner_file.unlink(missing_ok=True)


def consume_unread(root, session, name, runner_dir=None, expected_takeovers=None):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'outbox.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        mismatch = _ownership_mismatch(root, session, name, runner_dir, expected_takeovers=expected_takeovers)
        if mismatch:
            return 'ownership-lost', mismatch
        last_seq = read_cursor(root)
        unread = [item for item in _parse_outbox(root / 'outbox.jsonl') if item['seq'] > last_seq]
        if unread:
            write_cursor(root, unread[-1]['seq'])
        return 'ok', unread


def _classify_terminal(terminal, cleanup_result, disposable, pool_slot, has_checkout):
    if terminal not in ('merged', 'closed'):
        return 'none'
    status = (cleanup_result or {}).get('status') if isinstance(cleanup_result, dict) else None
    if terminal == 'closed':
        if pool_slot:
            if cleanup_result is None:
                return 'retrying'
            return 'cleaned' if status == 'released' else 'needs-attention'
        return 'cleaned'
    if pool_slot:
        if cleanup_result is None:
            return 'retrying'
        return 'cleaned' if status == 'released' else 'needs-attention'
    if status in ('cleaned', 'released'):
        return 'cleaned'
    if disposable:
        if cleanup_result is None:
            return 'retrying'
        if status in ('partial', 'interrupted', 'error') and cleanup_result.get('retryable', True):
            return 'retrying'
        return 'needs-attention'
    if not has_checkout and cleanup_result is None:
        return 'cleaned'
    return 'needs-attention'


def _extract_unread_events(text):
    lines = text.splitlines()
    marker = 'New since the last delivery:'
    if marker in lines:
        extracted = []
        for line in lines[lines.index(marker) + 1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(('After verifying the merge, run the protected foreground completion:',
                                    'The pool slot ')):
                break
            extracted.append(stripped)
        if extracted:
            return extracted
    return [line.strip() for line in lines if line.strip()]


def _format_delivery(unread, next_cmd, terminal_state, terminal_outcome=None, cleanup_result=None):
    latest = unread[-1]
    parts = [latest['text']]
    if len(unread) > 1:
        earlier_lines = []
        for item in unread[:-1]:
            for line in _extract_unread_events(item['text']):
                earlier_lines.append(f"[seq {item['seq']}] {line}")
        header = (f"Note: {len(unread)} outbox updates coalesced (seq {unread[0]['seq']}..{latest['seq']}); "
                  'showing the latest full state plus earlier unread events:')
        parts.append('\n'.join([header, *earlier_lines]))
    if terminal_state == 'cleaned':
        if cleanup_result is not None:
            parts.append(
                f'Terminal outcome: {terminal_outcome}; cleanup_result='
                + json.dumps(cleanup_result, ensure_ascii=False)
            )
        parts.append('PR reached terminal state; no further waiting is needed.')
        return 0, '\n\n'.join(parts)
    if terminal_state == 'needs-attention':
        parts.append(
            f'Terminal cleanup requires attention (terminal={terminal_outcome}); cleanup_result='
            + json.dumps(cleanup_result, ensure_ascii=False)
        )
        return 2, '\n\n'.join(parts)
    parts.append('After handling this update, resume waiting in the background with:\n' + next_cmd)
    return 0, '\n\n'.join(parts)


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
        f'{name} runner-inactive: the PR runner is not healthy, stopped before clean completion, or cleanup requires attention.\n'
        + json.dumps(detail, indent=2, ensure_ascii=False)
    )


def _handle_unread(unread, next_cmd, author_state=None):
    terminal_record = next((item for item in reversed(unread) if item.get('terminal') in ('merged', 'closed')), None)
    if terminal_record is not None:
        terminal_state = _classify_terminal(
            terminal_record.get('terminal'),
            terminal_record.get('cleanup_result'),
            bool(terminal_record.get('disposable')),
            bool(terminal_record.get('pool_slot')),
            bool(terminal_record.get('has_checkout')),
        )
        return _format_delivery(
            unread, next_cmd, terminal_state,
            terminal_outcome=terminal_record.get('terminal'),
            cleanup_result=terminal_record.get('cleanup_result'),
        )
    if any(_message_has_terminal_event(item['text']) for item in unread):
        target = (author_state or {}).get('target') or {}
        if target.get('terminal') in ('merged', 'closed'):
            terminal_state = _classify_terminal(
                target.get('terminal'),
                target.get('cleanup_result'),
                core.disposable_target(target),
                bool(target.get('pool_slot')),
                bool(target.get('checkout')),
            )
            return _format_delivery(
                unread, next_cmd, terminal_state,
                terminal_outcome=target.get('terminal'),
                cleanup_result=target.get('cleanup_result'),
            )
    return _format_delivery(unread, next_cmd, 'none')


def wait_for_event(root, session, name, runner_dir=None, interval=1.0, timeout=0.0, script=__file__):
    root = Path(root).expanduser().resolve()
    runner_dir = Path(runner_dir).expanduser().resolve() if runner_dir is not None else None
    lock_path = (runner_dir / 'run.lock') if runner_dir is not None else (root / 'run.lock')
    next_cmd = build_wait_command(script, session, name, state_dir=root, runner_dir=runner_dir)
    deadline = (time.monotonic() + timeout) if timeout > 0 else None
    try:
        with wait_lock(root, session, name, runner_dir=runner_dir):
            initial_author = _read_json(root / 'state.json')
            expected_takeovers = (
                len(((initial_author.get('target') or {}).get('takeovers')) or [])
                if isinstance(initial_author, dict) and initial_author.get('target') is not None else None
            )
            while True:
                status, payload = consume_unread(
                    root, session, name, runner_dir=runner_dir, expected_takeovers=expected_takeovers
                )
                if status == 'ownership-lost':
                    return 2, f'{name} ownership-lost: {payload}'
                if payload:
                    return _handle_unread(payload, next_cmd, _read_json(root / 'state.json'))
                live = lock_held(lock_path)
                author_state = _read_json(root / 'state.json')
                runner_state = _read_json(runner_dir / 'state.json') if runner_dir is not None else None
                mismatch = _ownership_mismatch(root, session, name, runner_dir, expected_takeovers=expected_takeovers)
                if mismatch:
                    return 2, f'{name} ownership-lost: {mismatch}'
                target = (author_state or {}).get('target')
                target_state = (
                    _classify_terminal(
                        target.get('terminal'),
                        target.get('cleanup_result'),
                        core.disposable_target(target),
                        bool(target.get('pool_slot')),
                        bool(target.get('checkout')),
                    )
                    if target is not None else 'none'
                )
                errored = bool(runner_state and runner_state.get('phase') == 'error')
                if not live or errored or target_state == 'needs-attention':
                    status, payload = consume_unread(
                        root, session, name, runner_dir=runner_dir, expected_takeovers=expected_takeovers
                    )
                    if status == 'ownership-lost':
                        return 2, f'{name} ownership-lost: {payload}'
                    if payload:
                        return _handle_unread(payload, next_cmd, _read_json(root / 'state.json'))
                    author_state = _read_json(root / 'state.json')
                    runner_state = _read_json(runner_dir / 'state.json') if runner_dir is not None else None
                    target = (author_state or {}).get('target')
                    target_state = (
                        _classify_terminal(
                            target.get('terminal'),
                            target.get('cleanup_result'),
                            core.disposable_target(target),
                            bool(target.get('pool_slot')),
                            bool(target.get('checkout')),
                        )
                        if target is not None else 'none'
                    )
                    settled_without_author = target is None and (runner_state or {}).get('phase') in ('merged', 'closed')
                    if not live and (target_state == 'cleaned' or settled_without_author):
                        return 0, _format_terminal_summary(name, author_state, runner_state)
                    return 2, _format_inactive_diagnostic(name, root, runner_dir, live, author_state, runner_state)
                if deadline is not None and time.monotonic() >= deadline:
                    return 3, (
                        f'{name} wait timed out after {timeout}s with no new events; runner is still active.\n'
                        'Resume waiting in the background with:\n' + next_cmd
                    )
                remaining = (deadline - time.monotonic()) if deadline is not None else interval
                time.sleep(min(interval, max(0.0, remaining)))
    except _OwnershipLost as error:
        return 2, f'{name} ownership-lost: {error}'


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
    def terminate(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    main()
