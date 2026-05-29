# harness_round03_01_6

Memory-centered harness that reduces noisy recall by routing compact lessons through topology and failure phase.

## Design Personality

It keeps action lightweight and lets memory do the cleanup: short route-matched recipes, no SearchQA leakage, and no long trace sketches.

## Module Change Map

| Module | Localized Failure Addressed | Mechanism | Preserved Behavior |
|---|---|---|---|
| Planning | Unvalidated plan packets and premature terminal intent | topology-tagged checklist contract with explicit validation and fallback contract | Compact plan packets and periodic summaries |
| Action | Surface support, dependency skips, partial completion, schema/repeat loops | balanced ledger execution that treats memory as hints, never evidence | Single executor, hard schema preflight, repeated-call awareness, raw final answers |
| Memory | Noisy lexical retrieval | route, dependency-depth, stateful/read-only, and failure-class retrieval | SearchQA no-leakage and memory-as-hint discipline |
| Builder/Wiring | Stale metadata and weak lineage | round03_01 identity, local project root, policy metadata | Existing harness factory contract |

## Differentiating Policy

`round03_topology_memory_react` uses: support_mode=strict, relation_min_overlap=1, completion_policy=mutation_coverage, mutation_coverage_cap=3, repeat_limit=1, partial_commit_on_blocker=False.

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
