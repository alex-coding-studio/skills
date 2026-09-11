# Claude Author Listener Runtime

## Compatibility and activation

Requires Python 3 on macOS/Linux and authorized `gh` read access through `gh_as bot`. The listener reads GitHub under the explicit bot role, never under whichever account happens to be active, and a missing `gh_as` fails at startup rather than falling back. Delivery uses the Claude Code `Monitor` tool. Its documented framing is that stdout lines written within 200ms are batched into a single notification, so a multiline block emitted by one write arrives as one notification rather than one per line. This listener relies on that: `deliver` builds the whole batch as one string and issues exactly one `print`, which `test_the_whole_batch_is_written_by_one_stdout_call` pins. Observed on this installation: a batch of six events plus its header and instructions arrived as a single notification, three separate times. If a future runtime fragments a multiline write, that test still passes while delivery degrades, so re-check the tool contract before assuming the framing still holds. There is no desktop queue, no IPC snapshot adapter and no idle probe, because a `Monitor` notification arrives in the session's own conversation instead of being inserted into another task's input queue.

Start the runner only through `Monitor` with `persistent: true`. Background Bash notifies once on process exit, which silently loses every event before that exit. Never substitute a Scheduled task. If `Monitor` is unavailable, report that automatic follow-up is inactive and say why.

## One monitor per pull request

Codex and Claude both run one listener per PR. Codex listeners use the same desktop task as their delivery destination without sharing batches. Claude uses a separate `Monitor` task with its own notification stream, description and `TaskStop`. Each PR gets its own listener, state directory, batch and acknowledgement token. Two PRs never share a batch, and finishing one does not wait for the other.

Use the installed Skill's absolute script path. Every command takes `--session` and `--pr`. Run from the state directory, never from a checkout that cleanup may remove; the runner changes its own working directory to its state directory.

```sh
python3 <monitor>/scripts/claude_pr_monitor.py --session <stable-session-id> \
  --pr 'owner/repo#123' register --checkout <absolute-task-owned-checkout>
```

Then arm one `Monitor` per PR:

```sh
python3 -u <monitor>/scripts/claude_pr_monitor.py --session <stable-session-id> \
  --pr 'owner/repo#123' run --interval 45
```

Give that `Monitor` task a description naming this exact PR. A description covering several PRs is wrong here, because one listener follows one PR.

`--author <login>` is optional validation against GitHub's actual PR author, not an override. `register` is idempotent. Re-registering cannot change author or a bound checkout. A previously unbound target can acquire explicitly validated ownership metadata. Binding failures preserve feedback monitoring with unproven ownership; they never authorize cleanup. Registering without `--checkout` authorizes feedback monitoring only, not local cleanup.

`--session` is any stable identifier of letters, digits, dot, underscore or hyphen; reuse the same one for every PR in a session. Default state lives at `${CLAUDE_CONFIG_DIR:-~/.claude}/state/author-pr-monitor/<session>/<owner>__<repo>__<number>`. If using `--state-dir`, use the same absolute path on every command for that PR. The stored session and PR identity reject mismatched reuse.

`run.lock` is held on that PR's own directory, so a second listener for the same PR exits immediately saying it is already followed, while a listener for a different PR starts normally. Never point two PRs at one `--state-dir` to work around this.

`run` refuses to start before that PR is registered. `run --once` polls and can print a batch; it is not a dry run. Registration itself makes no GitHub writes and prints nothing. Initial polling includes all currently visible non-self feedback, not only feedback newer than registration.

## Event and acknowledgement contract

```sh
python3 <monitor>/scripts/claude_pr_monitor.py --session <id> --pr 'owner/repo#123' status
python3 <monitor>/scripts/claude_pr_monitor.py --session <id> --pr 'owner/repo#123' ack --token <exact-batch-token>
python3 <monitor>/scripts/claude_pr_monitor.py --session <id> --pr 'owner/repo#123' \
  claim --events <explicit-pending-event-key> <another-key>
```

Conversation comments, inline comments/replies and submitted reviews are paginated. Comment body/update revisions and formal review states produce distinct event versions; pending draft reviews are excluded. Initial all-green CI stays quiet; failures and later current-head CI terminal changes are meaningful events, including failure while another check still runs. Branch/local changes are not events. Filtering requires both the fixed author login and `🤖` anywhere in the body; the current reader identity and signature wording do not influence it.

The ledger distinguishes pending, delivered, handled and terminal-settled events. One printed batch contains at most 40 compact events from that one PR, and the batch's own `ack` command line is printed directly under the header, before the event rows, so a truncated notification loses re-fetchable detail rather than the required action. While a batch is delivered or being handled, polling continues and accumulates later events without printing again. Only a matching token acknowledges that batch's delivered set. Stale tokens fail without changing state; a new commit never acknowledges feedback. Manual `claim` requires explicit pending keys, refuses an existing active batch and returns its own token.

