# Claude repository monitor

Use only when the user explicitly asks to watch a repository for PR review events. This is separate from the author-side named-PR monitor in `alex-coding:monitor`; leave that ownership unchanged.

The Python process queries GitHub every 45 seconds without model calls. New Ready PRs, new heads and Draft-to-Ready changes print one batch in a single write.

**On the delivery framing.** The Monitor tool documents that stdout lines written within 200ms are batched into a single notification, so a multiline block from one write arrives whole rather than one notification per line. No test in this repository can verify that: the tests own the printed string, and the transport belongs to the runtime. `test_the_whole_batch_is_written_by_one_stdout_call` and `test_no_event_row_is_written_outside_that_single_call` pin only the property this side controls, that the batch leaves as exactly one write. The framing itself rests on the tool contract plus installation observation: on 2026-09-09 the sibling author listener delivered batches of six and of three events, each with its header, acknowledgement command and every row, as one notification, four times, with no observed split. That is evidence from this installation, not a guarantee. If a runtime update fragments a multiline write, both tests still pass while delivery degrades into one notification per line, and the acknowledgement command survives because it is written before the rows. Re-check the tool contract before relying on the framing, and switch to a bounded single-line payload pointing at `reviews.json` if a split is ever observed. The acknowledgement instructions come first, before the per-PR rows, so a truncated notification loses re-fetchable detail rather than the required action. A queued or reviewing batch suppresses further wakeups until the Agent records the result. Startup and restart include existing Ready PRs without a handled claim. Same-head approvals from the configured reviewer suppress code-review notifications regardless of CI; an explicitly waiting-ci claim can still receive changed terminal checks. CI events wake only work explicitly marked waiting-ci; code findings and completed work remain quiet on CI changes. New heads arriving during a review are coalesced and dispatched after that review ends. This is polling GitHub, not a model heartbeat.

## Prerequisites and launch

Requires macOS/Linux Python 3 and `gh` read access through `gh_as admin`. The listener reads GitHub under the explicit admin role, never under whichever account happens to be active. A missing `gh_as` is fatal: falling back to bare `gh` would reintroduce exactly the ambiguity the role selection removes. `install.sh` links `gh_as` into `~/.local/bin` and warns when that directory is not on PATH. Windows is not supported by this version's `fcntl` lock. Never switch GitHub accounts or obtain tokens inside this monitor.

Start it only through the `Monitor` tool with `persistent: true`. Background Bash notifies once on process exit, so every event before that exit is lost. There is no desktop queue, IPC snapshot adapter or idle probe here: a `Monitor` notification arrives in the session's own conversation instead of being inserted into another task's input queue, so there is no busy-queue echo to gate against.

Run from the repository root:

```sh
python3 -u <installed-skill>/scripts/claude_repo_monitor.py owner/repo \
  --session <stable-session-id> --reviewer <github-login>
```

`--once` performs one poll and exits; it can print existing Ready PRs and is not a read-only baseline command. `--state-dir` selects an existing state location only for the same repository/session/reviewer; other identities are rejected. Default state lives under `${CLAUDE_CONFIG_DIR:-~/.claude}/state/repository-monitor/` and stores repository/head/CI metadata, not credentials. Reuse state on restart. `--interval` must be at least 10 seconds.

Stop with `TaskStop` on that exact monitor task. The lock prevents two live processes using the same state directory. Never kill all Python processes and never delete the state. No login or startup service is installed.

## Behavior and bounds

The monitor does not review, approve, merge, modify code or send GitHub comments. Printed batches preserve the session's prior authorization; they do not grant new remote-write permission. The receiving Agent must recheck the current head and review/check status before acting. Superseded or already-handled events should be skipped.

Every GitHub command has a 30-second timeout. Failures are written to `monitor.log` in the state directory and retried on the next poll; stdout carries only the first failure and the later recovery, so one outage wakes the session once rather than every interval. State advances only after a batch is printed and its claims are saved, so a failed poll does not drop events. Because printing and acknowledgement are separate steps, a crash between them leaves a queued claim; inspect `reviews.json` and acknowledge its real disposition rather than assuming the batch was lost.

An explicit repository watch remains active with no open PRs, so it can discover future ones. It watches Issues and external conversations not at all, and it reads comments only to notice that someone other than the configured reviewer replied after a claim; a reply during an active review is still suppressed. An Agent can review while CI runs; only an explicitly recorded waiting-ci outcome allows a later terminal CI change to wake the session again.

## Validation

Run `python3 -m unittest discover -s tests -p test_claude_repo_monitor.py` from the public skills repository.

## Required Agent acknowledgement

When manually asked to review a PR in a monitored repository, record `reviewing` before starting, using the existing monitor's repository/session/reviewer/state arguments. This prevents the watcher from independently dispatching that work. A monitor-generated batch already has a queued claim; acknowledge reviewing using the actual head before work.

```sh
python3 <installed-skill>/scripts/claude_repo_monitor.py owner/repo \
  --session <session-id> --reviewer <login> --state-dir <active-state-directory> \
  --ack <PR-number> --head <40-character-SHA> --phase reviewing
```

Before ending the review turn, acknowledge every PR in the batch:

- `--phase changes-requested`: code findings remain; same-head CI changes are irrelevant.
- `--phase waiting-ci --ci pending`: review passed and checks have not settled.
- `--phase waiting-ci --ci fail`: the existing check failure was inspected; only a changed terminal result wakes again.
- `--phase done`: approved, closed or no further action remains.

Use the actual observed CI state, including `none` if checks have not appeared. Do not enter waiting-ci while code findings remain. Do not guess status from free-text GitHub comments. These acknowledgements write local metadata only, not GitHub reviews. They do not change the user's authorization requirements.

`reviews.json` persists claims. If a review turn is interrupted before acknowledging, the monitor intentionally stays quiet instead of guessing it should repeatedly wake it. Resume that review and record its outcome, or explicitly reset it to the appropriate phase. There is no timeout that silently reassigns work or generates recurring wakeups. This dependency on acknowledgement is intentional and must be included in manual review handling.

A closed PR or a verified current-head approval releases its pending claim. An explicitly waiting-ci claim retains its check tracking until CI passes, without repeating code review. A batch may contain multiple PRs; all must be acknowledged. Pending commits for a claimed PR are represented by the current remote head after release, not one printed line per intermediate commit.
