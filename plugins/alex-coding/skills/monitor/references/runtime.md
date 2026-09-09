# Codex Author Listener Runtime

## Compatibility and activation

Requires Python 3 on macOS/Linux, authorized `gh` read access through `gh_as bot`, and a local Codex desktop supporting `codex queue` and the verified IPC snapshot adapter. The shared adapter is `alex-coding/scripts/codex_desktop_transport.py`; both reviewer and author listeners use it. It validates an owned socket and snapshot version 11, uses an eight-second read deadline and only queues into an explicitly idle existing task. Active, unloaded or unknown task states defer events locally. It is a version-bound adapter, not a public stable API or an OS wake service.

Before first use on an installation, verify the chosen executable's `queue --help` and evidence that its queue wakes this same desktop task. A successful CLI send alone is insufficient. Do not create another task or launch an app-server as a workaround. Do not send a synthetic live queue message without authorization. Reuse current verified installation evidence; if unavailable, explain the limitation before claiming the listener is active. The runner additionally probes queue capability and IPC before its startup log.

## One monitor per pull request

Use the installed Skill's absolute script path. Every command identifies both the existing task and the one PR. Run from the state directory or plugin directory, never from a checkout that cleanup may remove; the runner changes its own working directory to its state directory.

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <existing-uuid> --pr 'owner/repo#123' \
  register --checkout <absolute-task-owned-checkout>
python3 <monitor>/scripts/codex_pr_monitor.py --thread <existing-uuid> --pr 'owner/repo#123' \
  run --codex <verified-executable> --interval 45
```

A PR URL can replace `owner/repo#123`. `--author <login>` on registration validates GitHub's real PR author; it never overrides that identity. Re-registering the same task/PR is idempotent and cannot replace its author or bound checkout. Each additional PR gets a separate process and state directory, not another target on this listener.

Default state lives below `${CODEX_HOME:-~/.codex}/state/author-pr-monitor/<uuid>/` in a PR-specific hashed directory. State binds the task and canonical PR identity, contains exactly one target, and rejects a different PR even with the same explicit `--state-dir`. Use the same state path on registration, acknowledgement and completion. The per-PR lifetime lock prevents duplicate runners sharing that state. Choosing a different state directory creates an independent instance; never do so to bypass a lock.

After registration, launch a detached process with stdin disconnected and stdout/stderr redirected to that PR's local log. Capture its PID and verify the startup log and running process before saying it is active. Reuse an existing matching task/PR runner. Starting or stopping another PR must not affect this one. No login service or scheduled heartbeat is installed.

`run --once` can enqueue work and is not a dry run. Initial polling includes visible non-self feedback. Registration itself makes no GitHub writes and does not enqueue.

## Migrate old task-scoped state

Do not silently abandon a legacy task-level event ledger. Stop the old task-wide runner by verified PID before migration. Keep the old plugin/script accessible until its outstanding batches are acknowledged. Resolve any outstanding delivered batch using that original helper and its acknowledgement contract before upgrading/removing the old cache; old queued messages cannot be retracted or safely assigned new tokens. If the old helper is already unavailable, restore that verified version for acknowledgement rather than editing the ledger by hand.

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' \
  migrate --from-state <old-task-state-directory>
```

Migration locks the old runner/state, verifies task and PR identity, refuses outstanding batch/delivered claims, and copies only this PR's existing event, ownership and cleanup state into an absent per-PR destination. The source stays unchanged. Repeat explicitly for other PRs, then start the separate runners. Never reset delivered events to pending or overwrite a populated destination. Ordinary registration detects this PR in the legacy default state and requires migration instead of replaying from empty state; custom legacy state paths must be identified explicitly.

## Event and acknowledgement contract

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' status
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' ack --token <exact-batch-token>
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' \
  claim --events <explicit-pending-event-key> <another-key>
```

Conversation comments, inline comments/replies and submitted reviews are paginated. Comment body/update revisions and formal review states produce distinct event versions; pending draft reviews are excluded. Initial all-green CI stays quiet; failures and later current-head CI terminal changes are meaningful events, including failure while another check still runs. Branch/local changes are not events. Filtering requires both fixed author login and `🤖` anywhere in the body; current reader identity and signature wording do not influence it.

