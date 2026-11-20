# Antigravity Author Listener Runtime

## Compatibility and activation

Requires Python 3 on macOS/Linux and authorized `gh` read access through `gh_as bot`. The listener reads GitHub under the explicit bot role, never under whichever account happens to be active, and a missing `gh_as` fails at startup rather than falling back.

Antigravity uses local outbox delivery paired with a single-event local waiter. The PR's detached runner (`review_pr.py` with `--author-runtime antigravity`, or a standalone `antigravity_pr_monitor.py run` daemon for review-exempt PRs) polls GitHub without model calls and appends each complete-state delivery atomically as one JSONL record to `outbox.jsonl` under an exclusive `outbox.lock`, never blocking on the Antigravity host.

The Antigravity session wakes up reactively by running the returned `wait_command` as a single background command (for example with `WaitMsBeforeAsync=500`) and ending its turn. While caught up, `wait` polls only local files (`outbox.jsonl`, `run.lock`, and `state.json`) with zero GitHub API calls and zero token consumption. When a new outbox record arrives, or when the PR finishes or the runner stops unexpectedly, `wait` prints the full update to stdout and exits, triggering Antigravity's native background-task wakeup.

Do not use sleep loops, repeated GitHub/status polling, or scheduled wakeups. Never invent a `--session-remote` endpoint; `--session-remote` is unsupported for Antigravity.

## One monitor per pull request

Each PR gets its own state directory, event ledger, outbox (`outbox.jsonl`), cursor (`cursor.json`), and locks (`run.lock`, `outbox.lock`, `wait.lock`). For reviewed PRs opened through `implement/scripts/delivery.py`, the single `review_pr.py` runner owns the author ledger under `<runner-state-dir>/author/` and returns `wait_command` pointing at both `--state-dir <runner-state-dir>/author` and `--runner-dir <runner-state-dir>`.

For standalone watches (review-exempt PRs or explicit standalone registrations), use the installed Skill's absolute script path:

```sh
python3 <monitor>/scripts/antigravity_pr_monitor.py --session <stable-session-id> \
  --pr 'owner/repo#123' register --checkout <absolute-task-owned-checkout>
```

Start the detached listener (from the state directory, never from a disposable checkout):

```sh
python3 <monitor>/scripts/antigravity_pr_monitor.py --session <stable-session-id> \
  --pr 'owner/repo#123' run --interval 45
```

Then run `wait` as a background command and end the turn:

```sh
python3 <monitor>/scripts/antigravity_pr_monitor.py --session <stable-session-id> \
  --pr 'owner/repo#123' [--state-dir <path>] wait [--runner-dir <runner-state-dir>]
```

`--session` is any stable identifier of letters, digits, dot, underscore or hyphen (such as the Antigravity conversation UUID). Standalone state defaults to `${ANTIGRAVITY_HOME:-~/.gemini/antigravity}/state/author-pr-monitor/<session>/<owner>__<repo>__<number>`.

## Outbox and zero-race wakeup

Each delivery appended to `outbox.jsonl` has the form:

```json
{"seq": 1, "created_at": "2026-01-01T00:00:00Z", "text": "<complete current PR state>"}
```

`wait` enforces single-waiter safety via a non-blocking `wait.lock`; a duplicate concurrent `wait` exits immediately with status `1`.

- **Zero race:** if records with `seq > cursor.json.last_seq` already exist when `wait` starts, `wait` verifies session and PR ownership under `outbox.lock`, advances `cursor.json` atomically to the latest sequence number, prints the latest full-state delivery (preserving all earlier unread event lines when multiple updates coalesced), and exits `0` immediately.
- **Next wait:** when the consumed record(s) do not carry a settled terminal state, `wait` prints the exact next `wait` command to run in the background after handling the feedback.
- **Terminal completion:** when the PR merges with a `disposable-v1` worktree, the runner automatically verifies the repository/branch under `gh_as bot`, synchronizes the primary default checkout, force-removes the task worktree, deletes the merged local branch, discards its Xcode DerivedData, and writes the final `merged + cleanup` event to `outbox.jsonl` before stopping. `wait` exits `0` only when the terminal outcome actually cleaned/released (or closed an ordinary worktree) without requiring manual attention.
- **Cleanup attention, dead/errored runner, or takeover:** if post-merge cleanup is `preserved`, fails with `retryable: false` (such as an unowned Git index lock), fails to release a pool slot, or if the runner stops non-terminally / enters `phase == 'error'` / is taken over by another session or runtime, `wait` prints the actual cleanup result or diagnostic and exits `2` immediately (while continuing to wait when a disposable cleanup failure is still `retryable: true` and the runner is live).
- **Timeout:** passing `--timeout <seconds>` (default `0`, unlimited) exits `3` if no event arrives before the deadline while the runner remains live.

## Events and state delivery

```sh
python3 <monitor>/scripts/antigravity_pr_monitor.py --session <id> --pr 'owner/repo#123' status
```

Event collection, CI gating, self-echo filtering (`🤖` in body from the fixed PR author), and complete-state deliveries follow [feedback-and-completion.md](feedback-and-completion.md). No acknowledgement is required for state deliveries; batches claimed by an older version still accept `ack --token`.

## Publish authorized replies

Prepare the final body in a file, then use:

```sh
python3 <monitor>/scripts/antigravity_reply.py owner/repo 123 \
  --expected-login <verified-writer-login> --body-file <file>
python3 <monitor>/scripts/antigravity_reply.py owner/repo 123 \
  --expected-login <verified-writer-login> --body-file <file> --inline-comment <comment-id>
```

This helper uses `gh_as bot` for all GitHub reads, permission/identity checks, and the POST write (refusing to fall back to bare `gh` if `gh_as` is unavailable), appends `From Antigravity 🤖`, validates that an inline reply belongs to this PR, requires the expected writer to match the real PR author, and verifies repository push permission and the actual API login immediately before POST.

## Complete after the Agent merges

For standalone watches (such as after `delivery.py pin-merge` on a review-exempt PR), run `complete` from outside the owned checkout:

```sh
python3 <monitor>/scripts/antigravity_pr_monitor.py --session <id> --pr 'owner/repo#123' complete
```

## Validation

Run `python3 -m unittest discover -s tests -p test_antigravity_monitor.py -v` from the public skills repository.
