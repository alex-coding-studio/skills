# Skills

Practical Agent skills from Alex Coding Studio. Each skill includes the instructions and small tools needed to complete a focused workflow.

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

> 用 git-sanity-check 检查一下这个目录下的仓库。

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

> 用 respond-to-agent 加工一下你刚才的回答。

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
```

The skill includes its instructions, input contract, generator, offline template, and focused tests. Generated reports and personal answers do not belong in this repository.

## License

MIT. See [LICENSE](LICENSE).
