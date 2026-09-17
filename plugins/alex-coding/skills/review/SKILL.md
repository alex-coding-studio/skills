---
name: review
description: "Independently review one named GitHub PR and follow it through merge, closure or a user-attention handoff. Start automatically for Implement or Plan when review is required, or resume a named PR. Exclude repository-wide discovery and author feedback handling."
---

# Review One Pull Request

Own independent review of one exact GitHub PR after it exists. Implement/Plan starts it automatically when required; reuse an assigned reviewer or human-owned path, never create a competing repository watcher. Preserve explicit read-only, human acceptance and merge restrictions.

## Start and inspect

1. Resolve the PR, current acceptance, cumulative review-round limit and independent reviewer identity. Read [runtime.md](references/runtime.md) and use `scripts/review_pr.py` to start/reuse that PR's runner. Missing execution capabilities are inactive review, not permission to replace the runtime or self-approve.
2. Select complexity by the runtime's model policy: regular Codex Sol / Claude Opus uses low, medium or high, capped at high; high-certainty bounded work may use Luna max / Sonnet max. Unclassified or security-sensitive work uses high. Record the reason in existing acceptance. The runner persists and explicitly passes the selection on start and resume, independently of author defaults; no silent fallback.
3. Verify PR identity, active process and startup evidence. Session identity appears after the first invocation; startup does not prove publication or approval. Waiting invokes no model and never uses scheduled wakeups.

The independent worker follows [worker.md](references/worker.md). Start with the diff, necessary surrounding code, affected callers and scenario assertions; expand for missing facts, dependencies or risks. Author diagnoses are leads to verify, not verdicts. Reuse trustworthy exact-revision gate evidence while assessing its coverage and limits. Direct work can map outcomes to existing test names without synthetic IDs. Gates and independent judgment are unchanged.

The runner publishes formal reviews and inline findings against the exact reviewed head, verifying writer and permission immediately before each write. Review authorizes neither implementation changes nor merge. For an explicitly one-shot/read-only request, inspect directly within those limits instead of starting the publishing runner.

## Continue and finish

Approval retains the same reviewer through CI and subsequent heads until merge/closure. New code requires current-head review. CI-only events do not consume a code-review round; successful CI on an unchanged passing review needs no new model invocation. New feedback, failures and code/base changes remain actionable.

On continuation, use the existing session, checkpoint and new evidence first. Incremental patches are starting points; full acceptance, patch and history remain accessible. Preserve resolved findings and revisit supporting code when changes or contradictions warrant it.

Rounds survive session replacement. `retry` only republishes the saved result. After explicit user authorization, Implement/Plan may call `continue --decision-file` for a fresh independent session, preserving findings and cumulative rounds. Old phase or pending publication does not block it. The runner replaces its verified process; the author never chooses the verdict. Otherwise publish findings and a handoff before stopping at the escalation boundary.

Author Monitor owns replies, follow-up Issues, fixes, merge and protected cleanup. Preserve legacy watchers' outstanding ownership/acknowledgement contracts through the runtime's migration procedure. Regression scenarios live in `evals/` for skill maintenance.
