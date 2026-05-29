# harness_round03_01_4

Stateful workflow harness that directly addresses premature completion by tying terminal tools to planned mutation coverage.

## Design Personality

It is the most stateful-sensitive variant: one executor mutates, every requested operation is tracked at operation level, and completion waits for observed coverage.

## Module Change Map

| Module | Localized Failure Addressed | Mechanism | Preserved Behavior |
|---|---|---|---|
| Planning | Unvalidated plan packets and premature terminal intent | stateful mutation coverage checklist with explicit validation and fallback contract | Compact plan packets and periodic summaries |
| Action | Surface support, dependency skips, partial completion, schema/repeat loops | completion gate over required mutation coverage rather than one-success progress | Single executor, hard schema preflight, repeated-call awareness, raw final answers |
| Memory | Noisy lexical retrieval | stateful workflow recipes and authorization/not-found recovery lessons | SearchQA no-leakage and memory-as-hint discipline |
| Builder/Wiring | Stale metadata and weak lineage | round03_01 identity, local project root, policy metadata | Existing harness factory contract |

## Differentiating Policy

`round03_mutation_coverage_react` uses: support_mode=route, relation_min_overlap=0, completion_policy=mutation_coverage, mutation_coverage_cap=6, repeat_limit=1, partial_commit_on_blocker=False.

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
