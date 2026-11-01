---
name: project-monitor
description: "Work in a pooled worktree slot assigned by a Claude Project coordinator and follow its PR until merge or close, then release the slot. Use for Claude Project threads in a repository with a worktree pool; exclude ordinary task-owned worktrees."
---

# Monitor a Project Thread's PR from a Pooled Slot

A Claude Project runs a fixed pool of long-lived worktree slots per repository, plus the primary checkout as the pool main. The coordinator decides which thread gets work; the pool decides which slot it lands in. Slots are never deleted, so each keeps a warm build cache. This Skill replaces the disposable cleanup of `alex-coding:monitor` with a slot release for those threads. Feedback arrives as state deliveries without acknowledgement; handle it and publish replies as [feedback-and-completion.md](../monitor/references/feedback-and-completion.md) describes.

Use the installed Skill's absolute script paths. Every pool command accepts `--repo <any checkout>` and prints JSON.

## Acquire a slot before the first edit

```sh
python3 <skill>/scripts/worktree_pool.py --repo <checkout> acquire --holder <thread-id> --branch <new-branch>
```

The pool picks the first free slot, fetches the remote default, creates the branch from it, runs the pool's `prepare` command and records the holder. Repeating the same holder and branch returns the same slot. Work only in the returned `path`. Never create a worktree for this task, never run the generic lifecycle script, and never run `delivery.py open/start` without `--slot`: without it the slot would be registered as a disposable worktree.

Exit status 3 with `"status": "busy"` means every slot is held. Do not create another checkout. Tell the coordinator; it either queues the work or explicitly asks for the pool main as overflow with `acquire --main`. The pool main must be on the default branch with no uncommitted changes, and nothing syncs it while it is held.

`acquire` refuses a slot with uncommitted changes or untracked files left by an earlier task. Report the paths to the coordinator instead of deleting someone else's files.

`acquire` and `release` stop build and test processes still running for that slot (command lines naming the slot path or its `ios.derivedDataPath`, such as `xcodebuild`, `swift-frontend` or the test watchdog, plus their children). Builds started from the Xcode app are left alone. The JSON lists what was stopped under `stopped_processes`.

## Open the PR and start its runner

Open the PR through Implement's delivery helper with the slot, from the slot path:

```sh
python3 <implement>/scripts/delivery.py open --runtime claude --session <stable-session-id> \
  --repository owner/repo --slot <slot-path> --title 'Concrete outcome' --body-file <pr-body> \
  --reviewer <verified-admin-login> --complexity medium --max-rounds 3 --review-runtime codex
```

It binds the PR to the slot in the pool, so only this PR or its holder can release it, and starts the PR's single runner: independent review, state delivery to this session and the slot release below. Without a host endpoint the receipt says `native-monitor-required`: start its `monitor_command` through the `Monitor` tool, then repeat `delivery.py start --pr owner/repo#123 --slot <slot-path>` with the same arguments to confirm it is active. Pass `--session-remote` when the host supplies an endpoint. A PR registered with `project_pr_monitor.py` before this version keeps that listener until the PR ends.

## Release when the PR ends

When the listener sees the PR merged or closed, it releases the slot itself:

- A slot detaches to the fetched remote default. The pool main switches back to the default branch and fast-forwards.
- The local branch is deleted only when its head is the PR's final head, matches the remote branch, or has already landed on the default branch. Otherwise it is kept and reported, so committed work is never lost.
- Uncommitted changes stop the release and keep the slot held.
- After a merge, the pool main fast-forwards when it is free, on the default branch and has no uncommitted changes. Untracked files there are left alone. When it moves, the pool runs `prepare` and starts the background `warm` command.

The terminal delivery carries the release result; no acknowledgement is needed. When it says `released`, tell the coordinator the slot is free. Otherwise the slot stays held and nothing retries on its own: fix the reported cause and run `complete`, which re-verifies the PR and retries the release:

```sh
python3 <skill>/scripts/project_pr_monitor.py --session <stable-session-id> --pr 'owner/repo#123' \
  --state-dir <runner-state-directory>/author complete
```

The runner's status (`review_pr.py status --pr owner/repo#123`) names its `state_directory`. For a PR registered before this version, omit `--state-dir`.

`open` and `start` run the review-exemption check themselves. A `review-exempt` receipt means the repository's `.shared-config` exemption covers the PR: no reviewer starts, a standalone `project_pr_monitor.py` listener follows the PR (start the receipt's `monitor_command` through the `Monitor` tool), and you merge with `delivery.py pin-merge` once checks pass; the listener then releases the slot. See the Implement [declared exemptions](../implement/references/delivery.md#declared-review-exemptions).

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
