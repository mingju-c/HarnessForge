# harness_round03_02_2

## Design Summary

harness_round03_02_2 is a Round03_02 evolution of the round02_01_7 guarded single-executor harness. It keeps the direct ReAct topology, hard schema preflight, repeated-call blocking, SearchQA raw-query behavior, support records, compact planning packets, and phase-aware procedural memory. The local repair emphasis is failure-class recovery router with a read-only risk review tool.

## Module Change Map

- Planning repair: `recovery_packet_planning` emits a compact packet and normalizes first-action JSON into ledger fields instead of letting it replace the plan.
- Cross-module interface repair: Action parses `evidence_slots`, `required_mutations`, and `verification_targets` from the latest plan and includes those counts in terminal readiness.
- Action repair: `recovery_router_react` wraps the winner's guarded executor with bounded mutation closure, failure recovery hints, SearchQA raw-span checks, optional transform-source support, and current-evidence identifier quarantine.
- Memory repair: `recovery_rule_memory` masks concrete old values and labels retrieved memories as `procedure_hint_only`, preserving SearchQA leakage prevention.
- Preserved behavior: one acting executor, local schema preflight, repeated-failure guards, support-record logging, and compact summaries remain intact.

## Variant Personality

compact slots plus explicit recovery questions for schema, id, enum, repeat, and permission failures.

Planning rules:
- Name the active slot before each recovery step.
- For not-found or invalid-ID failures, prefer list/get/search discovery before retrying a mutation.
- For repeated failures, move to another pending slot or ask ledger_review for a read-only audit.
- Do not soften final support or stateful completion to escape a guard block.

Action policy highlights: completion_policy=mutation_closure, planned_mutation_cap=3, ledger_review=True, searchqa_minimal_span=True, memory_argument_quarantine=True.

## Generalization Notes

The harness avoids item-specific entities, UUIDs, dates, answers, or benchmark IDs. It operates through generic slots, mutation rows, dependency edges, failure classes, and memory provenance labels so the same behavior can transfer to unseen tools and tasks.
