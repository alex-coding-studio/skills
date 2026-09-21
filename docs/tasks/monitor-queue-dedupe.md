# Codex author Monitor queue deduplication

Accepted directly in the 2026-09-20 discussion: keep direct `codex queue`
delivery and do not restore desktop busy/idle probing. Prevent duplicate or
self-generated author notifications from accumulating while the owning task is
already working.

| Case | Required behavior | Evidence |
| --- | --- | --- |
| QD-01 | One accepted Codex feedback batch blocks later queue submissions until the owning Agent acknowledges that batch. | Queue receipt state tests |
| QD-02 | Feedback discovered behind the active batch remains pending and is delivered after acknowledgement. | Multi-event queue test |
| QD-03 | An author-marked inline reply and its empty GitHub `COMMENTED` review shell are both ignored as self echoes. | PR #76-shaped snapshot test |
| QD-04 | Same-account human feedback without the robot marker remains actionable. | Conservative echo-filter test |
| QD-05 | Direct queue delivery, submission retry, legacy claims, Claude acknowledgement and model-free disposable cleanup remain available. | Existing adapter and Monitor regression suites |

Unit tests establish event-ledger and GitHub-object behavior. They do not prove
the desktop UI presentation or exactly-once delivery across an uncertain
external queue timeout. A live task-owned PR exercises the installed queue path.

## Verification before PR review

`QD-01` and `QD-03` failed naturally against the previous implementation:
the second batch entered the queue while the first was active, and the empty
author `COMMENTED` review shell remained visible after its robot-marked inline
reply was filtered. After the change:

- `python3 -m unittest discover -s tests -v`: 299 tests passed;
- `python3 -m unittest discover -s skills/respond-to-agent/tests -v`: 5 tests passed;
- Codex plugin validation and Monitor skill quick validation passed;
- all Python sources parsed with the Python 3.9 grammar;
- `git diff --check` passed.

The plugin version is `0.8.1`, with a refreshed Codex cachebuster so the merged
behavior can be installed instead of remaining behind an unchanged cache key.
