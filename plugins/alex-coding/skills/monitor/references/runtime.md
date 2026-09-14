# Codex Author Listener Runtime

## Compatibility and activation

Select the transport from the actual session owner. The following desktop prerequisites apply to desktop delivery only; headless session delivery has its own requirements below.

Requires Python 3 on macOS/Linux, authorized `gh` read access through `gh_as bot`, and a local Codex desktop supporting `codex queue` and the verified IPC snapshot adapter. The shared adapter is `alex-coding/scripts/codex_desktop_transport.py`; both reviewer and author listeners use it. It validates an owned socket and snapshot version 11, uses an eight-second read deadline and only queues into an explicitly idle existing task. Active, unloaded or unknown task states defer events locally. It is a version-bound adapter, not a public stable API or an OS wake service.

Before first use on an installation, verify the chosen executable's `queue --help` and evidence that its queue wakes this same desktop task. A successful CLI send alone is insufficient. Do not create another task or launch an app-server as a workaround. Do not send a synthetic live queue message without authorization. Reuse current verified installation evidence; if unavailable, explain the limitation before claiming the listener is active. The runner additionally probes queue capability and IPC before its startup log.

## Queued delivery when desktop snapshots are unavailable

With explicit user authorization, `run --delivery queued` delegates message scheduling to `codex queue` instead of requiring an idle IPC snapshot at startup or delivery. Verify queue acceptance and actual receipt in the same task before claiming end-to-end delivery. A successful CLI response alone is insufficient. Keep the normal default (`--delivery idle`) for installations using the established idle-only policy; do not silently switch after an error.

Queued mode retains the same PR state directory, lock, pending-event ledger and batch acknowledgement. Queue failures leave feedback pending for retry. One accepted batch blocks later batches until acknowledgement. The chosen delivery mode is printed in the startup log.

Queued mode never performs background checkout cleanup, including when desktop state happens to be available. A merged PR is delivered as a terminal batch. The receiving Agent verifies the merge, handles and acknowledges that batch, then invokes the existing `complete` action. That foreground action retains all checkout, branch and process protections. This separates message scheduling from destructive cleanup and does not treat unknown desktop state as idle.

A task-authorized candidate runtime can be tested from its isolated development checkout before release. Keep that checkout available until its listeners stop and their batches are acknowledged; never remove a runner's code during an active watch.

## Headless session delivery

For an existing task owned by a persistent local Codex app-server, bind its host-provided endpoint at registration:

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <existing-uuid> --pr 'owner/repo#123' \
  register --checkout <absolute-task-owned-checkout> --session-remote unix:///absolute/owner.sock
python3 <monitor>/scripts/codex_pr_monitor.py --thread <existing-uuid> --pr 'owner/repo#123' \
  run --codex <verified-executable> --interval 45
```

A bound target defaults to `session` delivery. It calls `codex queue --remote <endpoint> --thread <same-uuid> --message <batch>`, without desktop IPC, a new thread, `exec resume`, or model/effort/permission overrides. The native owning server handles scheduling. Verify that the installed CLI supports `queue --remote` and that the intended server actually consumes a queued message in the same thread, including its busy-to-idle path. Queue acceptance alone does not prove consumption. Current compatibility evidence is in [session-delivery.md](../reports/session-delivery.md).

Only explicit absolute Unix socket URLs and numeric loopback WebSocket URLs are accepted. Do not put tokens in an endpoint. Network-hosted servers and remote authentication are outside this adapter. The route is persisted both with the PR and under the session's normal author-monitor state directory; another PR for the same session cannot bind a different endpoint. A bound target refuses desktop delivery overrides. Registration refuses rebinding while its monitor is running or while a batch is claimed. Session endpoint migration is not automatic: stop all that session's listeners, drain existing claims with their original helpers, and establish an explicit safe host migration before adding any new route. Do not clear state to bypass these checks.

The execution host must own the endpoint for the lifetime of the task, including review waits. It must preserve the session's configuration and arbitrate user input and concurrent PR messages. Monitor does not start a daemon, infer that `notLoaded` means globally idle, or transfer ownership from a live stdio process. If the original host terminates at turn completion and exposes no persistent endpoint, host integration is missing: report that limitation rather than falling back to desktop or launching a second executor. This change alone does not convert a short-lived Board driver into a persistent host.

Owner connection failures retain pending events and are retried through the normal listener loop. A delivery accepted by the server is still unhandled until the Agent acknowledges the exact batch. Later arrivals remain pending. A timeout after uncertain queue acceptance can produce duplicate delivery on retry, as in desktop queue mode; consumers must inspect the batch token before acting and never repeat acknowledged work. Exactly-once delivery is not claimed.

Background cleanup is disabled in session mode. The receiving Agent handles the terminal batch and invokes protected foreground `complete` from outside the owned checkout; no desktop snapshot is required. A missing or stopped endpoint is not task completion and must not cause cleanup. Existing desktop and Claude paths remain unchanged.

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

For merged targets, registration's explicit ownership metadata is passed to `postmerge_cleanup.py`. The helper fetches and verifies that the merged content reached the default branch, either because the final PR head is an ancestor of it or because GitHub's reported merge commit is, which is what a squash or rebase merge leaves behind; an unproven head with no such merge commit is preserved. It then safely fast-forwards the primary default checkout, verifies its HEAD/tree, then removes the owned merged worktree and branch. A linked worktree follows the same default-sync requirement. If the owned worktree is already absent, a repeat still synchronizes lagging default state. Tracked changes, hidden index flags, detached/unrelated branches, locks, branches checked out in other worktrees and divergent primary state are preserved. A process cwd inside the primary directory alone is not a synchronization blocker. An owned primary work branch switches directly to the fetched remote default after the local-default fast-forward check, so an identical squash-merged tree is not rewritten through a stale intermediate checkout. Nonconflicting untracked or ignored primary files may remain during fast-forward; Git no-overwrite checks still block collisions. Git-ignored build outputs (`.build`, `.swiftpm`, Xcode project bundles, DerivedData and CI result bundles) are disposable as a whole. Their contents are not inspected. Tracked changes and other untracked/ignored user files remain protected. When the owned checkout is the primary checkout itself, there is no worktree to remove and the remaining deletion is a branch deletion, `git branch -d` when the head is an ancestor of the default branch and `git branch -D` when a squash or rebase merge commit is what proves it landed, neither of which touches the working tree, so that case gates on tracked changes only: unrecognized untracked or ignored files no longer block synchronization and branch deletion, and they are left in place. A linked worktree keeps the strict check, because removing it would take those files with it. No fixed delay substitutes for fetch and commit verification; failed verification prevents deletion. Cleanup waits for this PR's delivered batch to be acknowledged and requires a fresh idle desktop snapshot immediately before invoking the helper. Busy tasks defer cleanup without queueing a normal merged event. Successful cleanup marks observed events `settled` with disposition `merged-cleanup`, not a fabricated user acknowledgement, and stops that target without queueing another turn. Missing metadata, preservation or errors retain feedback and produce a terminal exception. An attempt marker is persisted before the helper runs; interrupted/failed attempts are not automatically retried. Inspect and resolve the concrete exception under existing authorization, then acknowledge its batch. The idle check and cleanup cannot be atomic with new user activity; the helper rechecks Git state and uses Git no-overwrite operations for primary synchronization. Process cwd checks apply to deletion of a separate worktree only; an occupied linked worktree is preserved after safe primary synchronization. A cwd check cannot establish whether another process will write later, and removing the primary cwd veto does not establish concurrent-writer isolation. No generic cleanup script runs on closed-unmerged targets.

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
