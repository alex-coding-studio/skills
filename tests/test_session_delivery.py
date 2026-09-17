from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('session_monitor', ROOT / 'plugins/alex-coding/skills/monitor/scripts/codex_pr_monitor.py')
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
claude_spec = importlib.util.spec_from_file_location('claude_session_monitor', ROOT / 'plugins/alex-coding/skills/monitor/scripts/claude_pr_monitor.py')
claude = importlib.util.module_from_spec(claude_spec)
claude_spec.loader.exec_module(claude)
THREAD = '12345678-1234-1234-1234-123456789abc'
SESSION = 'board-claude-session'


@contextmanager
def owning_endpoint(reply):
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / 'control.sock')
        received = []
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)
        server.listen(1)

        def serve():
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                buffer = b''
                while b'\n' not in buffer:
                    chunk = connection.recv(4096)
                    if not chunk:
                        return
                    buffer += chunk
                received.append(buffer.split(b'\n', 1)[0].decode())
                connection.sendall(json.dumps(reply).encode() + b'\n')

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield 'unix://' + path, received
        finally:
            server.close()
            thread.join(timeout=5)


class SessionDeliveryTests(unittest.TestCase):
    def test_SESSION_05_bound_startup_selects_session_and_refuses_desktop_override(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = Path(directory) / 'state' / 'author-pr-monitor' / THREAD
            store = monitor.core.Store(owner / 'pr', THREAD, 'owner/repo#1', monitor.Runtime(THREAD, '/m.py'))
            with store.locked() as data:
                data['target'] = dict(repository='owner/repo', number=1)
            monitor.bind_session_route(store, owner, 'ws://127.0.0.1:54189')
            argv = ['m.py', '--thread', THREAD, '--pr', 'owner/repo#1', '--state-dir', str(store.root), 'run', '--once']
            with patch.dict(monitor.os.environ, {'CODEX_HOME': directory}), \
                    patch.object(sys, 'argv', argv), \
                    patch.object(monitor.shutil, 'which', return_value='/codex'), \
                    patch.object(monitor.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '--remote')), \
                    patch.object(monitor.transport, 'desktop_is_idle', side_effect=AssertionError('desktop used')), \
                    patch.object(monitor.core, 'run') as run:
                monitor.main()
                self.assertEqual(run.call_args.args[0].runtime.remote, 'ws://127.0.0.1:54189')
                with patch.object(sys, 'argv', argv + ['--delivery', 'session']):
                    monitor.main()
                with patch.object(sys, 'argv', argv + ['--delivery', 'idle']), self.assertRaises(SystemExit):
                    monitor.main()

    def test_SESSION_01_routes_to_owner_without_desktop_or_config_overrides(self):
        runtime = monitor.Runtime(THREAD, '/monitor.py', '/codex', delivery='session', remote='ws://127.0.0.1:54189')
        with patch.object(monitor.transport, 'desktop_is_idle', side_effect=AssertionError('desktop used')), \
                patch.object(monitor.subprocess, 'run') as run:
            self.assertTrue(runtime.deliver('feedback'))
        self.assertEqual(run.call_args.args[0], ['/codex', 'queue', '--remote', 'ws://127.0.0.1:54189', '--thread', THREAD, '--message', 'feedback'])
        self.assertFalse(runtime.may_clean({'checkout': '/work'}))

    def test_SESSION_02_unavailable_owner_preserves_pending_batch(self):
        runtime = monitor.Runtime(THREAD, '/monitor.py', '/codex', delivery='session', remote='ws://127.0.0.1:54189')
        with tempfile.TemporaryDirectory() as directory:
            store = monitor.core.Store(directory, THREAD, 'owner/repo#1', runtime)
            with store.locked() as data:
                data['target'] = dict(repository='owner/repo', number=1, stopped=False, terminal=None,
                                      cleanup_result=None, events={'e': dict(status='pending', kind='review', id=1, url='https://example.test')})
            with patch.object(monitor.subprocess, 'run', side_effect=subprocess.TimeoutExpired('codex', 45)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    store.deliver()
            self.assertIsNone(store.read()['batch'])
            self.assertEqual(store.read()['target']['events']['e']['status'], 'pending')

    def test_SESSION_03_target_route_cannot_change_or_move_a_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            store = monitor.core.Store(Path(directory) / 'pr', THREAD, 'owner/repo#1', monitor.Runtime(THREAD, '/m.py'))
            with store.locked() as data:
                data['target'] = dict(repository='owner/repo', number=1)
            monitor.bind_session_route(store, Path(directory), 'ws://127.0.0.1:54189')
            monitor.bind_session_route(store, Path(directory), 'ws://127.0.0.1:54189')
            with self.assertRaises(ValueError):
                monitor.bind_session_route(store, Path(directory), 'ws://127.0.0.1:54190')
            self.assertEqual(store.read()['target']['session_remote'], 'ws://127.0.0.1:54189')
            other = monitor.core.Store(Path(directory) / 'other', THREAD, 'owner/repo#2', monitor.Runtime(THREAD, '/m.py'))
            with other.locked() as data:
                data['target'] = dict(repository='owner/repo', number=2)
                data['batch'] = dict(token='claimed')
            with self.assertRaises(ValueError):
                monitor.bind_session_route(other, Path(directory), 'ws://127.0.0.1:54189')

    def test_SESSION_04_rejects_nonlocal_or_ambiguous_endpoints(self):
        for endpoint in ('unix://', 'unix://relative', 'ws://example.com:80', 'ws://user:secret@127.0.0.1:80', 'ws://127.0.0.1:80/path', 'http://127.0.0.1:80'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                monitor.validate_session_remote(endpoint)


class ClaudeSessionDeliveryTests(unittest.TestCase):
    def pending_store(self, directory, runtime):
        store = claude.core.Store(directory, SESSION, 'owner/repo#1', runtime)
        with store.locked() as data:
            data['target'] = dict(repository='owner/repo', number=1, stopped=False, terminal=None,
                                  cleanup_result=None,
                                  events={'e': dict(status='pending', kind='review', id=1, url='https://example.test')})
        return store

    def test_CLAUDE_SESSION_01_a_multiline_batch_reaches_the_owner_as_one_framed_line(self):
        batch = 'owner/repo#1 author feedback is ready.\nRun: python3 monitor.py ack --token abc\nreview id=1'
        with owning_endpoint({'ok': True}) as (endpoint, received):
            runtime = claude.Runtime(SESSION, '/monitor.py', delivery='session', remote=endpoint)
            self.assertTrue(runtime.deliver(batch))
        self.assertEqual(len(received), 1)
        self.assertNotIn('\n', received[0])
        self.assertEqual(json.loads(received[0]), {'text': batch})

    def test_CLAUDE_SESSION_02_a_refused_batch_stays_pending_and_claims_no_token(self):
        with owning_endpoint({'ok': False, 'error': 'session busy'}) as (endpoint, _):
            runtime = claude.Runtime(SESSION, '/monitor.py', delivery='session', remote=endpoint)
            with tempfile.TemporaryDirectory() as directory:
                store = self.pending_store(directory, runtime)
                with self.assertRaises(RuntimeError):
                    store.deliver()
                self.assertIsNone(store.read()['batch'])
                self.assertEqual(store.read()['target']['events']['e']['status'], 'pending')

    def test_CLAUDE_SESSION_03_an_unreachable_owner_preserves_the_pending_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            endpoint = 'unix://' + str(Path(directory) / 'absent.sock')
            runtime = claude.Runtime(SESSION, '/monitor.py', delivery='session', remote=endpoint)
            store = self.pending_store(Path(directory) / 'state', runtime)
            with self.assertRaises(OSError):
                store.deliver()
            self.assertIsNone(store.read()['batch'])
            self.assertEqual(store.read()['target']['events']['e']['status'], 'pending')

    def test_CLAUDE_SESSION_04_target_route_cannot_change_or_move_a_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            endpoint = 'unix://' + str(Path(directory) / 'control.sock')
            other_endpoint = 'unix://' + str(Path(directory) / 'other.sock')
            store = claude.core.Store(Path(directory) / 'pr', SESSION, 'owner/repo#1', claude.Runtime(SESSION, '/m.py'))
            with store.locked() as data:
                data['target'] = dict(repository='owner/repo', number=1)
            claude.bind_session_route(store, Path(directory), endpoint)
            claude.bind_session_route(store, Path(directory), endpoint)
            with self.assertRaises(ValueError):
                claude.bind_session_route(store, Path(directory), other_endpoint)
            self.assertEqual(store.read()['target']['session_remote'], endpoint)
            other = claude.core.Store(Path(directory) / 'other', SESSION, 'owner/repo#2', claude.Runtime(SESSION, '/m.py'))
            with other.locked() as data:
                data['target'] = dict(repository='owner/repo', number=2)
                data['batch'] = dict(token='claimed')
            with self.assertRaises(ValueError):
                claude.bind_session_route(other, Path(directory), endpoint)

    def test_CLAUDE_SESSION_05_rejects_endpoints_that_are_not_an_owned_local_socket(self):
        for endpoint in ('unix://', 'unix://relative', 'unix:///tmp/../etc/control.sock',
                         'unix:///tmp/control.sock?token=x', 'ws://127.0.0.1:54189', 'http://127.0.0.1:80'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                claude.validate_session_remote(endpoint)

    def test_CLAUDE_SESSION_06_bound_startup_selects_session_and_refuses_stdout_override(self):
        with tempfile.TemporaryDirectory() as directory:
            endpoint = 'unix://' + str(Path(directory) / 'control.sock')
            owner = Path(directory) / 'state' / 'author-pr-monitor' / SESSION
            store = claude.core.Store(owner / 'pr', SESSION, 'owner/repo#1', claude.Runtime(SESSION, '/m.py'))
            with store.locked() as data:
                data['target'] = dict(repository='owner/repo', number=1)
            claude.bind_session_route(store, owner, endpoint)
            argv = ['m.py', '--session', SESSION, '--pr', 'owner/repo#1', '--state-dir', str(store.root), 'run', '--once']
            with patch.dict(claude.os.environ, {'CLAUDE_CONFIG_DIR': directory}), \
                    patch.object(sys, 'argv', argv), \
                    patch.object(claude.core, 'run') as run:
                claude.main()
                self.assertEqual(run.call_args.args[0].runtime.remote, endpoint)
                self.assertEqual(run.call_args.args[0].runtime.delivery_name, 'session')
                with patch.object(sys, 'argv', argv + ['--delivery', 'stdout']), self.assertRaises(SystemExit):
                    claude.main()

    def test_CLAUDE_SESSION_07_session_delivery_without_a_stored_binding_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            store = claude.core.Store(Path(directory) / 'pr', SESSION, 'owner/repo#1', claude.Runtime(SESSION, '/m.py'))
            with store.locked() as data:
                data['target'] = dict(repository='owner/repo', number=1)
            argv = ['m.py', '--session', SESSION, '--pr', 'owner/repo#1', '--state-dir', str(store.root),
                    'run', '--once', '--delivery', 'session']
            with patch.dict(claude.os.environ, {'CLAUDE_CONFIG_DIR': directory}), \
                    patch.object(sys, 'argv', argv), \
                    patch.object(claude.core, 'run'), self.assertRaises(SystemExit):
                claude.main()


if __name__ == '__main__':
    unittest.main()
