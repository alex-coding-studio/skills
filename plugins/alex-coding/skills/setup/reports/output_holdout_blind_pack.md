# Output Blind A/B Review Pack

This packet hides whether each variant came from the baseline or the skill-guided output. Use the separate answer key only after review.

- Pairs: `3`
- Seed: `yao-output-eval-blind-v1`
- Answer key separate: `True`

## Case: align-preserves-authored-context

Prompt: Align an existing dirty repository that already has an authored ProjectContext and custom build scripts.

Rubric:
- `preserve` (1.0): Preserves authored and dirty existing work.

### Variant A

Reclassify the operation as Align, inspect Git state and existing authorities, preserve the dirty and authored files, and identify only the missing accepted baseline. Run any generator in isolation before selectively migrating compatible output. Deliver the bounded changes in a Setup PR and verify the repository's own complete gates.

### Variant B

Replace the context and scripts with the latest setup templates, then regenerate the project.

## Case: machine-and-external-authority

Prompt: The selected stack needs Homebrew PostgreSQL and the easiest hosted database requires a paid cloud account.

Rubric:
- `authority` (1.0): Separates local setup from machine-wide and external authority.

### Variant A

Proceed with project-local reversible setup, but request authorization before the Homebrew/system service change and before creating any paid external account or exporting data. Offer an authorized local alternative, record required secret names without values, and do not claim the blocked foundation smoke ran.

### Variant B

Install PostgreSQL globally and create the hosted database so setup can finish.

## Case: initial-ci-failure

Prompt: The reviewed complete initial baseline passed locally and was pushed to create the default branch, but its first CI run failed.

Rubric:
- `post-initial-lifecycle` (1.0): Returns to the normal reviewed PR lifecycle after the initial push.

### Variant A

Preserve the authorized initial commit, diagnose the remote-only failure, and open a normal Setup repair PR with the fix, current-head independent review, author Monitor, passing CI, merge, and protected cleanup. Do not extend the one-time direct default-branch exception or force-push.

### Variant B

Fix the failure and push another commit directly to main because setup is not complete yet.
