# harness_round03_02_8

## Design Summary

harness_round03_02_8 is a Round03_02 evolution of the round02_01_7 guarded single-executor harness. It keeps the direct ReAct topology, hard schema preflight, repeated-call blocking, SearchQA raw-query behavior, support records, compact planning packets, and phase-aware procedural memory. The local repair emphasis is low-overhead ledger, sparse memory, and conservative support repair.

## Module Change Map

- Planning repair: `light_ledger_planning` emits a compact packet and normalizes first-action JSON into ledger fields instead of letting it replace the plan.
- Cross-module interface repair: Action parses `evidence_slots`, `required_mutations`, and `verification_targets` from the latest plan and includes those counts in terminal readiness.
- Action repair: `light_ledger_react` wraps the winner's guarded executor with bounded mutation closure, failure recovery hints, SearchQA raw-span checks, optional transform-source support, and current-evidence identifier quarantine.
- Memory repair: `light_ledger_memory` masks concrete old values and labels retrieved memories as `procedure_hint_only`, preserving SearchQA leakage prevention.
- Preserved behavior: one acting executor, local schema preflight, repeated-failure guards, support-record logging, and compact summaries remain intact.

## Variant Personality

one-line slots for simple tasks with bounded ledger fields for complex tasks.

Planning rules:
- Use a one-slot fast path for direct SearchQA and one-hop lookup.
- Escalate to mutation rows or hop dependencies only when the task demands them.
- Keep memory sparse and abstract.
- Do not relax schema preflight or final support.

Action policy highlights: completion_policy=mutation_closure, planned_mutation_cap=2, ledger_review=False, searchqa_minimal_span=True, memory_argument_quarantine=True.

## Generalization Notes

The harness avoids item-specific entities, UUIDs, dates, answers, or benchmark IDs. It operates through generic slots, mutation rows, dependency edges, failure classes, and memory provenance labels so the same behavior can transfer to unseen tools and tasks.
