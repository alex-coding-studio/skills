# Audit protocol

## Discover repositories

A root that is a repository (or a subdirectory explicitly identified as “this repository”) selects that repository alone. Otherwise recursively search the directory tree. Detect both `.git` directories and `.git` files; validate candidates with Git, and stop descending once a repository is found. Do not scan its vendored repositories or submodules independently unless explicitly requested. Do not follow directory symlinks discovered during traversal; an explicitly selected symlink root may be resolved and reported. Use path-safe traversal that handles spaces and reports read errors; do not parse filenames by whitespace or silently drop hidden directories.

Deduplicate overlapping roots and linked worktrees by canonical Git common directory, retaining the discovered checkout paths. A linked worktree counts as a checkout of one repository, not another repository. Bare repositories have no primary checkout: report and skip them unless a bare-repository audit was requested. Do not infer “no repositories” from a failed search.

Git worktree metadata may name checkouts outside the selected roots. List these as outside scope, without inspecting their files or treating their cleanliness as known. Do not expand the scan to their parent directories. Paths explicitly selected as additional roots can be inspected.

## Gather evidence

This is an inspection task. Never delete branches or worktrees, switch branches, commit, push, clean, repair, or run mutating prune. A normal fetch may update remote-tracking refs and FETCH_HEAD; disclose that refresh. Unless the user requested offline or no writes, refresh the relevant remote with pruning and tag auto-follow disabled (`git fetch --no-prune --no-tags <remote>`). Offline requests use existing refs only. Use `git worktree prune --dry-run --verbose` solely to inspect stale metadata. Respect narrower user constraints and use `GIT_OPTIONAL_LOCKS=0` for local status reads.

Resolve each repository's remotes and default branch from available evidence. Prefer the remote hosting service's default branch, then a verified remote HEAD, then cached remote HEAD labeled as potentially stale. Do not assume `main`, `master`, `origin`, or that the current branch is the default. With several ambiguous remotes, report the ambiguity instead of guessing. Missing remote/default or authentication is a local-only or incomplete assessment, not a fatal error for other repositories. Never print credential-bearing remote URLs.

For GitHub remotes, enrich with archive status and PR state when authenticated access is available. Skip confirmed archived repositories and list them. Non-GitHub and local-only repositories still receive applicable local checks; unsupported archive/PR lookup means unknown. Do not infer a PR's state from its branch name. Bind any merged-PR evidence to the current branch tip: commits after a merge are not covered by that PR.

Inspect checkout status (including untracked files), `worktree list --porcelain`, prune dry-run output, local and remote branches, worktree occupancy, and ancestry/ahead-behind relative to the selected remote default. Missing objects, shallow history, failed refreshes, and Git errors limit the conclusion. A failed ancestry test alone cannot distinguish unmerged work from insufficient evidence.


Reference mechanisms: [worktree metadata and dry-run](https://git-scm.com/docs/git-worktree), [ancestry](https://git-scm.com/docs/git-merge-base), [fetch and pruning](https://git-scm.com/docs/git-fetch).

## Classification

Never classify the selected local or remote default branch, symbolic remote HEAD, or user/repository-designated protected refs as cleanup candidates. Unknown protection status is a limitation to disclose, not proof that a branch is disposable.

- Cleanup candidate branch: current tip is demonstrably included in the default branch or a corresponding merged PR, with no open PR or worktree occupancy. Identify local versus remote branches separately.
- Likely obsolete worktree: clean, current tip covered by merge evidence, no open PR or continuing-work evidence. Detached state alone does not prove obsolescence.
- Review needed: dirty, closed-unmerged PR, uncertain detached state, occupied branch, unavailable history, unknown external worktree state, or unclear purpose. Closed-unmerged does not mean disposable.
- Active: open PR or direct evidence of continuing work. Age and names alone do not establish activity or obsolescence.
- Stale metadata: prune dry-run identifies it as prunable; perform no pruning.

