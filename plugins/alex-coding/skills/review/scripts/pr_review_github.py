import importlib.util
import json
from pathlib import Path
import subprocess

import pr_review_state as state_core


spec = importlib.util.spec_from_file_location(
    'review_author_core', Path(__file__).resolve().parents[2] / 'monitor/scripts/author_monitor_core.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


class StaleHead(RuntimeError):
    pass


class GitHub:
    def __init__(self, pr, reviewer):
        self.repository, self.number = shared.parse_target(pr)
        self.reviewer = reviewer.casefold()
        self.base = f'repos/{self.repository}'

    def json(self, endpoint, paginate=False):
        return shared.gh_json(endpoint, 'admin', paginate)

    def pull(self):
        return self.json(f'{self.base}/pulls/{self.number}')

    def terminal(self):
        pr = self.pull()
        return 'merged' if pr.get('merged') else 'closed' if pr['state'] == 'closed' else None

    def verify_writer(self, author):
        if self.reviewer == author.casefold():
            raise PermissionError('the PR author cannot act as its independent reviewer')
        if self.json('user')['login'].casefold() != self.reviewer:
            raise PermissionError('admin API identity differs from the registered reviewer')
        if not self.json(self.base).get('permissions', {}).get('push'):
            raise PermissionError('reviewer requires repository push permission')

    def history(self):
        result = []
        for kind, endpoint in (
                ('conversation', f'issues/{self.number}/comments'),
                ('inline', f'pulls/{self.number}/comments'),
                ('review', f'pulls/{self.number}/reviews')):
            for row in self.json(f'{self.base}/{endpoint}?per_page=100', True):
                if kind == 'review' and (row.get('state') == 'PENDING' or not row.get('submitted_at')):
                    continue
                result.append({**row, 'kind': kind})
        return sorted(result, key=lambda row: (row.get('submitted_at') or row.get('created_at') or '', row['id']))

    def latest_checkpoint(self, history):
        found = None
        for row in history:
            if row.get('user', {}).get('login', '').casefold() != self.reviewer:
                continue
            record = state_core.decode_checkpoint(row.get('body'))
            if record and record.get('pr') == f'{self.repository}#{self.number}':
                found = (record, row)
        return found

    def snapshot(self, author):
        pr = self.pull()
        if pr['user']['login'].casefold() != author.casefold():
            raise ValueError('PR author changed from the registered identity')
        history = self.history()
        result = subprocess.run(
            [*shared.gh_command('admin'), 'pr', 'view', str(self.number), '--repo', self.repository,
             '--json', 'headRefOid,statusCheckRollup'], capture_output=True, text=True, timeout=30, check=True)
        detail = json.loads(result.stdout)
        if detail['headRefOid'] != pr['head']['sha']:
            raise StaleHead('head changed during snapshot')
        checks = detail['statusCheckRollup']
        events = []
        for row in history:
            if shared.self_echo(row, self.reviewer) and row.get('state') != 'DISMISSED':
                continue
            key = state_core.digest([row['kind'], row['id'], row.get('updated_at'),
                                     row.get('submitted_at'), row.get('state'), row.get('body')])
            events.append({'key': key, 'kind': row['kind'], 'id': row['id'], 'url': row.get('html_url')})
        return {'head': pr['head']['sha'], 'base': pr['base']['sha'], 'draft': pr['draft'],
                'terminal': 'merged' if pr.get('merged') else 'closed' if pr['state'] == 'closed' else None,
                'ci': shared.checks_state(checks), 'ci_key': state_core.digest(sorted(
                    json.dumps(check, sort_keys=True) for check in checks)),
                'checks': checks, 'events': events, 'history': history, 'pr': pr}

    def post(self, endpoint, payload, state, current):
        fresh = self.pull()
        if (fresh['head']['sha'] != current['head'] or fresh['base']['sha'] != current['base']
                or fresh['state'] != 'open' or fresh['draft']):
            raise StaleHead('PR no longer matches the reviewed ready head/base')
        if fresh['user']['login'].casefold() != state['author']:
            raise PermissionError('PR author identity changed')
        self.verify_writer(state['author'])
        response = subprocess.run(
            [*shared.gh_command('admin'), 'api', '--method', 'POST', endpoint, '--input', '-'],
            input=json.dumps(payload), capture_output=True, text=True, timeout=30, check=True)
        return json.loads(response.stdout)

    def publish(self, state, pending):
        marker = 'From Codex 🤖' if state['runtime'] == 'codex' else 'From Claude 🤖'
        record = pending['checkpoint']
        body = (pending['result']['body'].rstrip() + '\n\n'
                + f"Review progress: {record['phase']}; round {record['rounds']}/{record['round_limit']}; "
                + f"head `{record['head']}`.\n\n{state_core.encode_checkpoint(record)}\n\n{marker}")
        if len(body) > 60000:
            raise ValueError('checkpoint exceeds GitHub comment size; preserve the pending result')
        matches = [row for row in self.history()
                   if row.get('user', {}).get('login', '').casefold() == self.reviewer
                   and (state_core.decode_checkpoint(row.get('body')) or {}).get('token') == pending['token']]
        review = next((row for row in matches if row['kind'] == 'review'), None)
        if review is None:
            event = 'REQUEST_CHANGES' if record['phase'] in {'changes-requested', 'needs-user-attention'} else 'APPROVE'
            comments = [{**item, 'body': item['body'].rstrip() + '\n\n' + marker}
                        for item in pending['result']['comments']]
            review = self.post(f'{self.base}/pulls/{self.number}/reviews',
                               {'commit_id': record['head'], 'event': event, 'body': body, 'comments': comments},
                               state, pending['snapshot'])
        if record['phase'] == 'needs-user-attention' and not any(row['kind'] == 'conversation' for row in matches):
            self.post(f'{self.base}/issues/{self.number}/comments', {'body': body}, state, pending['snapshot'])
        return review['html_url']
