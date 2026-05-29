# harness_round03_01_8

Low-overhead variant that preserves the validated contract and coverage idea while using lighter support thresholds for robustness.

## Design Personality

It is the least heavy candidate: still validates plans and tracks coverage, but keeps memory sparse and answer support less brittle for paraphrases.

## Module Change Map

| Module | Localized Failure Addressed | Mechanism | Preserved Behavior |
|---|---|---|---|
| Planning | Unvalidated plan packets and premature terminal intent | minimal contract ledger with explicit validation and fallback contract | Compact plan packets and periodic summaries |
| Action | Surface support, dependency skips, partial completion, schema/repeat loops | light contract enforcement with non-strict token fallback and compact recovery | Single executor, hard schema preflight, repeated-call awareness, raw final answers |
| Memory | Noisy lexical retrieval | sparse compact reminders with topology filtering | SearchQA no-leakage and memory-as-hint discipline |
| Builder/Wiring | Stale metadata and weak lineage | round03_01 identity, local project root, policy metadata | Existing harness factory contract |

## Differentiating Policy

`round03_light_contract_react` uses: support_mode=route, relation_min_overlap=0, strict_single_token_support=False, completion_policy=mutation_coverage, mutation_coverage_cap=2, repeat_limit=2, partial_commit_on_blocker=True, min_successful_mutations_before_partial_complete=2.

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
