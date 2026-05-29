# harness_round01_2

Harness summary:
- Planning: schema_repair_planning emits a compact packet with evidence slots, mutation checklist, answer format, terminal criteria, and one next-tool intent.
- Action: schema_cooldown_react keeps the base single-executor ReAct path but adds local hard guards for evidence, schema preflight, repeated failures, empty steps, terminal readiness, and conservative final canonicalization.
- Memory: schema_hint_memory provides short provenance-aware procedural reminders and stores only successful reusable workflows.
- Default bench: caller-provided.

Module Change Map:
- Planning repair: Plan the minimum valid tool path. Include a tool_contract note: likely tool family, required identifiers, and argument names to verify before acting. Do not guess final answers.
- Action repair: Schema-first mode: before every call, check tool name and exact argument keys; after an error, change the argument object or tool.
- Memory repair: Prefer exact schema keys from the current tool list. A similar word is not a valid argument unless the schema lists it.
- Cross-module interface: plans and memory label observations vs hypotheses; action treats only observations or deterministic derivations as commit support.
- Preserved behavior: direct one-agent tool use, one-tool-by-default execution, short planning, and standard final_answer / terminal completion contracts.

Generalization notes:
- The harness does not hard-code task ids, entities, answers, or benchmark-specific records.
- Guards operate on tool schemas, observations, and generic terminal/evidence patterns.
- The design intentionally avoids heavy parallel acting and strong global budget constraints.
