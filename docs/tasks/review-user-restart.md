# User-authorized fresh review

Accepted directly on 2026-09-16. The user wants a lightweight review workflow: after explicitly approving another review, Implement can request a fresh independent reviewer even when the previous result could not be published. This request changes the public plugin; it does not authorize publishing the retained Harvis review or modifying its state.

## Acceptance

- Existing `continue --decision-file` starts a new independent session for an open PR without requiring an old pending result to publish. Retain previous findings, decisions and cumulative rounds as evidence; do not convert an old verdict into approval of the new request.
- An active owned runner is stopped before replacement. Missing user authorization, unsafe process ownership, unavailable execution or a closed/merged PR must preserve existing work. No concurrent reviewer or author self-approval is introduced.
- `retry` keeps its existing meaning: publish the saved result without another model invocation. Explicit fresh review and transport retry remain distinct.
- Check inline coordinates against the reviewed diff. Keep valid comments inline; move invalid/unavailable locations into the review body without dropping findings or changing the verdict.
- Keep the existing commands and state schema. Update Implement/Review instructions so the author can perform the authorized request without manually editing lifecycle state.

## Verification

- Natural Red reproduced the old pending-publication gate and invalid inline publication in `tests/test_pr_review_recovery.py` before implementation.
- `test_failed_publication_does_not_block_user_authorized_fresh_review` verifies a new independent invocation with the original finding and cumulative rounds preserved; interrupted execution and settled approval have separate recovery scenarios.
- Active-runner tests include a real local subprocess holding the PR lock: replacement waits for termination and lock release. Unrelated processes, missing decisions, unavailable execution and closed/merged PRs preserve the prior request.
- Inline scenarios cover invalid, valid LEFT/RIGHT, renamed/deleted and unavailable-diff locations while preserving the original result and verdict.
- `python3 -m unittest discover -s tests`: 256 tests passed. `python3 -m unittest discover -s skills/respond-to-agent/tests`: 5 tests passed.
- Native plugin and changed-skill validation passed. `git diff --check` passed.
- No live Harvis state or review was modified. The process scenario proves local ownership/termination; GitHub publication is verified with controlled adapter responses, not a new Harvis review. Independent review of this delivery is required before merge.
