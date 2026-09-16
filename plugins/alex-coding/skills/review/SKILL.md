---
name: review
description: "Independently review one named GitHub PR and follow it through merge, closure or a user-attention handoff. Start automatically for Implement or Plan when review is required, or resume a named PR. Exclude repository-wide discovery and author feedback handling."
---

# Review One Pull Request

Own independent review of one exact PR. Start after the PR exists; never prelaunch a repository watcher. Implement and Plan invoke this workflow automatically when independent review is required, unless the project already assigns this PR to another reviewer or explicitly requires a human-owned path. Do not ask the user to start a review session as a routine step.

## Start or continue

1. Resolve the exact GitHub PR, current acceptance, project review-round limit and configured reviewer identity. A missing PR number is not permission to scan and review the repository. Preserve existing UI acceptance, read-only and merge restrictions.
2. Read [runtime.md](references/runtime.md). Use its PR-bound runner to create an independent Codex or Claude review session, or reuse the existing owner. The runner verifies capabilities and owns waiting; a shell that only polls cannot supply reviewer execution. Report unavailable capabilities or failed startup as inactive.
3. Verify the exact PR, running process and startup evidence. A session identifier is reported after the first model invocation. Approval retains the same reviewer through CI and subsequent heads. Quiet waiting invokes no model and does not use scheduled model wakeups.

The independent worker follows [worker.md](references/worker.md), using current project instructions and the contract or settled direct acceptance bound to this PR. The author does not supply a verdict or impersonate independent judgment with another account. Formal reviews and inline findings are published against the exact reviewed head; the runner verifies the writer and repository permission immediately before each write. Review does not authorize implementation changes or merge.

## Finish and recover

Normal reviewer execution ends only after verified merge or closure. Keep the existing PR round limit; CI-only checks do not consume a code-review round. Replacing a session does not reset the PR's cumulative rounds. New code, including user-selected non-blocker fixes, requires a current-head review.

At the project's escalation boundary, publish the findings and a useful PR handoff before exiting. Preserve established facts, resolved findings, evidence locations, unresolved disagreements and the next action after a user decision. Recover from the latest published checkpoint and subsequent events; read older history or code when changed evidence requires it. Do not require a replacement reviewer to reconstruct the previous conversation.

Publication failure preserves the exact pending result and stops automatic model replay. An explicit continuation after user intervention can create a new independent session while retaining the PR's progress and recording any authorized round extension. Author Monitor retains ownership of author replies, follow-up Issues, merge and protected checkout cleanup.

For an explicit one-shot or read-only request, inspect the named PR directly under those limits; do not start the publishing runner. Existing repository watchers use the [migration procedure](references/runtime.md#legacy-repository-watchers); their state is never silently reset or assigned to a new PR worker.
