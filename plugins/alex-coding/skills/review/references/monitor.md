# Codex repository monitor

Use only when the user explicitly asks to watch a repository for PR review events. This is separate from Claude's named-PR lifecycle monitor; leave that implementation and ownership unchanged.

The Python process queries GitHub every 45 seconds without model calls. New ready PRs, new heads and draft-to-ready changes enqueue one batch in an existing Codex task. A queued or reviewing batch suppresses further wakeups until the Agent records the result. Startup and restart include existing Ready PRs without a handled claim. Same-head approvals from the configured reviewer suppress code-review notifications regardless of CI; an explicitly waiting-ci claim can still receive changed terminal checks. CI events wake only work explicitly marked waiting-ci; code findings and completed work remain quiet on CI changes. New heads arriving during a review are coalesced and dispatched after that review ends. This is polling GitHub, not a model heartbeat.

## Prerequisites and launch

Requires macOS/Linux Python 3, `gh` read access through `gh_as admin`, and a Codex executable supporting `queue`. The listener reads GitHub under the explicit admin role; a missing `gh_as` is fatal rather than a fall back to the active account. Windows is not supported by this version's `fcntl` lock. Never switch GitHub accounts or obtain tokens inside this monitor.

Before enabling on a new installation, verify that a queued message wakes the intended existing desktop task; successful CLI queue output alone does not prove desktop execution. Use an explicitly authorized disposable task if needed. Do not start a new app-server daemon as a substitute for the desktop task. Desktop app availability, computer sleep and network access affect delivery; this script is not an OS wake service.

Run from the repository root:

```sh
python3 -u <installed-skill>/scripts/codex_repo_monitor.py owner/repo \
  --thread <existing-task-uuid> --reviewer <github-login> \
  --codex <verified-codex-executable>
```

The agent may detach this process with stdin disconnected, stdout/stderr redirected to a local log, and a new process session. Capture its PID and verify the startup log and state before reporting monitoring active. This is explicitly different from Claude's Monitor tool: wakeup comes from `codex queue`, not from process-exit notification. Do not create a scheduled heartbeat alongside it.

`--once` performs one poll and exits; it can enqueue existing Ready PRs and is not a read-only baseline command. `--state-dir` selects an existing state location only for the same repository/task/reviewer; other identities are rejected. Default state lives under `~/.codex/state/repository-monitor/` and stores repository/head/CI metadata, not credentials. Reuse state on restart. `--interval` must be at least 10 seconds.

Stop by verifying the PID's command is this script with the expected arguments before sending SIGTERM. The lock prevents two live processes using the same state directory. Never kill all Python/Codex processes. No login/startup service is installed automatically. Keep one chosen state directory per repository/task; overriding it with another directory creates an independent monitor.

## Behavior and bounds

The monitor does not review, approve, merge, modify code or send GitHub comments. Enabling the review Skill authorizes formal review and inline finding publication on watched PRs unless the user explicitly requests read-only mode. Queue prompts preserve that scope; they do not authorize implementation edits, merges or unrelated writes. The receiving Agent must recheck current head and review/check status before acting. Superseded or already-handled events should be skipped.

Every GitHub command has a 30-second timeout; queue delivery has a 45-second timeout. Failures are logged locally and retried on the next poll. State is advanced only after successful queue delivery, preventing normal failed sends from dropping events. If queue delivery succeeds but acknowledgement is lost, a retry can duplicate a message: exactly-once delivery is not claimed. Local claims serialize watcher dispatch with Agent acknowledgements; they do not make external GitHub writes and queue insertion atomic. A message queued before manual takeover cannot be retracted by this script.

An explicit repository watch remains active with no open PRs, so it can discover future ones. It watches Issues and external conversations not at all, and it reads comments only to notice that someone other than the configured reviewer replied after a claim; a reply during an active review is still suppressed. Do not imply it follows every GitHub activity. An Agent can review while CI runs; only an explicitly recorded waiting-ci outcome allows a later terminal CI change to wake the task again.

## Validation

