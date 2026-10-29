import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex

HERE = Path(__file__).resolve().parent
MONITOR = HERE.parents[1] / 'monitor' / 'scripts'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load('author_monitor_core', MONITOR / 'author_monitor_core.py')
claude = load('claude_pr_monitor', MONITOR / 'claude_pr_monitor.py')
pool = load('worktree_pool', HERE / 'worktree_pool.py')


class ProjectStore(core.Store):
    def register_slot(self, slot, author=None):
        path = Path(slot).expanduser()
        if not path.is_absolute():
            raise ValueError('--slot must be an absolute path to the pool slot or pool main')
        path = path.resolve()
        created = self.register(author)
        binding = pool.bind(path, path, self.name)
        with self.locked() as data:
            target = self.require(data)
            stored = target.get('pool_slot')
            if stored and stored['path'] != str(path):
                raise ValueError('registered pool slot is immutable')
            target['pool_slot'] = dict(path=str(path), slot=binding['slot'], holder=binding['holder'], branch=binding['branch'])
        return created

    def apply(self, result):
        super().apply(result)
        if result['terminal'] != 'closed':
            return
        with self.locked() as data:
            target = self.require(data)
            if target['stopped'] or target.get('cleanup_result') is not None or data['batch'] is not None:
                return
            self._attempt_cleanup(data, target, result)

    def _attempt_cleanup(self, data, target, result, explicit=False):
        if target.get('cleanup_result') and not explicit:
            return copy.deepcopy(target['cleanup_result'])
        target['cleanup_result'] = dict(status='interrupted', reason='Slot release was interrupted; inspect before any retry')
        self.persist(data)
        binding = target.get('pool_slot')
        try:
            if not binding:
                outcome = dict(status='preserved', reason='No pool slot was registered for this PR')
            else:
                outcome = pool.release(binding['path'], binding['path'], pr=self.name, expect_head=result.get('head'))
                if result.get('terminal') == 'merged':
                    outcome['main'] = pool.sync_main(binding['path'])
        except pool.PoolError as error:
            outcome = error.result
        except Exception as error:
            outcome = dict(status='error', reason=f'{type(error).__name__}: {error}'[:300])
        target['cleanup_result'] = outcome
        for existing in target['events'].values():
            if existing['kind'] == 'terminal' and existing['status'] == 'pending':
                existing['cleanup'] = outcome
        return copy.deepcopy(outcome)

    def complete(self):
        with self.locked() as data:
            target = self.require(data)
            prior = target.get('cleanup_result')
            if prior and prior.get('status') == 'released':
                return copy.deepcopy(prior)
            current = core.snapshot(target, self.role)
            if current['terminal'] not in ('merged', 'closed'):
                raise ValueError('slot release requires a freshly verified merged or closed PR')
            for item in current['events']:
                target['events'].setdefault(item['key'], dict(item, status='pending'))
            target.update(terminal=current['terminal'], head=current['head'], ci=current['ci'], ci_version=current['ci_version'])
            return self._attempt_cleanup(data, target, current, explicit=True)

    def build_message(self, target, keys, token):
        message = super().build_message(target, keys, token).replace(
            'Use alex-coding:monitor to handle', 'Use alex-coding:project-monitor to handle', 1)
        if not any(target['events'][key]['kind'] == 'terminal' for key in keys):
            return message
        command = shlex.join(['python3', str(Path(self.runtime.script).resolve()), *self.runtime.identity_arguments,
                              '--pr', self.name, '--state-dir', str(self.root), 'complete'])
        outcome = target.get('cleanup_result') or {}
        if outcome.get('status') == 'released':
            note = 'The pool slot is released. Tell the project coordinator this slot is free before acknowledging.'
        else:
            note = ('The pool slot is still held. Fix the reported cause, then run: ' + command +
                    ' and tell the project coordinator once it reports released.')
        return message + '\n' + note


def main():
    parser = argparse.ArgumentParser(description='One PR listener per pull request for a Claude Project thread working in a pooled worktree slot')
    parser.add_argument('--session', required=True)
    parser.add_argument('--pr', required=True, help='owner/repo#number or a pull request URL')
    parser.add_argument('--state-dir', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    register = commands.add_parser('register')
    register.add_argument('--slot', type=Path, required=True)
    register.add_argument('--author')
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
    owner = Path(base) / 'state' / 'project-pr-monitor' / args.session
    root = args.state_dir or owner / core.readable_slug(name)
    store = ProjectStore(root, args.session, name, claude.Runtime(args.session, __file__))
    try:
        if args.command == 'register':
            print('registered' if store.register_slot(args.slot, args.author) else 'already registered')
            if args.session_remote:
                claude.bind_session_route(store, owner, args.session_remote)
        elif args.command == 'complete':
            os.chdir(store.root)
            outcome = store.complete()
            print(json.dumps(outcome, indent=2, ensure_ascii=False))
            if outcome.get('status') != 'released':
                raise SystemExit(1)
        elif args.command == 'status':
            print(json.dumps(store.read(), indent=2, ensure_ascii=False))
        elif args.command == 'reopen':
            store.reopen()
        elif args.command == 'ack':
            if (store.read()['target'] or {}).get('terminal'):
                claude.configure_delivery(store, owner, args, parser)
            print(store.acknowledge(args.token))
        elif args.command == 'claim':
            print(store.claim(args.events))
        else:
            if args.interval < 10:
                parser.error('interval must be at least 10 seconds')
            target = store.read()['target']
            if target is None or not target.get('pool_slot'):
                parser.error('register this pull request with its pool slot before running')
            remote = target.get('session_remote')
            delivery = args.delivery or ('session' if remote else 'stdout')
            if remote and delivery != 'session':
                parser.error('a bound session must use its owning endpoint, not stdout delivery')
            if delivery == 'session':
                route = owner / 'session-route.json'
                if not remote or not route.exists() or json.loads(route.read_text()) != dict(session=args.session, remote=remote):
                    parser.error('session owner binding is missing or changed; refusing delivery')
            store.runtime = claude.Runtime(args.session, __file__, delivery, remote)
            core.run(store, args.interval, args.once)
    except pool.PoolError as error:
        print(json.dumps(error.result, indent=2, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
