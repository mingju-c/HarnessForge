# harness_round02_02_1

Balanced single-executor harness with a compact evidence and mutation ledger, support-record finalization, recovery routing, and task-signature memory.

## Design Personality

Balanced ledger-guided direct ReAct. It evolves `harness_round01_4` by preserving compact planning, one mutating executor, strict schema preflight, provenance-aware memory, and standard `final_answer` / `complete_task` contracts. The new behavior is scoped to evidence and mutation ledgers, support-aware commitment, event-triggered recovery, and compact task-signature memory.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Broken evidence chains, missing mutation checklist, weak terminal criteria | Planning-to-action evidence and mutation ledger | compact checklist ledger for evidence slots, dependencies, mutation slots, terminal policy, and answer format | Short plan packets and periodic progress summaries |
| Action | Unsupported final answers, schema/repeat loops, premature terminal calls | Support gate, recovery router, stateful readiness | route-aware support gate and failure-class recovery while keeping one task-tool executor | Single executor, hard schema preflight, direct tool use |
| Memory | Broad retrieval and missing failure lessons | Task-signature memory with compact failure lessons | signature-token retrieval and short failure lessons for schema, repeat, not-found, and unsupported-final cases | Provenance reminders and memory-as-hint discipline |
| Builder/Wiring | Stale metadata and weak round identity | Round02_02 metadata and local project root | Candidate-local wiring with PlanningClass injection and policy metadata | Existing harness factory build contract |

## Differentiating Policy

`slot_ledger_react` uses: support_record_gate=True, support_mode=route, complete_gate=True, completion_policy=ledger_or_progress, drop_extra_keys=True, repeat_limit=2, partial_commit_on_blocker=True, min_successful_mutations_before_partial_complete=1, planned_mutation_cap=2, enable_ledger_review_tool=False, date_iso_canonicalization=True.

## Generalization Notes

This candidate avoids item-specific branches and does not encode benchmark answers, entity names, ids, or golden traces. Its repairs operate over task-general concepts: requested slots, ordered evidence dependencies, observed mutation progress, schema validity, failure classes, support records, terminal policy, and answer-format contracts. It intentionally avoids heavy multi-agent execution and aggressive budget caps.

## Required Files

- `builder.py`
- `__init__.py`
- `planning_module/provider.py`
- `planning_module/prompts/toolcalling_agent.yaml`
- `action_module/provider.py`
- `action_module/round02_02_agent.py`
- `action_module/prompts/toolcalling_agent.yaml`
- `memory_module/provider.py`
