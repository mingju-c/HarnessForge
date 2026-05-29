# harness_round01_4

Harness summary:
- Planning: read_only_evidence_planning emits a compact packet with evidence slots, mutation checklist, answer format, terminal criteria, and one next-tool intent.
- Action: read_only_commit_guard keeps the base single-executor ReAct path but adds local hard guards for evidence, schema preflight, repeated failures, empty steps, terminal readiness, and conservative final canonicalization.
- Memory: evidence_digest_memory provides short provenance-aware procedural reminders and stores only successful reusable workflows.
- Default bench: caller-provided.

Module Change Map:
- Planning repair: Classify the task as read_only_lookup, computation, or stateful. For lookup tasks, list the first evidence tool target and the exact answer_format. Keep the plan under six lines.
- Action repair: Read-only evidence mode: if any evidence tool exists, observe before final_answer; then return only the requested raw span.
- Memory repair: Memory may suggest search routes, but only current tool observations can justify a lookup final answer.
- Cross-module interface: plans and memory label observations vs hypotheses; action treats only observations or deterministic derivations as commit support.
- Preserved behavior: direct one-agent tool use, one-tool-by-default execution, short planning, and standard final_answer / terminal completion contracts.

Generalization notes:
- The harness does not hard-code task ids, entities, answers, or benchmark-specific records.
- Guards operate on tool schemas, observations, and generic terminal/evidence patterns.
- The design intentionally avoids heavy parallel acting and strong global budget constraints.
