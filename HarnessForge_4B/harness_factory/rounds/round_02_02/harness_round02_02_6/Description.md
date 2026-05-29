# harness_round02_02_6

Commit-time format harness that infers a compact output contract and normalizes supported answers without changing the evidence route.

## Design Personality

Format-contract direct ReAct. It evolves `harness_round01_4` by preserving compact planning, one mutating executor, strict schema preflight, provenance-aware memory, and standard `final_answer` / `complete_task` contracts. The new behavior is scoped to evidence and mutation ledgers, support-aware commitment, event-triggered recovery, and compact task-signature memory.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Broken evidence chains, missing mutation checklist, weak terminal criteria | Planning-to-action evidence and mutation ledger | format_contract field tied to evidence slots and deterministic transforms | Short plan packets and periodic progress summaries |
| Action | Unsupported final answers, schema/repeat loops, premature terminal calls | Support gate, recovery router, stateful readiness | canonicalize only a supported final candidate; keep units and leading zeros when the task asks for them | Single executor, hard schema preflight, direct tool use |
| Memory | Broad retrieval and missing failure lessons | Task-signature memory with compact failure lessons | short reminders for ISO dates, raw spans, list completeness, and not overusing aliases | Provenance reminders and memory-as-hint discipline |
| Builder/Wiring | Stale metadata and weak round identity | Round02_02 metadata and local project root | Candidate-local wiring with PlanningClass injection and policy metadata | Existing harness factory build contract |

## Differentiating Policy

`format_contract_react` uses: support_record_gate=True, support_mode=route, complete_gate=True, completion_policy=progress, drop_extra_keys=True, repeat_limit=2, partial_commit_on_blocker=True, min_successful_mutations_before_partial_complete=1, planned_mutation_cap=1, enable_ledger_review_tool=False, date_iso_canonicalization=True, narrow_alias_trim=True.

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