A restart preserves delivered claims, so it does not reprint unacknowledged work automatically. If a turn was interrupted, resume it and acknowledge its actual disposition. Because stdout delivery and acknowledgement are separate steps, a crash between printing and acknowledging leaves that batch delivered; inspect `status` and acknowledge its real disposition rather than assuming it was lost.

## Terminal handling

Closed-unmerged targets are preserved. They stop only after the terminal feedback batch is acknowledged and a final successful snapshot has no unhandled events. Other PRs have their own listeners and are unaffected. A reopened PR requires an explicit `reopen` and a running listener; old event history stays intact.

For merged targets, registration's explicit ownership metadata is passed to `postmerge_cleanup.py`, the same helper the Codex listener uses. It fetches and verifies that the merged content reached the default branch, either because the final PR head is an ancestor of it or because GitHub's reported merge commit is, which is what a squash or rebase merge leaves behind; an unproven head with no such merge commit is preserved. It then safely fast-forwards the primary default checkout, verifies its HEAD/tree, then removes the owned merged worktree and branch. A linked worktree follows the same default-sync requirement. If the owned worktree is already absent, a repeat still synchronizes lagging default state. Tracked changes, hidden index flags, detached/unrelated branches, locks, occupied checkouts and divergent primary state are preserved. Nonconflicting untracked or ignored primary files may remain during fast-forward; Git no-overwrite checks still block collisions. Git-ignored build outputs (`.build`, `.swiftpm`, Xcode project bundles, DerivedData and CI result bundles) are disposable as a whole. Their contents are not inspected. Tracked changes and other untracked/ignored user files remain protected. When the owned checkout is the primary checkout itself, there is no worktree to remove and the remaining deletion is `git branch -d`, which does not touch the working tree, so that case gates on tracked changes only: unrecognized untracked or ignored files no longer block synchronization and branch deletion, and they are left in place. A linked worktree keeps the strict check, because removing it would take those files with it. No fixed delay substitutes for fetch and commit verification; failed verification prevents deletion. Cleanup waits for any delivered batch to be acknowledged. The helper refuses to act while a process is working inside the checkout, which is the guard that replaces the Codex idle-desktop snapshot. Successful cleanup marks observed events `settled` with disposition `merged-cleanup`, not a fabricated acknowledgement, and stops that listener without printing another batch. Missing metadata, preservation or errors retain feedback and produce a terminal exception carried on the terminal event. An attempt marker is persisted before the helper runs; interrupted or failed attempts are not automatically retried. Inspect and resolve the concrete exception under existing authorization, then acknowledge its batch.

The process exits once its PR is stopped and no batch remains, which ends that `Monitor` watch and leaves every other PR's listener running. To stop earlier, use `TaskStop` on that exact monitor task; never use a user-wide process kill and never delete its event ledger. Resume with the same session and PR identity and state path.

Repeated identical retries go to `monitor.log` in that PR's state directory. Stdout carries only the first failure and the later recovery, so one outage wakes the session once rather than every interval.

## Publish authorized replies

Prepare the final body in a file, then use:

```sh
python3 <monitor>/scripts/claude_reply.py owner/repo 123 \
  --expected-login <verified-writer-login> --body-file <file>
python3 <monitor>/scripts/claude_reply.py owner/repo 123 \
  --expected-login <verified-writer-login> --body-file <file> --inline-comment <comment-id>
```

This helper appends `From Claude 🤖`, validates that an inline reply belongs to this PR, requires the expected writer to match the real PR author, and checks `gh auth status`, repository push permission and the actual API writer immediately before POST. It does not switch accounts, handle tokens or grant publication permission. Serialize writes with other Agent tasks using shared account state. If the write response is uncertain, inspect GitHub before retrying to avoid duplicate comments. Formal review publication follows the task's authorized review workflow; any Agent-authored text there also includes the marker.

## Complete after the Agent merges

Run the end action immediately after verifying a successful merge, from a directory outside the owned checkout:

```sh
python3 <monitor>/scripts/claude_pr_monitor.py --session <id> --pr 'owner/repo#123' complete
```

It reads the registered identity and fresh PR state, rejects a non-merged PR or an unacknowledged batch, and enters the same completion helper used by background merge detection. Safe success settles only this PR; every other PR's listener remains active. A repeat reports the existing completion. A recorded failed or interrupted attempt remains an exception rather than an automatic retry. Report a preserved or error outcome honestly; it is not complete local synchronization.

## Validation

Run `python3 -m unittest discover -s tests -p test_author_adapters.py -v` from the public skills repository.
