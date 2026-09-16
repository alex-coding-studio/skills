import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid


def review_settings(runtime, complexity='high'):
    if complexity not in {'deterministic', 'low', 'medium', 'high'}:
        raise ValueError('review complexity must be deterministic, low, medium or high')
    if runtime not in {'codex', 'claude'}:
        raise ValueError('unsupported review runtime')
    models = {'codex': ('gpt-5.6-sol', 'gpt-5.6-luna'),
              'claude': ('claude-opus-5', 'claude-sonnet-5')}
    cheap = complexity == 'deterministic'
    return {'model': models[runtime][int(cheap)], 'effort': 'max' if cheap else complexity}


class PRFinished(Exception):
    def __init__(self, phase):
        self.phase = phase
        super().__init__(phase)


def schema():
    return {'type': 'object', 'additionalProperties': False,
            'properties': {
                'outcome': {'type': 'string', 'enum': ['approved', 'changes-requested', 'waiting-ci', 'needs-user-attention']},
                'body': {'type': 'string'},
                'comments': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                    'properties': {'path': {'type': 'string'}, 'line': {'type': 'integer'},
                                   'side': {'type': 'string', 'enum': ['LEFT', 'RIGHT']}, 'body': {'type': 'string'}},
                    'required': ['path', 'line', 'side', 'body']}}},
            'required': ['outcome', 'body', 'comments']}


def preflight(runtime, executable=None):
    executable = shutil.which(executable or runtime)
    if not executable:
        raise RuntimeError(f'{runtime} CLI is unavailable; reviewer is inactive')
    probes = [(['exec', '--help'], ['--json', '--output-schema', '--sandbox', '--model', '--config']),
              (['exec', 'resume', '--help'], ['--json', '--output-schema', '--model', '--config'])] if runtime == 'codex' else [
                  (['--help'], ['--resume', '--json-schema', '--tools', '--strict-mcp-config', '--permission-mode', '--add-dir', '--model', '--effort'])]
    for arguments, flags in probes:
        output = subprocess.run([executable, *arguments], capture_output=True, text=True, timeout=15, check=True).stdout
        if not all(flag in output for flag in flags):
            raise RuntimeError(f'{runtime} CLI lacks the required noninteractive review capabilities')
    return str(Path(executable).resolve())


def command(state, root, output):
    executable, session = state['executable'], state['session']
    settings = review_settings(state['runtime'], state.get('complexity', 'high'))
    if state['runtime'] == 'codex':
        arguments = [executable, 'exec']
        if session:
            arguments += ['resume', session]
        arguments += ['--model', settings['model'], '-c', f'model_reasoning_effort="{settings["effort"]}"',
                      '-c', 'sandbox_mode="read-only"', '-c', 'approval_policy="never"',
                      '-c', 'features.multi_agent=false', '-c', 'web_search="disabled"',
                      '--json', '--output-schema', str(root / 'result-schema.json'),
                      '--output-last-message', str(output), '-']
        return arguments
    arguments = [executable, '-p', '--model', settings['model'], '--effort', settings['effort'],
                 '--output-format', 'json', '--json-schema', json.dumps(schema()),
                 '--tools', 'Read,Glob,Grep', '--permission-mode', 'dontAsk', '--strict-mcp-config',
                 '--mcp-config', str(root / 'empty-mcp.json'), '--settings', '{"disableAllHooks":true}',
                 '--add-dir', str(root)]
    return arguments + (['--resume', session] if session else ['--session-id', state['next_session']])


def execute(state, root, prompt, persist, terminal_probe=None):
    root = Path(root)
    token = state['pending']['token']
    output = root / f'{token}.result.json'
    events = root / f'{token}.events.jsonl'
    (root / 'result-schema.json').write_text(json.dumps(schema()))
    (root / 'empty-mcp.json').write_text('{"mcpServers":{}}')
    state['next_session'] = str(uuid.uuid4())
    persist(state)
    prompt_path = root / f'{token}.prompt.txt'
    prompt_path.write_text(prompt)
    with prompt_path.open() as source, events.open('w') as target, (root / 'runtime.log').open('a') as errors:
        process = subprocess.Popen(command(state, root, output), cwd=root / 'checkout', stdin=source,
                                   stdout=target, stderr=errors, start_new_session=True)
        state['worker_pid'] = process.pid
        persist(state)
        try:
            deadline = time.monotonic() + state['worker_timeout']
            next_probe = time.monotonic() + state.get('interval', 45)
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError('review worker exceeded its execution deadline')
                if terminal_probe and time.monotonic() >= next_probe:
                    next_probe = time.monotonic() + state.get('interval', 45)
                    try:
                        terminal = terminal_probe()
                    except Exception:
                        terminal = None
                    if terminal in {'merged', 'closed'}:
                        raise PRFinished(terminal)
                time.sleep(0.25)
            if process.returncode:
                raise RuntimeError(f'{state["runtime"]} review worker failed; inspect runtime.log')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            state['worker_pid'] = None
            persist(state)
    if state['runtime'] == 'codex':
        for line in events.read_text().splitlines():
            event = json.loads(line)
            if event.get('type') == 'thread.started':
                session = event['thread_id']
                if state['session'] and state['session'] != session:
                    raise RuntimeError('Codex resumed a different review session')
                state['session'] = session
            if event.get('type') == 'turn.completed':
                state['last_usage'] = event.get('usage')
        if not state['session']:
            raise RuntimeError('Codex did not report its review session identity')
        result = json.loads(output.read_text())
    else:
        envelope = json.loads(events.read_text())
        expected = state['session'] or state['next_session']
        if envelope.get('is_error') or envelope.get('session_id') != expected:
            raise RuntimeError('Claude did not complete the expected review session')
        state['session'] = expected
        state['last_usage'] = envelope.get('usage')
        result = envelope['structured_output']
        output.write_text(json.dumps(result))
    persist(state)
    return result
