import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('session_monitor', ROOT / 'plugins/alex-coding/skills/monitor/scripts/codex_pr_monitor.py')
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
THREAD = '12345678-1234-1234-1234-123456789abc'


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


if __name__ == '__main__':
    unittest.main()
