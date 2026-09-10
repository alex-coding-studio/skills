# Queued author monitor delivery

The user needs author feedback delivered to the existing Codex task when desktop stream ownership cannot be discovered. The current idle snapshot preflight times out before the listener starts. Keep the existing idle-only default and provide an explicit queued mode for this task.

## Acceptance

- MQ-01: `run --delivery queued` starts without desktop snapshot access and sends pending feedback through `codex queue`; existing idle-only behavior remains the default.
- MQ-02: A failed queue command preserves pending events without claiming a batch. A successful queue claims one batch; later feedback waits for its acknowledgement.
- MQ-03: Queued mode never performs background checkout cleanup. A merged PR queues a terminal event instructing the receiving Agent to acknowledge processed feedback and call `complete`, which retains existing filesystem safety checks.
- MQ-04: Each PR retains its own process, lock and persistent state. Runtime selection and startup output identify the chosen delivery behavior.

## Verification

Use scenario tests with unavailable desktop state, queue failure/recovery and merged targets. Run the repository test suite. Verify a real PR-status message queues to this existing active task and observe its later delivery; a CLI success alone does not prove wakeup. No mutation testing.
