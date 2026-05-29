# harness_round03_02_6

## Design Summary

harness_round03_02_6 is a Round03_02 evolution of the round02_01_7 guarded single-executor harness. It keeps the direct ReAct topology, hard schema preflight, repeated-call blocking, SearchQA raw-query behavior, support records, compact planning packets, and phase-aware procedural memory. The local repair emphasis is abstract memory with action-side stale identifier quarantine.

## Module Change Map

- Planning repair: `quarantine_memory_planning` emits a compact packet and normalizes first-action JSON into ledger fields instead of letting it replace the plan.
- Cross-module interface repair: Action parses `evidence_slots`, `required_mutations`, and `verification_targets` from the latest plan and includes those counts in terminal readiness.
- Action repair: `quarantine_react` wraps the winner's guarded executor with bounded mutation closure, failure recovery hints, SearchQA raw-span checks, optional transform-source support, and current-evidence identifier quarantine.
- Memory repair: `abstract_quarantine_memory` masks concrete old values and labels retrieved memories as `procedure_hint_only`, preserving SearchQA leakage prevention.
- Preserved behavior: one acting executor, local schema preflight, repeated-failure guards, support-record logging, and compact summaries remain intact.

## Variant Personality

current-observation ledger with memory explicitly marked non-evidence.

Planning rules:
- Treat old memory as procedure_hint_only.
- Current task text and current observations are the only sources for concrete entities and IDs.
- For ToolHop, never transform a memory-only entity.
- For EnvScaler, resolve IDs from current list/get/search observations before mutation.

Action policy highlights: completion_policy=mutation_closure, planned_mutation_cap=3, ledger_review=False, searchqa_minimal_span=True, memory_argument_quarantine=True.

## Generalization Notes

The harness avoids item-specific entities, UUIDs, dates, answers, or benchmark IDs. It operates through generic slots, mutation rows, dependency edges, failure classes, and memory provenance labels so the same behavior can transfer to unseen tools and tasks.
