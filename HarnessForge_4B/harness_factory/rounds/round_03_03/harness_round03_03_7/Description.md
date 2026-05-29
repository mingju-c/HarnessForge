# harness_round03_03_7

Memory-guided variant: focuses on compact abstract lessons and phase-specific reminders while preserving current observations as the only evidence.

## Module Change Map

- Planning repair: `route_memory_planning` normalizes every initial plan into a fixed route ledger with `evidence_slots`, `dependency_edges`, `required_mutations`, `verification_targets`, `answer_format`, and `terminal_policy`. Tool-call-shaped plans are repaired into ledger fields before Action sees them.
- Action repair: `route_memory_react` keeps the single executor but replaces blocker-after-progress partial commit with all-slot terminal readiness. `complete_task` is ready only when planned stateful mutation slots are succeeded or verified.
- Action support repair: final answers use slot-bound support records with source observation, relation tokens, and deterministic-transform allowance; answer-span presence alone is not enough in strict variants.
- Action recovery repair: schema, repeat, not-found, enum, authorization, empty-action, terminal, and unsupported-final failures are assigned repair classes so the next move changes argument source, relation path, or tool family.
- Memory repair: `compact_route_memory` stores compact route/failure-class lessons instead of long raw traces with stale identifiers. Memory is always a procedural hint, never current evidence.
- Builder/wiring repair: metadata names `round_03_03`, candidate index `7`, and the local planning/action/memory systems consistently.

## Variant Difference

Design focus: route-aware procedural memory plus validated ledger and moderate guards.

This candidate is intentionally compact: no multiple acting agents, no benchmark-specific entity branches, and no hard-coded task answers. It preserves the winner's direct ReAct topology and hard schema preflight while repairing the diagnosed ledger, terminal, support, and recovery gaps.
