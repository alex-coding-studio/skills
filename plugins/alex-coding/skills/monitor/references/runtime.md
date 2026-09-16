# Codex Author Queue Runtime

## Delivery boundary

Monitor submits PR events to the existing author session's native queue. The host and Agent own scheduling, interruption and processing. Startup and delivery never inspect desktop busy/idle state. Queue acceptance is the completion boundary for delivery; it is not a claim that feedback has been processed. Later event batches may enqueue while earlier messages are still waiting. There is no Agent acknowledgement requirement, five-minute withdrawal or model heartbeat for this Codex path.

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

The host owns session persistence and scheduling for the task's lifetime. A missing endpoint is a transport failure, not task completion. Historical start/resume evidence is in [session-delivery.md](../reports/session-delivery.md); its older Agent-ack protocol is retained only for compatibility with old messages.

## Events, receipts and retry

Conversation comments, inline replies and submitted reviews are paginated. Body/update versions and review states identify distinct events; pending draft reviews are excluded. Only the fixed PR author's robot-marked replies are self echoes. Unmarked human comments from that account and other reviewers' feedback remain visible. Branch/local changes are not events.

Each submission contains at most 40 compact events with stable version IDs. A successful CLI call settles those versions with disposition `queue-accepted` and records `last_delivery`. No new active acknowledgement batch is created. Later events remain eligible for submission, and normal polls/restarts do not resend settled versions. The receiving Agent reads current PR evidence, ignores already-handled work and acts within its existing authorization; notifications themselves grant no new scope.

Failed or uncertain submissions remain pending. GitHub polling continues while delivery is unavailable. The CLI call has a 45-second submission deadline; this is not a deadline for the Agent to read or finish the work. No five-minute cancellation, acknowledgement polling or automatic message withdrawal is implemented. A crash or timeout after acceptance but before local persistence can duplicate a notification. Stable event versions support recipient recognition; exactly-once delivery is not claimed.

Queue receipt does not mean a blocker was fixed or the PR is approved. Those remain the author's and independent reviewer's decisions, established from the current PR rather than a Monitor acknowledgement.

## Terminal delivery and protected completion

Codex performs no background checkout cleanup. A merged or closed PR produces a terminal notification; after all event versions are accepted by the queue, the listener stops. The final merged notification includes the protected completion command. Closed-unmerged work stays local.

After the author verifies its own merge, or processes a merged notification, invoke:

```sh
python3 <monitor>/scripts/codex_pr_monitor.py --thread <uuid> --pr 'owner/repo#123' complete
```

Run from outside the owned checkout. Completion freshly verifies the merge and calls the existing protected helper to synchronize the primary default checkout and clean only proven owned merged work. It does not wait for acknowledgements of new queue-receipt deliveries. Preserve dirty, occupied, diverged or unproven work and report the concrete exception. Failed/interrupted cleanup is not blindly retried. See [feedback and completion](feedback-and-completion.md) for the author responsibilities and protection boundaries. Invoking completion directly after an author-initiated merge can settle the listener without another model wakeup.

## Existing ledgers and messages

Keep existing task/PR identities and state directories. Do not erase old batches or rewrite their event status as though the Agent processed them. An old in-flight acknowledgement batch remains valid; its original `ack --token` command still works, and protected completion still requires that old claim to be resolved. New event deliveries do not wait for that legacy batch. Claude's native Monitor and acknowledgement protocol are unchanged.

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
