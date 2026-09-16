---
name: implement
description: "Implement and deliver accepted repository changes, using the current Delivery Contract when present or the user request directly. Exclude planning, setup and review-only work."
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

Use TDD for unit-observable new behavior and concrete regressions: start with a meaningful failing scenario, implement the behavior, then return Green. Reuse adequate existing coverage. Documentation, prompt and mechanical changes use their applicable validation; do not manufacture unit tests or Red evidence for them. Never deliberately break correct code or assertions to test the tests. Historical plans and review suggestions do not override this boundary.

## Implement and verify

1. Resolve current/default branches and worktree state. Use a work branch and isolate concurrent work when needed; never overwrite unrelated changes.
2. Read [execution.md](references/execution.md). Derive the numbered acceptance checklist before writing implementation code, retain the contract clause IDs in executable test names/display names, and prioritize unit-testable cases. Implement only accepted behavior, using the project's existing code organization and specialist guidance. Consult relevant risk/pitfall references identified by Plan.
3. Use meaningful tests and the project's declared verification entry points. Record evidence against the exact revision. Do not run platform-specific tools or require a device unless project rules and user authorization call for them.
4. Obtain explicit user acceptance when the task's criteria require human or subjective evaluation. A passing build or screenshot does not supply that acceptance. Follow the project's PR timing rule for UI or other human-gated work.
5. Open a ready code PR using the configured author identity; include outcome, scope, verification and material limits. Use Draft only when requested or explicitly required by an accepted project workflow.
6. Register the exact task-owned PR with the configured author-side monitor when available. Handle current comments, inline threads, reviews and check results under existing task authorization. A new commit does not resolve earlier feedback by itself.
7. When independent review is required, invoke `alex-coding:review` for this exact PR using [review startup](../review/references/runtime.md). Starting the independent PR reviewer is part of Implement; do not wait for the user to open a session. Reuse an existing assigned reviewer and respect an explicitly human-owned project path. Pass acceptance and evidence, not a suggested verdict. The author never reviews or approves its own work. Verify actual runner startup and report unsupported execution as inactive.
8. Recheck reviewed head, required approvals, checks, blocking feedback and mergeability. Merge only under existing authorization. A new head invalidates a previous head-bound approval. Use the configured completion/cleanup mechanism after a verified merge and preserve unsafe or unproven local work.

Continue through the accepted scope, required verification and authorized delivery steps. A first implementation or passing test is not completion when accepted work remains. Pause only at an actual user-owned acceptance/review gate or a blocker that prevents further progress; complete independent authorized work first. Report the result, verification, PR and remaining gate or cleanup limit. Do not infer a milestone transition or retrospective from merge.

Use the bundled `alex-coding:monitor` for newly opened task-owned PRs by default unless the user opts out or a project explicitly chooses another compatible mechanism. Read its runtime reference and verify actual startup; unavailable transport is a reported limitation, not permission to invent a background wakeup. Independent Review stays attached to this PR after approval until merge, closure or a published user-attention handoff. Follow-up Issues, fixes, merge and protected cleanup remain author responsibilities. Do not extend the PR's review-round limit without an authorized user continuation.
