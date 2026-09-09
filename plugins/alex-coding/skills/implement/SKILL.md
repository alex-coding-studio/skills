---
name: implement
description: Implement accepted repository work from a merged delivery contract or a small settled direct request, verify it using project rules, and deliver a code PR through review and feedback. Use for accepted feature implementation, bug fixes and continued coding. Exclude new product planning, contract redefinition, project setup, reviewer-only work and unapproved implementation.
---

# Implement Accepted Repository Work

Own implementation, evidence, the code PR and author-side feedback. Use project context for domain and platform requirements; this workflow has no built-in iOS, web or backend architecture.

## Verify acceptance

Read [project context](../../references/project-context.md) and [delivery policy](../../references/delivery-policy.md) before work.

- For a Plan handoff, verify the planning PR is merged, the supplied full SHA is its actual merge result, and the contract exists at that revision. Read the frozen contract and cited sources, not a moving branch copy. Do not accept an open planning PR or merely a SHA that happens to exist.
- Compare relevant current project state with the accepted contract. Later code can change implementation details but cannot silently replace acceptance. Return material contradictions or product changes to `alex-coding:plan`.
- Reuse the user's accepted scope. Do not demand the same confirmation again because a Worker or task changed.
- A small direct request with settled requirements and an agreed verification method may proceed without a planning PR. This exception does not permit bypassing an unfinished Plan-owned contract.
- Preserve the project's rules for context changes, human approvals and protected documents; do not bundle an otherwise separately approved ProjectContext change into implementation.

## Implement and verify

1. Resolve current/default branches and worktree state. Use a work branch and isolate concurrent work when needed; never overwrite unrelated changes.
2. Read [execution.md](references/execution.md). Implement only accepted behavior, using the project's existing code organization and specialist guidance. Consult relevant risk/pitfall references identified by Plan.
3. Use meaningful tests and the project's declared verification entry points. Record evidence against the exact revision. Do not run platform-specific tools or require a device unless project rules and user authorization call for them.
4. Obtain explicit user acceptance when the task's criteria require human or subjective evaluation. A passing build or screenshot does not supply that acceptance. Follow the project's PR timing rule for UI or other human-gated work.
5. Open a ready code PR using the configured author identity; include outcome, scope, verification and material limits. Use Draft only when requested or explicitly required by an accepted project workflow.
6. Register the exact task-owned PR with the configured author-side monitor when available. Handle current comments, inline threads, reviews and check results under existing task authorization. A new commit does not resolve earlier feedback by itself.
7. Follow the project's existing reviewer path. Do not create a parallel reviewer or post an approval as though it came from independent review. Delegated implementation or an alternate independent reviewer requires the applicable authorization; neither is inferred from these skill names.
8. Recheck reviewed head, required approvals, checks, blocking feedback and mergeability. Merge only under existing authorization. A new head invalidates a previous head-bound approval. Use the configured completion/cleanup mechanism after a verified merge and preserve unsafe or unproven local work.

Report the delivered result, exact verification evidence, PR and remaining user-owned acceptance or cleanup limits. Do not infer a milestone transition or retrospective from merge; those are project-specific workflows.
