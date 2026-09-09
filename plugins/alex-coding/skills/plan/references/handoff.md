# Verified Merged Handoff

After verifying the planning PR is merged, provide a prompt containing actual values:

```text
Use alex-coding:implement in <repository>.
Planning PR: <merged PR URL>
Contract revision: <full actual merge commit SHA>
Contract: <repository-relative path at that SHA>
Acceptance: <criterion IDs>
Source evidence and mapping: <frozen source reference and contract mapping path>
Read the project context and this frozen contract with its cited sources. Implement and verify the accepted scope, publish the code PR, and follow the project's review and author-feedback process. Return material scope or acceptance conflicts to Plan rather than redefining them.
```

Name any remaining human acceptance steps and known environment constraints. Do not label this ready if the contract is missing, the PR is unmerged or a material planning decision is unresolved. Verify the path at the actual merge revision, including after squash/rebase merges.

A cleanup-preserved result is a local operational limit to report, not evidence that the merged contract is absent. Do not read handoff content from a removed worktree. Fetch/read the verified revision as needed.

Always show the complete handoff prompt, including when the user explicitly authorizes a subagent to implement it. Pass that same visible packet to the subagent; spawning a Worker is not a substitute for the output. Emitting the prompt does not create a task or authorize automatic Worker dispatch. Preserve existing user authorization separately from the source document.
