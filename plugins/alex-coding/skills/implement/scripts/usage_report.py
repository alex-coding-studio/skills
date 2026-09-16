import argparse
import json
from pathlib import Path


FIELDS = ('input', 'cache_read', 'cache_write', 'output')


def normalized(runtime, value):
    if runtime == 'claude':
        result = dict(zip(FIELDS, [value.get(key, 0) for key in (
            'input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens')]))
    else:
        cached = value.get('cached_input_tokens', 0)
        written = value.get('cache_write_input_tokens', 0)
        result = {'input': value.get('input_tokens', 0) - cached - written,
                  'cache_read': cached, 'cache_write': written, 'output': value.get('output_tokens', 0)}
    if any(type(number) is not int or number < 0 for number in result.values()):
        raise ValueError('usage contains invalid or inconsistent token counters')
    return result


def summarize(runtime, rows):
    records = []
    models = set()
    session_ids = set()
    contexts = []
    source_kind = None
    calls = None
    if runtime == 'claude':
        messages = {}
        summaries = []
        for row in rows:
            session_ids.update([row[key] for key in ('sessionId', 'session_id') if row.get(key)])
            if row.get('type') == 'assistant' and row.get('message', {}).get('usage'):
                message = row['message']
                if not message.get('id'):
                    raise ValueError('assistant usage lacks the message ID needed for deduplication')
                key = (row.get('sessionId'), message['id'])
                value = normalized(runtime, message['usage'])
                previous = messages.get(key, dict.fromkeys(FIELDS, 0))
                messages[key] = {name: max(previous[name], value[name]) for name in FIELDS}
                if message.get('model'):
                    models.add(message['model'])
            elif row.get('usage') and (row.get('type') == 'result' or 'structured_output' in row):
                summaries.append(normalized(runtime, row['usage']))
                models.update(row.get('modelUsage', {}))
        if messages and summaries:
            raise ValueError('do not mix Claude native messages and their CLI summaries')
        source_kind = 'native' if messages else 'cli-summary'
        records = list(messages.values()) if messages else summaries
        calls = len(messages) if messages else None
        if messages:
            contexts = [value['input'] + value['cache_read'] + value['cache_write'] for value in records]
    elif runtime == 'codex':
        cumulative = []
        turns = []
        for row in rows:
            if row.get('type') == 'session_meta' and row.get('payload', {}).get('id'):
                session_ids.add(row['payload']['id'])
            if row.get('type') == 'thread.started':
                session_ids.add(row['thread_id'])
            if row.get('type') == 'turn_context' and row.get('payload', {}).get('model'):
                models.add(row['payload']['model'])
            if row.get('type') == 'turn.completed' and row.get('usage'):
                turns.append(normalized(runtime, row['usage']))
            payload = row.get('payload', {})
            if row.get('type') == 'event_msg' and payload.get('type') == 'token_count' and payload.get('info'):
                info = payload['info']
                if info.get('total_token_usage'):
                    cumulative.append(normalized(runtime, info['total_token_usage']))
                if info.get('last_token_usage'):
                    contexts.append(info['last_token_usage'].get('input_tokens', 0))
        if cumulative and turns:
            raise ValueError('do not mix Codex native cumulative usage with CLI turn summaries')
        if len(session_ids) > 1:
            raise ValueError('one Codex input must describe one session')
        if cumulative:
            for before, after in zip(cumulative, cumulative[1:]):
                if any(after[key] < before[key] for key in FIELDS):
                    raise ValueError('cumulative usage decreased; inspect reset/overlap before comparing')
            records = cumulative[-1:]
        else:
            records = turns
        source_kind = 'native' if cumulative else 'cli-summary'
    else:
        raise ValueError('runtime must be claude or codex')
    if not records:
        raise ValueError('no supported usage evidence found')
    return {'source_kind': source_kind, 'sessions': sorted(session_ids), 'models': sorted(models),
            'model_calls': calls, 'usage_records': len(records),
            'tokens': {key: sum(value[key] for value in records) for key in FIELDS},
            'peak_input_context': max(contexts) if contexts else None,
            'mean_input_context': sum(contexts) / len(contexts) if contexts and runtime == 'claude' else None}


def read_rows(path):
    text = path.read_text()
    try:
        value = json.loads(text)
    except ValueError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return value if isinstance(value, list) else [value]


def main():
    parser = argparse.ArgumentParser(description='Summarize explicit local author/reviewer logs without model calls or transcript output.')
    parser.add_argument('--input', nargs=3, action='append', required=True, metavar=('RUNTIME', 'ROLE', 'PATH'))
    parser.add_argument('--rates', type=Path, help='Optional per-million token prices keyed by runtime:role, matching actual model/cache TTL.')
    args = parser.parse_args()
    rates = json.loads(args.rates.read_text()) if args.rates else {}
    reports = []
    paths = set()
    ownership = {}
    for runtime, role, name in args.input:
        path = Path(name).expanduser().resolve()
        if path in paths:
            parser.error('the same source file was supplied twice')
        paths.add(path)
        report = summarize(runtime, read_rows(path))
        for session in report['sessions']:
            key = (runtime, session)
            prior = ownership.get(key)
            current = (role, report['source_kind'])
            if prior and (prior != current or report['source_kind'] == 'native'):
                parser.error('overlapping session sources or conflicting author/reviewer attribution')
            ownership[key] = current
        report.update(runtime=runtime, role=role, source=str(path), estimated_cost=None)
        price = rates.get(f'{runtime}:{role}')
        if price is not None:
            if (set(price) != set(FIELDS) or any(type(value) not in (int, float) or value < 0 for value in price.values())):
                parser.error('each rate requires nonnegative input, cache_read, cache_write and output prices per million')
            report['estimated_cost'] = sum(report['tokens'][key] * price[key] for key in FIELDS) / 1000000
        reports.append(report)
    print(json.dumps({'reports': reports,
                      'total_tokens': {key: sum(row['tokens'][key] for row in reports) for key in FIELDS},
                      'estimated_cost': sum(row['estimated_cost'] for row in reports)
                      if all(row['estimated_cost'] is not None for row in reports) else None,
                      'limits': ['Prices are caller-supplied estimates, not billing reconciliation.',
                                 'Model calls and context size are null when the log does not establish them.',
                                 'Reasoning tokens are part of output; cache reads are part of Codex input before normalization.',
                                 'No phase or wakeup-cause attribution is inferred from message text.']}, indent=2))


if __name__ == '__main__':
    main()
