Harness summary:
- Candidate: `harness_round03_02_6` for `round_03_02`.
- Planning: CONTRADICTION_ARBITER creates a compact task contract focused on conflicting observation arbitration.
- Execution: one primary ReAct executor owns all environment actions, with guarded tools, a local route-change guard, and `contradiction_arbiter_check` as a rare non-environment checker.
- Memory: lightweight procedural rule cards keyed to execution markers; no task facts, IDs, answers, or labels are persisted.
- Default bench: caller-provided.

Design summary:
A contradiction-aware direct executor for inconsistent API/tool feedback, with compact conflict rows and route-change repair.

Module Change Map:
| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Pending obligations were prose-only | Compact Status Fusion / targeted contract | `conflict_rows` with observed success, observed failure, remaining, repair guidance, and final readiness | Compact planning plus periodic summaries |
| Action | Repeated failed routes and premature terminal calls | Stateful/repair/slot/raw gates as applicable | Guarded tools plus a route-change wrapper that blocks a third identical failed non-terminal call | Single executor owns all tool use |
| Action Checker | Checker text could replace evidence | Rare non-acting verifier constraints | `contradiction_arbiter_check` returns parseable fields: verdict, controlling_observation, conflict, next_safe_move | Checker remains non-environmental and optional |
| Memory | Generic reminders did not target failure class | Failure-Class Procedural Memory | Marker-matched rule cards for high-risk phases | Low-noise procedural memory only |
| Builder | Round identity and wiring need factory compatibility | Builder/Wiring preservation | Local `PlanningClass`, project root, metadata, tool-agent binding, max two tool calls per step | Existing ActionContext flow |

Coordination pattern:
- Keep a direct single-executor loop; do not add workers, debate, or parallel state mutation.
- Treat planned work as pending until a tool observation closes it.
- Use the checker only at risk points such as final readiness, ambiguous evidence, contradiction, or repeated failure.
- Prefer raw observed final values and prompt terminal tool use once the contract is satisfied.

Generalization guardrails:
- No hard-coded benchmark answers, IDs, entities, status values, or dataset-specific cases.
- Tool names and argument keys must come from the live Available tool schemas block.
- Memory stores reusable procedural guidance only.
- The candidate is self-contained within its directory except for stable framework imports and the shared `_harness_guards` helper used by existing harnesses.

Runtime notes:
- Generated bundle: `harness_round03_02_6`.
- Planning system: `round03_02_contradiction_arbiter_planning`.
- Action system: `round03_02_contradiction_arbiter_react`.
- Memory system: `round03_02_contradiction_arbiter_memory`.
- Improvement focus: contradiction_arbitration, stateful_repair, bounded_retries.
