---
name: implement
description: Implement accepted repository work from the current delivery contract when one exists or directly from the user's request when it does not, verify it using project rules, and deliver a code PR through review and feedback. Use for accepted feature implementation, bug fixes and continued coding. Exclude requested product planning, contract authoring or redefinition, project setup, reviewer-only work and unapproved implementation.
---

# Implement Accepted Repository Work

Own implementation, evidence, the code PR and author-side feedback. Use project context for domain and platform requirements; this workflow has no built-in iOS, web or backend architecture.

## Verify acceptance

Read [project context](../../references/project-context.md) and [delivery policy](../../references/delivery-policy.md) before work.

- For a Plan handoff, verify the planning PR is merged, the supplied full SHA is its actual merge result, the contract exists at that revision and the handoff identifies this delivery. Read that frozen contract and its cited sources, not a moving branch copy or every contract in the repository. Do not accept an open planning PR or merely a SHA that happens to exist.
- Compare relevant current project state with this delivery's accepted contract. Return a material contradiction or product change within the active delivery to `alex-coding:plan`. A mismatch with a contract completed by an earlier delivery is not a contradiction and does not require editing that historical contract.
- Reuse the user's accepted scope. Do not demand the same confirmation again because a Worker or task changed.
- If the current work has no Delivery Contract, use the user's current request and any direct clarifications as its acceptance source and proceed without a planning PR. Ask only about material ambiguity that prevents implementation or verification; do not turn clarification into Plan or contract authoring. The request may intentionally change behavior recorded by a completed contract; do not upgrade it to Plan or create a contract on that basis. This path does not permit silently bypassing or redefining an unfinished Plan-owned delivery for the same work.
- Preserve the project's rules for context changes, human approvals and protected documents; do not bundle an otherwise separately approved ProjectContext change into implementation.

## TDD boundary

Cover relevant normal and exceptional business scenarios through TDD. New behavior starts with a meaningful failing test, followed by the implementation that makes it pass. Add or strengthen a scenario test when coverage is missing. Do not perform mutation testing or deliberately break correct implementation, assertions or expected results to check whether existing tests fail. Historical plans and review suggestions do not override this boundary; preserve their business acceptance and express missing coverage as scenario tests.

## Implement and verify

1. Resolve current/default branches and worktree state. Use a work branch and isolate concurrent work when needed; never overwrite unrelated changes.
2. Read [execution.md](references/execution.md). Derive the numbered acceptance checklist before writing implementation code, retain the contract clause IDs in executable test names/display names, and prioritize unit-testable cases. Implement only accepted behavior, using the project's existing code organization and specialist guidance. Consult relevant risk/pitfall references identified by Plan.
3. Use meaningful tests and the project's declared verification entry points. Record evidence against the exact revision. Do not run platform-specific tools or require a device unless project rules and user authorization call for them.
4. Obtain explicit user acceptance when the task's criteria require human or subjective evaluation. A passing build or screenshot does not supply that acceptance. Follow the project's PR timing rule for UI or other human-gated work.
5. Open a ready code PR using the configured author identity; include outcome, scope, verification and material limits. Use Draft only when requested or explicitly required by an accepted project workflow.
6. Register the exact task-owned PR with the configured author-side monitor when available. Handle current comments, inline threads, reviews and check results under existing task authorization. A new commit does not resolve earlier feedback by itself.
7. Follow the project's existing reviewer path. Do not create a parallel reviewer or post an approval as though it came from independent review. Delegated implementation or an alternate independent reviewer requires the applicable authorization; neither is inferred from these skill names.
8. Recheck reviewed head, required approvals, checks, blocking feedback and mergeability. Merge only under existing authorization. A new head invalidates a previous head-bound approval. Use the configured completion/cleanup mechanism after a verified merge and preserve unsafe or unproven local work.

Report the delivered result, exact verification evidence, PR and remaining user-owned acceptance or cleanup limits. Do not infer a milestone transition or retrospective from merge; those are project-specific workflows.

Use the bundled `alex-coding:monitor` for newly opened task-owned PRs by default unless the user opts out or a project explicitly chooses another compatible mechanism. Read its runtime reference and verify actual startup; unavailable transport is a reported limitation, not permission to invent a background wakeup. `alex-coding:review` remains explicitly activated repository-wide reviewer work, not an author substitute.
