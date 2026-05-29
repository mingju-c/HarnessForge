# harness_round03_02_7

## Design Summary

harness_round03_02_7 is a Round03_02 evolution of the round02_01_7 guarded single-executor harness. It keeps the direct ReAct topology, hard schema preflight, repeated-call blocking, SearchQA raw-query behavior, support records, compact planning packets, and phase-aware procedural memory. The local repair emphasis is triggered non-acting review for guard clusters and final readiness.

## Module Change Map

- Planning repair: `risk_review_planning` emits a compact packet and normalizes first-action JSON into ledger fields instead of letting it replace the plan.
- Cross-module interface repair: Action parses `evidence_slots`, `required_mutations`, and `verification_targets` from the latest plan and includes those counts in terminal readiness.
- Action repair: `risk_review_react` wraps the winner's guarded executor with bounded mutation closure, failure recovery hints, SearchQA raw-span checks, optional transform-source support, and current-evidence identifier quarantine.
- Memory repair: `risk_review_memory` masks concrete old values and labels retrieved memories as `procedure_hint_only`, preserving SearchQA leakage prevention.
- Preserved behavior: one acting executor, local schema preflight, repeated-failure guards, support-record logging, and compact summaries remain intact.

## Variant Personality

risk-tagged ledger with verification questions and review triggers.

Planning rules:
- Keep the acting topology single-executor; ledger_review is read-only.
- Trigger review for guard clusters, ambiguous final answers, or stateful terminal readiness.
- Do not call review for every simple direct lookup.
- Preserve raw SearchQA and current-evidence support.

Action policy highlights: completion_policy=verified_mutation_closure, planned_mutation_cap=3, ledger_review=True, searchqa_minimal_span=True, memory_argument_quarantine=True.

## Generalization Notes

The harness avoids item-specific entities, UUIDs, dates, answers, or benchmark IDs. It operates through generic slots, mutation rows, dependency edges, failure classes, and memory provenance labels so the same behavior can transfer to unseen tools and tasks.
