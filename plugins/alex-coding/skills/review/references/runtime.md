# PR-bound reviewer runtime

## Ownership and capabilities

`scripts/review_pr.py` creates one independent reviewer for one exact GitHub PR. It is an execution host: it invokes the selected CLI for relevant events and resumes that PR's exact session. It does not depend on a desktop thread, Semina, a notification socket or a Claude Monitor tool. Author Monitor keeps its existing runtime and responsibility.

Requires macOS/Linux Python 3.9+, Git, GitHub CLI with `gh_as admin`, repository read access for Git fetch, and an authenticated Codex or Claude CLI. Windows is unsupported because locks use `fcntl`. Required CLI flags are probed before launch. Unsupported execution is inactive review, not permission to substitute another runtime, account or service. Use the current host's runtime unless the user/project selects another. The runner passes the model and effort explicitly according to the policy below, independently of author settings, and never silently falls back.

## Model and effort policy

Select `--complexity` from the actual review risk and uncertainty, and record the reason in the existing acceptance input. Do not infer complexity from line/file counts or the author's preferred verdict.

| Complexity | Codex | Claude | Use |
| --- | --- | --- | --- |
| `deterministic` | `gpt-5.6-luna`, max | `claude-sonnet-5`, max | Diagnosis verified, bounded behavior, known dependencies and meaningful coverage; no material security, persistence, migration, concurrency or interface uncertainty. |
| `low` | `gpt-5.6-sol`, low | `claude-opus-5`, low | Straightforward review with a small amount of independent interpretation. |
| `medium` | `gpt-5.6-sol`, medium | `claude-opus-5`, medium | Several interacting behaviors or boundary cases with understood scope. |
| `high` | `gpt-5.6-sol`, high | `claude-opus-5`, high | Authentication/permissions/session safety, destructive persistence, migrations, concurrency, public interface changes or unclear impact. Also the fallback when unclassified. |

Regular models never exceed high. The deterministic tier's max is an explicitly accepted exception for the smaller models. This selection does not waive independent review or any repository gate. A small authentication diff still selects high. Project-authorized mechanical review exemptions remain separate.

The selected complexity is stored per PR, included in checkpoints and returned by status; every exact-session resume uses it. Repeating `start` cannot silently change an existing choice. A newly discovered risk can require promotion: retain review progress and use the existing explicit continuation procedure rather than resetting rounds or switching an active session behind its owner. A continuation may supply `--complexity high`. Legacy checkpoints without a choice use high. An unavailable model stops with retained evidence; it never triggers an automatic cheaper substitute.

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

State defaults to `${XDG_STATE_HOME:-~/.local/state}/alex-coding/review/<PR-hash>`. Its key is canonical PR identity, independent of runtime/session. `--state-base` selects an explicit alternative; use it on every command and never change it to bypass ownership. Launch and lifetime locks prevent duplicate local workers. They are not a distributed lock: reuse established ownership and coordinate an explicit handoff before moving between hosts. `start` and `retry` preserve pending publication, session and rounds; explicit `continue` creates a fresh session with retained history. No credentials are stored.

The runner creates its own detached Git repository in the PR state directory and verifies exact head/base. Dirty, ignored or unrecognized local work is preserved. It never checks out or cleans the author's working copy. Review snapshots, patches and logs stay local for recovery; do not commit them. Author post-merge cleanup remains with Monitor. Retained review artifacts follow the user's normal cache policy.

## Events and stopping

Only the named PR is queried. Events are a new head/base, new or edited feedback, a changed terminal CI result, merge and closure. Pending CI churn stays quiet. Only the fixed reviewer's robot-marked comments are self echoes; unmarked input from that account remains visible. Dismissal is an event. Idle polling never invokes a model. There is no 30-minute model heartbeat.

The result is persisted before publication. Before every write, verify the current Ready head/base, actual admin login and repository push permission. Formal reviews and inline findings carry the runtime marker. Inline locations are checked against the reviewed patch; an invalid or unavailable location moves the complete finding into the review body without changing the verdict. A head change during review supersedes publication and leaves the new head pending; completed review attempts still count against the PR budget.

