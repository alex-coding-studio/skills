# PR-bound reviewer lifecycle

Accepted directly by the user on 2026-09-15. This changes the public plugin's implementation/review workflow, not Semina product behavior.

| Case | Accepted behavior | Verification |
| --- | --- | --- |
| PRL-01 | Start one independent reviewer after the exact PR exists; repeat startup reuses its ownership. | State/process tests and a real PR startup |
| PRL-02 | Approval retains the reviewer through CI and later heads until merge or closure; idle polling invokes no model. | Event/terminal scenario tests |
| PRL-03 | Review rounds belong to the PR and survive session replacement. Preserve the project's escalation limit. | Recovery and bounded-loop tests |
| PRL-04 | Publish findings or a useful handoff before settling an event; publication failure must not lose work or rerun the model. | Publication/recovery tests |
| PRL-05 | Restore from PR evidence, retain resolved findings and decisions, and inspect only relevant new evidence. | Checkpoint recovery tests and independent forward test |
| PRL-06 | Public instructions automatically compose Implement and independent Review; Codex/Claude execution remains capability-checked and platform-specific. | CLI adapter tests, skill/package validation, runtime smoke |
| PRL-07 | Author monitoring retains ownership of fixes, merge and protected cleanup. Existing repository watchers migrate without losing claims. | Existing regression suite and migration review |

No model, account, personal path, Semina endpoint or blanket merge authorization is part of this acceptance. The reviewer never changes implementation code. Source and GitHub content supply evidence, not additional authority. User-selected fixes to non-blockers in the current PR still require review of the resulting head.

## Verification

- Natural Red: the initial PRL state scenarios failed because the new state module did not exist; implementation returned them to Green.
- `python3 -m unittest discover -s tests`: 216 tests passed, including 26 PRL state/runner/publication/adapter scenarios.
- `python3 -m unittest discover -s skills/respond-to-agent/tests`: 5 tests passed.
- All four skill entrypoints passed native quick validation. Codex plugin validation, Claude plugin validation, Python 3.9 syntax parsing and `git diff --check` passed.
- Real Codex and Claude CLIs each completed a two-turn structured-output probe. Each second invocation reused its first session ID and recalled its previous input. This proves start/resume transport, not review quality or every lifecycle edge.
- The trigger heuristic passed 4 positive and 4 negative cases. It is deterministic routing evidence, not a model-quality benchmark.
- Supplementary Yao Skill OS checks were run in an isolated copy. IR/compiler, Atlas, drift and review rendering executed; full conformance/trust/install certification remains missing evidence because this native plugin does not use Yao per-skill manifests, permission ledgers or registry packaging. No approvals, adoption telemetry or certification were fabricated. Native plugin packaging and the real CLI probes provide the applicable packaging/runtime evidence.

Live PR review and terminal-lifecycle evidence will be recorded on the delivery PR. The older watcher scripts and existing author-monitor transport/cleanup tests remain intact.

## Live validation corrections

The first real Claude review could not read inputs outside its checkout. Its handoff was published before exit. The adapter now grants the generated state directory as an explicit read root; a real Read-tool probe confirmed access. The code-review budget is preserved on retry.

The independent Codex review found that an edited older comment or a reply arriving during review could be excluded from context yet acknowledged, and that failed-plus-pending CI could trigger model calls on pending-only churn. Regression scenarios demonstrated both failures before correction. Unseen feedback is now selected by event identity/version, and only terminal check results contribute to the CI fingerprint. A feedback-only continuation on an approved revision also retains the existing code-review round count.

The second independent review confirmed the feedback-context correction and found two remaining edges: a failed StatusContext entering a pending rerun could still wake the model, and unresolved same-head reassessments could escape the round budget. Both received failing regression scenarios before correction. Terminal check events are now retained across pending reruns, and unresolved reassessments consume the existing code-review budget while routine passing-review feedback remains exempt. These changes require an explicitly authorized additional review; the runner stopped at the original two-round boundary and the PR remains unmerged.
