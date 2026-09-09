import argparse
import importlib.util
import json
import os
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location('author_monitor_core', Path(__file__).with_name('author_monitor_core.py'))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


class Runtime:
    role = 'bot'
    marker = 'From Claude 🤖'
    delivery_name = 'stdout'
    state_keys = ('session', 'name')

    def __init__(self, session, script):
        self.session = session
        self.script = script
        self.failing = False

    @property
    def identity_arguments(self):
        return ['--session', self.session]

    def deliver(self, message):
        print(message, flush=True)
        return True

    def may_clean(self, target):
        return True

    def report(self, root, failures):
        for line in failures:
            core.note(root, line)
        if failures and not self.failing:
            self.failing = True
            print(failures[0] + '; further identical retries go to monitor.log until it recovers', flush=True)
        elif not failures and self.failing:
            self.failing = False
            print('monitor recovered; polling continues', flush=True)


def main():
    parser = argparse.ArgumentParser(description='One named PR author feedback listener per pull request, delivered to a Claude Code session through stdout')
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
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', args.session):
        parser.error('--session must be a stable identifier of letters, digits, dot, underscore or hyphen')
    try:
        name = core.canonical(args.pr)
    except ValueError as error:
        parser.error(str(error))
    base = os.environ.get('CLAUDE_CONFIG_DIR') or str(Path.home() / '.claude')
    root = args.state_dir or Path(base) / 'state' / 'author-pr-monitor' / args.session / core.readable_slug(name)
    store = core.Store(root, args.session, name, Runtime(args.session, __file__))
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
        store.acknowledge(args.token)
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
