import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "plugins/alex-coding/skills/setup"


def normalized(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value.casefold())
    return re.sub(r"\s+", " ", value).strip()


def has_phrase(value: str, phrase: str) -> bool:
    value = normalized(value)
    phrase = normalized(phrase)
    if re.search(r"[\u4e00-\u9fff]", phrase):
        return phrase in value
    return f" {phrase} " in f" {value} "


def deterministic_trigger(value: str, config: dict) -> bool:
    for concept in config["fallback_positive_concepts"]:
        if not any(has_phrase(value, phrase) for phrase in config["positive_concepts"][concept]["phrases"]):
            return False
    return not any(
        spec.get("exclusive") and any(has_phrase(value, phrase) for phrase in spec["phrases"])
        for spec in config["negative_concepts"].values()
    )


class SetupSkillTests(unittest.TestCase):
    def test_package_carries_the_setup_contract_and_required_resources(self):
        skill = (SETUP / "SKILL.md").read_text()
        self.assertIn("name: setup", skill)
        self.assertIn("Create, align, or update", skill)
        for relative in [
            "references/operation.md",
            "references/technical-baseline.md",
            "references/delivery.md",
            "assets/ProjectContext.md",
            "assets/AGENTS.md",
            "assets/CLAUDE.md",
            "agents/interface.yaml",
            "agents/openai.yaml",
            "evals/trigger_cases.json",
            "evals/semantic_config.json",
            "evals/output/cases.jsonl",
            "manifest.json",
        ]:
            self.assertTrue((SETUP / relative).is_file(), relative)

    def test_trigger_cases_cover_setup_and_reject_neighboring_jobs(self):
        cases = json.loads((SETUP / "evals/trigger_cases.json").read_text())
        config = json.loads((SETUP / "evals/semantic_config.json").read_text())
        positive = {case["family"] for case in cases["should_trigger"]}
        negative = {case["family"] for case in cases["should_not_trigger"]}
        self.assertTrue({"create", "align", "reference", "dependency-add", "dependency-add-short", "dependency-remove-short", "dependency-update-zh", "dependency-update", "new-layer"} <= positive)
        self.assertTrue({"plan", "implement", "feature-create", "feature-export", "feature-package-noun", "feature-upgrade-word", "discussion-update", "discussion-package", "review", "discussion", "narrower-platform", "deploy"} <= negative)
        self.assertTrue(all(deterministic_trigger(case["text"], config) for case in cases["should_trigger"]))
        self.assertTrue(all(not deterministic_trigger(case["text"], config) for case in cases["should_not_trigger"]))

    def test_initial_delivery_exception_is_bounded_in_shared_policy(self):
        policy = (ROOT / "plugins/alex-coding/references/delivery-policy.md").read_text()
        self.assertIn("exactly one direct default-branch push", policy)
        self.assertIn("subsequent changes use the normal PR lifecycle", policy)
        self.assertIn("does not itself grant that exception", policy)
        setup_delivery = (SETUP / "references/delivery.md").read_text()
        self.assertIn("empty-tree-to-commit patch", setup_delivery)
        self.assertIn("This is not the bundled PR-only Review workflow", setup_delivery)
        self.assertIn("fresh review of that new SHA", setup_delivery)

    def test_output_cases_prove_runnable_delivery_and_boundaries(self):
        cases = [
            json.loads(line)
            for line in (SETUP / "evals/output/cases.jsonl").read_text().splitlines()
            if line.strip()
        ]
        self.assertEqual({case["id"] for case in cases}, {
            "create-runnable-baseline",
            "reference-technical-only",
            "dependency-separation",
            "version-update-transaction",
        })
        for case in cases:
            self.assertTrue(case["assertions"])
            self.assertEqual(case["human_review"]["expected_winner"], "with_skill")
        reference = next(case for case in cases if case["id"] == "reference-technical-only")
        self.assertIn("Do not copy Harvis business", reference["with_skill_output"])

        holdouts = [
            json.loads(line)
            for line in (SETUP / "evals/output/holdout_cases.jsonl").read_text().splitlines()
            if line.strip()
        ]
        self.assertEqual({case["id"] for case in holdouts}, {
            "align-preserves-authored-context",
            "machine-and-external-authority",
            "initial-ci-failure",
        })
        self.assertTrue(all(case["metadata"]["case_type"] == "holdout" for case in holdouts))


if __name__ == "__main__":
    unittest.main()
