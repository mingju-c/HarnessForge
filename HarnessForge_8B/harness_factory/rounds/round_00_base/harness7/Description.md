Harness summary:
- Planning: outline a few parallel angles worth checking.
- Execution: launch a direct batch of generic solvers and compare their reports.
- Memory: maintain a compact running cheatsheet of reusable findings.
- Default bench: caller-provided

Coordination pattern:
- Keep the initial plan small and parallel-friendly.
- Run several independent solver passes in one batch.
- Synthesize after comparing the returned evidence and candidate answers.

Runtime notes:
- Generated bundle: `harness7`
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The coordinator can launch 2-4 generic agents in a single parallel batch.
