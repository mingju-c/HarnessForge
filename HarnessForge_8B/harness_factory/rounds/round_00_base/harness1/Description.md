Harness summary:
- Planning: compact initial planning with periodic progress refreshes.
- Execution: one primary agent works directly with the available task tools.
- Memory: lightweight retrieval of prior takeaways when they help.
- Default bench: caller-provided

Coordination pattern:
- Keep the loop simple: plan once, execute directly, and summarize as needed.
- Prefer direct tool use over delegation.
- Fall back cleanly when no harness-specific execution layer is available.

Runtime notes:
- Generated bundle: `harness1`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
