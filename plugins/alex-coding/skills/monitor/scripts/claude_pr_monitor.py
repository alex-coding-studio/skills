import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import uuid
from urllib.parse import urlsplit

_spec = importlib.util.spec_from_file_location('author_monitor_core', Path(__file__).with_name('author_monitor_core.py'))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


class Runtime:
    role = 'bot'
    marker = 'From Claude 🤖'
    delivery_name = 'stdout'
    state_keys = ('session', 'name')

    def __init__(self, session, script, delivery='stdout', remote=None):
        if delivery not in ('stdout', 'session'):
            raise ValueError('Claude author delivery uses stdout or the owning session endpoint')
        self.session = session
        self.script = script
        self.failing = False
        self.delivery_name = delivery
        self.remote = validate_session_remote(remote) if delivery == 'session' else None

    @property
    def identity_arguments(self):
        return ['--session', self.session]

    def deliver(self, message):
        if self.remote:
            return deliver_to_session(self.remote, message)
        print(message, flush=True)
        return True

    def may_clean(self, target):
        return True

    def report(self, root, failures):
        for line in failures:
            core.note(root, line)
        if self.remote:
            for line in failures:
                print(line, flush=True)
            return
        if failures and not self.failing:
            self.failing = True
            print(failures[0] + '; further identical retries go to monitor.log until it recovers', flush=True)
        elif not failures and self.failing:
            self.failing = False
            print('monitor recovered; polling continues', flush=True)


def validate_session_remote(remote):
    if not isinstance(remote, str):
        raise ValueError('session delivery requires the explicit owning Claude host endpoint')
    value = urlsplit(remote)
    if value.query or value.fragment or value.username or value.password:
        raise ValueError('session endpoint must not contain credentials, query or fragment')
    if value.scheme != 'unix' or value.netloc or not value.path.startswith('/'):
        raise ValueError('session endpoint must be an explicit unix socket address')
    if str(Path(value.path)) != value.path or '..' in Path(value.path).parts:
        raise ValueError('session socket requires a normalized absolute path')
    return remote


def deliver_to_session(remote, message, timeout=45):
    payload = json.dumps(dict(text=message), ensure_ascii=False).encode() + b'\n'
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(urlsplit(remote).path)
        connection.sendall(payload)
        buffer = b''
        while b'\n' not in buffer:
            chunk = connection.recv(4096)
            if not chunk:
                raise RuntimeError('the owning Claude session closed the endpoint before accepting this batch')
            buffer += chunk
    reply = json.loads(buffer.split(b'\n', 1)[0].decode())
    if not reply.get('ok'):
        raise RuntimeError('the owning Claude session refused this batch: ' + str(reply.get('error', ''))[:200])
    return True


def bind_session_route(store, owner_root, remote):
    remote = validate_session_remote(remote)
    owner_root.mkdir(parents=True, exist_ok=True)
    with (store.root / 'run.lock').open('a') as runner:
        fcntl.flock(runner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (owner_root / 'session-route.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with store.locked() as data:
                target = store.require(data)
                if data['batch'] is not None:
                    raise ValueError('acknowledge the existing batch before binding session delivery')
                route = owner_root / 'session-route.json'
                expected = dict(session=store.identity, remote=remote)
                if route.exists() and json.loads(route.read_text()) != expected:
                    raise ValueError('this session already has a different owner endpoint; refusing reroute')
                if target.get('session_remote') not in (None, remote):
                    raise ValueError('registered session endpoint is immutable')
                temporary = owner_root / ('session-route.' + uuid.uuid4().hex + '.tmp')
                temporary.write_text(json.dumps(expected))
                temporary.replace(route)
                target['session_remote'] = remote


def main():
    parser = argparse.ArgumentParser(description='One named PR author feedback listener per pull request, delivered to a Claude Code session through stdout')
    parser.add_argument('--session', required=True)
    parser.add_argument('--pr', required=True, help='owner/repo#number or a pull request URL')
    parser.add_argument('--state-dir', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    register = commands.add_parser('register')
    register.add_argument('--author')
    register.add_argument('--checkout', type=Path)
    register.add_argument('--session-remote', help='Explicit owning Claude host endpoint; enables session delivery')
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
    run.add_argument('--delivery', choices=('stdout', 'session'),
                     help='Defaults to the owning session endpoint when bound, otherwise stdout')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', args.session):
        parser.error('--session must be a stable identifier of letters, digits, dot, underscore or hyphen')
    try:
        name = core.canonical(args.pr)
    except ValueError as error:
        parser.error(str(error))
    base = os.environ.get('CLAUDE_CONFIG_DIR') or str(Path.home() / '.claude')
    owner = Path(base) / 'state' / 'author-pr-monitor' / args.session
    root = args.state_dir or owner / core.readable_slug(name)
    store = core.Store(root, args.session, name, Runtime(args.session, __file__))
    if args.command == 'register':
        print('registered' if store.register(args.author, args.checkout) else 'already registered')
        if args.session_remote:
            bind_session_route(store, owner, args.session_remote)
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
        store.acknowledge(args.token)
    elif args.command == 'claim':
        print(store.claim(args.events))
    else:
        if args.interval < 10:
            parser.error('interval must be at least 10 seconds')
        target = store.read()['target']
        if target is None:
            parser.error('register this pull request before running')
        remote = target.get('session_remote')
        delivery = args.delivery or ('session' if remote else 'stdout')
        if remote and delivery != 'session':
            parser.error('a bound session must use its owning endpoint, not stdout delivery')
        if delivery == 'session':
            if not remote:
                parser.error('register --session-remote before using session delivery')
            route = owner / 'session-route.json'
            if not route.exists() or json.loads(route.read_text()) != dict(session=args.session, remote=remote):
                parser.error('session owner binding is missing or changed; refusing delivery')
        store.runtime = Runtime(args.session, __file__, delivery, remote)
        core.run(store, args.interval, args.once)


if __name__ == '__main__':
    main()
