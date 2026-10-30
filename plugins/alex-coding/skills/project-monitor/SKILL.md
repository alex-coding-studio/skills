---
name: project-monitor
description: "Work in a pooled worktree slot assigned by a Claude Project coordinator and follow its PR until merge or close, then release the slot. Use for Claude Project threads in a repository with a worktree pool; exclude ordinary task-owned worktrees."
---

# Monitor a Project Thread's PR from a Pooled Slot

A Claude Project runs a fixed pool of long-lived worktree slots per repository, plus the primary checkout as the pool main. The coordinator decides which thread gets work; the pool decides which slot it lands in. Slots are never deleted, so each keeps a warm build cache. This Skill replaces `alex-coding:monitor` registration and its disposable cleanup for those threads. Feedback handling, batch acknowledgement and reply publication are unchanged: read [claude-runtime.md](../monitor/references/claude-runtime.md) and [feedback-and-completion.md](../monitor/references/feedback-and-completion.md) for them, substituting this Skill's script.

Use the installed Skill's absolute script paths. Every pool command accepts `--repo <any checkout>` and prints JSON.

## Acquire a slot before the first edit

```sh
python3 <skill>/scripts/worktree_pool.py --repo <checkout> acquire --holder <thread-id> --branch <new-branch>
```

The pool picks the first free slot, fetches the remote default, creates the branch from it, runs the pool's `prepare` command and records the holder. Repeating the same holder and branch returns the same slot. Work only in the returned `path`. Never create a worktree for this task, and never run the generic lifecycle script or `delivery.py open/start`.

Exit status 3 with `"status": "busy"` means every slot is held. Do not create another checkout. Tell the coordinator; it either queues the work or explicitly asks for the pool main as overflow with `acquire --main`. The pool main must be on the default branch with no uncommitted changes, and nothing syncs it while it is held.

`acquire` refuses a slot with uncommitted changes or untracked files left by an earlier task. Report the paths to the coordinator instead of deleting someone else's files.

## Register the PR

After opening the PR, register it with its slot and start one persistent listener, exactly as the generic Claude runtime does:

```sh
python3 <skill>/scripts/project_pr_monitor.py --session <stable-session-id> --pr 'owner/repo#123' register --slot <slot-path>
python3 -u <skill>/scripts/project_pr_monitor.py --session <stable-session-id> --pr 'owner/repo#123' run --interval 45
```

Arm the `run` command through the `Monitor` tool with `persistent: true`, or pass `--session-remote` on `register` when the host supplies an endpoint. Registration binds the PR to the slot in the pool, so only this PR or its holder can release it.

## Release when the PR ends

When the listener sees the PR merged or closed, it releases the slot itself:

- A slot detaches to the fetched remote default. The pool main switches back to the default branch and fast-forwards.
- The local branch is deleted only when its head is the PR's final head, matches the remote branch, or has already landed on the default branch. Otherwise it is kept and reported, so committed work is never lost.
- Uncommitted changes stop the release and keep the slot held.
- After a merge, the pool main fast-forwards when it is free, on the default branch and has no uncommitted changes. Untracked files there are left alone. When it moves, the pool runs `prepare` and starts the background `warm` command.

The terminal batch carries the release result. When it says `released`, tell the coordinator the slot is free, then acknowledge the batch. Otherwise fix the reported cause and run `complete`, which re-verifies the PR and retries the release:

```sh
python3 <skill>/scripts/project_pr_monitor.py --session <stable-session-id> --pr 'owner/repo#123' complete
```

Run `complete` yourself right after merging your own PR.

When project instructions waive review for version or pin bumps, run the Implement skill's `delivery.py pin-check` on the opened PR. Only a `pin-only` result skips Review; merge it with `delivery.py pin-merge` once checks pass, then run `complete`. See the Implement [delivery reference](../implement/references/delivery.md#version-or-pin-bumps-under-a-project-waiver).

## Pool administration

These commands belong to the pool owner, not to a task thread:

```sh
python3 <skill>/scripts/worktree_pool.py --repo <checkout> init --prepare '<command>' --warm '<command>'
python3 <skill>/scripts/worktree_pool.py --repo <checkout> add-slot --slot <existing-linked-worktree>
python3 <skill>/scripts/worktree_pool.py --repo <checkout> remove-slot --slot <free-slot>
python3 <skill>/scripts/worktree_pool.py --repo <checkout> status
python3 <skill>/scripts/worktree_pool.py --repo <checkout> sync-main
```

The pool state lives in the repository's Git common directory, so every checkout sees the same pool. `add-slot` locks the worktree with `git worktree lock`, which also keeps generic post-merge cleanup from removing it.

## Validation

Run `python3 -m unittest discover -s tests -p test_worktree_pool.py -v` from the public skills repository.
