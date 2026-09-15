---
name: review
description: "Watch and formally review repository Ready PRs when explicitly invoked or asked to monitor repository reviews. Exclude author feedback follow-up, one-shot reviews and retrospectives."
---

# Review Repository Pull Requests

Watch Ready PRs in the current repository and publish formal reviews against their exact heads. Explicit invocation authorizes publication; a read-only or do-not-publish request overrides it. This does not authorize implementation edits, merges or unrelated GitHub mutations.

## Start or resume

1. Resolve the current repository root and GitHub owner/repository from its remote. Verify the existing task identity and chosen reviewer login; ask only if the repository or reviewer identity is ambiguous.
2. Read [monitor.md](references/monitor.md) in Codex for the installed queue/IPC preflight, or [claude-monitor.md](references/claude-monitor.md) in Claude for the `Monitor` tool path. Either one carries the state identity, launch and acknowledgement contract. Reuse the existing watcher for this repository/task rather than creating a duplicate. Do not create a new task.
3. In Codex, start the watcher only after the required desktop wakeup capability is verified. In Claude, start it only through `Monitor` with `persistent: true`; background Bash notifies once on exit and loses every earlier event. Its first poll includes all existing Ready PRs that lack a handled claim or current-head approval from the configured reviewer. Drafts wait until Ready. On restart, retain claims and pending work.
4. Report the repository and whether monitoring actually started. Missing queue/IPC support in Codex, or an unavailable `Monitor` tool in Claude, means automatic review is inactive; explain the concrete limitation. Do not claim a background shell alone can wake this task.

## Review dispatched work

Read [review-batches.md](references/review-batches.md) when a review batch arrives or a manual review is requested under an active watcher. It defines acceptance checks, publication and acknowledgement, including head changes and publication failures. Runtime state transitions stay in the selected runtime reference; do not read the other runtime's instructions.

Review the current delivery's contract or settled direct acceptance with proportionate verification. Preserve the author/reviewer identity boundary and publish before acknowledging. Reuse a completed code review for CI-only events. Keep watching quietly until explicitly stopped; a single completed batch does not end the watcher.

Personal reflection is user-led. Retired milestone or Retro references do not activate this watcher or a replacement workflow.
