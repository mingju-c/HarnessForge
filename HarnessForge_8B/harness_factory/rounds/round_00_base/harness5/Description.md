Harness summary:
- Planning: decompose the objective into tracked sub-tasks with explicit status updates.
- Execution: a hierarchical coordinator advances the plan while checking progress after key actions.
- Memory: graph-style text and tool memory supports reuse across runs.
- Default bench: caller-provided

Coordination pattern:
- Break the objective into manageable units before execution.
- Keep plan state synchronized with explicit progress tools.
- Synthesize only after the tracked work items are resolved.

Runtime notes:
- Generated bundle: `harness5`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
