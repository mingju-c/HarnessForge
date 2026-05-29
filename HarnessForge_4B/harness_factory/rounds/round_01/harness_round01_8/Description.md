# harness_round01_8

Harness summary:
- Planning: failsoft_planning emits a compact packet with evidence slots, mutation checklist, answer format, terminal criteria, and one next-tool intent.
- Action: failsoft_guarded_react keeps the base single-executor ReAct path but adds local hard guards for evidence, schema preflight, repeated failures, empty steps, terminal readiness, and conservative final canonicalization.
- Memory: failsoft_hint_memory provides short provenance-aware procedural reminders and stores only successful reusable workflows.
- Default bench: caller-provided.

Module Change Map:
- Planning repair: Create a minimal robust plan: first valid action, fallback if no tool fits, evidence_needed, completion_signal, and answer_format. Avoid benchmark-specific assumptions.
- Action repair: Fail-soft mode: if output is empty or invalid, recover with one concrete valid action; avoid hard assumptions about domains while still requiring evidence when evidence tools exist.
- Memory repair: Recover from format and schema failures by making the next action smaller and valid. Do not loop on empty or identical calls.
- Cross-module interface: plans and memory label observations vs hypotheses; action treats only observations or deterministic derivations as commit support.
- Preserved behavior: direct one-agent tool use, one-tool-by-default execution, short planning, and standard final_answer / terminal completion contracts.

Generalization notes:
- The harness does not hard-code task ids, entities, answers, or benchmark-specific records.
- Guards operate on tool schemas, observations, and generic terminal/evidence patterns.
- The design intentionally avoids heavy parallel acting and strong global budget constraints.
