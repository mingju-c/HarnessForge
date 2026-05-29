# harness_round03_01_7

Checkpoint variant that adds only a read-only ledger_review tool for commit audits while preserving single-executor mutation safety.

## Design Personality

It gives the model a bounded way to inspect the ledger before risky finalization, without introducing additional acting roles or heavy orchestration.

## Module Change Map

| Module | Localized Failure Addressed | Mechanism | Preserved Behavior |
|---|---|---|---|
| Planning | Unvalidated plan packets and premature terminal intent | verifier-gated checklist contract with explicit validation and fallback contract | Compact plan packets and periodic summaries |
| Action | Surface support, dependency skips, partial completion, schema/repeat loops | single executor with optional read-only ledger_review checkpoint and strict terminal gates | Single executor, hard schema preflight, repeated-call awareness, raw final answers |
| Memory | Noisy lexical retrieval | checkpoint-triggered recovery and finalization reminders | SearchQA no-leakage and memory-as-hint discipline |
| Builder/Wiring | Stale metadata and weak lineage | round03_01 identity, local project root, policy metadata | Existing harness factory contract |

## Differentiating Policy

`round03_checkpoint_react` uses: support_mode=strict, relation_min_overlap=2, completion_policy=mutation_coverage, mutation_coverage_cap=4, repeat_limit=1, enable_ledger_review_tool=True, partial_commit_on_blocker=False.

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
