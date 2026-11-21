import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid


MODELS = {'codex': ('gpt-6.2-sol', 'gpt-6-luna'),
          'claude': ('claude-opus-5-5', 'claude-sonnet-5-5')}
LEGACY_MODELS = {'codex': ('gpt-5.6-sol', 'gpt-5.6-luna'),
                 'claude': ('claude-opus-5', 'claude-sonnet-5')}
PINNED_MODELS = {'codex': (('gpt-6-sol', 'gpt-6.1-sol'), ()),
                 'claude': ((), ())}
ANTIGRAVITY_FAMILIES = {
    'claude': {'low': 'claude-opus-5-5-low', 'medium': 'claude-opus-5-5-medium',
               'high': 'claude-opus-5-5-high', 'deterministic': 'claude-sonnet-5-5-high'},
    'neon': {'low': 'gemini-4-neon-low', 'medium': 'gemini-4-neon-medium',
             'high': 'gemini-4-neon-high', 'deterministic': 'gemini-4-neon-low'},
}
ANTIGRAVITY_MODELS = frozenset({
    'claude-opus-5-5-low', 'claude-opus-5-5-medium', 'claude-opus-5-5-high',
    'claude-sonnet-5-5-low', 'claude-sonnet-5-5-medium', 'claude-sonnet-5-5-high',
    'gemini-4-neon-low', 'gemini-4-neon-medium', 'gemini-4-neon-high', 'gemini-4-neon-xhigh',
    'gemini-4-hydrogen-low', 'gemini-4-hydrogen-medium', 'gemini-4-hydrogen-high', 'gemini-4-hydrogen-xhigh',
})


def antigravity_settings(root):
    return {
        'agentMode': '',
        'toolPermission': 'request-review',
        'allowNonWorkspaceAccess': False,
        'disableSlashCommands': True,
        'permissions': {
            'allow': [f'read_file({root.resolve()})'],
            'deny': [
                'write_file(*)',
                'command(*)',
                'unsandboxed(*)',
                'mcp(*)',
                'read_url(*)',
                'execute_url(*)',
            ],
        },
    }


def antigravity_family(model):
    if not model:
        return None
    if model.startswith('gemini-4-neon-'):
        return 'neon'
    if model.startswith(('claude-opus-5-5-', 'claude-sonnet-5-5-')):
        return 'claude'
    return None


def antigravity_agent_name(root, state=None):
    if state and state.get('antigravity_agent'):
        return state['antigravity_agent']
    digest = hashlib.sha256(str(Path(root)).encode()).hexdigest()[:12]
    return f'alex-coding-pr-reviewer-{digest}'


def write_antigravity_agent(root, name):
    checkout = Path(root) / 'checkout'
    for folder in ('.agents', '.agent', '_agents', '_agent'):
        agents = checkout / folder / 'agents'
        if (agents / f'{name}.md').exists() or (agents / name).exists():
            raise RuntimeError(f'review checkout shadows reserved Antigravity agent {name!r}')
    agents_dir = Path(root) / '.agents' / 'agents'
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f'{name}.md').write_text(
        f'---\nname: {name}\n'
        'description: Read-only independent PR review worker\n'
        'mainAgent: true\nsubagent: false\n'
        'tools:\n  - read_file\n  - finish\n---\n'
        'You are a read-only independent PR review worker. Follow the user prompt instructions '
        'and return only the required structured output.\n')
    return name


def review_settings(runtime, complexity='high', model=None):
    if complexity not in {'deterministic', 'low', 'medium', 'high'}:
        raise ValueError('review complexity must be deterministic, low, medium or high')
    if runtime == 'antigravity':
        selected = model or 'claude'
        if selected in ANTIGRAVITY_FAMILIES:
            resolved = ANTIGRAVITY_FAMILIES[selected][complexity]
        elif selected in ANTIGRAVITY_MODELS:
            resolved = selected
        else:
            raise ValueError(f'unsupported antigravity review model: {selected!r}')
        return {'model': resolved, 'effort': resolved.rsplit('-', 1)[-1]}
    if runtime not in {'codex', 'claude'}:
        raise ValueError('unsupported review runtime')
    cheap = complexity == 'deterministic'
    default = MODELS[runtime][int(cheap)]
    if model is not None and model != default:
        raise ValueError(f'review model {model!r} is not supported for {runtime} ({complexity})')
    return {'model': default, 'effort': 'max' if cheap else complexity}