The ledger distinguishes pending, delivered, handled and terminal-settled events. One queue batch contains at most 40 compact events for this PR only. Its token cannot acknowledge another PR's batch. A delivered batch blocks only this listener's next batch; other PR listeners remain eligible for delivery. While it is queued or being handled, polling continues and accumulates later events without further model calls. Only a matching token acknowledges that batch's delivered set. Stale tokens fail without changing state; a new commit never acknowledges feedback. Manual `claim` requires explicit pending keys, refuses an existing active batch and returns its own token.

Queue/IPC failures retain pending work. A restart preserves delivered claims, so it does not replay unacknowledged work automatically. If a turn was interrupted, resume it and acknowledge its actual disposition. A lost acknowledgement after a successful external queue insertion can still cause a duplicate after a crash; exactly-once external delivery is not claimed. The idle check and enqueue are not atomic. Independent PR listeners can both observe idle and queue separate messages to the same task, and a new user turn can delay them. This does not merge their batches or acknowledgement state. No global in-flight acknowledgement barrier is added. Existing queued messages cannot be retracted.

## Terminal handling

Closed-unmerged targets are preserved. They stop only after the terminal feedback batch is acknowledged and a final successful snapshot has no unhandled events. Other targets keep polling. A reopened PR requires explicit `--pr 'owner/repo#123' reopen` and ensuring the runner is active; old event history stays intact.

For merged targets, registration's explicit ownership metadata is passed to `postmerge_cleanup.py`. The helper fetches and verifies merge ancestry, safely fast-forwards the primary default checkout, verifies its HEAD/tree, then removes the owned merged worktree and branch. A linked worktree follows the same default-sync requirement. If the owned worktree is already absent, a repeat still synchronizes lagging default state. Dirty, detached, unrelated-branch, locked, occupied or diverged primary state is preserved. Regenerable caches such as `__pycache__` do not count as dirty; any other ignored file still preserves the checkout, and the preserved reason names what blocked it. No fixed delay substitutes for fetch and commit verification; failed verification prevents deletion. Cleanup waits for this PR's delivered batch to be acknowledged and requires a fresh idle desktop snapshot immediately before invoking the helper. Busy tasks defer cleanup without queueing a normal merged event. Successful cleanup marks observed events `settled` with disposition `merged-cleanup`, not a fabricated user acknowledgement, and stops that target without queueing another turn. Missing metadata, preservation or errors retain feedback and produce a terminal exception. An attempt marker is persisted before the helper runs; interrupted/failed attempts are not automatically retried. Inspect and resolve the concrete exception under existing authorization, then acknowledge its batch. The idle check and cleanup cannot be atomic with new user activity; the helper also rechecks Git state and refuses any process working inside the checkout. Dormant tasks without such a process remain outside that physical guard. No generic cleanup script runs on closed-unmerged targets.

The process exits once its own PR is stopped and its batch is settled. Other PRs' state and processes remain unchanged. To stop earlier, check `run.pid` against the actual script/task arguments, then terminate that process only. Never kill all Python/Codex processes or delete its event ledger. Resume with the same identity and state path.

## Publish authorized replies

Prepare the final body in a file, then use:

```sh
python3 <monitor>/scripts/reply.py owner/repo 123 \
  --expected-login <verified-writer-login> --body-file <file>
python3 <monitor>/scripts/reply.py owner/repo 123 \
  --expected-login <verified-writer-login> --body-file <file> --inline-comment <comment-id>
```

This helper appends `From Codex 🤖`, validates that an inline reply belongs to this PR, requires the expected writer to match the real PR author, and checks `gh auth status`, repository push permission and the actual API writer immediately before POST. It does not switch accounts, handle tokens or grant publication permission. Serialize writes with other Agent tasks using shared account state. If the write response is uncertain, inspect GitHub before retrying to avoid duplicate comments. Formal review publication follows the task's authorized review workflow; any Agent-authored text there also includes the marker.

## Complete after the Agent merges

Run this monitor end action immediately after verifying a successful merge, from the state directory or another directory outside the owned checkout:

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' complete
```

It reads the registered identity and fresh PR state, rejects a non-merged PR or an unacknowledged batch, and enters the same completion helper used by background merge detection. Because this is the author's explicit foreground handoff, it does not wait for the author task to become idle; all local checkout protection remains in force. Safe success settles only this target; other targets remain active. A repeat reports existing completion. A recorded failed/interrupted attempt remains an exception rather than an automatic retry. The Agent must report a preserved/error outcome honestly; it is not complete local synchronization.
