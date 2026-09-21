# Skills

Practical Agent skills from Alex Coding Studio. Each skill includes the instructions and small tools needed to complete a focused workflow.

## alex-coding plugin

General technical setup, GitHub PR-based planning and implementation, guided by the current repository rather than a fixed technology stack.

- **`alex-coding:setup`** creates, aligns or updates a runnable technical project baseline. It owns runtimes, frameworks, direct dependencies, data infrastructure, commands, CI, ProjectContext and initial repository delivery, while excluding product planning and business-feature implementation. It selects stable unspecified technical details, can reuse another project's technical setup without copying business code, and carries update-required compatibility changes in the same Setup PR.
- **`alex-coding:plan`** turns accepted requirements into a delivery contract and documentation PR. After the required review and merge, it returns an Implement prompt bound to the actual full merge commit, contract path and acceptance IDs. The contract governs that delivery only and becomes an unchanged historical record after implementation review and merge. It does not start a Worker automatically.
- **`alex-coding:implement`** consumes the current work's merged contract when one exists; otherwise it uses the user's current request as acceptance. It writes and verifies the code, opens a code PR and handles author feedback through the project's existing review process. A completed contract does not force later direct work back through Plan; an unfinished Plan-owned delivery for the same work cannot be silently bypassed.

Plan and Implement respect existing human acceptance and merge restrictions. After opening a PR and registering author feedback monitoring, they automatically start one independent reviewer for that PR unless a reviewer is already assigned or the project requires a human-owned path. The plugin bundles `alex-coding:monitor` for author feedback, `alex-coding:review` for PR-bound independent review, their runtime scripts, and `gh_as`. Unsupported execution and notification capabilities are reported honestly; credentials stay with the existing CLIs.

### ProjectContext.md

A root `ProjectContext.md` gives Agents a concise map of project-specific requirements. Setup creates or aligns it as a required part of a Setup-owned technical baseline. It remains optional for repositories that have not accepted Setup: if absent, Plan and Implement use existing repository instructions, README and relevant project documents and continue with their general workflow. They do not create one as a side effect of feature work.

The canonical [Setup template](plugins/alex-coding/skills/setup/assets/ProjectContext.md) covers:

1. Project purpose and technology stack.
2. Code structure and architectural constraints.
3. Current authoritative requirements, active-contract locations and historical delivery-record locations.
4. Actual lint, test and build commands.
5. Human acceptance and existing delivery rules.
6. Exceptions, open questions and the agreed context-update process.

Reference existing documentation, record only verified facts, and adapt only what the project needs. The template is not authority to overwrite authored context. A narrower platform setup capability can add its verified platform-specific facts while preserving the same baseline contract.

### Install the plugin

After cloning this repository, install the complete plugin so its shared references are included. Do not copy only the Plan or Implement subdirectory.

Codex, from this repository root:

```sh
codex plugin marketplace add "$PWD"
codex plugin add alex-coding@alex-coding-studio
```

Claude Code:

```sh
claude plugin marketplace add alex-coding-studio/skills
claude plugin install alex-coding@alex-coding-studio
```

Start a new Codex task or restart Claude Code after installation to load the entries. This does not remove separately installed skills or replace an existing platform-specific plugin.

Example requests:

> Use alex-coding:setup to create this project as a verified local and GitHub technical baseline.

> Use alex-coding:setup to add this dependency in a separate Setup PR, then I will resume feature implementation.

> Use alex-coding:setup to upgrade this framework and include every compatibility change caused by the update.

> Use alex-coding:plan to plan this repository change and publish its accepted delivery contract.

> Use alex-coding:implement with this merged planning PR, full merge SHA and contract path.

> Use alex-coding:implement to fix this small, agreed-scope issue, then verify and deliver it according to the project rules.

## respond-to-agent

Turn a long Agent response into a local, interactive page. Answer individual matters, add qualifications, and export one contextual Markdown reply to paste back into your conversation.

- Free-text answers, single or multiple selections, and overall feedback.
- An editable **Response to Agent** dialog with **Copy all** and **Save as .md**.
- Exported answers include selected option text, not every unselected alternative.
- No server, account, network dependency, or Markdown reader.
- English and Chinese interface labels; automatic discovery and explicit invocation.

