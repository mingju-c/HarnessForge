# harness_round02_01_4

Multi-hop provenance harness that keeps one executor but makes source entity, relation result, transformed field, and final value explicit.

## Design Personality

Hop-provenance direct ReAct. The harness evolves `harness_round01_2` rather than replacing it: compact planning, one acting executor, schema preflight, repeated-call cooldown, and procedural memory remain intact. The new behavior is a small operational ledger plus candidate-specific verifier/recovery/memory emphasis.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Broken evidence chains, stateful checklist gaps, terminal confusion | Shared evidence/mutation ledger and terminal contract | ordered source-to-relation-to-transform evidence chain | Compact plan packets and periodic summaries |
| Action | Unsupported final answers and guard blocks without recovery | Evidence-supported final gate and failure-type recovery router | strict final support gate for multi-hop read-only answers | Single executor, schema preflight, repeated-call cooldown |
| Memory | Broad retrieval and missing failure lessons | Task-signature memory and compact failure lessons | relation/lookup failure lessons and provenance reminders | Provenance reminders and successful procedure reuse |
| Builder/Wiring | Weak plan-action interface and stale metadata | Round02 metadata and planning-class wiring | Candidate-local project root and policy metadata | Existing harness factory contract |

## Differentiating Policy

`hop_provenance_react` uses: support_record_gate=True, support_mode=strict, complete_gate=False, completion_policy=progress, drop_extra_keys=True, repeat_limit=1, partial_commit_on_blocker=False, enable_ledger_review_tool=False.

## Generalization Notes

The harness avoids item-specific branches and does not encode benchmark answers, entity names, ids, or golden traces. Its repairs operate over task-general concepts: evidence slots, mutation progress, terminal policy, schema validity, failure classes, and answer formatting.

## Required Files

- `builder.py`
- `__init__.py`
- `planning_module/provider.py`
- `planning_module/prompts/toolcalling_agent.yaml`
- `action_module/provider.py`
- `action_module/round02_agent.py`
- `action_module/prompts/toolcalling_agent.yaml`
- `memory_module/provider.py`
- `memory_module/round02_memory.py`
