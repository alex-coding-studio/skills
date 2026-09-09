import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("generate", Path(__file__).resolve().parents[1] / "scripts/generate.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def packet():
    return {"version": 1, "id": "sample", "title": "反馈", "language": "zh", "source": "原文", "items": [{"id": "one", "subject": "事项", "question": "意见？", "context": "背景", "kind": "text"}]}


class GeneratorTests(unittest.TestCase):
    def test_hostile_source_round_trips_without_closing_script(self):
        data = packet()
        data["source"] = '</script><script>alert("x")</script>&中文'
        output = generator.generate(data)
        embedded = output.split('<script id="packet" type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertNotIn('<', embedded)
        self.assertEqual(json.loads(embedded), data)

    def test_duplicate_ids_are_rejected(self):
        data = packet()
        data["items"].append(dict(data["items"][0]))
        with self.assertRaises(ValueError):
            generator.validate(data)

    def test_invalid_choice_cannot_silently_disappear(self):
        for options in ([], ['one'], ['one', 'one'], ['one', 3]):
            data = packet()
            data["items"][0].update(kind="single", options=options)
            with self.assertRaises(ValueError):
                generator.validate(data)

    def test_unknown_defaults_are_rejected(self):
        data = packet()
        data["items"][0]["default"] = "approved"
        with self.assertRaises(ValueError):
            generator.validate(data)

    def test_all_supported_question_types(self):
        for kind in ('single', 'multiple', 'text'):
            data = packet()
            data['items'][0]['kind'] = kind
            if kind != 'text':
                data['items'][0]['options'] = ['one', 'two']
            self.assertIn('Response to Agent', generator.generate(data))


if __name__ == '__main__':
    unittest.main()
