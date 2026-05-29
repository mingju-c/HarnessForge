# harness_round03_02_4

## Design Summary

harness_round03_02_4 is a Round03_02 evolution of the round02_01_7 guarded single-executor harness. It keeps the direct ReAct topology, hard schema preflight, repeated-call blocking, SearchQA raw-query behavior, support records, compact planning packets, and phase-aware procedural memory. The local repair emphasis is SearchQA-safe raw-span arbitration while preserving direct ReAct.

## Module Change Map

- Planning repair: `raw_span_planning` emits a compact packet and normalizes first-action JSON into ledger fields instead of letting it replace the plan.
- Cross-module interface repair: Action parses `evidence_slots`, `required_mutations`, and `verification_targets` from the latest plan and includes those counts in terminal readiness.
- Action repair: `raw_span_react` wraps the winner's guarded executor with bounded mutation closure, failure recovery hints, SearchQA raw-span checks, optional transform-source support, and current-evidence identifier quarantine.
- Memory repair: `raw_span_safe_memory` masks concrete old values and labels retrieved memories as `procedure_hint_only`, preserving SearchQA leakage prevention.
- Preserved behavior: one acting executor, local schema preflight, repeated-failure guards, support-record logging, and compact summaries remain intact.

## Variant Personality

short-answer route packet with answer type, evidence slot, distractor check, and raw output contract.

Planning rules:
- For short-answer retrieval, preserve the current question wording for the first search.
- Predict the answer format as person, place, date, number, title, alias, list, or description.
- Do not normalize dates or strip units unless the task asks for that format.
- Use stateful mutation rows only when state-changing tools are present.

Action policy highlights: completion_policy=ledger_or_progress, planned_mutation_cap=2, ledger_review=False, searchqa_minimal_span=True, memory_argument_quarantine=True.

## Generalization Notes

The harness avoids item-specific entities, UUIDs, dates, answers, or benchmark IDs. It operates through generic slots, mutation rows, dependency edges, failure classes, and memory provenance labels so the same behavior can transfer to unseen tools and tasks.
