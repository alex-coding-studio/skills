# Skills

Practical Agent skills from Alex Coding Studio. Each skill includes the instructions and small tools needed to complete a focused workflow.

## alex-coding plugin

General GitHub PR-based planning and implementation, guided by the current repository rather than a fixed technology stack.

- **`alex-coding:plan`** turns accepted requirements into a delivery contract and documentation PR. After the required review and merge, it returns an Implement prompt bound to the actual full merge commit, contract path and acceptance IDs. It does not start a Worker automatically.
- **`alex-coding:implement`** consumes that merged contract, writes and verifies the code, opens a code PR and handles author feedback through the project's existing review process. A small settled direct request can bypass Plan; an unfinished Plan-owned contract cannot.

Both skills respect existing human acceptance and merge restrictions. They do not create another reviewer pipeline when the project already has a reviewer. They do not bundle a monitor, credential store or cleanup daemon; configured integrations can be used when available, and unavailable automatic follow-up is reported honestly. Reviewer and monitor integrations may be added separately in a future release.

### Optional ProjectContext.md

A root `ProjectContext.md` gives Agents a concise map of project-specific requirements. It is **optional**. If absent, Plan and Implement use existing repository instructions, README and relevant project documents and continue with their general workflow. They ask only about missing facts that actually block the current task, and do not automatically create a context file.

A [plain example](plugins/alex-coding/examples/ProjectContext.md) covers:

1. Project purpose and technology stack.
2. Code structure and architectural constraints.
3. Authoritative requirements and contract locations.
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
