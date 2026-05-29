# harness_round01_5

Harness summary:
- Planning: checkpoint_planning emits a compact packet with evidence slots, mutation checklist, answer format, terminal criteria, and one next-tool intent.
- Action: repair_checkpoint_react keeps the base single-executor ReAct path but adds local hard guards for evidence, schema preflight, repeated failures, empty steps, terminal readiness, and conservative final canonicalization.
- Memory: checkpoint_hint_memory provides short provenance-aware procedural reminders and stores only successful reusable workflows.
- Default bench: caller-provided.

Module Change Map:
- Planning repair: Write a tiny plan with checkpoints: first evidence/action, repair trigger, stop trigger, and answer_format. The repair checkpoint is read-only and should be used only after trouble.
- Action repair: Checkpoint mode: act directly, but call repair_checkpoint once after a repeated/schema failure or before a risky terminal action.
- Memory repair: Use checkpoint guidance as procedural advice only. It never replaces live observations or tool schemas.
- Cross-module interface: plans and memory label observations vs hypotheses; action treats only observations or deterministic derivations as commit support.
- Preserved behavior: direct one-agent tool use, one-tool-by-default execution, short planning, and standard final_answer / terminal completion contracts.

Generalization notes:
- The harness does not hard-code task ids, entities, answers, or benchmark-specific records.
- Guards operate on tool schemas, observations, and generic terminal/evidence patterns.
- The design intentionally avoids heavy parallel acting and strong global budget constraints.
