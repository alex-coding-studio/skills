import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid


PLUGIN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLUGIN / 'skills/review/scripts'))
import review_pr as review


def invoke(arguments, cwd=None):
    result = subprocess.run([str(item) for item in arguments], cwd=cwd, capture_output=True,
                            text=True, timeout=120, check=True)
    try:
        return json.loads(result.stdout)
    except ValueError:
        return result.stdout.strip()


def monitor_root(args):
    name = review.remote.shared.canonical(args.pr)
    if args.runtime == 'codex':
        identity = str(uuid.UUID(args.session))
        base = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
        slug = review.remote.shared.hashed_slug(name)
    else:
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', args.session):
            raise ValueError('invalid existing Claude session identity')
        identity = args.session
        base = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude')
        slug = review.remote.shared.readable_slug(name)
    return (base / 'state/author-pr-monitor' / identity / slug).resolve()


def monitor_command(args):
    script = PLUGIN / f'skills/monitor/scripts/{args.runtime}_pr_monitor.py'
    return [sys.executable, str(script), '--thread' if args.runtime == 'codex' else '--session',
            args.session, '--pr', review.remote.shared.canonical(args.pr)]


def monitor_live(root, command):
    if not review.running(root) or not (root / 'run.pid').exists():
        return False
    pid = int((root / 'run.pid').read_text())
    process = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
    expected = [command[1], command[3], command[5]]
    log = root / 'monitor.log'
    return (process.returncode == 0 and all(item in process.stdout for item in expected)
            and log.exists() and 'author PR monitor started' in log.read_text())


def start(args):
    if not args.checkout or not args.acceptance_file or not args.reviewer:
        raise ValueError('start requires checkout, acceptance file and independent reviewer')
    if not args.acceptance_file.read_text().strip():
        raise ValueError('acceptance must be nonempty')
    command = monitor_command(args)
    root = monitor_root(args)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with review.lock(root, 'launch.lock'):
        registration = command + ['register', '--checkout', str(args.checkout.resolve())]
        if args.session_remote:
            if args.runtime != 'codex':
                raise ValueError('session-remote is only supported by the Codex host')
            existing = json.loads((root / 'state.json').read_text()) if (root / 'state.json').exists() else {}
            bound = (existing.get('target') or {}).get('session_remote')
            if bound and bound != args.session_remote:
                raise ValueError('existing session endpoint differs; refusing reroute')
            if not bound:
                registration += ['--session-remote', args.session_remote]
        invoke(registration)
        run = command + ['run', '--interval', '45']
        if not monitor_live(root, command):
            if review.running(root):
                raise RuntimeError('monitor lock is occupied without verified process/startup evidence')
            if args.runtime == 'claude':
                return {'status': 'native-monitor-required', 'pr': args.pr, 'reviewer_active': False,
                        'monitor_command': shlex.join(run), 'persistent': True,
                        'next': 'Start this command with the native Monitor tool, then repeat start.'}
            with (root / 'startup.log').open('a') as log:
                process = subprocess.Popen(run, cwd=root, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=log, start_new_session=True)
            deadline = time.monotonic() + 8
            while not monitor_live(root, command):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f'monitor startup is unverified; inspect {root / "startup.log"}')
                time.sleep(0.1)
        arguments = [sys.executable, str(PLUGIN / 'skills/review/scripts/review_pr.py'),
                     'start', '--pr', args.pr, '--runtime', args.runtime, '--reviewer', args.reviewer,
                     '--acceptance-file', str(args.acceptance_file.resolve()), '--max-rounds', str(args.max_rounds)]
        if args.complexity:
            arguments += ['--complexity', args.complexity]
        result = invoke(arguments)
        return {'status': 'started' if result['active'] else 'reviewer-inactive', 'pr': args.pr,
                'monitor_active': True, 'reviewer_active': result['active'], 'reviewer': result}


def open_pr(args):
    if not all([args.repository, args.checkout, args.title, args.body_file, args.acceptance_file, args.reviewer]):
        raise ValueError('open requires repository, checkout, title, body file, acceptance file and reviewer')
    repository, _ = review.remote.shared.parse_target(args.repository + '#1')
    command = review.remote.shared.gh_command('bot')
    author = invoke([*command, 'api', 'user'])['login']
    metadata = invoke([*command, 'api', f'repos/{repository}'])
    if not metadata.get('permissions', {}).get('push'):
        raise PermissionError('bot requires repository push permission')
    branch = review.git(args.checkout, 'branch', '--show-current').strip()
    if not branch or branch == metadata['default_branch']:
        raise ValueError('open requires a non-default work branch')
    head = review.git(args.checkout, 'rev-parse', 'HEAD').strip()
    if review.git(args.checkout, 'status', '--porcelain').strip():
        raise ValueError('commit the accepted changes before opening a PR')
    pushed = invoke([*command, 'api', f'repos/{repository}/git/ref/heads/{branch}'])
    if pushed['object']['sha'] != head:
        raise ValueError('remote work branch does not match the verified local head')
    existing = invoke([*command, 'pr', 'list', '--repo', repository, '--head', branch,
                       '--base', metadata['default_branch'], '--state', 'open',
                       '--json', 'number,author,headRefOid'])
    if len(existing) > 1:
        raise ValueError('multiple matching PRs; select the exact PR instead')
    if existing:
        row = existing[0]
        if row['author']['login'].casefold() != author.casefold() or row['headRefOid'] != head:
            raise ValueError('existing PR ownership or revision differs')
        args.pr = f'{repository}#{row["number"]}'
    else:
        writer = invoke([*command, 'api', 'user'])['login']
        permission = invoke([*command, 'api', f'repos/{repository}']).get('permissions', {}).get('push')
        if writer.casefold() != author.casefold() or not permission:
            raise PermissionError('bot identity or push permission changed before PR creation')
        args.pr = invoke([*command, 'pr', 'create', '--repo', repository, '--head', branch,
                          '--base', metadata['default_branch'], '--title', args.title,
                          '--body-file', str(args.body_file.resolve())])
    args.pr = review.remote.shared.canonical(args.pr)
    return start(args)


