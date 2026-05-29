# harness_round03_01_2

QA-focused harness that keeps the winner's direct execution but tightens final-answer support around requested slots and distractor-aware evidence clauses.

## Design Personality

Best for read-only evidence tasks: it asks the planner to name the requested answer slot and asks action to reject answers that merely appear near unrelated distractors.

## Module Change Map

| Module | Localized Failure Addressed | Mechanism | Preserved Behavior |
|---|---|---|---|
| Planning | Unvalidated plan packets and premature terminal intent | answer-slot evidence contract with explicit validation and fallback contract | Compact plan packets and periodic summaries |
| Action | Surface support, dependency skips, partial completion, schema/repeat loops | strict answer-span arbitration with stronger relation overlap before final_answer | Single executor, hard schema preflight, repeated-call awareness, raw final answers |
| Memory | Noisy lexical retrieval | short evidence-finalization reminders with SearchQA no-leakage | SearchQA no-leakage and memory-as-hint discipline |
| Builder/Wiring | Stale metadata and weak lineage | round03_01 identity, local project root, policy metadata | Existing harness factory contract |

## Differentiating Policy

`round03_answer_slot_react` uses: support_mode=strict, relation_min_overlap=2, strict_single_token_support=True, completion_policy=mutation_coverage, mutation_coverage_cap=3, repeat_limit=1, partial_commit_on_blocker=False.

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
