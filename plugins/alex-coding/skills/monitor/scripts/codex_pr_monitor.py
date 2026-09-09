import argparse
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

_spec = importlib.util.spec_from_file_location('author_monitor_core', Path(__file__).with_name('author_monitor_core.py'))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

_transport = importlib.util.spec_from_file_location(
    'codex_desktop_transport', Path(__file__).resolve().parents[3] / 'scripts' / 'codex_desktop_transport.py')
transport = importlib.util.module_from_spec(_transport)
_transport.loader.exec_module(transport)


class Runtime:
    role = 'bot'
    marker = 'From Codex 🤖'
    delivery_name = 'queue'
    state_keys = ('thread', 'pr')

    def __init__(self, thread, script, executable=None):
        self.thread = thread
        self.script = script
        self.executable = executable

    @property
    def identity_arguments(self):
        return ['--thread', self.thread]

    def deliver(self, message):
        if not transport.desktop_is_idle(self.thread):
            return False
        transport.queue_message(self.executable, self.thread, message)
        return True

    def may_clean(self, target):
        return not target.get('checkout') or transport.desktop_is_idle(self.thread)

    def report(self, root, failures):
        for line in failures:
            core.note(root, line)
            print(line, flush=True)


def guard_legacy(store, source):
    destination = store.root / 'state.json'
    if destination.exists():
        existing = json.loads(destination.read_text())
        if (existing.get('schema') == core.SCHEMA and existing.get('thread') == store.identity
                and existing.get('pr') == store.name and existing.get('target') is not None):
            return
    path = Path(source).expanduser().resolve() / 'state.json'
    if path.exists():
        legacy = json.loads(path.read_text())
        if legacy.get('schema') == 1 and legacy.get('thread') == store.identity and store.name in legacy.get('targets', {}):
            raise ValueError('legacy state contains this PR; stop its runner and explicitly migrate before registration')


def migrate_legacy(store, source):
    source = Path(source).expanduser().resolve()
    if source == store.root:
        raise ValueError('migration destination must differ from source')
    with (source / 'run.lock').open('a') as runner:
        fcntl.flock(runner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (source / 'state.lock').open('a') as state_lock:
            fcntl.flock(state_lock, fcntl.LOCK_EX)
            legacy = json.loads((source / 'state.json').read_text())
            if legacy.get('schema') != 1 or legacy.get('thread') != store.identity:
                raise ValueError('source is not matching schema1 task state')
            if legacy.get('batch') is not None:
                raise ValueError('acknowledge the old batch with the old helper before migration')
            target = copy.deepcopy(legacy.get('targets', {}).get(store.name))
            if target is None:
                raise ValueError('source does not contain the selected PR')
            repository, number = core.parse_target(store.name)
            if target.get('repository', '').casefold() != repository or target.get('number') != number:
                raise ValueError('source target identity mismatch')
            if any(e.get('status') == 'delivered' for e in target['events'].values()):
                raise ValueError('unacknowledged delivered events require the old helper')
            with store.locked() as data:
                if data['target'] is not None:
                    raise ValueError('migration destination already has state; refusing overwrite')
                data['target'] = target


def main():
    parser = argparse.ArgumentParser(description='One named PR author feedback listener per pull request, delivered to an existing Codex task')
    parser.add_argument('--thread', required=True)
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
    migrate = commands.add_parser('migrate')
    migrate.add_argument('--from-state', required=True, type=Path)
    run = commands.add_parser('run')
    run.add_argument('--codex', default='codex')
    run.add_argument('--interval', type=int, default=45)
    run.add_argument('--once', action='store_true')
    args = parser.parse_args()
    try:
        args.thread = str(uuid.UUID(args.thread))
    except ValueError:
        parser.error('--thread must be an existing task UUID')
    try:
        name = core.canonical(args.pr)
    except ValueError as error:
        parser.error(str(error))
    legacy = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'state' / 'author-pr-monitor' / args.thread
    root = args.state_dir or legacy / core.hashed_slug(name)
    runtime = Runtime(args.thread, __file__)
    store = core.Store(root, args.thread, name, runtime)
    if args.command == 'migrate':
        migrate_legacy(store, args.from_state)
        print('migrated')
    elif args.command == 'register':
        guard_legacy(store, legacy)
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
        store.acknowledge(args.token)
    elif args.command == 'claim':
        print(store.claim(args.events))
    else:
        runtime.executable = shutil.which(args.codex)
        if not runtime.executable or args.interval < 10:
            parser.error('verified Codex executable and interval >= 10 seconds required')
        if store.read()['target'] is None:
            parser.error('register or migrate this PR before starting its runner')
        subprocess.run([runtime.executable, 'queue', '--help'], capture_output=True, text=True, timeout=10, check=True)
        transport.desktop_is_idle(args.thread)
        core.run(store, args.interval, args.once)


if __name__ == '__main__':
    main()