Answers live only in the open page. Copy or download your reply before closing or refreshing. Clipboard access depends on the browser; the page selects the text for manual copying when needed.

## git-sanity-check

Inspect Git branches, worktrees, and checkout state across a repository or a directory tree you choose. The Agent asks for the scan scope when you have not supplied it; no machine-specific workspace or saved scope is assumed.

> Use git-sanity-check to inspect all repositories under ~/Projects and ~/Work.

> Use git-sanity-check to inspect the repositories under this directory.

It discovers repositories recursively, handles paths with spaces and linked worktrees, and separates cleanup candidates from active, dirty, or uncertain work. GitHub metadata enriches the report when available; other repositories still receive local checks. It does not perform cleanup. By default it may fetch remote-tracking evidence without pruning; request offline/no-write inspection to use cached refs only.

If `respond-to-agent` is also installed, audits with multiple decisions prefer its interactive reply page. Otherwise the audit produces a normal report; neither skill is a required dependency of the other.

## Install

Clone this repository:

```sh
git clone https://github.com/alex-coding-studio/skills.git
cd skills
```

Copy the skill you want (`skills/respond-to-agent` or `skills/git-sanity-check`) into your Agent's personal skill directory. The examples below install `respond-to-agent`; replace the name with `git-sanity-check` for Git audits. For a fresh installation:

Claude Code:

```sh
mkdir -p ~/.claude/skills
cp -R skills/respond-to-agent ~/.claude/skills/
```

Codex:

```sh
mkdir -p ~/.codex/skills
cp -R skills/respond-to-agent ~/.codex/skills/
```

If you already have a skill with that name, compare it before replacing it. Start a new Agent session after installation if the skill is not yet listed. These examples use the default configuration locations; use your configured skill directory if customized.

## Use

Ask your Agent:

> Use respond-to-agent to turn your previous response into a page I can answer point by point.

Or:

> Use respond-to-agent to make your previous response easier to answer point by point.

The Agent prepares a JSON packet, generates an HTML file, and gives you a link to open locally. Fill in any items you want, click **Response to Agent**, edit the Markdown if needed, and copy or download it. Paste that reply into the original conversation.

The skill may also be selected automatically when a response contains many independent matters requiring user replies. A long informational explanation alone does not call for a form. Automatic selection depends on the host Agent.

## Generate directly

Requires Python 3.9 or newer and a modern browser supporting HTML dialogs and `light-dark()` colors. The Python tool uses only the standard library.

```sh
python3 skills/respond-to-agent/scripts/generate.py packet.json --output response.html
```

See the [input contract](skills/respond-to-agent/references/input.md) for the packet format. Existing output files are not overwritten. No report data is uploaded by the generated page.

## Development

```sh
python3 -m unittest discover -s skills/respond-to-agent/tests -v
python3 -m unittest discover -s tests -v
```

The skill includes its instructions, input contract, generator, offline template, and focused tests. Generated reports and personal answers do not belong in this repository.

## License

MIT. See [LICENSE](LICENSE).

## PR monitoring and GitHub roles

`alex-coding:monitor` runs one author listener per named task-owned PR. New deliveries use a disposable worktree created from the synchronized default checkout. Newly registered linked worktrees are force-removed after their exact PR head merges, independently of resetting the primary default checkout to the fetched remote commit; residue does not block disposal. The listener performs this mechanically, and retries partial/interrupted operations without a model wakeup. Existing legacy registrations retain their original protections. Codex submits directly to the existing session's native queue without inspecting desktop busy/idle state. One accepted batch stays active until the Agent acknowledges its concrete disposition; later events accumulate without adding more queue messages. Failed submissions remain pending for retry. Claude's persistent Monitor and acknowledgement behavior are unchanged. Existing old claims remain valid for their original acknowledgement commands.