Run `python3 -m unittest discover -s tests -p test_codex_repo_monitor.py` from the public skills repository. Existing local evidence: a detached ten-second test successfully queued a second turn in the same desktop task, and the Praxis pilot triggered reviews on real new PR/head events. This evidence is installation-specific, not a promise that all Codex distributions expose the same connection.

## Required Agent acknowledgement

When manually asked to review a PR in a monitored repository, record `reviewing` before starting, using the existing monitor's repository/task/reviewer/state arguments. This prevents the watcher from independently dispatching that work. A monitor-generated batch already has a queued claim; acknowledge reviewing using the actual head before work.

```sh
python3 <installed-skill>/scripts/codex_repo_monitor.py owner/repo \
  --thread <task-uuid> --reviewer <login> --state-dir <active-state-directory> \
  --ack <PR-number> --head <40-character-SHA> --phase reviewing
```

Publish the head-bound review and inline findings on GitHub before acknowledging its outcome. Do not replace publication with a chat-only report unless the user explicitly requested read-only mode. Failed publication retains the reviewing claim for recovery. Before ending the review turn after successful publication (or completed explicit read-only inspection), acknowledge every PR in the batch:

- `--phase changes-requested`: code findings remain; same-head CI changes are irrelevant.
- `--phase waiting-ci --ci pending`: review passed and checks have not settled.
- `--phase waiting-ci --ci fail`: the existing check failure was inspected; only a changed terminal result wakes again.
- `--phase done`: approved, closed or no further action remains.

Use the actual observed CI state, including `none` if checks have not appeared. Do not enter waiting-ci while code findings remain. Do not guess status from free-text GitHub comments. These acknowledgements write local metadata only, not GitHub reviews. They do not change the user's authorization requirements.

`reviews.json` persists claims. If a review task is interrupted before acknowledging, the monitor intentionally stays quiet instead of guessing it should repeatedly wake it. Resume that review and record its outcome, or explicitly reset it to the appropriate phase. There is no timeout that silently reassigns work or generates recurring model wakeups. This dependency on acknowledgement is intentional and must be included in manual review handling.

A closed PR or a verified current-head approval releases its pending claim. An explicitly waiting-ci claim retains its check tracking until CI passes, without repeating code review. A batch may contain multiple PRs; all must be acknowledged. Pending commits for a claimed PR are represented by the current remote head after release, not one queued message per intermediate commit.


## Idle-only desktop delivery

A busy task can manually finish a PR review before an earlier queued notification is delivered. Local acknowledgements cannot retract that message. Before adding a new event to the desktop queue, the monitor now checks the target desktop task's runtime status through the same local IPC coordination socket used by the installed desktop. Only an explicit idle snapshot permits delivery. Active, unloaded, unavailable, or unknown states defer delivery without invoking a model or advancing the event baseline. Each poll still refreshes GitHub and local acknowledgements, so a manually handled PR disappears before the next send. Busy tasks do not accumulate monitor messages in the desktop queue.

The state probe is read-only: a temporary follower subscribes to the selected local task snapshot and then unsubscribes/disconnects. It sends no turn, settings, history-edit or approval request. It never logs or persists snapshot content. The probe runs only when actionable events exist, has an eight-second deadline and a 64 MiB frame bound. It checks the current user's owned IPC socket under CODEX_HOME (default ~/.codex); it is not a remote-host adapter.

Compatibility boundary: the installed desktop IPC snapshot version 11 and threadRuntimeStatus are explicitly checked. This is a version-bound desktop adapter, not a claim of a stable public API. If the app changes the shape or no task owner is loaded, the monitor retains pending work and retries locally instead of queuing blind. A long-lived busy task therefore delays automatic reviews until it becomes idle; manual review is unaffected.

This prevents the observed long busy-queue echo, but does not provide atomic check-and-enqueue. A user can start a turn between the idle check and queue submission, and messages already queued by older monitor versions cannot be recalled. No direct desktop storage writes, queue replacement, or deletion of user messages are attempted. The CLI queue command exposes no removal option; the generated App Server queue-delete API is not assumed to control this desktop's separate IPC follow-up queue.
