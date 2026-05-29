# harness_round03_01_5

Recovery-focused harness that turns guard text into a more active policy table for schema and repeated-call failures.

## Design Personality

It is useful when tools are noisy: unknown tools, missing keys, lookup misses, and repeated signatures are converted into concrete repair moves.

## Module Change Map

| Module | Localized Failure Addressed | Mechanism | Preserved Behavior |
|---|---|---|---|
| Planning | Unvalidated plan packets and premature terminal intent | failure-class recovery contract with explicit validation and fallback contract | Compact plan packets and periodic summaries |
| Action | Surface support, dependency skips, partial completion, schema/repeat loops | schema-aware recovery router with missing-key repair from observations and strict repeat blocking | Single executor, hard schema preflight, repeated-call awareness, raw final answers |
| Memory | Noisy lexical retrieval | failure-class recipes routed by topology and phase | SearchQA no-leakage and memory-as-hint discipline |
| Builder/Wiring | Stale metadata and weak lineage | round03_01 identity, local project root, policy metadata | Existing harness factory contract |

## Differentiating Policy

`round03_recovery_router_react` uses: support_mode=strict, relation_min_overlap=1, completion_policy=mutation_coverage, mutation_coverage_cap=3, repeat_limit=1, repair_missing_from_evidence=True, repair_unknown_tool_name=True, partial_commit_on_blocker=False.

## Generalization Notes

This harness avoids item-specific branches and does not encode benchmark answers, entity names, ids, or golden traces. Its repairs operate over task-general concepts: plan contracts, evidence slots, dependency edges, mutation coverage, relation-bound support, failure classes, schema validity, and compact topology memory.

## Required Files

- `builder.py`
- `__init__.py`
- `planning_module/provider.py`
- `planning_module/prompts/toolcalling_agent.yaml`
- `action_module/provider.py`
- `action_module/round03_agent.py`
- `action_module/prompts/toolcalling_agent.yaml`
- `memory_module/provider.py`
