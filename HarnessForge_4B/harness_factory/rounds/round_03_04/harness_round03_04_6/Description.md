# harness_round03_04_6

Compact Hint Ledger is an evolutionary repair of `harness_round02_02_6`. It preserves the guarded single-executor ReAct shape, hard schema preflight, support records, compact planner, and memory-as-hint discipline, while changing the module-localized behavior named below.

## Module Change Map

| Module | Mechanism | Generalization intent | Preserved behavior |
|---|---|---|---|
| Planning | `compact_hint_ledger_planning` normalizes every initial plan into route, evidence, dependency, mutation, verification, format, and terminal fields. | Prevent tool-call-shaped plans and keep read-only work out of mutation slots. | Short plan packet and periodic progress summaries. |
| Action | `compact_hint_react` uses all-slot stateful completion, configurable slot matching, support records, and failure-class repair state. | Avoid partial-progress completion and repeated invalid strategies across unseen tools. | One acting executor, schema preflight, direct tool use, canonicalization. |
| Memory | `compact_route_memory` stores compact route/failure-class hints and marks them as non-evidence. | Transfer procedural lessons without stale identifiers or benchmark answers. | Memory remains advisory; current observations stay authoritative. |
| Builder/Wiring | Metadata names `round_03_04`, candidate index `6`, and local provider systems. | Keep harness-factory selection and reporting unambiguous. | `PlanningClass` injection, local `project_root`, tool back-references. |

## Differentiating Policy

compact variant: it keeps the same repairs but uses sparser memory exposure and less frequent summaries to reduce prompt clutter for the 4B model.

Action config highlights: `support_mode=balanced_slot`, `completion_policy=all_slots`, `partial_commit_on_blocker=False`, `slot_match_fallback=True`, `enable_ledger_review_tool=False`.

## Generalization Notes

This harness avoids item-specific branches, benchmark answers, entity names, and hard-coded tool ids. The repair operates over task-general slots, dependency edges, current observations, mutation success, answer format, and failure classes. It deliberately avoids broad multi-agent orchestration and strong budget constraints.
