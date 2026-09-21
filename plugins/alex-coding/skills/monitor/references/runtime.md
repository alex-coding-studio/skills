# Codex Author Queue Runtime

## Delivery boundary

Monitor submits PR events to the existing author session's native queue. The host and Agent own scheduling, interruption and processing. Startup and delivery never inspect desktop busy/idle state. Queue acceptance claims one active PR-scoped batch; it is not a claim that feedback has been processed. Later events accumulate in the ledger without adding queue messages until the Agent gives that exact batch a concrete disposition and acknowledgement. There is no five-minute withdrawal or model heartbeat for this Codex path.

Requires Python 3 on macOS/Linux, GitHub CLI read access through `gh_as bot`, and an installed Codex CLI supporting `queue`. Verify command capability, the stored PR/session identity and the running listener. Report actual queue acceptance when an event is submitted; do not make session receipt or completion a startup prerequisite. A rejected or timed-out submission retains events for retry. Report the submission failure without inventing an idle state, switching hosts, starting a replacement executor or silently changing the bound session.

`--delivery queued` is the default for a desktop session and is optional. `--delivery idle` is retired. The old desktop snapshot adapter remains only for legacy repository watchers; this author listener does not call it.

## Register and start

Use the installed script's absolute path. Every command identifies the existing author task and one exact PR. Run the listener from its state directory or the plugin directory, not a worktree that completion may remove.

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <existing-uuid> --pr 'owner/repo#123' \
  register --checkout <absolute-task-owned-checkout>
python3 <monitor>/scripts/codex_pr_monitor.py --thread <existing-uuid> --pr 'owner/repo#123' \
  run --codex <verified-executable> --interval 45
```

Registration binds GitHub's real PR author as the fixed source identity. `--author` validates it and never overrides it. A PR URL can replace `owner/repo#123`. Re-registration is idempotent and preserves author and checkout ownership. Each additional PR has a separate listener and event ledger, even when it shares the same receiving session.

Launch a detached process with disconnected stdin and local stdout/stderr logs. Verify the process identity and startup log before reporting a running listener. Queue submission remains a separate observable result. A failed submission does not stop GitHub collection or discard pending events; the listener logs the failure and retries on a later poll. A dead receiving session requires restoring that actual session/host, not guessing another target. No OS service or scheduled model wakeup is installed.

Default state lives below `${CODEX_HOME:-~/.codex}/state/author-pr-monitor/<uuid>/` in a PR-specific hashed directory. Reuse the exact state path on every action. The lifetime lock prevents duplicate local listeners using that state; do not change directories to bypass ownership. `run --once` can submit events and is not a read-only probe.

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' status
```

## Host-bound session delivery

When the task is owned by a persistent local app-server, register the endpoint supplied by that actual execution host:

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <existing-uuid> --pr 'owner/repo#123' \
  register --checkout <absolute-task-owned-checkout> --session-remote unix:///absolute/owner.sock
```

A bound target defaults to `session` delivery and invokes `codex queue --remote <endpoint> --thread <same-uuid> --message <batch>`. It has the same queue-receipt semantics as desktop delivery. It does not query desktop IPC, create another thread or change model/effort/permission settings. Verify CLI support for `queue --remote`. Preserve the host's existing session and configuration.

Only explicit absolute Unix socket URLs and numeric loopback WebSocket URLs are accepted. Credentials, network-hosted servers and remote authentication are outside this adapter. The endpoint is persisted with the PR and owning session; another PR cannot silently bind that session to a different endpoint. Bound targets refuse a desktop delivery override. Registration refuses rebinding while a listener is running or an old batch is claimed. Do not migrate routes, clear ledgers or create a new app-server as an automatic fallback.

The host owns session persistence and scheduling for the task's lifetime. A missing endpoint is a transport failure, not task completion. Historical start/resume evidence is in [session-delivery.md](../reports/session-delivery.md); its exact-batch acknowledgement remains the current processing boundary.

