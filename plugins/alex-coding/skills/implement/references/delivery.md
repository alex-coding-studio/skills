# Compact delivery operations

Use `scripts/delivery.py` from the installed Implement skill to start the PR's single runner. It creates no extra ledger and does not change repository gates, review requirements, round limits, identities or human acceptance. Use existing direct procedures for project-assigned reviewers, explicit review exemptions, Draft PRs or non-default target branches. The helper never merges a reviewed PR.

The PR description is the only acceptance and evidence record, and the reviewer reads it directly; do not export a separate acceptance file. Use this short template, written in the language the project's human-facing records require:

1. What changed.
2. Why: the request, Issue or Contract it fulfils.
3. Checks: which gates and tests ran, with the exact head they ran on.
4. Limits and human acceptance: what remains unverified, and the status of any required human or UI acceptance.

A Contract delivery keeps its clause → case → test mapping table in the description. Add one sentence giving the reason for the chosen [review complexity](../../review/references/runtime.md#model-and-effort-policy). Do not include private reasoning or a suggested verdict. When later commits change the evidence, edit the description; the reviewer rereads it on every invocation.

After committed, pushed changes, passing unchanged repository gates (in a CI project, CI runs them after the PR opens: do not run local tests or polish the description first, and add results to the description afterwards) and, for UI work, either the user's UI acceptance or their batch authorization to accept after delivery (opening the PR needs no separate approval):

```sh
python3 <implement>/scripts/delivery.py open --runtime codex --session <existing-task-uuid> \
  --repository owner/repo --checkout <owned-checkout> --title 'Concrete outcome' \
  --body-file <pr-body> --reviewer <verified-admin-login> \
  --complexity medium --max-rounds 3 --review-runtime codex
```

`open` verifies the bot writer/push permission and committed remote work-branch head, creates a ready PR targeting the remote default, or reuses the matching existing bot-authored PR. If a write response is uncertain, reconcile the remote PR before retrying. `start` takes `--pr owner/repo#123` instead of repository/title/body and attaches to an already opened PR. Both start or reuse one `review_pr.py` runner for the PR: it reviews independently, delivers author feedback to this session and, after merge, synchronizes the default checkout and disposes of the registered owned checkout. The author ledger lives in the runner's state directory under `author/`. `--review-runtime` selects the reviewer CLI; without it the PR head's `.ci/config.json` `review_runtime` (`codex` or `claude`) applies, and only then the author's runtime. When the selected CLI is unavailable the reviewer is reported inactive; no other runtime is substituted. A Claude Project thread or Codex worker in a pool slot passes `--slot <slot-path>` instead of `--checkout`; see `alex-coding:project-monitor`. A pool slot passed as `--checkout` is refused with a nonzero exit before anything is created or registered. Pass the project's actual review-round limit. `--acceptance-file` is only for an acceptance source that cannot live in the PR description, such as a planning PR's frozen source evidence. A PR already registered with a standalone Monitor before this version, or covered by a declared review exemption, keeps the standalone Monitor path below.

When the PR's runner has stopped and another session must take over the PR (a replaced worker, a lost session, or a PR opened with `--checkout <slot>` by a version before 0.9.16), repeat `start` from the new session with `--takeover` and the new `--checkout` or `--slot`. The helper refuses while the previous runner holds the PR's lock or its runner or review-worker PID is alive, and without `--takeover` a different session, checkout or slot is still refused. Takeover rebinds the same author ledger to the new session and checkout or slot, keeps its events, review rounds, published findings and approved fingerprint, records the change under `takeovers` in both the runner state and the author ledger, and starts the runner again. It never deletes state or releases the previous slot; tell the coordinator about a previous slot that is still held. A PR followed by a standalone Monitor has no takeover entry.

For Codex the helper launches the runner with disconnected stdin and verifies its lock and PID. If the host supplies an explicit persistent endpoint, pass `--session-remote`; never invent one. Queue acceptance and reviewer publication remain distinct from startup.

For Claude use `--runtime claude --session <existing-session-id>`. When the execution host supplies an explicit persistent endpoint, pass `--session-remote`; the helper binds it and launches the runner the same way it does for Codex. Never invent one. Without a bound endpoint the receipt says `native-monitor-required`: start its `monitor_command` (the runner itself, whose stdout carries only author deliveries) through the native `Monitor` tool, then repeat `start` with the returned exact PR identity to confirm it is active. No background Bash substitute is used. An unavailable Monitor remains a reported limitation. Deliveries carry the complete current PR state and need no acknowledgement; see Monitor's [feedback handling](../../monitor/references/feedback-and-completion.md).

Read the compact receipt. `started` establishes active processes, not approval or completed event delivery. An occupied lock without verifiable startup, inactive reviewer, attention gate or failed step is a reported exception. Inspect the retained state/log for that exact PR; do not repeatedly call status during quiet waiting, launch another owner or erase state to retry.

For a user-authorized fresh review, use Review's [`continue --decision-file`](../../review/references/runtime.md#continue-after-user-intervention) directly. Repeating this helper's `start` only reuses the existing reviewer. The continuation entrypoint replaces its verified process/session and retains previous findings without requiring a failed publication to succeed first.

## Merge and cleanup

The repository's `.github/workflows/auto-merge.yml` is the only merge path for reviewed PRs. It runs when an approving review is submitted, waits for the other workflow runs on the approved commit, and merges only when that commit is still the head and every other check passed (no other checks also passes); otherwise it comments on the PR and leaves it open. The author does not merge: handle feedback, create required follow-up Issues and satisfy project/human acceptance before the independent approval, except UI acceptance the user explicitly authorized for after delivery, which stays pending without blocking approval or merge (acceptance without that authorization still applies), then end the turn. After the merge, the PR's runner synchronizes the default checkout and disposes of the owned worktree on its own; Monitor's per-PR `complete` remains for standalone registrations. A repository with `.ci/config.json` at the PR head is a CI project: `ios-plan` and `ios-unit` must each be present on that head with a `SUCCESS` conclusion, and a missing, pending, cancelled, skipped or timed-out required check is not passing. In a CI project the PR's runner also merges the approved head itself once those checks pass, and keeps waiting while they are pending; a failed result reaches the author as a CI event. The repository's own gate stays in force because a private repository may have no required checks. A repository without that workflow or CI has no Agent merge path: report the approved PR as waiting for a human merge or for the workflow to be added.

## Declared review exemptions

A repository may waive independent review for version/pin bumps and text-only changes by declaring it in the `.shared-config` at its repository root:

```sh
review_exempt="pin text"
```

`pin` covers existing lockfiles (`Package.resolved`, `Podfile.lock`, `package-lock.json` and similar) and `.yml`, `.yaml`, `.xcconfig`, `.toml` or `.pbxproj` files whose every changed line sets a version or pin key (`MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`, `exactVersion`, `revision`, `version`). `text` covers `.md`, `.markdown`, `.txt` and `.rst` documents, including added, removed or renamed-from-text files. A PR is `review-exempt` only when every file falls into a declared kind; any other file, line or omitted patch is `review-required`. The declaration is read from the PR's base commit, so a PR never exempts itself.

`open` and `start` run this check after registering Monitor. A `review-exempt` receipt means no reviewer was started; merge once checks pass:

```sh
python3 <implement>/scripts/delivery.py pin-merge --pr owner/repo#123 \
  --expected-head <full-head-sha> --merge-method merge
```

It rechecks the current head, requires a ready open PR at that head, passing or absent checks (a CI project's required checks must all succeed), clean mergeability and admin push permission, and merges with a matching-head guard. Then run the registered Monitor's `complete`. A new commit is reclassified on the next `pin-merge`; a head that is no longer exempt needs `start` to launch the reviewer. Threads that do not use `open`/`start` run `delivery.py pin-check --pr owner/repo#123` themselves before starting Review.

Preserved/error cleanup stays an explicit exception and is never described as completed or blindly retried. Closed-unmerged PRs keep local work. Other PR listeners and ledgers remain untouched.

### Coordinator-approved mechanical changes and pending CI

The default remains independent review and passing CI, except for the base revision's existing `pin`/`text` declarations. For purely mechanical changes explicitly approved by Alex (moves, deletions or straightforward interface narrowing), a coordinator or human may apply `ci-skip-approved` after the local repository hooks pass. The label also approves exemption from independent review for source changes that do not fit `pin`/`text`. It is not authorization for behavioral changes or Setup. The author and script never add this label.

`pin-check` recognizes the label and reports `review-exempt` with `exemption: coordinator-approved-mechanical` when the declared exemptions do not already cover the PR. `open`/`start` then register only Monitor, without starting an independent reviewer. Since a newly created PR cannot already have a coordinator-applied label, the mechanical path is to create the ready PR using the normal author identity, report its exact head and successful hooks to the coordinator, wait for the coordinator to add the label, then call `delivery.py start` with the normal runtime/session/checkout (or slot) arguments. Do not call `open` before the label if the intent is to avoid reviewer startup: without a label it follows the unchanged review path. A labeled PR with an existing active reviewer runner is refused rather than creating a competing Monitor; retain that review path or stop the existing runner through its owning workflow before registering Monitor. Keep its state and review rounds.

The merge additionally requires the existing explicit flag; no new coordinator flag is needed:

```sh
python3 <implement>/scripts/delivery.py pin-merge --pr owner/repo#123 \
  --expected-head <full-head-sha> --merge-method merge --allow-pending-ci
```

For a source PR exempted only by the coordinator label, both label and flag are mandatory even when CI has already passed or is absent. Without them, source changes still need independent review. Declared pin/text merges without the flag retain their existing behavior and receipts.

Both the explicit flag and label waive CI waiting. A missing required check alone does not activate a pending-CI merge: at least one queued/running check or pending status must be present. In this coordinator mode every completed check must be `SUCCESS`, including when no other check is pending; status contexts must be `SUCCESS`, `PENDING` or `EXPECTED`. Failures, cancellations, timeouts, action-required, neutral, skipped and unknown terminal results refuse the exception. The expected Ready head, role-aware admin identity/push permission and GitHub mergeability/protection checks remain enforced. The label and Ready head are rechecked immediately before every coordinator-mode merge, including passing/absent-CI merges. The flag never enables `--admin`; report branch-protection errors without bypassing them. It remains available only to `pin-merge`, not `open`, `start` or `pin-check`.

After a confirmed coordinator-mode merge, the helper requests cancellation only for unfinished workflow runs matching the PR's exact head SHA, head branch and head repository. The JSON receipt includes `exemption: coordinator-approved-mechanical`, `approval_label: ci-skip-approved`, `head`, `merged_without_waiting_for_ci: true`, the explicit audit message `协调者批准的机械改动：免独立审查、未等 CI 合并`, `cancel_requested_run_ids` and `cancel_errors`. Cancellation errors retain the confirmed `status: merged` and identify the remaining work; an accepted cancellation request does not prove the run has stopped. Do not repeat the merge to repair cancellation errors. Refetch those exact runs before retrying cancellation, then run the registered Monitor's `complete` for cleanup or pool release. Merges outside coordinator mode keep their existing receipt and do not cancel runs.
