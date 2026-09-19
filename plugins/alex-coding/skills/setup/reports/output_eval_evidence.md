# Output Evaluation Evidence

Four static with-skill versus baseline cases cover new-project creation, technical-only reference reuse, dependency separation, and a version-update transaction.

- Baseline assertion pass rate: `0%`
- With-skill assertion pass rate: `100%`
- Regressions: `0`
- Boundary cases: `1`
- Near-neighbor cases: `1`

Three separate holdout fixtures cover preserving an existing authored context, machine/external authority, and a first-CI failure after the one authorized initial push. Their with-skill assertion pass rate is recorded separately in `output_holdout_scorecard.md`.

An independent model forward review separately checked bare package/framework shorthand and unseen feature near-neighbors; see `model_forward_review.md`.

The scorecard and blind A/B pack are generated from recorded fixtures. Their `gate_pass` value means only that the recorded with-skill fixture satisfies its assertions without regressions. They are not provider-backed model execution or completed human blind review. Those remain missing evidence for promotion beyond experimental scaffold maturity.