## Events, receipts and retry

Conversation comments, inline replies and submitted reviews are paginated. Body/update versions and review states identify distinct events; pending draft reviews are excluded. Only the fixed PR author's robot-marked replies are self echoes. An empty author `COMMENTED` review shell is also ignored when every inline comment attached to that review is a robot-marked author reply. Unmarked human comments from that account and other reviewers' feedback remain visible. Branch/local changes are not events.

Each submission contains at most 40 compact events with stable version IDs. A successful CLI call marks those versions `delivered` and records one active batch with its acknowledgement token. Normal polls and restarts do not resubmit that batch, and acknowledged versions never become pending again. Later events remain `pending` until the active batch is acknowledged, then form at most one next batch. The receiving Agent reads current PR evidence, acts within its existing authorization and runs the supplied exact-token acknowledgement only after every listed event has a concrete disposition; notifications themselves grant no new scope.

Failed or uncertain submissions remain pending. GitHub polling continues while delivery is unavailable. The CLI call has a 45-second submission deadline; this is not a deadline for the Agent to read or finish the work. No five-minute cancellation, acknowledgement polling or automatic message withdrawal is implemented. A crash or timeout after acceptance but before local persistence can duplicate a notification. Stable event versions support recipient recognition; exactly-once delivery is not claimed.

Queue receipt does not mean a blocker was fixed or the PR is approved. Those remain the author's and independent reviewer's decisions, established from the current PR rather than a Monitor acknowledgement.

## Terminal delivery and protected completion

For newly registered disposable linked worktrees, the listener calls the completion script directly after verifying a merge, without an Agent wakeup. It synchronizes the primary default checkout and force-removes the owned worktree independently. Partial/interrupted operations remain pending for model-free retry. Existing legacy targets retain terminal queue delivery and foreground completion. Closed-unmerged work stays local.

After the author verifies its own merge, or processes a merged notification, invoke:

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' complete
```

Run from outside the owned checkout. Completion freshly verifies PR identity, the merged head and default branch, then uses the [disposable lifecycle](../../../references/worktree-lifecycle.md) for a disposable registration. All remaining task files are discarded; primary default changes are overwritten by the fetched commit. Synchronization and disposal have separate receipts, and repeating completion retries a partial or interrupted disposable operation. Disposable cleanup does not wait for a feedback acknowledgement, but the listener retains the active batch and does not settle until its exact acknowledgement. Legacy registrations retain their existing foreground and preservation behavior. See [feedback and completion](feedback-and-completion.md).

## Existing ledgers and messages

Keep existing task/PR identities and state directories. Do not erase old batches or rewrite their event status as though the Agent processed them. An old in-flight acknowledgement batch remains valid; its original `ack --token` command still works, blocks another queue submission and must receive a concrete disposition. Events already settled by the former queue-receipt path remain historical ledger entries and are not replayed. Claude's native Monitor and acknowledgement protocol are unchanged.

Older task-scoped ledgers still use the explicit migration command after their original listener is stopped and delivered claims are resolved:

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' \
  migrate --from-state <old-task-state-directory>
```

Keep the old script cache while its listener/messages depend on it. Migration locks and validates source ownership, refuses delivered claims or an existing destination, and preserves the source. Already queued messages cannot be recalled. Never run competing listeners or repurpose another session's state.

## Publish author replies

Prepare a body file, then use the established role-aware author write path. The bundled reply helper validates the fixed PR author and actual writer, appends `From Codex 🤖`, and checks push permission:

```sh
python3 <monitor>/scripts/reply.py owner/repo 123 \
  --expected-login <verified-writer-login> --body-file <file>
python3 <monitor>/scripts/reply.py owner/repo 123 \
  --expected-login <verified-writer-login> --body-file <file> --inline-comment <comment-id>
```

Use the project's per-command identity selector and never change global accounts to satisfy the helper. A failed identity check is not permission to post under another account. Reply publication does not serve as a transport acknowledgement or authorize merge.
