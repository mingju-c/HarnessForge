# harness_round01_1

Harness summary:
- Planning: evidence_packet_planning emits a compact packet with evidence slots, mutation checklist, answer format, terminal criteria, and one next-tool intent.
- Action: evidence_ledger_react keeps the base single-executor ReAct path but adds local hard guards for evidence, schema preflight, repeated failures, empty steps, terminal readiness, and conservative final canonicalization.
- Memory: provenance_hint_memory provides short provenance-aware procedural reminders and stores only successful reusable workflows.
- Default bench: caller-provided.

Module Change Map:
- Planning repair: Emit a compact execution packet with task_type, evidence_slots, required_mutations, answer_format, terminal_criteria, and next_tool_intent. Keep it short. Never put a candidate answer in the plan unless marked hypothesis.
- Action repair: Balanced mode: gather one supporting observation before final answers, repair schema mismatches before retrying, and complete state tasks only after observed progress.
- Memory repair: Use live observations as facts. Treat plan text, thoughts, and old memory as hypotheses until a tool observation supports them.
- Cross-module interface: plans and memory label observations vs hypotheses; action treats only observations or deterministic derivations as commit support.
- Preserved behavior: direct one-agent tool use, one-tool-by-default execution, short planning, and standard final_answer / terminal completion contracts.

Generalization notes:
- The harness does not hard-code task ids, entities, answers, or benchmark-specific records.
- Guards operate on tool schemas, observations, and generic terminal/evidence patterns.
- The design intentionally avoids heavy parallel acting and strong global budget constraints.
