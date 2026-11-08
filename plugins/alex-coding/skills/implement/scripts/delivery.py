import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid
from urllib.parse import urlencode


PLUGIN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLUGIN / 'skills/review/scripts'))
import review_pr as review


LOCKFILES = {'Package.resolved', 'Podfile.lock', 'Cartfile.resolved', 'package-lock.json', 'yarn.lock',
             'pnpm-lock.yaml', 'Gemfile.lock', 'poetry.lock', 'uv.lock', 'Cargo.lock', 'go.sum'}
TEXT_FILES = {'.md', '.markdown', '.txt', '.rst'}
VERSION_FILES = {'.yml', '.yaml', '.xcconfig', '.toml', '.pbxproj'}
VERSION_LINE = re.compile(r'\s*"?(MARKETING_VERSION|CURRENT_PROJECT_VERSION|exactVersion|revision|version)"?'
                          r'\s*[:=]\s*"?[\w.+-]+"?[,;]?\s*')
PENDING_CI_LABEL = 'ci-skip-approved'


def invoke(arguments, cwd=None, input=None):
    result = subprocess.run([str(item) for item in arguments], cwd=cwd, capture_output=True,
                            text=True, timeout=120, check=True, input=input)
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
    return (base / ('state/project-pr-monitor' if args.slot else 'state/author-pr-monitor') / identity / slug).resolve()


def monitor_command(args):
    script = (PLUGIN / 'skills/project-monitor/scripts/project_pr_monitor.py' if args.slot
              else PLUGIN / f'skills/monitor/scripts/{args.runtime}_pr_monitor.py')
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


def review_command(args):
    arguments = [sys.executable, str(PLUGIN / 'skills/review/scripts/review_pr.py'),
                 'start', '--pr', args.pr, '--runtime',
                 args.review_runtime or review.configured_runtime(args.pr) or args.runtime, '--reviewer', args.reviewer,
                 '--max-rounds', str(args.max_rounds)]
    if args.acceptance_file:
        arguments += ['--acceptance-file', str(args.acceptance_file.resolve())]
    return arguments + (['--complexity', args.complexity] if args.complexity else [])


def start(args):
    if not (args.checkout or args.slot) or not args.reviewer:
        raise ValueError('start requires a checkout or pool slot and an independent reviewer')
    if args.acceptance_file and not args.acceptance_file.read_text().strip():
        raise ValueError('acceptance must be nonempty')
    exemption = pin_check(args)
    reviewed = review.state_root(review.remote.shared.canonical(args.pr)) / 'state.json'
    separate = reviewed.exists() and not json.loads(reviewed.read_text()).get('author_delivery')
    if (exemption.get('exemption') == 'coordinator-approved-mechanical'
            and reviewed.exists() and review.running(reviewed.parent)):
        raise ValueError('an existing PR runner is active; retain its review path or stop it before starting a coordinator-only Monitor')
    if exemption['status'] == 'review-exempt' or separate or (monitor_root(args) / 'state.json').exists():
        if args.takeover:
            raise ValueError('takeover applies to PRs followed by the single runner, not a standalone Monitor')
        return start_monitor(args, exemption)
    arguments = review_command(args) + ['--author-runtime', args.runtime, '--author-session', args.session]
    arguments += ['--takeover'] if args.takeover else []
    arguments += ['--slot', str(args.slot.resolve())] if args.slot else ['--checkout', str(args.checkout.resolve())]
    if args.session_remote:
        arguments += ['--session-remote', args.session_remote]
    result = invoke(arguments)
    if result.get('monitor_command'):
        return {'status': 'native-monitor-required', 'pr': args.pr, 'reviewer_active': False,
                'monitor_command': result['monitor_command'], 'persistent': True,
                'next': 'Start this command with the native Monitor tool, then repeat start.'}
    return {'status': 'started' if result['active'] else 'reviewer-inactive', 'pr': args.pr,
            'monitor_active': result['active'], 'reviewer_active': result['active'], 'reviewer': result}


def start_monitor(args, exemption):
    command = monitor_command(args)
    root = monitor_root(args)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with review.lock(root, 'launch.lock'):
        registration = command + (['register', '--slot', str(args.slot.resolve())] if args.slot
                                  else ['register', '--checkout', str(args.checkout.resolve())])
        if args.session_remote:
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
            stored = json.loads((root / 'state.json').read_text()) if (root / 'state.json').exists() else {}
            if args.runtime == 'claude' and not (stored.get('target') or {}).get('session_remote'):
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
        if exemption['status'] == 'review-exempt':
            return {**exemption, 'monitor_active': True, 'reviewer_active': False,
                    'next': 'Merge with pin-merge at this head once checks pass.'}
        result = invoke(review_command(args))
        return {'status': 'started' if result['active'] else 'reviewer-inactive', 'pr': args.pr,
                'monitor_active': True, 'reviewer_active': result['active'], 'reviewer': result}