def settings_for(state):
    runtime = state['runtime']
    complexity = state.get('complexity', 'high')
    if runtime == 'antigravity':
        settings = review_settings('antigravity', complexity)
        model = state.get('model')
        if model is None:
            return settings
        if model not in ANTIGRAVITY_MODELS:
            raise ValueError('review model does not match its runtime and complexity')
        return {'model': model, 'effort': model.rsplit('-', 1)[-1]}
    settings = review_settings(runtime, complexity)
    cheap = complexity == 'deterministic'
    model = state.get('model', LEGACY_MODELS[runtime][int(cheap)])
    if model not in {MODELS[runtime][int(cheap)], LEGACY_MODELS[runtime][int(cheap)],
                     *PINNED_MODELS[runtime][int(cheap)]}:
        raise ValueError('review model does not match its runtime and complexity')
    return {**settings, 'model': model}


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
    if runtime not in {'codex', 'claude', 'antigravity'}:
        raise ValueError('unsupported review runtime')
    binary = 'agy' if runtime == 'antigravity' else runtime
    executable = shutil.which(executable or binary)
    if not executable:
        raise RuntimeError(f'{runtime} CLI is unavailable; reviewer is inactive')
    if runtime == 'codex':
        probes = [(['exec', '--help'], ['--json', '--output-schema', '--sandbox', '--model', '--config']),
                  (['exec', 'resume', '--help'], ['--json', '--output-schema', '--model', '--config'])]
    elif runtime == 'antigravity':
        probes = [(['--help'], ['--model', '--agent', '--conversation', '--input-format', '--output-format',
                                '--json-schema', '--add-dir', '--settings'])]
    else:
        probes = [(['--help'], ['--resume', '--json-schema', '--tools', '--strict-mcp-config',
                                '--permission-mode', '--add-dir', '--model', '--effort'])]
    for arguments, flags in probes:
        completed = subprocess.run([executable, *arguments], capture_output=True, text=True, timeout=15, check=True)
        output = (completed.stdout or '') + (completed.stderr or '')
        if not all(flag in output for flag in flags):
            raise RuntimeError(f'{runtime} CLI lacks the required noninteractive review capabilities')
    return str(Path(executable).resolve())


def command(state, root, output):
    executable, session = state['executable'], state['session']
    settings = settings_for(state)
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
    if state['runtime'] == 'antigravity':
        arguments = [executable, '--model', settings['model'],
                     '--agent', antigravity_agent_name(root, state),
                     '--input-format', 'stream-json', '--output-format', 'stream-json',
                     '--json-schema', str(root / 'result-schema.json'),
                     '--settings', str(root / 'agy-settings.json'),
                     '--add-dir', str(root)]
        return arguments + (['--conversation', session] if session else [])
    arguments = [executable, '-p', '--model', settings['model'], '--effort', settings['effort'],
                 '--output-format', 'json', '--json-schema', json.dumps(schema()),
                 '--tools', 'Read,Glob,Grep', '--permission-mode', 'dontAsk', '--strict-mcp-config',
                 '--mcp-config', str(root / 'empty-mcp.json'), '--settings', '{"disableAllHooks":true}',
                 '--add-dir', str(root)]
    return arguments + (['--resume', session] if session else ['--session-id', state['next_session']])


def run_worker(state, root, input_path, events, output, persist, terminal_probe):
    with input_path.open() as source, events.open('w') as target, (root / 'runtime.log').open('a') as errors:
        environment = dict(os.environ)
        if state['runtime'] == 'antigravity':
            environment['AGY_DART_DISABLE_READ_HOOK'] = '1'
        process = subprocess.Popen(command(state, root, output), cwd=root / 'checkout', stdin=source,
                                   stdout=target, stderr=errors, start_new_session=True, env=environment)
        state['worker_pid'] = process.pid
        state['worker_deadline'] = time.time() + state['worker_timeout']
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


ANTIGRAVITY_DENIED_READ_RESUMES = 2
ANTIGRAVITY_DENIED_READ_NUDGE = (
    'A read outside the review directory was denied and ended your turn. Do not retry it or read '
    'outside the review directory. Finish the review from the evidence you have and return the '
    'structured result.'
)


