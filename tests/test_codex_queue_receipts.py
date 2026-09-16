import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_author_monitor_core import FakeRuntime, core, ending, enrol, notice, result, store


SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/monitor/scripts/codex_pr_monitor.py'
spec = importlib.util.spec_from_file_location('queue_receipt_codex', SCRIPT)
codex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codex)
THREAD = '12345678-1234-1234-1234-123456789abc'


class QueueRuntime(FakeRuntime):
    requires_ack = False
    foreground_cleanup = True
    delivery_name = 'queued'

    def __init__(self):
        super().__init__(clean=False)


class QueueReceiptTests(unittest.TestCase):
    def test_CQ_02_later_batches_enqueue_without_waiting_for_agent_ack(self):
        runtime = QueueRuntime()
        with store(runtime=runtime) as subject:
            enrol(subject).apply(result(notice(1)))
            self.assertTrue(subject.deliver())
            subject.apply(result(notice(1), notice(2)))
            self.assertTrue(subject.deliver())
            self.assertEqual(len(runtime.delivered), 2)
            self.assertIsNone(subject.read()['batch'])
            self.assertEqual(subject.read()['target']['events'][notice(1)['key']]['disposition'], 'queue-accepted')
            self.assertNotIn('ack --token', runtime.delivered[0])

    def test_CQ_03_failed_submission_retries_and_acceptance_survives_restart(self):
        runtime = QueueRuntime()
        with store(runtime=runtime) as subject:
            enrol(subject).apply(result(notice(1)))
            with patch.object(runtime, 'deliver', side_effect=subprocess.TimeoutExpired('codex', 45)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    subject.deliver()
            self.assertEqual(subject.read()['target']['events'][notice(1)['key']]['status'], 'pending')
            self.assertTrue(subject.deliver())
            resumed = core.Store(subject.root, subject.identity, subject.name, runtime)
            resumed.apply(result(notice(1)))
            self.assertFalse(resumed.deliver())
            resumed.apply(result(notice(1), core.event('conversation', 1, 'edited', 'https://example/comment')))
            self.assertTrue(resumed.deliver())

    def test_CQ_04_terminal_receipt_stops_without_background_cleanup(self):
        runtime = QueueRuntime()
        with store(runtime=runtime) as subject:
            enrol(subject, checkout='/work')
            with patch.object(core, 'cleanup_target') as cleanup:
                subject.apply(result(ending(), terminal='merged'))
                self.assertTrue(subject.deliver())
            cleanup.assert_not_called()
            self.assertTrue(subject.read()['target']['stopped'])
            self.assertIsNone(subject.read()['batch'])
            self.assertIn('complete', runtime.delivered[0])

    def test_CQ_04_foreground_completion_has_no_new_agent_ack_gate(self):
        runtime = QueueRuntime()
        with store(runtime=runtime) as subject:
            enrol(subject, checkout='/work')
            with subject.locked() as data:
                data['target']['foreground_cleanup'] = True
            with patch.object(core, 'snapshot', return_value=result(notice(1), ending(), terminal='merged')), \
                 patch.object(core, 'cleanup_target', return_value={'status': 'cleaned'}) as cleanup:
                self.assertEqual(subject.complete()['status'], 'cleaned')
            cleanup.assert_called_once()

    def test_CQ_05_old_inflight_batch_is_preserved_while_new_events_can_enqueue(self):
        runtime = QueueRuntime()
        with store(runtime=runtime) as subject:
            enrol(subject).apply(result(notice(1)))
            token = subject.claim([notice(1)['key']])
            subject.apply(result(notice(1), notice(2)))
            self.assertTrue(subject.deliver())
            self.assertEqual(subject.read()['batch']['token'], token)
            self.assertEqual(subject.read()['target']['events'][notice(1)['key']]['status'], 'delivered')
            subject.acknowledge(token)
            self.assertIsNone(subject.read()['batch'])

    def test_CQ_02_more_than_one_batch_reaches_queue_before_terminal_stop(self):
        runtime = QueueRuntime()
        with store(runtime=runtime) as subject:
            enrol(subject).apply(result(*(notice(i) for i in range(core.BATCH_LIMIT + 1)),
                                        ending('closed'), terminal='closed'))
            self.assertTrue(subject.deliver())
            self.assertFalse(subject.read()['target']['stopped'])
            self.assertTrue(subject.deliver())
            self.assertTrue(subject.read()['target']['stopped'])
            self.assertEqual(len(runtime.delivered), 2)

    def test_CQ_05_claude_style_delivery_still_requires_its_original_ack(self):
        runtime = FakeRuntime(clean=False)
        with store(runtime=runtime) as subject:
            enrol(subject).apply(result(notice(1)))
            subject.deliver()
            token = subject.read()['batch']['token']
            subject.apply(result(notice(1), notice(2)))
            self.assertFalse(subject.deliver())
            subject.acknowledge(token)
            self.assertTrue(subject.deliver())


class CodexDefaultQueueTests(unittest.TestCase):
    def test_CQ_01_default_startup_does_not_read_desktop_state(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = codex.Runtime(THREAD, '/monitor.py')
            subject = codex.core.Store(directory, THREAD, 'owner/repo#1', runtime)
            with subject.locked() as data:
                data['target'] = {'repository': 'owner/repo', 'number': 1}
            argv = ['monitor.py', '--thread', THREAD, '--pr', 'owner/repo#1', '--state-dir', directory, 'run', '--once']
            with patch.object(sys, 'argv', argv), \
                 patch.object(codex.shutil, 'which', return_value='/codex'), \
                 patch.object(codex.subprocess, 'run'), \
                 patch.object(codex.transport, 'desktop_is_idle', side_effect=AssertionError('idle probe called')), \
                 patch.object(codex.core, 'run') as run:
                codex.main()
            self.assertEqual(run.call_args.args[0].runtime.delivery_name, 'queued')


if __name__ == '__main__':
    unittest.main()
