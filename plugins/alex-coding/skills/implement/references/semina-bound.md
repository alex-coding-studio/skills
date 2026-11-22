# Task-card delivery

Read this when the work has a Semina task card: one from Plan, a paired Issue card, or a task the execution host bound to this session. Small direct fixes without a task card skip this file. When the dispatching agent says it keeps the card, leave status to it and still do the card alignment below.

The PR runner never calls Semina. Its events wake this session, and this session sets the state with `semina_update_task`. Read the task (and its project when needed) before each working turn and before each write; pass the current revision and reconcile on `REVISION_CHANGED`.

## Status points

| Point | Status | Content |
| --- | --- | --- |
| Accepted work starts or resumes | `in_progress` | Claim the card |
| A PR is opened | `in_progress` | Append the PR URL to the task references |
| Waiting on CI, review or merge | `in_progress` | No change; these waits end on their own |
| Only the user can unblock the work (a decision, UI or human acceptance, missing information, an authorization) | `blocked` | Write exactly what the user must do in the task description, and ask in your own conversation; Semina delivers no answers |
| The user answers | `in_progress` | Record an approved direction change on the task card right away |
| The last PR has merged and acceptance is met | `completed` | Same call carries `knowledgeImpact`: `{cardIds: [...]}` for cards created or updated, or `{none: "one-line reason"}` |

A started card never returns to `not_started`. A task delivered in several PRs stays `in_progress` between them; only the last merge completes it.

## Align cards before merge

After the independent reviewer approves and before merge, compare the final diff with the decision cards the task references and the module card it belongs to. Rewrite them in place so they describe what actually ships: changed decisions, a new reusable pitfall, the module's current state. Mark replaced decisions `superseded` with `supersededBy`. Send the user each card link. Do this before merge because the task worktree is force-removed after merge. The reviewer does not review card edits.

Keep process narrative out of cards. Evidence stays in the PR description and reviews; Semina holds decisions, state and links to the PRs.
