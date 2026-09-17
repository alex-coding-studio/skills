# Compact delivery operations

Use `scripts/delivery.py` from the installed Implement skill to compose the existing bundled Monitor and Review runners. It creates no third ledger and does not change repository gates, review requirements, round limits, identities or human acceptance. Use existing direct procedures for project-assigned reviewers, explicit review exemptions, Draft PRs or non-default target branches. The helper is not merge authorization.

Keep one acceptance/evidence record in the existing task or PR. Export it to a local UTF-8 file for the reviewer; include the scope, sources, actual revision-bound checks, remaining limits, human decisions and the reason for the chosen [review complexity](../../review/references/runtime.md#model-and-effort-policy). Do not include private reasoning or a suggested verdict. The PR body can be that same file when appropriate.

After committed, pushed changes, passing unchanged repository gates and any required human UI acceptance:

```sh
python3 <implement>/scripts/delivery.py open --runtime codex --session <existing-task-uuid> \
  --repository owner/repo --checkout <owned-checkout> --title 'Concrete outcome' \
  --body-file <pr-body> --acceptance-file <accepted-scope> --reviewer <verified-admin-login> \
  --complexity medium --max-rounds 2
```

`open` verifies the bot writer/push permission and committed remote work-branch head, creates a ready PR targeting the remote default, or reuses the matching existing bot-authored PR. If a write response is uncertain, reconcile the remote PR before retrying. `start` takes `--pr owner/repo#123` instead of repository/title/body and attaches to an already opened PR. Both register the owned checkout, reuse a verified monitor and start/reuse the exact independent reviewer. Pass the project's actual review-round limit.

For Codex the helper starts the queue listener with disconnected stdin, checks its lock, PID, command and startup log, then launches Review. If the host supplies an explicit persistent endpoint, pass `--session-remote`; never invent one. Queue acceptance and reviewer publication remain distinct from startup.

For Claude use `--runtime claude --session <existing-session-id>`. When the receipt says `native-monitor-required`, start its `monitor_command` through the native `Monitor` tool with `persistent: true`, then repeat `start` with the returned exact PR identity. No background Bash substitute is used. An unavailable Monitor remains a reported limitation. Claude's exact-batch acknowledgements stay mandatory; Codex's queue receipts do not add an acknowledgement gate.

Read the compact receipt. `started` establishes active processes, not approval or completed event delivery. An occupied lock without verifiable startup, inactive reviewer, attention gate or failed step is a reported exception. Inspect the retained state/log for that exact PR; do not repeatedly call status during quiet waiting, launch another owner or erase state to retry.

For a user-authorized fresh review, use Review's [`continue --decision-file`](../../review/references/runtime.md#continue-after-user-intervention) directly. Repeating this helper's `start` only reuses the existing reviewer. The continuation entrypoint replaces its verified process/session and retains previous findings without requiring a failed publication to succeed first.

Once the author has handled feedback, created required follow-up Issues, satisfied human/project acceptance, verified all declared gates, and has existing authorization to merge:

```sh
python3 <implement>/scripts/delivery.py finish --runtime codex --session <existing-task-uuid> \
  --pr owner/repo#123 --expected-head <full-reviewed-head-sha> \
  --merge-method squash --feedback-settled
```

Select the project's authorized merge method. `--feedback-settled` records the author's actual disposition of feedback; it is not a new user approval request or permission to ignore comments. The helper freshly checks the unchanged reviewed head/base, current independent approval, new feedback, check results, blocking reviews, mergeability and actual admin writer/push permission. GitHub still enforces its own protections; the merge uses a matching-head guard and no admin bypass. It then verifies the merge and calls the existing per-PR Monitor `complete` from outside the checkout. Local gate evidence and human decisions remain author/reviewer responsibilities; an empty CI list does not prove them.

If another actor already merged the PR, `finish` only verifies the registered target and invokes protected completion. Preserved/error cleanup stays an explicit exception and is never described as completed or blindly retried. Closed-unmerged PRs keep local work. Other PR listeners and ledgers remain untouched.
