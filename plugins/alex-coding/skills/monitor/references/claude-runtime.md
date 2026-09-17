# Claude Author Listener Runtime

## Compatibility and activation

Requires Python 3 on macOS/Linux and authorized `gh` read access through `gh_as bot`. The listener reads GitHub under the explicit bot role, never under whichever account happens to be active, and a missing `gh_as` fails at startup rather than falling back.

Two delivery paths exist. Stdout delivery, described in the rest of this section, uses the Claude Code `Monitor` tool and suits an interactive session. [Session delivery](#session-delivery-to-the-owning-host) suits a session started by an execution host that keeps its input open across turns and supplies an explicit endpoint. The event ledger, the exact-batch acknowledgement contract, terminal handling and completion are identical on both paths; startup, framing and failure reporting are not, and each path states its own. Sections below that name the `Monitor` tool describe stdout delivery only.

The `Monitor` tool's documented framing is that stdout lines written within 200ms are batched into a single notification, so a multiline block emitted by one write arrives as one notification rather than one per line. This listener relies on that: `deliver` builds the whole batch as one string and issues exactly one `print`, which `test_the_whole_batch_is_written_by_one_stdout_call` pins. Observed on this installation: a batch of six events plus its header and instructions arrived as a single notification, three separate times. If a future runtime fragments a multiline write, that test still passes while delivery degrades, so re-check the tool contract before assuming the framing still holds. There is no desktop queue, no IPC snapshot adapter and no idle probe, because a `Monitor` notification arrives in the session's own conversation instead of being inserted into another task's input queue.

Without a bound session endpoint, start the runner only through `Monitor` with `persistent: true`. Background Bash notifies once on process exit, which silently loses every event before that exit. Never substitute a Scheduled task. If `Monitor` is unavailable, report that automatic follow-up is inactive and say why.

## Session delivery to the owning host

When the execution host states that it keeps this session's input open and gives an explicit endpoint, register that endpoint and let the listener write to it. Use only an endpoint the host supplied; never construct one.

```sh
python3 <monitor>/scripts/claude_pr_monitor.py --session <stable-session-id> \
  --pr 'owner/repo#123' register --checkout <absolute-task-owned-checkout> \
  --session-remote unix:///absolute/path/control.sock
```

The endpoint must be a normalized absolute `unix://` socket path with no credentials, query or fragment. Registration records it on the target and writes `session-route.json` under the session's state root. The binding is immutable: rebinding the same endpoint is idempotent, a different endpoint is refused, and an unacknowledged batch must be acknowledged first. A run whose stored binding is missing or changed refuses to deliver.

`run` then selects session delivery automatically; `--delivery stdout` against a bound target is refused, and `--delivery session` without a binding is refused. Because delivery no longer travels through stdout, this runner is started as a detached background process rather than through the `Monitor` tool. `scripts/delivery.py start --runtime claude --session-remote <endpoint>` performs registration, startup and startup verification.

Each batch is written as one line:

```json
{"text": "<the whole batch, newlines included>"}
```

The line is written as UTF-8, and non-ASCII characters are sent unescaped, so the host must decode it as UTF-8. The host decodes that line and delivers its text to the session as a single user message. It answers `{"ok": true}` on acceptance and `{"ok": false, "error": ...}` when it cannot deliver. A refusal, a closed connection or an unreachable socket leaves the batch pending and unclaimed, so the next poll retries it; the failure is written to `monitor.log` and to this runner's stdout log. Do not send raw multi-line text to the endpoint: the host reads line by line, so an unframed batch becomes one user turn per line.

The exact-batch acknowledgement contract is unchanged. The batch carries its own `ack` command, and only that token settles it.

## One monitor per pull request

Codex and Claude both run one listener per PR. Codex listeners use the same desktop task as their delivery destination without sharing batches. Claude uses a separate `Monitor` task with its own notification stream, description and `TaskStop`. Each PR gets its own listener, state directory, batch and acknowledgement token. Two PRs never share a batch, and finishing one does not wait for the other.

Use the installed Skill's absolute script path. Every command takes `--session` and `--pr`. Run from the state directory, never from a checkout that cleanup may remove; the runner changes its own working directory to its state directory.

```sh
python3 <monitor>/scripts/claude_pr_monitor.py --session <stable-session-id> \
  --pr 'owner/repo#123' register --checkout <absolute-task-owned-checkout>
```

Then arm one `Monitor` per PR. This step belongs to stdout delivery; a bound session endpoint starts its runner as a detached process instead:

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

For merged targets, newly registered linked worktrees use the [disposable lifecycle](../../../references/worktree-lifecycle.md) through the shared completion helper. The listener synchronizes the default checkout and force-removes the task worktree independently, without waiting for a feedback acknowledgement. Existing delivered claims are retained verbatim and still require their real acknowledgement before listener settlement; disposal never marks their feedback handled. Residual files and process cwd do not veto removal. Partial/interrupted disposable operations retry without a model call; successful completion settles and stops only this PR. Legacy registrations retain their original conservative synchronization/removal rules and one-attempt exception handling. Never silently migrate ownership or acknowledgement state.

The process exits once its PR is stopped and no batch remains, which ends that `Monitor` watch and leaves every other PR's listener running. To stop earlier, use `TaskStop` on that exact monitor task; never use a user-wide process kill and never delete its event ledger. Resume with the same session and PR identity and state path.

Repeated identical retries go to `monitor.log` in that PR's state directory. On stdout delivery, stdout carries only the first failure and the later recovery, so one outage wakes the session once rather than every interval. Session delivery has no such deduplication and no channel back to the session: every failing cycle is written to `monitor.log` and to the detached runner's own log, so a lastingly unreachable endpoint retries quietly until someone reads that log.

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

It reads the registered identity and fresh PR state, rejects a non-merged PR (and an unacknowledged batch for legacy cleanup), and enters the same completion helper used by background merge detection. Safe success settles only this PR; every other PR's listener remains active. A repeat reports success or retries a partial/interrupted disposable operation. Legacy failed or interrupted attempts retain their original exception handling. Report a preserved or error outcome honestly; it is not complete local synchronization.

## Validation

Run `python3 -m unittest discover -s tests -p test_author_adapters.py -v` from the public skills repository.