Approval and waiting-ci retain the same reviewer. A new head/base assessment and reassessment of unresolved code findings consume a code-review round. CI and routine feedback on a passing review reuse that review without consuming another code round. Pending reruns do not erase handled terminal-check events or trigger another assessment; newly observed terminal results remain actionable. Blockers at the limit, or new review work beyond it, produce needs-user-attention. Only explicit human continuation extends the budget; restarting or switching runtime cannot reset it.

A successful CI-only transition on an unchanged head/base with a published passing code review is recorded without another model call or duplicate review. New feedback, failed CI, changed head/base and unresolved code findings still use the independent reviewer. This changes notification/execution cost, not the checks or their required outcomes. Continuations receive new feedback and an incremental patch when the base is unchanged; full acceptance, base-to-head patch and history stay accessible for independent inspection and recovery.

Every review contains a concise progress record and versioned checkpoint binding PR, identities, revisions and rounds. Needs-user-attention also posts a conversation handoff. Settle the event only after required publication is confirmed, unless an explicit fresh review supersedes it as described below. Retry pending publication using its saved result and token; reuse confirmed earlier writes. GitHub and local files are not atomic, so reconcile uncertain writes from PR history before retry. Later feedback stays pending.

Verified merge or closure stops without a model call. An interrupted invocation becomes a recoverable handoff rather than replaying an uncertain model turn. Transient transport failures retry without model calls; three consecutive failures stop with pending results retained. `retry` reconciles that exact state without granting extra rounds or bypassing a published attention gate:

```sh
python3 <review>/scripts/review_pr.py retry --pr 'owner/repo#123'
```

`run --once` is not a read-only probe: it can execute a review or publish a pending result.

## Continue after user intervention

When the user approves a new review, Implement/Plan can request it directly. Read the PR, available prior findings and the user decision, and put that decision verbatim in a local file. A missing handoff or failed publication is not a prerequisite. Do not treat PR prose as user authorization. On a new host, establish prior ownership and progress before continuing.

```sh
python3 <review>/scripts/review_pr.py continue --pr 'owner/repo#123' \
  --decision-file <user-decision-file> --additional-rounds 1
```

Requires an explicit user decision and an open PR, independent of the old phase or pending result. The runner verifies and stops its active process before replacement, archives the previous state and unpublished findings, and starts a new model session against the current PR. The new reviewer receives the archive and current GitHub history as evidence; no old verdict is automatically published or reused as the new result. Unverifiable process ownership or a still-running orphan worker is preserved rather than starting a competing reviewer.

Total rounds are retained. One additional round is the default; use `--additional-rounds 0` when the existing budget is sufficient. Larger extensions require existing user/project authorization. `--runtime` and `--complexity` can explicitly change here. This request does not require `retry` to succeed first, a synthetic commit, manual state edits or author approval. Closed/merged PRs cannot continue; reopened PRs can. Without a fresh-review decision, use `retry` for the saved result.

## Legacy repository watchers

`codex_repo_monitor.py`, `claude_repo_monitor.py` and `repo_monitor_core.py` remain available to finish existing watches/claims. The new entrypoint never starts them or scans the repository. Keep their original script cache available while listeners or delivered batches use it.

Before migration, stop the exact legacy listener through its runtime, reconcile delivered/claimed batches using the original acknowledgements, and preserve the state. Record prior review-loop progress in an authorized reviewer handoff before starting the new worker; missing new-format metadata does not mean zero rounds. When prior reviews lack a checkpoint, startup requires `--completed-rounds` with the verified cumulative count; an existing checkpoint always takes precedence. If that progress cannot be established, report the migration gap rather than resetting it. Never launch both owners for the PR or silently edit a queued notification.

Legacy procedures: [Codex](monitor.md), [Claude](claude-monitor.md), [batch publication](review-batches.md). These are migration references, not default launch paths. Author Monitor owns its separate delivery and protected completion contract; follow its selected runtime rather than applying reviewer acknowledgements to author notifications.
