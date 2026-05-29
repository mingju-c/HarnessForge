# harness_round01_3

Harness summary:
- Planning: mutation_ledger_planning emits a compact packet with evidence slots, mutation checklist, answer format, terminal criteria, and one next-tool intent.
- Action: mutation_ledger_react keeps the base single-executor ReAct path but adds local hard guards for evidence, schema preflight, repeated failures, empty steps, terminal readiness, and conservative final canonicalization.
- Memory: closure_hint_memory provides short provenance-aware procedural reminders and stores only successful reusable workflows.
- Default bench: caller-provided.

Module Change Map:
- Planning repair: If the task asks to change external state, write a flat checklist: required_mutations, verification_queries, risk_notes, and terminal_criteria. For read-only tasks, write evidence_slots and answer_format.
- Action repair: Stateful closure mode: perform one mutation or verification at a time, maintain the checklist mentally, and call completion only after success evidence.
- Memory repair: For stateful tasks, remember requirement -> action -> observation. A terminal call is safe only after each required change has supporting observation or a clear blocker.
- Cross-module interface: plans and memory label observations vs hypotheses; action treats only observations or deterministic derivations as commit support.
- Preserved behavior: direct one-agent tool use, one-tool-by-default execution, short planning, and standard final_answer / terminal completion contracts.

Generalization notes:
- The harness does not hard-code task ids, entities, answers, or benchmark-specific records.
- Guards operate on tool schemas, observations, and generic terminal/evidence patterns.
- The design intentionally avoids heavy parallel acting and strong global budget constraints.