def verify_merge(state, current, expected_head, author):
    if state['reviewer'].casefold() == author.casefold():
        raise ValueError('the author cannot supply independent approval')
    if (current['terminal'] or current['draft'] or current['head'] != expected_head
            or state.get('head') != current['head'] or state.get('base') != current['base']):
        raise ValueError('PR does not match the expected ready reviewed head/base')
    if (state.get('pending') or state['phase'] not in {'approved', 'waiting-ci'}
            or current['ci'] not in {'pass', 'none'}
            or (state['phase'] == 'waiting-ci' and current['ci'] != 'pass')):
        raise ValueError('review or checks are unresolved')
    if any(row['key'] not in state['seen'] for row in current['events']):
        raise ValueError('new feedback requires the existing reviewer before merge')
    if current['pr'].get('mergeable') is not True or current['pr'].get('mergeable_state') in {'blocked', 'dirty', 'unknown'}:
        raise ValueError('mergeability or required GitHub protection is unresolved')
    latest = {}
    for row in current['history']:
        if row['kind'] == 'review' and row.get('state') in {'APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'}:
            latest[row['user']['login'].casefold()] = row
    approval = latest.get(state['reviewer'].casefold(), {})
    if approval.get('state') != 'APPROVED' or approval.get('commit_id') != current['head']:
        raise ValueError('current-head independent approval is missing or dismissed')
    if any(row['state'] == 'CHANGES_REQUESTED' for row in latest.values()):
        raise ValueError('blocking review remains unresolved')


def finish(args):
    if not args.expected_head or not args.merge_method or not args.feedback_settled:
        raise ValueError('finish requires expected head, authorized merge method and settled feedback')
    pr = review.remote.shared.canonical(args.pr)
    root = monitor_root(args)
    command = monitor_command(args)
    target = invoke(command + ['status'])['target']
    if not target:
        raise ValueError('the task-owned PR must already be registered')
    state = review.read(review.state_root(pr), pr)
    github = review.remote.GitHub(pr, state['reviewer'])
    current = github.snapshot(target['author'])
    if current['terminal'] != 'merged':
        verify_merge(state, current, args.expected_head, target['author'])
        fresh = github.pull()
        if fresh['head']['sha'] != current['head'] or fresh['base']['sha'] != current['base']:
            raise ValueError('head/base changed before merge; retain the PR for review')
        github.verify_writer(target['author'])
        invoke([*review.remote.shared.gh_command('admin'), 'pr', 'merge', str(github.number),
                '--repo', github.repository, '--' + args.merge_method,
                '--match-head-commit', args.expected_head], cwd=root)
        if not github.pull().get('merged'):
            raise RuntimeError('merge is not confirmed; completion was not attempted')
    os.chdir(root)
    cleanup = subprocess.run(command + ['complete'], cwd=root, capture_output=True, text=True, timeout=120)
    try:
        result = json.loads(cleanup.stdout)
    except ValueError:
        result = {'status': 'error', 'reason': 'inspect the existing Monitor completion state before retrying'}
    return {'status': 'merged', 'pr': pr, 'cleanup': result,
            'complete': cleanup.returncode == 0 and result.get('status') == 'cleaned'}


def parser():
    result = argparse.ArgumentParser(description='Compose existing author Monitor and independent Review operations.')
    result.add_argument('action', choices=['open', 'start', 'finish'])
    result.add_argument('--runtime', choices=['codex', 'claude'], required=True)
    result.add_argument('--session', required=True)
    result.add_argument('--pr')
    result.add_argument('--repository')
    result.add_argument('--title')
    result.add_argument('--body-file', type=Path)
    result.add_argument('--checkout', type=Path)
    result.add_argument('--acceptance-file', type=Path)
    result.add_argument('--reviewer')
    result.add_argument('--complexity', choices=['deterministic', 'low', 'medium', 'high'])
    result.add_argument('--max-rounds', type=int, default=2)
    result.add_argument('--session-remote')
    result.add_argument('--expected-head')
    result.add_argument('--merge-method', choices=['squash', 'merge', 'rebase'])
    result.add_argument('--feedback-settled', action='store_true')
    return result


def main():
    args = parser().parse_args()
    try:
        if args.action != 'open' and not args.pr:
            raise ValueError('start and finish require the exact PR')
        result = {'open': open_pr, 'start': start, 'finish': finish}[args.action](args)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'error', 'reason': str(error)}))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))
    if result['status'] == 'reviewer-inactive' or result.get('complete') is False:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