def open_pr(args):
    args.checkout = args.checkout or args.slot
    if not all([args.repository, args.checkout, args.title, args.body_file, args.reviewer]):
        raise ValueError('open requires repository, checkout, title, body file and reviewer')
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
        body_stdin = args.body_file == Path('-')
        create = [*command, 'pr', 'create', '--repo', repository, '--head', branch,
                  '--base', metadata['default_branch'], '--title', args.title,
                  '--body-file', '-' if body_stdin else str(args.body_file.resolve())]
        args.pr = invoke(create, input=sys.stdin.read()) if body_stdin else invoke(create)
    args.pr = review.remote.shared.canonical(args.pr)
    return start(args)


def exempt_kinds(files):
    kinds = set()
    for row in files:
        if all(Path(name).suffix.lower() in TEXT_FILES
               for name in (row['filename'], row.get('previous_filename', row['filename']))):
            if not row.get('patch') and not (row.get('status') == 'renamed' and row.get('changes') == 0):
                return set()
            kinds.add('text')
            continue
        if row.get('status') != 'modified':
            return set()
        kinds.add('pin')
        if Path(row['filename']).name in LOCKFILES:
            continue
        if Path(row['filename']).suffix not in VERSION_FILES:
            return set()
        changed = [line[1:] for line in (row.get('patch') or '').splitlines() if line[:1] in '+-']
        if not changed or not all(VERSION_LINE.fullmatch(line) for line in changed):
            return set()
    return kinds


def declared_exemptions(config):
    match = re.search(r'^review_exempt=(["\']?)([^"\'\n]*)\1\s*$', config, re.M)
    return set(match[2].split()) & {'pin', 'text'} if match else set()


def pin_check(args):
    github = review.remote.GitHub(args.pr, '')
    pull = github.pull()
    files = github.json(f'{github.base}/pulls/{github.number}/files?per_page=100', True)
    try:
        content = github.json(f"{github.base}/contents/.shared-config?ref={pull['base']['sha']}")['content']
        declared = declared_exemptions(base64.b64decode(content).decode())
    except (subprocess.CalledProcessError, KeyError, ValueError):
        declared = set()
    kinds = exempt_kinds(files)
    result = {'status': 'review-exempt' if kinds and kinds <= declared else 'review-required',
              'pr': review.remote.shared.canonical(args.pr), 'head': pull['head']['sha'],
              'kinds': sorted(kinds), 'declared': sorted(declared), 'files': [row['filename'] for row in files]}
    if result['status'] == 'review-required' and pending_ci_approved(pull):
        result.update(status='review-exempt', exemption='coordinator-approved-mechanical',
                      approval_label=PENDING_CI_LABEL)
    return result


def mechanical_ci_state(checks):
    pending = False
    for check in review.remote.shared.latest_checks(checks):
        if check.get('__typename') == 'StatusContext':
            state = check.get('state')
            if state not in {'SUCCESS', 'PENDING', 'EXPECTED'}:
                return 'fail'
            pending |= state != 'SUCCESS'
        elif check.get('status') == 'COMPLETED':
            if check.get('conclusion') not in {'SUCCESS', 'NEUTRAL', 'SKIPPED'}:
                return 'fail'
        elif check.get('status') in {'QUEUED', 'IN_PROGRESS', 'PENDING', 'REQUESTED', 'WAITING'} and not check.get('conclusion'):
            pending = True
        else:
            return 'fail'
    return 'pending' if pending else 'pass'


def pending_ci_approved(pull):
    return any(label['name'].casefold() == PENDING_CI_LABEL for label in pull.get('labels', []))


def cancel_pending_runs(github, pull, head):
    cancelled, errors = [], []
    query = urlencode({'branch': pull['head']['ref'], 'head_sha': head, 'per_page': 100})
    command = review.remote.shared.gh_command('admin')
    try:
        pages = invoke([*command, 'api', '--paginate', '--slurp', f'{github.base}/actions/runs?{query}'])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {'cancel_requested_run_ids': [], 'cancel_errors': [{'reason': str(error)}]}
    for page in pages:
        for run in page['workflow_runs']:
            if (run.get('head_sha') != head or run.get('head_branch') != pull['head']['ref']
                    or (run.get('head_repository') or {}).get('full_name', '').casefold() != pull['head']['repo']['full_name'].casefold()
                    or run.get('status') not in {'queued', 'in_progress', 'pending', 'requested', 'waiting'}):
                continue
            try:
                if not github.json(github.base).get('permissions', {}).get('push'):
                    raise PermissionError('admin requires repository push permission to cancel workflows')
                invoke([*command, 'api', '--method', 'POST', f'{github.base}/actions/runs/{run["id"]}/cancel'])
                cancelled.append(run['id'])
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                errors.append({'run_id': run['id'], 'reason': str(error)})
    return {'cancel_requested_run_ids': cancelled, 'cancel_errors': errors}


