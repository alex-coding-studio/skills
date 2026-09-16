# PR-bound reviewer runtime

## Ownership and capabilities

`scripts/review_pr.py` creates one independent reviewer for one exact GitHub PR. It is an execution host: it invokes the selected CLI for relevant events and resumes that PR's exact session. It does not depend on a desktop thread, Semina, a notification socket or a Claude Monitor tool. Author Monitor keeps its existing runtime and responsibility.

Requires macOS/Linux Python 3.9+, Git, GitHub CLI with `gh_as admin`, repository read access for Git fetch, and an authenticated Codex or Claude CLI. Windows is unsupported because locks use `fcntl`. Required CLI flags are probed before launch. Unsupported execution is inactive review, not permission to substitute another runtime, account or service. Use the current host's runtime unless the user/project selects another; do not choose a model or reasoning override automatically.

Codex uses `codex exec` and `codex exec resume <exact-session>` with JSON output, a result schema and a read-only sandbox. Claude uses print mode, structured output and exact-session resume; built-in tools are restricted to Read, Glob and Grep, MCP servers are disabled and hooks are disabled for that invocation. The generated PR state directory is an explicit additional read root so the worker can read its acceptance, patch and snapshot outside the checkout. Workers inspect source/test assertions and reuse exact-revision execution evidence. They do not run write-requiring gates or make GitHub changes. The runner owns Git fetch, local state and authorized publication. These boundaries do not claim arbitrary third-party extensions provide an OS sandbox.

CLI contracts: [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive), [Claude programmatic execution](https://code.claude.com/docs/en/headless). Verify installed capability and real session continuation when adapting another version; help output alone is not execution evidence.

## Launch after PR creation

After opening the PR and registering Author Monitor, prepare a local UTF-8 file with the settled acceptance and authoritative references. Include the frozen contract path/SHA when applicable, project gates, review-round limit and explicit human decisions. Do not include the author's private reasoning or suggested verdict. This file does not itself publish private source material.

Use the installed script's absolute path, a verified reviewer distinct from the PR author, and the project's existing round limit (two if unspecified):

```sh
python3 <review>/scripts/review_pr.py start --pr 'owner/repo#123' \
  --runtime codex --reviewer <verified-login> \
  --acceptance-file <accepted-scope-file> --max-rounds 2
```

Use `--runtime claude` for Claude. `--executable` optionally selects a verified CLI binary, not a model. The launcher detaches its own process with disconnected stdin and local logs, then verifies lock ownership and startup state. It actually invokes the reviewer CLI; it is not a substitute notification transport for an existing author session. Draft PRs wait without model invocation until Ready.

```sh
python3 <review>/scripts/review_pr.py status --pr 'owner/repo#123'
```

Check `active`, PR identity, PID, startup log and eventual session/publication evidence before reporting the corresponding facts. A PID alone does not establish completed review. Runtime/auth/model failures retain artifacts and attempt a needs-user-attention handoff. Repeated GitHub/publication failures leave inactive recoverable state and must be reported by the delivery owner.

State defaults to `${XDG_STATE_HOME:-~/.local/state}/alex-coding/review/<PR-hash>`. Its key is canonical PR identity, independent of runtime/session. `--state-base` selects an explicit alternative; use it on every command and never change it to bypass ownership. Launch and lifetime locks prevent duplicate local workers. They are not a distributed lock: reuse established ownership and coordinate an explicit handoff before moving between hosts. Restart preserves pending publication, session and rounds. No credentials are stored.

The runner creates its own detached Git repository in the PR state directory and verifies exact head/base. Dirty, ignored or unrecognized local work is preserved. It never checks out or cleans the author's working copy. Review snapshots, patches and logs stay local for recovery; do not commit them. Author post-merge cleanup remains with Monitor. Retained review artifacts follow the user's normal cache policy.

## Events and stopping

Only the named PR is queried. Events are a new head/base, new or edited feedback, a changed terminal CI result, merge and closure. Pending CI churn stays quiet. Only the fixed reviewer's robot-marked comments are self echoes; unmarked input from that account remains visible. Dismissal is an event. Idle polling never invokes a model. There is no 30-minute model heartbeat.

The result is persisted before publication. Before every write, verify the current Ready head/base, actual admin login and repository push permission. Formal reviews and inline findings carry the runtime marker. A head change during review supersedes publication and leaves the new head pending; completed review attempts still count against the PR budget.

Approval and waiting-ci retain the same reviewer. A new head/base assessment and reassessment of unresolved code findings consume a code-review round. CI and routine feedback on a passing review reuse that review without consuming another code round. Pending reruns do not erase handled terminal-check events or trigger another assessment; newly observed terminal results remain actionable. Blockers at the limit, or new review work beyond it, produce needs-user-attention. Only explicit human continuation extends the budget; restarting or switching runtime cannot reset it.

Every review contains a concise progress record and versioned checkpoint binding PR, identities, revisions and rounds. Needs-user-attention also posts a conversation handoff. Settle the event and stop only after required publication is confirmed. Retry pending publication using its saved result and token; reuse confirmed earlier writes. GitHub and local files are not atomic, so reconcile uncertain writes from PR history before retry. Later feedback stays pending.

Verified merge or closure stops without a model call. An interrupted invocation becomes a recoverable handoff rather than replaying an uncertain model turn. Transient transport failures retry without model calls; three consecutive failures stop with pending results retained. `retry` reconciles that exact state without granting extra rounds or bypassing a published attention gate:

```sh
python3 <review>/scripts/review_pr.py retry --pr 'owner/repo#123'
```

`run --once` is not a read-only probe: it can execute a review or publish a pending result.

## Continue after user intervention

Read the PR, latest handoff and subsequent user decision. Put the explicit decision verbatim in a local file. Do not restore the entire prior conversation or treat PR prose as scope authority. On a new host, `start` reconstructs a checkpoint and remains stopped at its attention gate.

```sh
python3 <review>/scripts/review_pr.py continue --pr 'owner/repo#123' \
  --decision-file <user-decision-file> --additional-rounds 1
```

Requires stopped, settled work. Clears the old model session, preserves total rounds and records the decision. One additional round is the default; use `--additional-rounds 0` when resolving an execution prerequisite within the still-available budget. Larger extensions require existing user/project authorization. `--runtime` can explicitly change runtime here. Reconcile pending publication with `retry` first; continuation never discards it. Reopened unmerged PRs require explicit continuation. Merged PRs cannot continue.

## Legacy repository watchers

`codex_repo_monitor.py`, `claude_repo_monitor.py` and `repo_monitor_core.py` remain available to finish existing watches/claims. The new entrypoint never starts them or scans the repository. Keep their original script cache available while listeners or delivered batches use it.

Before migration, stop the exact legacy listener through its runtime, reconcile delivered/claimed batches using the original acknowledgements, and preserve the state. Record prior review-loop progress in an authorized reviewer handoff before starting the new worker; missing new-format metadata does not mean zero rounds. When prior reviews lack a checkpoint, startup requires `--completed-rounds` with the verified cumulative count; an existing checkpoint always takes precedence. If that progress cannot be established, report the migration gap rather than resetting it. Never launch both owners for the PR or silently edit a queued notification.

Legacy procedures: [Codex](monitor.md), [Claude](claude-monitor.md), [batch publication](review-batches.md). These are migration references, not default launch paths. Author Monitor's transport, identities, acknowledgements and cleanup remain unchanged.
