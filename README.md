# Skills

Practical Agent skills from Alex Coding Studio. Each skill includes the instructions and small tools needed to complete a focused workflow.

## alex-coding plugin

General GitHub PR-based planning and implementation, guided by the current repository rather than a fixed technology stack.

- **`alex-coding:plan`** turns accepted requirements into a delivery contract and documentation PR. After the required review and merge, it returns an Implement prompt bound to the actual full merge commit, contract path and acceptance IDs. The contract governs that delivery only and becomes an unchanged historical record after implementation review and merge. It does not start a Worker automatically.
- **`alex-coding:implement`** consumes that merged contract, writes and verifies the code, opens a code PR and handles author feedback through the project's existing review process. Small settled logic changes, visual refinements and interaction refinements can use direct acceptance and bypass Plan, even when they evolve behavior delivered by an older completed contract; an unfinished Plan-owned delivery for the same work cannot be silently bypassed.

Both skills respect existing human acceptance and merge restrictions. They do not create another reviewer pipeline when the project already has a reviewer. The plugin also bundles `alex-coding:monitor` for author feedback, `alex-coding:review` for repository review, their notification and cleanup scripts, and the `gh_as` role helper. Unsupported transports are reported honestly; credentials stay in GitHub CLI.

### Optional ProjectContext.md

A root `ProjectContext.md` gives Agents a concise map of project-specific requirements. It is **optional**. If absent, Plan and Implement use existing repository instructions, README and relevant project documents and continue with their general workflow. They ask only about missing facts that actually block the current task, and do not automatically create a context file.

A [plain example](plugins/alex-coding/examples/ProjectContext.md) covers:

1. Project purpose and technology stack.
2. Code structure and architectural constraints.
3. Current authoritative requirements, active-contract locations and historical delivery-record locations.
4. Actual lint, test and build commands.
5. Human acceptance and existing delivery rules.
6. Exceptions, open questions and the agreed context-update process.

Reference existing documentation, leave unknowns explicitly undecided, and adapt only what the project needs. The example is not an instruction to change existing rules. Domain-specific setup tools can generate a richer version without changing these general skills.

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

`alex-coding:monitor` runs one independent listener per named task-owned PR, with separate state, batch and acknowledgement. `alex-coding:review` explicitly watches a repository for review work. Both support Codex desktop queue/IPC and Claude persistent Monitor delivery; see each skill's runtime reference for version-bound requirements. No OS service is installed.

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

Plan always emits the full handoff prompt, even when the user explicitly asks to pass it to a subagent. Contract IDs, source evidence and mapping travel with the fixed merge SHA and contract path.
