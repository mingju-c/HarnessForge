# harness_round01_6

Harness summary:
- Planning: provenance_planning emits a compact packet with evidence slots, mutation checklist, answer format, terminal criteria, and one next-tool intent.
- Action: provenance_direct_react keeps the base single-executor ReAct path but adds local hard guards for evidence, schema preflight, repeated failures, empty steps, terminal readiness, and conservative final canonicalization.
- Memory: provenance_card_memory provides short provenance-aware procedural reminders and stores only successful reusable workflows.
- Default bench: caller-provided.

Module Change Map:
- Planning repair: Produce a plan with provenance fields: observed_so_far, hypotheses, evidence_needed, derived_steps, and commit_rule. Empty observed_so_far is acceptable; do not fill it with guesses.
- Action repair: Provenance mode: when deciding, name whether a claim comes from observation, derivation, plan, memory, or prior knowledge; only the first two can support final_answer.
- Memory repair: Memory is procedural and provenance tagged. Never promote thoughts, plans, or old guesses to facts without a current observation.
- Cross-module interface: plans and memory label observations vs hypotheses; action treats only observations or deterministic derivations as commit support.
- Preserved behavior: direct one-agent tool use, one-tool-by-default execution, short planning, and standard final_answer / terminal completion contracts.

Generalization notes:
- The harness does not hard-code task ids, entities, answers, or benchmark-specific records.
- Guards operate on tool schemas, observations, and generic terminal/evidence patterns.
- The design intentionally avoids heavy parallel acting and strong global budget constraints.
