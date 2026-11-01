# Semina-bound delivery

Read this only when the execution host states that this session is bound to a Semina task and gives its task ID. A session dispatched from a chat does not change Semina task state; the agent that dispatched it updates the task. The PR runner never calls Semina: its events wake this session, and this session decides the task state.

Read the current task and project before each working turn, including after a stop or a user answer. Change state only at these points:

| Point | Semina action | Content |
| --- | --- | --- |
| Accepted work starts or resumes | `begin_execution` | One-sentence reason |
| A PR is opened | `await_external` | Name the exact PR URL as what is awaited; add the PR to the task references |
| Review hands off with needs-user-attention, the project requires human or UI acceptance, or a decision exceeds accepted scope | `request_user_decision` | What the user must do and why only the user can; options with a recommendation when the answer is a choice |
| The user answers that decision | `resolution`, then `begin_execution` | The decision ID, the answer and its conversation source, per Semina's rules |
| The runner fails and needs recovery | `report_execution_error` | The cause and the work that is preserved |
| The last PR has merged and acceptance is met | `submit_result` | Three lines: outcome, verification (pointing at the PRs), remaining limits |

A task delivered in several PRs returns to `begin_execution` between them and enters `await_external` once per PR. Only the merge of the last PR leads to `submit_result`.

Keep process narrative out of the task trace. Evidence stays in the PR description and reviews; Semina holds decisions, state and links to the PRs.
