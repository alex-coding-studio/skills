import base64
import hashlib
import json
import re


PHASES = {'starting', 'reviewing', 'approved', 'changes-requested', 'waiting-ci',
          'needs-user-attention', 'merged', 'closed', 'error'}
TERMINAL = {'needs-user-attention', 'merged', 'closed', 'error'}
MARKER = 'alex-coding-review:v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def initial_state(pr, reviewer, author, runtime, limit):
    if type(limit) is not int or limit < 1:
        raise ValueError('review round limit must be a positive integer')
    return {'schema': 1, 'pr': pr, 'reviewer': reviewer.lower(), 'author': author.lower(),
            'runtime': runtime, 'phase': 'starting', 'rounds': 0, 'round_limit': limit,
            'head': None, 'base': None, 'ci': None, 'ci_key': None, 'ci_seen': [], 'seen': [],
            'review_phase': None,
            'session': None, 'pending': None}


def next_event(state, current):
    if current['terminal']:
        return current['terminal']
    if state['phase'] in TERMINAL or current['draft'] or state.get('pending'):
        return None
    if state['head'] != current['head'] or state.get('base') != current['base']:
        return 'head'
    if any(row['key'] not in state['seen'] for row in current['events']):
        return 'feedback'
    terminal_changed = current['ci_key'] != state['ci_key']
    if 'ci_events' in current and state.get('ci_seen') is not None:
        terminal_changed = any(key not in state['ci_seen'] for key in current['ci_events'])
    if current['ci'] in {'pass', 'fail'} and terminal_changed:
        return 'ci'
    return None


def disposition(outcome, rounds, limit):
    if outcome not in {'approved', 'changes-requested', 'waiting-ci', 'needs-user-attention'}:
        raise ValueError('invalid review outcome')
    if outcome == 'changes-requested' and rounds >= limit:
        return 'needs-user-attention'
    return outcome


def settle(state, current, phase, seen):
    if phase not in PHASES:
        raise ValueError('invalid review phase')
    state.update(phase=phase, head=current['head'], base=current['base'], ci=current['ci'],
                 ci_key=current['ci_key'], seen=list(seen), pending=None)
    state['review_phase'] = phase
    if 'ci_events' in current:
        state['ci_seen'] = sorted(set(state.get('ci_seen') or []) | set(current['ci_events']))


def checkpoint(state, token):
    keys = ('schema', 'pr', 'reviewer', 'author', 'phase', 'rounds', 'round_limit',
            'head', 'base', 'ci', 'ci_key', 'ci_seen', 'seen', 'review_phase', 'complexity')
    return {**{key: state.get(key) for key in keys}, 'token': token}


def restore(state, record):
    for key in ('schema', 'pr', 'reviewer', 'author'):
        if record.get(key) != state[key]:
            raise ValueError('checkpoint identity does not match this PR and reviewer')
    if (record.get('phase') not in PHASES or type(record.get('rounds')) is not int
            or record['rounds'] < 0 or type(record.get('round_limit')) is not int
            or record['round_limit'] < 1 or not isinstance(record.get('seen'), list)
            or any(not isinstance(key, str) for key in record['seen'])):
        raise ValueError('invalid checkpoint progress')
    for key in ('head', 'base'):
        if record.get(key) is not None and not re.fullmatch(r'[0-9a-f]{40}', record[key]):
            raise ValueError('invalid checkpoint revision')
    for key in ('phase', 'rounds', 'round_limit', 'head', 'base', 'ci', 'ci_key', 'seen'):
        state[key] = record.get(key)
    ci_seen = record.get('ci_seen')
    if ci_seen is not None and (not isinstance(ci_seen, list) or any(not isinstance(key, str) for key in ci_seen)):
        raise ValueError('invalid checkpoint CI progress')
    state['ci_seen'] = ci_seen
    state['review_phase'] = record.get('review_phase') or record['phase']
    complexity = record.get('complexity') or 'high'
    if complexity not in {'deterministic', 'low', 'medium', 'high'}:
        raise ValueError('invalid checkpoint review complexity')
    state['complexity'] = complexity


def encode_checkpoint(record):
    payload = base64.urlsafe_b64encode(json.dumps(record, sort_keys=True).encode()).decode()
    return f'<!-- {MARKER} {payload} -->'


def decode_checkpoint(body):
    matches = re.findall(r'<!-- ' + re.escape(MARKER) + r' ([A-Za-z0-9_=-]+) -->', body or '')
    if len(matches) != 1:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(matches[0]))
    except (ValueError, UnicodeError):
        return None


def validate_result(result):
    if not isinstance(result, dict):
        raise ValueError('review result must be an object')
    disposition(result.get('outcome'), 0, 1)
    if not isinstance(result.get('body'), str) or not result['body'].strip():
        raise ValueError('review result needs a useful summary or handoff')
    if len(result['body']) > 40000 or MARKER in result['body']:
        raise ValueError('review body is too large or contains reserved metadata')
    if not isinstance(result.get('comments'), list) or len(result['comments']) > 30:
        raise ValueError('review result needs at most 30 inline comments')
    for item in result['comments']:
        if (not isinstance(item, dict) or not isinstance(item.get('path'), str)
                or item['path'].startswith('/') or '..' in item['path'].split('/')
                or type(item.get('line')) is not int or item['line'] < 1
                or item.get('side') not in {'LEFT', 'RIGHT'}
                or not isinstance(item.get('body'), str) or not item['body'].strip()
                or len(item['body']) > 10000 or MARKER in item['body']):
            raise ValueError('invalid inline finding')
    return result
