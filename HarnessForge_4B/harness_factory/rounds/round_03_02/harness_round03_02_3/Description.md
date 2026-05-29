# harness_round03_02_3

## Design Summary

harness_round03_02_3 is a Round03_02 evolution of the round02_01_7 guarded single-executor harness. It keeps the direct ReAct topology, hard schema preflight, repeated-call blocking, SearchQA raw-query behavior, support records, compact planning packets, and phase-aware procedural memory. The local repair emphasis is dependency-checked multi-hop provenance with single executor.

## Module Change Map

- Planning repair: `hop_provenance_planning` emits a compact packet and normalizes first-action JSON into ledger fields instead of letting it replace the plan.
- Cross-module interface repair: Action parses `evidence_slots`, `required_mutations`, and `verification_targets` from the latest plan and includes those counts in terminal readiness.
- Action repair: `hop_provenance_react` wraps the winner's guarded executor with bounded mutation closure, failure recovery hints, SearchQA raw-span checks, optional transform-source support, and current-evidence identifier quarantine.
- Memory repair: `hop_procedure_memory` masks concrete old values and labels retrieved memories as `procedure_hint_only`, preserving SearchQA leakage prevention.
- Preserved behavior: one acting executor, local schema preflight, repeated-failure guards, support-record logging, and compact summaries remain intact.

## Variant Personality

ordered source -> relation result -> derived field -> transform input -> final slot chain.

Planning rules:
- For multi-hop tasks, dependency_edges must show the chain order.
- A transform input must come from a current observation slot or a deterministic derivation of one.
- If an intermediate lookup fails, repair that edge before transforming the original subject.
- Keep stateful requirements compact and avoid global hop verbosity for simple retrieval.

Action policy highlights: completion_policy=mutation_closure, planned_mutation_cap=3, ledger_review=True, searchqa_minimal_span=False, memory_argument_quarantine=True.

## Generalization Notes

The harness avoids item-specific entities, UUIDs, dates, answers, or benchmark IDs. It operates through generic slots, mutation rows, dependency edges, failure classes, and memory provenance labels so the same behavior can transfer to unseen tools and tasks.
