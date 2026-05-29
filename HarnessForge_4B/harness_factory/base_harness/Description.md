Planning: `generic_planning` (generic_planning)
Action: `single_react` (single_react)
Memory: `lightweight_memory`
Default bench: `generic`

Pairing policy:
- Reason: `fallback_single_react`
- If a same-name action module exists, use it directly.
- Otherwise fall back to `single_react`.

Runtime notes:
- Generated bundle: `base_harness`
- Builder uses a generic default unless the caller already supplies a benchmark-specific context.
- Benchmark-specific tool loaders validate their own required context.
- The builder keeps the current `ActionContext` object flow and only normalizes planning/action pairing.
