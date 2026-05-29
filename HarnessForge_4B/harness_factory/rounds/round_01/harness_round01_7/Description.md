# harness_round01_7

Harness summary:
- Planning: answer_format_planning emits a compact packet with evidence slots, mutation checklist, answer format, terminal criteria, and one next-tool intent.
- Action: format_normalizing_react keeps the base single-executor ReAct path but adds local hard guards for evidence, schema preflight, repeated failures, empty steps, terminal readiness, and conservative final canonicalization.
- Memory: format_hint_memory provides short provenance-aware procedural reminders and stores only successful reusable workflows.
- Default bench: caller-provided.

Module Change Map:
- Planning repair: Plan the evidence path and answer_format. Include requested_granularity, unit_or_width_constraints, and whether a final deterministic transform is needed.
- Action repair: Format mode: after evidence, transform only to the requested granularity; strip explanations and labels, preserve units or leading zeros only when requested.
- Memory repair: Exact-match tasks reward the requested span, not explanations. Apply formatting at the end and only when task wording supports it.
- Cross-module interface: plans and memory label observations vs hypotheses; action treats only observations or deterministic derivations as commit support.
- Preserved behavior: direct one-agent tool use, one-tool-by-default execution, short planning, and standard final_answer / terminal completion contracts.

Generalization notes:
- The harness does not hard-code task ids, entities, answers, or benchmark-specific records.
- Guards operate on tool schemas, observations, and generic terminal/evidence patterns.
- The design intentionally avoids heavy parallel acting and strong global budget constraints.
