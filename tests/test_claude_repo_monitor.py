import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/review/scripts/claude_repo_monitor.py'
spec = importlib.util.spec_from_file_location('claude_repo_monitor', SCRIPT)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


@contextlib.contextmanager
def invoked(extra=(), session='session-one'):
    with tempfile.TemporaryDirectory() as directory:
        argv = [str(SCRIPT), 'owner/repo', '--session', session, '--reviewer', 'Reviewer',
                '--state-dir', directory, *extra]
        with patch.object(sys, 'argv', argv):
            yield Path(directory)


class DeliveryTests(unittest.TestCase):
    def test_delivery_prints_and_reports_success(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(monitor.deliver('batch text'))
        self.assertIn('batch text', output.getvalue())


class ConfigurationTests(unittest.TestCase):
    def test_the_watch_selects_the_admin_role(self):
        captured = {}
        with invoked(['--once']) as directory:
            with patch.object(monitor.core, 'run', side_effect=lambda w, *a: captured.update(role=w.role, root=w.root)):
                monitor.main()
        self.assertEqual(captured['role'], 'admin')
        self.assertEqual(captured['root'], directory)

    def test_the_identity_file_records_the_session(self):
        with invoked(['--once']) as directory:
            with patch.object(monitor.core, 'run'):
                monitor.main()
            self.assertEqual(json.loads((directory / 'identity.json').read_text()),
                             {'repository': 'owner/repo', 'session': 'session-one', 'reviewer': 'reviewer'})

    def test_a_malformed_session_is_refused(self):
        with invoked(['--once'], session='has space'), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            monitor.main()

    def test_state_bound_to_another_session_is_refused(self):
        with invoked(['--once']) as directory:
            with patch.object(monitor.core, 'run'):
                monitor.main()
            argv = [str(SCRIPT), 'owner/repo', '--session', 'other', '--reviewer', 'Reviewer', '--state-dir', str(directory), '--once']
            with patch.object(sys, 'argv', argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                monitor.main()

    def test_acknowledgement_skips_the_polling_loop(self):
        with invoked(['--ack', '1', '--head', 'a' * 40, '--phase', 'done']) as directory:
            with patch.object(monitor.core, 'run') as loop, contextlib.redirect_stdout(io.StringIO()):
                monitor.main()
            loop.assert_not_called()
            self.assertEqual(monitor.core.read_reviews(directory)['1']['phase'], 'done')

    def test_the_default_state_root_follows_the_claude_configuration(self):
        root = monitor.core.default_root('CLAUDE_CONFIG_DIR', '.claude', 'owner/repo', 'session-one')
        self.assertIn('repository-monitor', str(root))


if __name__ == '__main__':
    unittest.main()
