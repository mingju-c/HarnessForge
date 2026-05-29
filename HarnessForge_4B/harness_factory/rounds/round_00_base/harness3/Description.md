Harness summary:
- Planning: augment the task, retrieve relevant memory, then route work deliberately.
- Execution: a small mixed team combines one structured worker with several adaptive workers.
- Memory: reusable skill-like procedures can be surfaced during execution.
- Default bench: caller-provided

Coordination pattern:
- Use one stable planner-executor for high-precision work.
- Run several adaptive workers for broader exploration.
- Compare the returned candidates before committing to an answer.

Runtime notes:
- Generated bundle: `harness3`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