def antigravity_denied_without_output(state, events):
    if state['runtime'] != 'antigravity':
        return None
    envelope = None
    for line in events.read_text().splitlines():
        if line.strip():
            event = json.loads(line)
            if event.get('event') == 'result':
                envelope = event.get('result')
    if (isinstance(envelope, dict) and envelope.get('status') == 'SUCCESS'
            and not isinstance(envelope.get('structured_output'), dict)
            and envelope.get('denied_actions') and envelope.get('conversation_id')
            and state['session'] in {None, envelope['conversation_id']}):
        return envelope
    return None


def execute(state, root, prompt, persist, terminal_probe=None):
    root = Path(root)
    token = state['pending']['token']
    output = root / f'{token}.result.json'
    events = root / f'{token}.events.jsonl'
    (root / 'result-schema.json').write_text(json.dumps(schema()))
    (root / 'empty-mcp.json').write_text('{"mcpServers":{}}')
    if state['runtime'] == 'antigravity':
        (root / 'agy-settings.json').write_text(json.dumps(antigravity_settings(root)))
        agent_name = state.get('antigravity_agent') or f'alex-coding-pr-reviewer-{uuid.uuid4().hex[:12]}'
        state['antigravity_agent'] = agent_name
        write_antigravity_agent(root, agent_name)
    state['next_session'] = str(uuid.uuid4())
    persist(state)
    prompt_path = root / f'{token}.prompt.txt'
    prompt_path.write_text(prompt)
    if state['runtime'] == 'antigravity':
        input_path = root / f'{token}.input.jsonl'
        input_path.write_text(json.dumps({'event': 'user', 'message': {'content': prompt}}) + '\n')
    else:
        input_path = prompt_path
    run_worker(state, root, input_path, events, output, persist, terminal_probe)
    for attempt in range(1, ANTIGRAVITY_DENIED_READ_RESUMES + 1):
        envelope = antigravity_denied_without_output(state, events)
        if envelope is None:
            break
        events.rename(root / f'{token}.events.{attempt}.jsonl')
        state['session'] = envelope['conversation_id']
        persist(state)
        resume_path = root / f'{token}.resume.{attempt}.jsonl'
        resume_path.write_text(json.dumps({'event': 'user', 'message': {'content': ANTIGRAVITY_DENIED_READ_NUDGE}}) + '\n')
        run_worker(state, root, resume_path, events, output, persist, terminal_probe)
    return collect(state, root, token, persist)


def worker_alive(state, root):
    if not state.get('worker_pid'):
        return False
    found = subprocess.run(['ps', '-o', 'command=', '-p', str(state['worker_pid'])], capture_output=True, text=True)
    return str(Path(root)) in found.stdout


def stop_worker(state, root):
    try:
        os.killpg(state['worker_pid'], signal.SIGTERM)
        for _ in range(50):
            if not worker_alive(state, root):
                return
            time.sleep(0.1)
        os.killpg(state['worker_pid'], signal.SIGKILL)
    except ProcessLookupError:
        pass


def collect(state, root, token, persist):
    output = root / f'{token}.result.json'
    events = root / f'{token}.events.jsonl'
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
    elif state['runtime'] == 'antigravity':
        init = None
        envelope = None
        for line in events.read_text().splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get('event') == 'init':
                init = event.get('init')
            elif event.get('event') == 'result':
                envelope = event.get('result')
        expected_agent = antigravity_agent_name(root, state)
        if (not isinstance(init, dict) or init.get('agent') != expected_agent
                or init.get('permission_mode') != 'request-review'):
            raise RuntimeError('Antigravity did not run with the expected read-only review agent')
        if not isinstance(envelope, dict) or envelope.get('status') != 'SUCCESS':
            raise RuntimeError('Antigravity did not complete the review session')
        session = envelope.get('conversation_id')
        if not session:
            raise RuntimeError('Antigravity did not report its review session identity')
        if state['session'] and state['session'] != session:
            raise RuntimeError('Antigravity resumed a different review session')
        if not isinstance(envelope.get('structured_output'), dict):
            raise RuntimeError('Antigravity did not return structured review output')
        state['session'] = session
        state['last_usage'] = envelope.get('usage')
        result = envelope['structured_output']
        output.write_text(json.dumps(result))
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
