import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/alex-coding"


class PluginPackageTests(unittest.TestCase):
    def test_marketplaces_resolve_bundled_plugin_and_skill_entries(self):
        codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        for market in [codex, claude]:
            entry = next(p for p in market["plugins"] if p["name"] == "alex-coding")
            source = entry["source"]
            path = source["path"] if isinstance(source, dict) else source
            self.assertEqual((ROOT / path).resolve(), PLUGIN)
        for manifest in [".codex-plugin/plugin.json", ".claude-plugin/plugin.json"]:
            self.assertEqual(json.loads((PLUGIN / manifest).read_text())["name"], "alex-coding")
        for name in ["plan", "implement"]:
            skill = PLUGIN / "skills" / name / "SKILL.md"
            self.assertIn(f"name: {name}\n", skill.read_text())

    def test_skill_reference_closure_stays_inside_installable_plugin(self):
        for source in PLUGIN.rglob("*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", source.read_text()):
                path = target.split("#", 1)[0]
                if not path or "://" in path:
                    continue
                destination = (source.parent / path).resolve()
                self.assertTrue(destination.is_relative_to(PLUGIN), (source, target))
                self.assertTrue(destination.is_file(), (source, target))

    def test_public_plugin_has_no_machine_or_platform_plugin_dependencies(self):
        for source in PLUGIN.rglob("*"):
            if source.is_file():
                text = source.read_text()
                for private in ["/Users/", "/private/tmp/", "ios-dev-agent:"]:
                    self.assertNotIn(private, text, source)


if __name__ == "__main__":
    unittest.main()
