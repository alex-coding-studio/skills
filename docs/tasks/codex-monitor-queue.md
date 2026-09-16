# Codex author Monitor queue delivery

Accepted directly in the 2026-09-15 discussion: Monitor submits PR events to the host queue. The host and Agent own scheduling and processing. Do not inspect desktop busy/idle state, wait for an Agent receipt before sending later events, or implement a five-minute withdrawal. Preserve failed submissions for retry and report unavailable delivery. Claude's working native Monitor path is outside this behavior change.

| Case | Required behavior | Evidence |
| --- | --- | --- |
| CQ-01 | Default Codex startup and delivery never call the desktop idle probe. | Entrypoint and transport tests; real task delivery |
| CQ-02 | Queue acceptance settles delivery only; later batches can enqueue before Agent processing. | Multi-batch, restart and failure scenarios |
| CQ-03 | Submission failures preserve events for retry; accepted event versions do not resend on normal polls. | Failure/retry and event-version tests |
| CQ-04 | Codex performs no background checkout cleanup. Terminal delivery can stop the listener; the author invokes protected completion after verified merge. | Terminal and completion scenarios |
| CQ-05 | Claude acknowledgement behavior, existing ownership and old in-flight batches remain intact. | Existing regression suite and compatibility scenarios |

This changes the public plugin and the shared instruction wording. Independent PR review, GitHub identities, accepted-scope handling and protected cleanup checks remain required. Queue acceptance is not proof that the Agent has processed feedback. A crash or timeout after uncertain acceptance can duplicate a delivery; stable event versions let the recipient recognize already-handled work. No exactly-once claim is made.

## Verification before PR review

The six initial CQ scenarios failed naturally against the previous implementation. After the change, all eight new queue-receipt scenarios and the existing regression suite pass: `python3 -m unittest discover -s tests` reports 224 tests. Existing tests were updated only where the accepted default behavior changed. Native skill/plugin validation and `git diff --check` passed. The deterministic trigger cases pass; they are routing checks, not a model-quality benchmark.

Real native queue delivery will be exercised by this delivery's PR feedback. GitHub writes still use role verification, and author actions remain within the accepted scope regardless of when a queued notification is processed.
