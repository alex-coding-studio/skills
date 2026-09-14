# Owning-session delivery evidence

## Accepted scope

The user requested an author-monitor fix after a headless task could create its PR but could not start monitoring because desktop IPC discovery timed out. The monitor must deliver to the task's actual execution owner without requiring desktop injection. This delivery adds an explicitly bound persistent local app-server route. It does not change a product's short-lived execution host, create a new executor, or grant new task authority.

Owner: alex-coding maintainers. Review cadence: recheck the live transport on Codex upgrades and changes to the host integration. Output contract: one PR-scoped pending ledger and exact-batch acknowledgement, routed to the original thread. Rollback boundary: keep registered session routes and pending batches; stop their listeners before reverting the adapter, and do not redirect them into desktop delivery.

## Acceptance cases

| Case | Expected behavior | Evidence |
| --- | --- | --- |
| SESSION-01 | Deliver to the registered session owner without desktop IPC or config overrides | `test_SESSION_01_routes_to_owner_without_desktop_or_config_overrides`; live test below |
| SESSION-02 | Unavailable owner leaves feedback pending, not acknowledged | `test_SESSION_02_unavailable_owner_preserves_pending_batch` |
| SESSION-03 | Bind one endpoint per session; refuse rerouting or migrating a claimed batch | `test_SESSION_03_target_route_cannot_change_or_move_a_claim` |
| SESSION-04 | Reject nonlocal, credential-bearing and ambiguous endpoints | `test_SESSION_04_rejects_nonlocal_or_ambiguous_endpoints` |
| SESSION-05 | Restart a bound target in session mode without desktop checks; refuse a desktop override | `test_SESSION_05_bound_startup_selects_session_and_refuses_desktop_override` |

These new tests first failed naturally because session delivery and binding did not exist, then passed after implementation. Existing author-core, desktop, Claude and cleanup tests remain the regression gates. Temporary file-backed state tests prove adapter behavior, not a live execution host's ownership lifecycle.

## Live compatibility: Codex 0.153.1

On 2026-09-14 UTC an isolated temporary loopback app-server owned one disposable read-only test thread. No production task was resumed or changed. Its model was gpt-5.6-sol. No tools or file changes were requested.

1. `codex queue --remote <loopback-endpoint> --thread <test-thread>` submitted an exact-reply prompt. Reading the same thread showed a completed turn and `MONITOR_SESSION_DELIVERED`. No desktop IPC was used.
2. While the server emitted `turn/started` for a counting prompt, the modified monitor's `Runtime.deliver` submitted a second exact-reply prompt. Both turns completed on that same thread. The first ended at Unix timestamp 1789364658; the second started at 1789364658 and ended at 1789364660 with `MONITOR_SECOND_BATCH`. This verifies native busy-to-idle queue scheduling rather than concurrent duplicate execution in this scenario.
3. The CLI connected to an explicit temporary Unix endpoint and rejected an intentionally nonexistent thread through `thread/queue/add`. This verifies Unix transport negotiation, not full Unix end-to-end execution.

The [official app-server documentation](https://learn.chatgpt.com/docs/app-server) describes persisted thread identity, resume and runtime state. The installed CLI help and generated protocol schema establish this version's `queue --remote` capability. The live test, not help text alone, establishes observed consumption.

## Trust report and remaining evidence

No credential reads, global account switches, permission overrides, daemon installation or background cleanup are added. Only an explicit local endpoint is accepted. Routing is frozen at session and PR level; it does not cryptographically attest the service at that address. The host must retain ownership of its endpoint and avoid concurrent independent executors for the same thread. A dead endpoint preserves pending feedback instead of changing transport.

Missing evidence: end-to-end integration with a production Board host, restart/reboot recovery of that host, and full Unix-socket model execution. A short-lived stdio driver still needs a persistent host integration. Queue acceptance timeouts can still cause duplicate delivery on retry; exactly-once transport is not claimed. There is no new approval authority or promise that a model will correctly process every review.

Yao Meta Skill informed the explicit target boundary, compact runtime reference, acceptance cases and trust limits. This is a scoped adapter update, not a claim of a fully certified Yao package migration; independent reviewer approval and broader certification telemetry are not supplied by these tests.

## Repository and Skill checks

- `python3 -m unittest discover -s tests -q`: 190 passed, including package reference closure and the five new session cases.
- `python3 -m unittest discover -s skills/respond-to-agent/tests -q`: five passed.
- `git diff --check`: passed.
- Yao `trigger_eval.py` with the bundled `evals/trigger-cases.json` and `evals/trigger-config.json`, threshold 0.5: six of six deterministic smoke cases passed. These are phrase-based checks, not blind or model-judged routing evidence.
- Yao `validate_skill.py`: failed on the pre-existing missing `agents/interface.yaml`; the repository uses its existing `agents/openai.yaml` format. The same check fails on unchanged main.
- Yao `resource_boundary_check.py`: failed its 1,000-token default initial-load budget on both unchanged main (1,641 estimated tokens) and this revision (1,841). No unused resource directory warning remains. This is recorded as a limit, not a passing certification or an authorization to migrate unrelated packaging.

Broader Skill OS certification, blind output eval and independent approval remain missing evidence. This update makes no certification or public-quality claim beyond the concrete checks above.
