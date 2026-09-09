import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/review/scripts/codex_repo_monitor.py'
spec = importlib.util.spec_from_file_location('codex_repo_monitor', SCRIPT)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)

THREAD = '12345678-1234-1234-1234-123456789abc'


@contextlib.contextmanager
def invoked(extra=(), thread=THREAD):
    with tempfile.TemporaryDirectory() as directory:
        argv = [str(SCRIPT), 'owner/repo', '--thread', thread, '--reviewer', 'Reviewer',
                '--state-dir', directory, *extra]
        with patch.object(sys, 'argv', argv), patch.object(monitor.shutil, 'which', return_value='/path/codex'):
            yield Path(directory)


class DeliveryTests(unittest.TestCase):
    def test_a_busy_desktop_refuses_delivery_without_queueing(self):
        with patch.object(monitor.desktop_transport, 'desktop_is_idle', return_value=False), \
             patch.object(monitor.desktop_transport, 'queue_message') as queue:
            self.assertFalse(monitor.deliverer('/path/codex', THREAD)('batch'))
        queue.assert_not_called()

    def test_an_idle_desktop_queues_the_batch(self):
        with patch.object(monitor.desktop_transport, 'desktop_is_idle', return_value=True), \
             patch.object(monitor.desktop_transport, 'queue_message') as queue:
            self.assertTrue(monitor.deliverer('/path/codex', THREAD)('batch'))
        queue.assert_called_once_with('/path/codex', THREAD, 'batch')


class ConfigurationTests(unittest.TestCase):
    def test_the_watch_selects_the_admin_role(self):
        captured = {}
        with invoked(['--once']) as directory:
            with patch.object(monitor.core, 'run', side_effect=lambda w, *a: captured.update(role=w.role, root=w.root)):
                monitor.main()
        self.assertEqual(captured['role'], 'admin')
        self.assertEqual(captured['root'], directory)

    def test_the_identity_file_records_the_thread(self):
        with invoked(['--once']) as directory:
            with patch.object(monitor.core, 'run'):
                monitor.main()
            self.assertEqual(json.loads((directory / 'identity.json').read_text()),
                             {'repository': 'owner/repo', 'thread': THREAD, 'reviewer': 'reviewer'})

    def test_a_malformed_thread_is_refused(self):
        with invoked(['--once'], thread='not-a-uuid'), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            monitor.main()

    def test_a_missing_codex_executable_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            argv = [str(SCRIPT), 'owner/repo', '--thread', THREAD, '--reviewer', 'Reviewer', '--state-dir', directory, '--once']
            with patch.object(sys, 'argv', argv), patch.object(monitor.shutil, 'which', return_value=None), \
                 self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                monitor.main()

    def test_acknowledgement_skips_the_polling_loop(self):
        with invoked(['--ack', '1', '--head', 'a' * 40, '--phase', 'done']) as directory:
            with patch.object(monitor.core, 'run') as loop, contextlib.redirect_stdout(io.StringIO()):
                monitor.main()
            loop.assert_not_called()
            self.assertEqual(monitor.core.read_reviews(directory)['1']['phase'], 'done')


if __name__ == '__main__':
    unittest.main()
