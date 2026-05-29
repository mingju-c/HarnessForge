Harness summary:
- Planning: explicit task planning with regular status summarization.
- Execution: one primary agent uses the current task tools directly.
- Memory: reusable workflow notes and prior solutions.
- Default bench: caller-provided

Coordination pattern:
- Start with a clearer plan than the base single-agent loop.
- Keep execution centralized in one active agent.
- Fall back cleanly when no harness-specific execution layer is available.

Runtime notes:
- Generated bundle: `harness2`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
