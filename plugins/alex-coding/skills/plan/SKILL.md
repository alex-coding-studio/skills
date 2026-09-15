---
name: plan
description: "Plan a repository change and publish its accepted Delivery Contract through a documentation PR. Use for scope, acceptance or contract work; exclude implementation and technical setup."
---

# Plan Repository Work

Own the requested outcome, scope and Delivery Contract when the user asks to plan work or produce one. `alex-coding:implement` owns implementation and its code PR. Work without a Delivery Contract uses the user's current request as its acceptance source and does not route through Plan first. This workflow targets GitHub PR-based repositories without assuming a language, framework, directory layout or product-document scheme.

## Establish the input

1. Read [project context](../../references/project-context.md) and [delivery policy](../../references/delivery-policy.md). Identify the repository, relevant accepted requirements and current project constraints. Read only the sources needed for this delivery slice; completed contracts from earlier deliveries are optional history, not acceptance criteria to reconcile.
2. Clarify material ambiguity and confirm scope and acceptance before authoring normative project documents. Reuse confirmation already given; do not ask again because a skill or session changed.
3. For an idea without a repository, prepare a provisional proposal and name repository setup as the prerequisite to the planning PR. Do not create a technical shell, fabricate a merge or claim an implementation-ready handoff.

## Build the contract

Read [source-fidelity.md](references/source-fidelity.md) and [contract.md](references/contract.md). Freeze the accepted input and preserve a source-to-clause mapping. Define observable outcomes, exclusions, source anchors, acceptance criteria and the evidence each criterion requires. Use the existing project documentation location; otherwise propose a simple repository-relative contract path rather than a new documentation system.

Apply platform-specific guidance from ProjectContext and its relevant references. Preserve explicit project choices. Do not introduce an iOS, web or backend checklist automatically, require EXPERIENCE.md or milestones, prescribe implementation internals without a real constraint, or add features to make the plan look complete.

Make project-specific pitfalls available to the Worker when relevant: explain the symptom, applicability and source. Unrelated pitfalls are not extra requirements. Review the contract for contradictory or untestable acceptance before publication. A planning review compares the frozen source against the numbered contract, checking completeness and unchanged meaning. It does not establish the correctness of code that has not been written.

## Publish and hand off

1. Write only the user-accepted planning documents on a work branch. Protect existing edits. Changes to ProjectContext follow its own approval and separate-PR rules; ordinary planning authorization does not bypass them.
2. Open a ready documentation PR with the configured author identity. Use Draft only when requested. Register author-side follow-up through the project's existing monitoring mechanism when configured and available.
3. Follow the existing reviewer path described in delivery policy. Address document feedback, obtain the required approval on the current head and satisfy applicable document checks. Do not launch another Reviewer by default when the project already provides one.
4. When existing user/project authorization permits merge and all required conditions are satisfied, merge and verify the terminal state. Otherwise retain the PR and state the missing authorization or gate. Never hand off an open or rejected planning PR as implementation-ready.
5. Produce [the merged handoff](references/handoff.md) with the repository, merged PR URL, full merge commit SHA, contract path and criterion IDs. Use the same configured post-merge completion mechanism as other project PRs; report preserved cleanup honestly.
6. Stop after giving the user a ready-to-use `alex-coding:implement` prompt. Do not start a Worker or create another task without explicit authorization.

If the accepted contract must change after handoff but before its implementation delivery finishes, publish the revision through the same planning process and explicitly replace that delivery's handoff. A moving branch must not silently redefine active implementation acceptance. Once implementation review and merge finish, leave that contract unchanged. Later work follows its own Delivery Contract when one exists and otherwise follows the user's current request.

Use the bundled `alex-coding:monitor` for newly opened task-owned PRs by default unless the user opts out or a project explicitly chooses another compatible mechanism. Read its runtime reference and verify actual startup; unavailable transport is a reported limitation, not permission to invent a background wakeup. `alex-coding:review` remains explicitly activated repository-wide reviewer work, not an author substitute.
