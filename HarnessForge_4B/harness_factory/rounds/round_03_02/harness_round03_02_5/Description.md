# harness_round03_02_5

## Design Summary

harness_round03_02_5 is a Round03_02 evolution of the round02_01_7 guarded single-executor harness. It keeps the direct ReAct topology, hard schema preflight, repeated-call blocking, SearchQA raw-query behavior, support records, compact planning packets, and phase-aware procedural memory. The local repair emphasis is stateful terminal contract with rare exceptional partial completion.

## Module Change Map

- Planning repair: `stateful_contract_planning` emits a compact packet and normalizes first-action JSON into ledger fields instead of letting it replace the plan.
- Cross-module interface repair: Action parses `evidence_slots`, `required_mutations`, and `verification_targets` from the latest plan and includes those counts in terminal readiness.
- Action repair: `stateful_contract_react` wraps the winner's guarded executor with bounded mutation closure, failure recovery hints, SearchQA raw-span checks, optional transform-source support, and current-evidence identifier quarantine.
- Memory repair: `stateful_contract_memory` masks concrete old values and labels retrieved memories as `procedure_hint_only`, preserving SearchQA leakage prevention.
- Preserved behavior: one acting executor, local schema preflight, repeated-failure guards, support-record logging, and compact summaries remain intact.

## Variant Personality

operation-level mutation checklist with verification observations and terminal readiness.

Planning rules:
- Represent each requested state change as a separate mutation row.
- Mark terminal_ready only when rows are verified or an explicit blocker remains.
- Use partial completion only as an exceptional state, never as normal progress completion.
- Keep read-only and SearchQA routes lightweight.

Action policy highlights: completion_policy=mutation_closure, planned_mutation_cap=5, ledger_review=True, searchqa_minimal_span=True, memory_argument_quarantine=True.

## Generalization Notes

The harness avoids item-specific entities, UUIDs, dates, answers, or benchmark IDs. It operates through generic slots, mutation rows, dependency edges, failure classes, and memory provenance labels so the same behavior can transfer to unseen tools and tasks.
