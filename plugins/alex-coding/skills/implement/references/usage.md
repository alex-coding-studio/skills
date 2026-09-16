# Optional cost comparison

Use `scripts/usage_report.py` only for an explicitly requested measurement. It reads named local logs without model calls and prints counters, never message bodies. Do not scan every session, add recurring telemetry or launch comparison agents for routine implementation.

```sh
python3 <implement>/scripts/usage_report.py \
  --input claude author <native-session.jsonl> \
  --input claude reviewer <review-invocation.events.jsonl>
```

Repeat `--input RUNTIME ROLE PATH` for each explicitly identified source. `RUNTIME` is `claude` or `codex`; use role names such as `author` and `reviewer`. Include every independent reviewer invocation. Claude native records deduplicate split assistant blocks by session/message ID and retain final usage counters. Claude CLI result envelopes are invocation totals, not individual model calls. Codex native cumulative totals are counted once; CLI `turn.completed` totals are handled separately. Do not combine native logs with summaries of the same session. Duplicate sources, conflicting roles, mixed formats and decreasing cumulative counters fail instead of silently inflating totals.

Input counters are normalized into uncached input, cache read, cache write and output. Reasoning output is not added a second time. Actual API-call counts are only reported when native message identities establish them; unavailable counts/context sizes stay null. Raw token totals across runtimes are not prices. Context peaks from CLI invocation aggregates are unavailable.

Optional `--rates <json>` supplies prices per million keyed by `runtime:role`, for example:

```json
{"claude:author":{"input":2,"cache_read":0.2,"cache_write":2.5,"output":10}}
```

These numbers illustrate the format, not current pricing. Supply verified rates matching the actual model, provider and cache TTL. Split differently priced sources into separate role labels; do not use a single cache-write price for mixed TTLs unless intentionally reporting an explicit approximation. Missing rates leave cost null. Estimates are not billing reconciliation.

For a later Sonnet comparison, record the baseline/candidate plugin revisions, actual author/reviewer models and efforts, accepted task and checks, source paths, elapsed time and outcome. Keep conditions comparable; a different task or model is an observational comparison rather than an isolated causal experiment. Reuse the historical baseline and start with one candidate delivery. Preserve the measurement command and JSON output locally instead of publishing private logs.

Phase costs and author-wakeup reasons require explicit timing/event evidence; this tool does not guess them from prose. Inspect the existing PR runner/Monitor event records when diagnosing repeated invocations. Do not infer savings from diff size, tool count or a theoretical quadratic context model.
