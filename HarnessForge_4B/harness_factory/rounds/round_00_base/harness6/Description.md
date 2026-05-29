Harness summary:
- Planning: create a short parallel work outline for a fixed worker pool.
- Execution: one coordinator delegates focused subtasks to generic workers and merges the results.
- Memory: reusable skill-like procedures can be surfaced during execution.
- Default bench: caller-provided

Coordination pattern:
- Keep the worker pool small and stable.
- Delegate only focused subtasks, not whole-task restatements.
- Merge concise worker reports instead of building deep hierarchies.

Runtime notes:
- Generated bundle: `harness6`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- Keep orchestration simple: inspect the worker board, delegate focused work, then finalize.
