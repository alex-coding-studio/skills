import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / 'plugins/alex-coding/skills/implement/scripts/usage_report.py'
spec = importlib.util.spec_from_file_location('usage_report', PATH)
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


class UsageTests(unittest.TestCase):
    def test_claude_split_message_usage_is_counted_once_with_final_output(self):
        first = {'type': 'assistant', 'sessionId': 's', 'message': {'id': 'm', 'model': 'sonnet',
            'usage': {'input_tokens': 3, 'cache_read_input_tokens': 20,
                      'cache_creation_input_tokens': 10, 'output_tokens': 2}}}
        last = {**first, 'message': {**first['message'], 'usage': {**first['message']['usage'], 'output_tokens': 8}}}
        report = usage.summarize('claude', [first, last, last])
        self.assertEqual(report['model_calls'], 1)
        self.assertEqual(report['tokens'], {'input': 3, 'cache_read': 20, 'cache_write': 10, 'output': 8})
        self.assertEqual(report['peak_input_context'], 33)

    def test_codex_cumulative_usage_is_not_added_for_every_snapshot(self):
        def event(total):
            return {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                'total_token_usage': {'input_tokens': total, 'cached_input_tokens': total // 2, 'output_tokens': 10},
                'last_token_usage': {'input_tokens': 50}}}}
        report = usage.summarize('codex', [event(100), event(100), event(200)])
        self.assertEqual(report['tokens'], {'input': 100, 'cache_read': 100, 'cache_write': 0, 'output': 10})
        self.assertIsNone(report['model_calls'])
        self.assertEqual(report['peak_input_context'], 50)

    def test_codex_cli_turn_totals_and_native_totals_cannot_be_combined(self):
        rows = [{'type': 'turn.completed', 'usage': {'input_tokens': 10}},
                {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 10}}}}]
        with self.assertRaises(ValueError):
            usage.summarize('codex', rows)

    def test_claude_summary_cannot_be_added_to_its_native_messages(self):
        rows = [{'type': 'result', 'usage': {'input_tokens': 9}},
                {'type': 'assistant', 'message': {'id': 'm', 'usage': {'input_tokens': 9}}}]
        with self.assertRaises(ValueError):
            usage.summarize('claude', rows)

    def test_missing_usage_or_message_identity_is_reported_not_invented(self):
        with self.assertRaises(ValueError):
            usage.summarize('claude', [{'type': 'assistant', 'message': {'usage': {'input_tokens': 4}}}])
        with self.assertRaises(ValueError):
            usage.summarize('codex', [{'type': 'user'}])


if __name__ == '__main__':
    unittest.main()
