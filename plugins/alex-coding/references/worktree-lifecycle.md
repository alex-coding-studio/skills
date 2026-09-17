# Disposable Task Worktrees

One delivery owns one task worktree. Continue its review fixes in that worktree; start a later independent delivery in a new one. The primary checkout stays on the remote default branch and is a rebuildable source copy. Keep durable project data and configuration outside task worktrees. Noncolliding untracked/ignored primary data is retained; it is not part of the source snapshot.

## Create

For a new delivery, run the bundled script before editing:

```sh
python3 <plugin>/skills/monitor/scripts/worktree_lifecycle.py \
  --repository <existing-repository> --destination <new-absolute-worktree-path> \
  --branch <new-task-branch>
```

The script resolves the remote default, requires the primary checkout on it, fetches without a stale-cache fallback, resets tracked source to the fetched commit and creates the task worktree from that exact SHA. It serializes with Monitor completion through the common Git directory lock. Both `main` and `master` work without a hardcoded default. An existing destination or branch is never reused as a new delivery. Do not switch an unrelated primary branch or bypass a failure; reconcile that checkout before adopting this lifecycle.

## Develop and merge

Implement and verify in the task worktree. Create its ready PR, register its exact owned checkout with Monitor, handle feedback and obtain the required independent approval before merging. Registration of a linked checkout records `lifecycle: disposable-v1`. Registration without a proven owned checkout grants no deletion authority. Review and business correctness stay with PR delivery, not cleanup.

Publish or export every result that must survive before merge. After merge, all remaining files and uncommitted changes in this task directory are disposable, regardless of tracked, untracked or ignored status. Stop using the task directory once its PR merges.

## Complete

Monitor verifies the merged PR targets the registered default branch and the worktree/branch still names its final head. A squash merge is sufficient evidence; the original head need not be an ancestor of default. Another delivery's later commits, a changed identity, a locked worktree and an unmerged PR are outside the deletion boundary.

The script performs two independent operations:

1. Fetch and reset the primary default checkout to the fetched remote commit. This is overwrite synchronization, not rebase; local default commits, tracked edits and obstructing files do not need merging.
2. Run `git worktree remove --force` on the exact registered task path, then remove its final-head branch reference. No file classification or process-cwd scan gates disposal.

The receipt contains separate `sync` and `cleanup` results. A synchronization error must not prevent deletion, and a deletion error must not undo successful synchronization. Only both succeeding is `cleaned`. Partial/interrupted disposable operations can be retried after fresh identity checks; an already absent directory/branch is normal on retry. The model-free listener retries partial operations. The author may also invoke the existing per-PR `complete` command immediately after its own merge, from outside the task directory.

Existing registrations without this lifecycle marker keep their original cleanup and acknowledgement contracts. This change does not bulk-migrate or delete old worktrees. Keep each PR's runner and ledger independent and place runtime scripts/state outside directories they may delete.
