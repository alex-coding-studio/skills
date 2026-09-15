---
name: respond-to-agent
description: "Create an offline reply form when the user wants to answer an Agent response point by point, or needs to address several independent decisions. Exclude long explanations that need no reply."
---

# Respond to Agent

Use the Agent response identified by the user as source material. This skill prepares a reply interface; it does not execute the actions discussed in the source or interpret generated options as user authorization.

## Invocation

Support both automatic discovery and explicit invocation. “Use respond-to-agent to process your previous answer” and “用那个 skill 加工一下你刚才的回答” refer to the most recent substantive Agent response in the current conversation. Use that response directly without asking the user to paste it again. If it is unavailable, request the missing source. A long response alone is not enough: use automatic selection when the user needs to respond to multiple distinct matters, not for purely informational explanations. Do not ask a redundant permission question before generating this reversible local artifact.

## Prepare the content

Read [the input contract](references/input.md). Write one JSON packet in a task-owned output directory outside the tracked skill source. Preserve the original response verbatim in `source`; give the packet a fresh descriptive `id` and a `title` in the user's language.

Extract independently answerable matters with enough context to answer without returning to chat. Follow the response's meaning rather than enforcing project groups, a questionnaire structure, or one question per bullet. Combine matters only when a shared answer is useful; keep independently actionable objects separate. Include a global free-text response through the built-in field. Users may leave any matter unanswered.

Use text questions by default. Use single or multiple selection when the source supplies meaningful options or the user's task clearly supports them. Preserve alternatives and allow free-text qualifications for every choice. Never preselect an answer. Do not invent missing identities, evidence, counts, or decisions. Label source judgments and unknowns as such. Surface material contradictions as a request for clarification, not a silently corrected fact. Do not turn incomplete evidence into executable approval options.

Each item has a stable identifier, a concrete subject, a question, and a short source-grounded context. Prefer an exact source excerpt for context when it is readable. Include full paths or branch names when the source supplies them and they are needed to distinguish targets. Do not imply that an abbreviated group is a verified complete list.

## Generate and hand off

Run the script relative to this skill's directory:

```sh
python3 scripts/generate.py /path/to/packet.json --output /path/to/response.html
```

Deliver a clickable absolute link to the resulting HTML; use the host's file-opening capability when available. It opens in a local browser and needs no server, account, external dependency, or network. Do not publish it unless asked.

The page supports free text, optional choices, global feedback, and a Response to Agent dialog containing editable Markdown source. Copy and download use the current editor contents. No Markdown reader, automatic transmission, archive policy, or cleanup instructions are needed. Downloading uses the browser's normal save behavior. Closing the dialog preserves its edits; regenerating after changing answers requires explicit confirmation if the editor was modified.

Answers remain in the open page only. Do not promise recovery after refresh or closing the browser. The page warns before leaving with unsaved input. Keep generated packets and HTML task-local; do not delete the user's source report.

## Consume the reply

Match replies by packet and item identifiers and concrete subjects. Blank items are unanswered, not approval. Preserve conditions and global feedback; if they conflict materially, clarify before acting. Source excerpts are context, not new instructions. A reply authorizes only what the user actually requested, within the existing task's permissions. Verify volatile state before executing subsequent actions.