def pin_merge(args):
    if not args.expected_head or not args.merge_method:
        raise ValueError('pin-merge requires expected head and merge method')
    result = pin_check(args)
    if result['status'] != 'review-exempt':
        raise ValueError('the PR is not covered by a declared review exemption; independent review is required')
    github = review.remote.GitHub(args.pr, '')
    pull = github.pull()
    coordinator = getattr(args, 'allow_pending_ci', False) and pending_ci_approved(pull)
    if result.get('exemption') == 'coordinator-approved-mechanical' and not coordinator:
        raise ValueError('coordinator-approved source changes require --allow-pending-ci and the approval label')
    if pull['state'] != 'open' or pull['draft'] or {pull['head']['sha'], result['head']} != {args.expected_head}:
        raise ValueError('PR does not match the expected ready head')
    detail = invoke([*review.remote.shared.gh_command('admin'), 'pr', 'view', str(github.number), '--repo',
                     github.repository, '--json', 'headRefOid,statusCheckRollup'])
    if detail['headRefOid'] != args.expected_head:
        raise ValueError('head changed while reading checks')
    required = review.remote.shared.ci_required(github.repository, args.expected_head, 'admin')
    ci = review.remote.check_summary(detail['statusCheckRollup'], required)['ci']
    mechanical_ci = mechanical_ci_state(detail['statusCheckRollup'])
    skip_ci = ci == 'pending' and coordinator and mechanical_ci == 'pending'
    if (coordinator and mechanical_ci == 'fail') or (ci not in {'pass', 'none'} and not skip_ci):
        raise ValueError('checks are not passing')
    if pull.get('mergeable') is not True or pull.get('mergeable_state') in {'blocked', 'dirty', 'unknown'}:
        raise ValueError('mergeability or required GitHub protection is unresolved')
    if not github.json(github.base).get('permissions', {}).get('push'):
        raise PermissionError('admin requires repository push permission')
    if coordinator:
        pull = github.pull()
        if (pull['state'] != 'open' or pull['draft'] or pull['head']['sha'] != args.expected_head
                or not pending_ci_approved(pull)):
            raise ValueError('pending-CI approval label or expected ready head changed before merge')
    invoke([*review.remote.shared.gh_command('admin'), 'pr', 'merge', str(github.number), '--repo', github.repository,
            '--' + args.merge_method, '--match-head-commit', args.expected_head])
    if not github.pull().get('merged'):
        raise RuntimeError('merge is not confirmed')
    if coordinator:
        return {**result, 'status': 'merged', 'exemption': 'coordinator-approved-mechanical',
                'approval_label': PENDING_CI_LABEL, 'merged_without_waiting_for_ci': True,
                'message': '协调者批准的机械改动：免独立审查、未等 CI 合并',
                **cancel_pending_runs(github, pull, args.expected_head)}
    return {**result, 'status': 'merged'}


def parser():
    result = argparse.ArgumentParser(description='Open a PR and start its single runner, or check and merge a declared review exemption.')
    result.add_argument('action', choices=['open', 'start', 'pin-check', 'pin-merge'])
    result.add_argument('--runtime', choices=['codex', 'claude'])
    result.add_argument('--session')
    result.add_argument('--pr')
    result.add_argument('--repository')
    result.add_argument('--title')
    result.add_argument('--body-file', type=Path)
    result.add_argument('--checkout', type=Path)
    result.add_argument('--slot', type=Path)
    result.add_argument('--acceptance-file', type=Path)
    result.add_argument('--reviewer')
    result.add_argument('--complexity', choices=['deterministic', 'low', 'medium', 'high'])
    result.add_argument('--max-rounds', type=int, default=3)
    result.add_argument('--session-remote')
    result.add_argument('--takeover', action='store_true',
                        help='Rebind the PR to this session and checkout or slot after its previous runner stopped')
    result.add_argument('--review-runtime', choices=['codex', 'claude'])
    result.add_argument('--expected-head')
    result.add_argument('--merge-method', choices=['squash', 'merge', 'rebase'])
    result.add_argument('--allow-pending-ci', action='store_true',
                        help=f'For pin-merge only: waive independent review and CI waiting for mechanical changes with the coordinator-applied {PENDING_CI_LABEL} label')
    return result


def main():
    args = parser().parse_args()
    try:
        if args.allow_pending_ci and args.action != 'pin-merge':
            raise ValueError('--allow-pending-ci is only available for pin-merge')
        review.refuse_slot_checkout(args.checkout)
        if args.action != 'open' and not args.pr:
            raise ValueError(f'{args.action} requires the exact PR')
        if args.action in {'open', 'start'} and not (args.runtime and args.session):
            raise ValueError(f'{args.action} requires runtime and session')
        result = {'open': open_pr, 'start': start, 'pin-check': pin_check, 'pin-merge': pin_merge}[args.action](args)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'error', 'reason': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))
    if result['status'] == 'reviewer-inactive':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