`alex-coding:review` uses `review_pr.py` to run one independent Codex or Claude reviewer per PR. It starts after PR creation, resumes the same session for feedback or new heads, and waits without model calls after approval. Merge or closure ends it automatically. `retry` publishes the saved result; a user-authorized `continue` starts a fresh session with retained findings and cumulative rounds, even if the previous result could not publish. Invalid inline locations remain visible in the review body. See the [review runtime](plugins/alex-coding/skills/review/references/runtime.md) for CLI requirements, startup, recovery and legacy watcher migration. No desktop reviewer thread, recurring model wakeup or OS service is required.

Author Monitor also supports headless Codex tasks through an explicitly bound persistent local app-server endpoint, without desktop IPC. It does not create a replacement execution host; see Monitor's session-delivery runtime instructions.

### Configure gh_as

Install GitHub CLI and save the accounts through its normal login flow. Create `~/.config/alex-coding/github-roles.json` (or set `GH_AS_CONFIG` to another file). This contains account names and expected API identities, never tokens:

```json
{
  "bot": {"account": "saved-author-account", "login": "expected-author-login"},
  "admin": {"account": "saved-review-account", "login": "expected-review-login"}
}
```

From a persistent clone of this repository, link the helper into PATH. Inspect any existing gh_as before replacing it; this command intentionally refuses an existing destination:

```sh
mkdir -p ~/.local/bin
ln -s "$PWD/plugins/alex-coding/scripts/gh_as" ~/.local/bin/gh_as
gh_as bot api user --jq .login
gh_as admin api user --jq .login
```

Ensure `~/.local/bin` is on PATH. The helper supports github.com, validates the actual API identity on every call, uses the selected saved credential only in the child process, refuses aliases/extensions and debug-output flags, and never changes the globally active gh account. Different saved-account and API-login names are supported. Missing/malformed role configuration fails before credential access. Plugin installation alone does not create this PATH link or your account mapping.

### Migration from an older plugin

Keep each existing repository/task/PR identity and state directory. Before retiring an old script cache, inspect all live listeners and claimed batches; handle claimed events with their original acknowledgement contract. Stop only the verified old process and resume the same state with the new adapter. Do not reset ledgers or launch both copies. The namespace changes to alex-coding; state schemas and keys remain compatible. Already queued messages cannot be recalled. Update script paths used by launchers, then verify process and startup output.

## From accepted source to tested code

Plan accepts a user-confirmed Markdown file, document export or explicitly accepted discussion; no particular product-context application is required. It fixes readable source evidence and its revision/hash, translates accepted requirements into numbered Agent-readable clauses, and records the source mapping. The planning reviewer checks fidelity to that source, not just contract prose. Material ambiguities return to the user; equivalent technical wording does not need repeat approval. Private inputs are not automatically published.

Implement derives numbered acceptance cases from the merged clauses before implementation, then prioritizes unit-testable cases through natural Red/Green work. Test names or display names retain case IDs (for example `MOVE-02/T03`) so failures trace back to requirements. Existing adequate tests can be mapped and labeled instead of duplicated. Integration and human/UI evidence remain distinct; UI automation and CI UI jobs are not added by default.

Direct Issue work uses one proportionate outcome-to-test checklist without mandatory test renames or a separate contract. Diagnosed issues start from the named code and existing coverage, expanding only when current evidence warrants it. The [delivery helper](plugins/alex-coding/skills/implement/references/delivery.md) composes PR creation, native author monitoring, independent reviewer startup and authorized merge/completion while preserving all gates and runtime-specific transports. The optional [usage report](plugins/alex-coding/skills/implement/references/usage.md) supports later cost comparisons from explicit author and reviewer logs.

Reviewer complexity is selected by risk: regular Codex reviews use Sol and Claude reviews use Opus at low/medium/high, capped at high. High-certainty bounded work may use Luna max or Sonnet max. Unclassified/security-sensitive work uses Sol/Opus high. The runner passes and persists the choice, supplies incremental follow-up input and handles successful CI-only transitions without another model invocation. See the [model policy](plugins/alex-coding/skills/review/references/runtime.md#model-and-effort-policy).

Plan always emits the full handoff prompt, even when the user explicitly asks to pass it to a subagent. Contract IDs, source evidence and mapping travel with the fixed merge SHA and contract path.
