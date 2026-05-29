Harness summary:
- Planning: decide how much parallel investigation the task deserves.
- Execution: a coordinator launches multiple focused investigators, then synthesizes their findings.
- Memory: workflow traces can be retrieved to ground later decisions.
- Default bench: caller-provided

Coordination pattern:
- Start with parallel evidence gathering.
- Consolidate intermediate findings before final synthesis.
- Use the coordinator only for orchestration and final answer assembly.

Runtime notes:
- Generated bundle: `harness4`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
