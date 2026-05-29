# harness_round01_8

This round 01 harness is a self-contained evolution of the base single-ReAct harness.

## Design Summary

Status-packet harness that keeps a compact plan/action/memory contract separating pending intent from observed facts.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Plan-as-fact drift and shallow evidence chains | Typed planning-to-action contract | STATUS_PACKET plan with target, pending items, observed evidence, remaining work, and final criteria | Concise initial planning and direct execution handoff |
| Action | Premature completion, repeated failed calls, weak final arbitration | typed planning-to-action status packet | Carry a compact status packet as a note-taking aid: target, planned_or_pending, observed_success, observed_failure, remaining, next, final_criteria. Update it only from observations. status_packet_check is optional and should not gate direct valid tool execution. | One primary executor, strict JSON tool calls, no heavy committee |
| Memory | Memory contamination from planned actions | Phase-aware observation grounding | Memory returns procedural reminders and never stores planned calls as facts | Lightweight guidance with safe fallback |
| Builder | Compatibility risk | Preserve factory wiring | Standard ActionContext preparation, planning_class injection, metadata, and tool reference binding | Base harness build contract |

## Runtime Notes

- Candidate directory: `harness_round01_8`
- Planning system: `round01_status_packet_planning`
- Action system: `round01_status_packet_react`
- Memory system: `round01_status_packet_memory`
- The harness does not hard-code benchmark answers, entity IDs, or dataset-specific cases.
- Any verifier/checker tool is non-environmental and only reads the trajectory.
- Budgeting is intentionally light; summary cadence and checker use are advisory, not gates. The main discipline is observation grounding and schema-aware repair.
- Action prompts must use Jinja variables `{{tool_functions_json}}` and `{{task}}` so available schemas and tasks are actually rendered at run time.
- Repeated identical failed calls should trigger a soft advisory and strategy switch, not a hard block. Short-answer final answers should copy decisive tool fields exactly, especially dates, numbers, names, and calculated outputs.
