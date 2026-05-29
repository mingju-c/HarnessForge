Harness summary:
- Candidate: `harness_round03_02_1` for `round_03_02`.
- Planning: OBSERVED_STATUS_LEDGER creates a compact task contract focused on status ledger fusion.
- Execution: one primary ReAct executor owns all environment actions, with guarded tools, a local route-change guard, and `status_packet_check` as a rare non-environment checker.
- Memory: lightweight procedural rule cards keyed to execution markers; no task facts, IDs, answers, or labels are persisted.
- Default bench: caller-provided.

Design summary:
A compact observed-status ledger that keeps the winner direct but makes pending rows, observed facts, failures, blockers, and terminal criteria explicit for Action.

Module Change Map:
| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Pending obligations were prose-only | Compact Status Fusion / targeted contract | `status_ledger` with observed success, observed failure, remaining, repair guidance, and final readiness | Compact planning plus periodic summaries |
| Action | Repeated failed routes and premature terminal calls | Stateful/repair/slot/raw gates as applicable | Guarded tools plus a route-change wrapper that blocks a third identical failed non-terminal call | Single executor owns all tool use |
| Action Checker | Checker text could replace evidence | Rare non-acting verifier constraints | `status_packet_check` returns parseable fields: verdict, open_rows, blocker, next_safe_move | Checker remains non-environmental and optional |
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
- Generated bundle: `harness_round03_02_1`.
- Planning system: `round03_02_observed_status_planning`.
- Action system: `round03_02_observed_status_react`.
- Memory system: `round03_02_observed_status_memory`.
- Improvement focus: compact_status_fusion, stateful_progress_rows, terminal_readiness.
