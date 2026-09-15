---
name: git-sanity-check
description: "Audit Git branches, worktrees and checkout state in a user-selected repository or directory tree. Report repository hygiene without cleanup; exclude code-quality and security reviews."
---

# Git Sanity Check

## Resolve the scope

Use paths explicitly supplied in the request or an unambiguous scope established in the current conversation. “This repository” means the current Git repository. “This workspace” means the current workspace directory. If neither is established, ask which directory or repositories to scan before discovery; never default to the home directory, filesystem root, or a personal workspace. Accept multiple roots and expand user-relative paths in the user's environment.

Keep scope in the conversation and repeat the resolved absolute roots in the report. Do not create a configuration file or persist scope across unrelated conversations. A repeat request in the same conversation can reuse the established scope. A nonexistent or unreadable root is an incomplete scan, not an empty success.

## Inspect

Read [the audit protocol](references/audit-protocol.md) before discovery and Git inspection. Recursively discover repositories within the selected roots, stopping at repository boundaries. Handle `.git` files, spaces, overlapping roots, linked checkouts, and read errors. Report outside-scope worktree paths without inspecting their files.

Never clean up, switch, commit, push, repair, or run mutating prune. Honor offline/no-write requests; otherwise disclose remote-tracking refreshes. Missing remote, hosting access, default branch, or complete history limits conclusions rather than stopping other repositories. Protect default and designated protected refs from cleanup-candidate classification.

## Classify and report

For in-scope checkouts off the default branch, report branch or detached commit, cleanliness, ahead/behind when known, and evidence of purpose. Clearly distinguish facts from judgments; say `purpose unclear` rather than inventing intent. Preserve external occupancy when judging whether a branch is a cleanup candidate.

Lead with scope, unique repository count, checkout count, audited/skipped/incomplete counts, refresh outcome, and finding totals. Use only applicable sections; identify each finding by repository and branch or worktree path. Explain skipped traversal and evidence gaps, including non-GitHub limitations. Reconcile totals against actual listed findings before delivery. End with what was refreshed, if anything, and confirmation that no cleanup occurred. Ask only for decisions that require the user; this report never authorizes cleanup.

## Optional interactive reply

When the report contains multiple matters requiring separate user decisions, prefer the installed `respond-to-agent` skill to turn the completed evidence-backed report into an interactive reply page. Read and follow that skill, preserving findings, scope, unknowns, and identifiers. In chat, give a short audit summary and the page link rather than duplicating the entire report. The generated form does not authorize cleanup, and no options may be preselected.

If `respond-to-agent` is unavailable, use a normal report with clearly addressable findings. Do not install it automatically or fail the audit. An informational report with no decisions, one simple decision, or an explicit request for plain text does not need a form.
