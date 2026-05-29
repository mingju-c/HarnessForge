### PART 1: LOCALIZATION SUMMARY

The current winner is `harness_round01_8`, evaluated in `round02_02` with model label `Qwen3-8B`. Its architecture is a direct single-executor ReAct harness with a compact STATUS_PACKET plan, a strict closed-set JSON action prompt, an optional non-environment `status_packet_check` tool, and lightweight phase-aware memory. The builder is compatible with the harness factory and wires `builder.py`, `planning_module/provider.py`, `action_module/provider.py`, and `memory_module/provider.py` in the expected local structure. The only builder issue is metadata drift: the evaluated harness is under `round_02_02`, but metadata and description still identify it as `round_01`.

Stage 1 attributes the dominant failures to Action and the Planning -> Action interface, not to missing factory wiring. The main failures are premature or partial EnvScaler completion without invariant-level verification, repeated failed-call loops, tool/schema hallucination, placeholder identifier use, weak SearchQA evidence arbitration, ToolHop intermediate-binding failures, final-answer formatting losses, and an optional checker that is advisory but not binding. Memory is mostly a secondary contributor: it is low-noise and phase-aware, but too generic to prevent repeated schema errors, stale failed-call retries, or raw-answer formatting mistakes.

The transferable capability gaps are: missing observation-backed state ledger for stateful workflows, missing blocked-call and error-class repair state, missing argument provenance checks before mutable calls, missing candidate-evidence arbitration for retrieval QA, missing typed binding state for multi-hop chains, missing raw final-answer canonicalization, and missing verifier-to-executor contract. Highest-leverage repair targets are Action-side execution control, Planning -> Action structured state handoff, and a compact Memory update that reminds the executor about provenance, repeated failures, and exact final copying. The generator should preserve the winner's strengths: direct single-executor continuity, compact status-packet discipline, strict closed-set tool schemas, low-noise memory, guarded task tools, and efficient one-hop or clean-chain execution.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round01_6`

- **Observed Structure:** Direct single executor with CANONICAL_TARGET planning, final observation binding, cautious answer-type canonicalization, and phase-aware canonicalization memory.
- **Relevant Strength:** Best fair-first200 mixed score among round01 candidates, best fair-slice EnvScaler score and done proxy, lowest fair-slice max-step rate among top round01 candidates, and strong full-run mixed score.
- **Relevant Weakness / Risk:** SearchQA trails `harness_round01_5`, and ToolHop is solid rather than best. Over-borrowing its answer focus could under-repair stateful mutation ledgers and repeated-call loops.
- **Related Winner Failure:** Final-answer canonicalization failure; stateful completion weakness; cost and max-step instability.
- **Transferable Module Pattern:** Add Action-side target answer type detection, decisive-observation binding, and exact raw-field copying before `final_answer`; keep the rule cautious and answer-type driven rather than benchmark-case driven.
- **Generalization Rationale:** Dates, numbers, names, strings, lists, yes/no answers, IDs, and calculated outputs recur across unseen QA and tool-chain tasks. Binding final output to an observed field prevents natural-language paraphrase errors without relying on specific entities.
- **Do Not Borrow:** Do not replace the winner's ToolHop-oriented status packet wholesale; do not add narrow answer-format branches tied to observed training examples.
- **Transfer Confidence:** High

#### Example: `harness_round01_5`

- **Observed Structure:** Direct single executor with COMMIT_LEDGER planning, sequential commit discipline for mutable calls, read-after-write reminders, optional terminal preflight, and phase-aware commit memory.
- **Relevant Strength:** Best fair-first200 SearchQA score among round01 candidates, second-best fair-first200 mixed score, strong EnvScaler signal, and explicit verified-state-change discipline.
- **Relevant Weakness / Risk:** Full-run score drops behind `harness_round01_6` and `harness_round01_8`; ToolHop correctness is only moderate; cost and max-step rate remain high.
- **Related Winner Failure:** Stateful completion without invariant-level verification; partial EnvScaler completions after local successes; weak completion gating.
- **Transferable Module Pattern:** Borrow the commit ledger concept: sequentially record requested mutations, successful observations, failed observations, remaining predicates, terminal blockers, and readiness for `complete_task`.
- **Generalization Rationale:** Stateful CRUD, scheduling, billing, healthcare, support, and order workflows all need observation-backed mutation predicates before terminal completion.
- **Do Not Borrow:** Do not require unconditional extra verification calls; do not make the optional terminal preflight a repeated checker loop.
- **Transfer Confidence:** High

#### Example: `harness_round01_2`

- **Observed Structure:** QA-oriented single executor with EVIDENCE_CHAIN planning, explicit evidence slots, answer support checks, and optional arbitration when candidates remain ambiguous.
- **Relevant Strength:** Positive fair-first200 delta over base, stable all-available mixed score, improved SearchQA subEM over base, and reliable search use.
- **Relevant Weakness / Risk:** ToolHop correctness does not improve over base, and it still reaches max steps on roughly one tenth of aligned tasks.
- **Related Winner Failure:** SearchQA evidence arbitration weakness; distractor acceptance; unsupported final answers after retrieval.
- **Transferable Module Pattern:** Add a compact candidate-evidence table with candidate answer, source observation, matching question qualifiers, contradiction or ambiguity note, and final support status.
- **Generalization Rationale:** Retrieval tasks frequently contain distractors, aliases, partial qualifiers, date constraints, and multiple plausible entities. Candidate evidence slots transfer beyond the observed questions because they track support rather than task IDs.
- **Do Not Borrow:** Do not make arbitration a frequent non-environment call; prefer internal state in the executor unless ambiguity remains after real evidence gathering.
- **Transfer Confidence:** High

#### Example: `harness_round01_3`

- **Observed Structure:** Direct single executor focused on schema-aware repair, soft duplicate-failure advisories, and strategy changes after tool errors.
- **Relevant Strength:** Explicitly classifies failed calls as unknown tool, schema mismatch, missing entity, empty output, execution error, or contradiction; SearchQA uses search reliably.
- **Relevant Weakness / Risk:** Overall score is below base, ToolHop is weak, max-step rate and token cost are high. The concept is better than the measured implementation.
- **Related Winner Failure:** Failed-call repair collapses into repeated loops; tool/schema hallucination; placeholder identifier use.
- **Transferable Module Pattern:** Borrow only the error taxonomy and the requirement that repeated failures force a strategy switch to a different schema-listed tool, different observed argument, or explicit impossible-state reasoning.
- **Generalization Rationale:** Unknown tools, invalid arguments, not-found records, permission failures, validation failures, empty retrieval, and contradictions are common across dynamic tool environments.
- **Do Not Borrow:** Do not copy its heavy repair style or let classification add more loops; the repair state should be cheaper and earlier than repeated failed calls.
- **Transfer Confidence:** Medium

#### Example: `harness_round01_4`

- **Observed Structure:** Checkpointed direct executor with concise summaries and a non-acting critic for stop and repair decisions.
- **Relevant Strength:** Non-acting critic preserves single-executor state discipline and checks known facts, missing facts, repeated failures, and final readiness.
- **Relevant Weakness / Risk:** Quality does not justify using it as a main parent; checkpointing does not lower cost enough; SearchQA is weak.
- **Related Winner Failure:** Optional `status_packet_check` is not action-binding and can become a distraction.
- **Transferable Module Pattern:** Borrow the "rare, decisive, non-acting critic" discipline: a verifier should be called only at genuine uncertainty points and its output must produce a concrete next-action constraint or finalization block.
- **Generalization Rationale:** Verifier tools generalize only when they alter executor state. A rare critic can reduce unsupported finalization without turning into repeated self-checking.
- **Do Not Borrow:** Do not add frequent checkpoint calls; do not create a second environment actor.
- **Transfer Confidence:** Medium

#### Example: `harness_round01_7`

- **Observed Structure:** Schema-routed single executor with read-only versus mutable task routing. Read-only lookup can gather limited independent evidence, while mutable tasks use sequential observation before completion.
- **Relevant Strength:** Useful routing diversity, reliable SearchQA search use, and lower SearchQA/ToolHop tool-call counts among round01 candidates.
- **Relevant Weakness / Risk:** It is not benchmark-leading; EnvScaler score is close to base; max-step rate remains above `harness_round01_6`.
- **Related Winner Failure:** Mixing retrieval-style behavior with stateful mutation behavior; overusing optional checkers on mutable tasks; weak stateful completion discipline.
- **Transferable Module Pattern:** Borrow lightweight mutability routing inside Action: classify available tools as read-only or mutating, allow limited parallel or grouped evidence only for read-only tools, and force sequential observation for mutating tools.
- **Generalization Rationale:** The distinction between read-only lookup and state-changing calls is domain-agnostic and helps prevent unsafe parallel writes or premature completion.
- **Do Not Borrow:** Do not introduce router/debate complexity; do not let routing override the current tool schemas or observations.
- **Transfer Confidence:** Medium

#### Example: `harness3`

- **Observed Structure:** Guarded JoyAgent-style augmented ReAct with tool whitelist checks, repeated-call detection, early-stop guards, and compact MEMP memory.
- **Relevant Strength:** Very low token footprint and low max-step rate.
- **Relevant Weakness / Risk:** SearchQA does not actually use search; EnvScaler completion does not translate into high score; early stopping can under-complete stateful workflows.
- **Related Winner Failure:** High max-step rate, repeated low-value loops, and cost growth.
- **Transferable Module Pattern:** Borrow only the budget-control idea: repeated-call guards and early loop cutoffs should force a new strategy, not shallow completion.
- **Generalization Rationale:** Cost control and loop blocking transfer across task families when tied to observed repeated failures rather than arbitrary step limits.
- **Do Not Borrow:** Do not copy the retrieval route because `used_search` is zero; do not use early stopping as a substitute for state verification.
- **Transfer Confidence:** Medium

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style multi-agent harness with broader coordination and Cerebra fusion memory.
- **Relevant Strength:** Moderate EnvScaler score and reliable SearchQA search use.
- **Relevant Weakness / Risk:** Highest token cost, highest max-step rate among active candidates, and heavy orchestration appears too expensive for Qwen3-8B.
- **Related Winner Failure:** Temptation to solve verification and arbitration by adding broad multi-agent complexity.
- **Transferable Module Pattern:** Mainly a negative control. Use it as evidence that the new harness should stay direct and add bounded verifier contracts rather than broad orchestration.
- **Generalization Rationale:** The observed failures need state, provenance, repair, and finalization discipline; they do not require multiple acting agents or large memory fusion.
- **Do Not Borrow:** Do not copy heavy role orchestration, broad memory exposure, or multiple environment actors.
- **Transfer Confidence:** Low

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Planning | STATUS_PACKET is prose-like and not consumed as a typed execution contract | Missing reusable decomposition into required mutations, answer variables, evidence targets, and final criteria | `harness_round01_5`, `harness_round01_2`, winner pattern | Keep compact status packet but add explicit ledger fields for mutation predicates, answer bindings, unresolved blockers, and final readiness | State, evidence, and variable ledgers transfer across workflows, retrieval QA, and tool chains | Avoid verbose plans or executable-looking invented tool calls | High | Medium |
| Action: tool-use repair | Repeated failed calls, unknown tools, placeholder IDs, and low-yield retrieval loops | Missing blocked-call registry, error classification, and argument provenance discipline | `harness_round01_3`, `harness3` | Classify failed observations and block identical repeated failed calls unless a successful observation changed preconditions | Tool/API failure classes recur across domains and tool schemas | Avoid costly repair loops from `harness_round01_3`; avoid shallow early stop from `harness3` | High | Medium |
| Action: stateful commit | `complete_task` is called after partial local success or not called after productive progress | Missing observation-backed invariant ledger and terminal readiness gate | `harness_round01_5`, `harness_round01_6` | Sequential commit ledger with read-after-write evidence and `complete_task` gate | Multi-step stateful tasks need verified mutation predicates independent of domain | Avoid unconditional verification calls and repeated checker use | High | Medium |
| Action: evidence arbitration | SearchQA final answers accept distractors or ignore qualifier mismatch | Missing answer-candidate arbitration and decisive-evidence binding | `harness_round01_2`, `harness_round01_5` | Candidate-evidence table with qualifier match, contradiction note, and support status | Retrieval tasks commonly include distractors and partial evidence | Avoid broad debate or frequent non-environment arbitration | High | Medium |
| Action: finalization | Correct observations are reformatted into wrong answers | Missing raw final-answer canonicalization | `harness_round01_6` | Target-type detection, exact raw-field copy, and cautious generic normalization | Exact formats matter for dates, numbers, strings, names, lists, and IDs across tasks | Avoid benchmark-specific format cases | High | Low |
| Action: orchestration | Optional checker is ignored or becomes a loop target | Missing verifier-to-executor contract | `harness_round01_4`, `harness4` | Rare non-acting verifier whose output blocks unsupported finalization or forces the next real action | Verifier tools help only when they alter executor state | Avoid heavy `harness5` orchestration and multiple acting agents | Medium | Low |
| Memory | Memory reminders are low-noise but too generic for current failures | Missing compact procedural reminders for provenance, repeated-call repair, and raw answer copying | Winner memory, `dynamic_cheatsheet_provider_lite`, `agent_workflow_memory_provider_lite` | Phase-aware reminders plus top-k relevant distilled workflow/cheatsheet notes from successful trajectories when available | Compact retrieval of reusable procedures can help without contaminating current observations | Avoid rich fusion memory from `harness5`; avoid stale or verbose memory | Medium | Low |
| Cross-Module Interface | Planning summaries do not enforce Action behavior | Missing simple Planning -> Action and verifier -> Action state contract | `harness_round01_5`, `harness_round01_2`, winner pattern | Pass structured status fields for required mutations, bindings, blockers, evidence, and final criteria; update from observations | Interfaces based on observed state and pending predicates are domain-agnostic | Avoid new orchestration layers or whole benchmark-loop changes | High | Medium |
| Builder/Wiring | Metadata still says `round_01`; no typed state metadata is exposed | Minor identity drift and no explicit harness policy for new contracts | None; repair within winner pattern | Preserve factory wiring while updating metadata and harness policy labels for the new candidate | Clean metadata helps later analysis without changing evaluator behavior | Avoid evaluator, dataset, or benchmark-loop changes | Medium | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve compact STATUS_PACKET discipline in Planning because it separates pending intent from observed facts without adding verbose planning overhead.
- Preserve the single primary executor in Action because it maintains continuity for ToolHop chains and stateful workflows.
- Preserve strict closed-set JSON tool calling in Action because schema copying is a core defense against unavailable tools.
- Preserve guarded task tools in Action because repeated-failure and schema advisories are useful signals when consumed as repair state.
- Preserve lightweight phase-aware memory in Memory because it adds procedural reminders without stale factual contamination.
- Preserve `PlanningClass` injection, project-root setup, selected-tool binding, and vector-tool memory wiring in Builder/Wiring because they keep the candidate compatible with the harness factory.
- Preserve efficient direct execution for one-hop SearchQA and clean deterministic ToolHop tasks because unnecessary verification would regress easy cases.

#### Borrow

- Borrow from `harness_round01_6` into Action the exact raw-value finalization pattern to recover date, number, string, list, yes/no, and entity-format losses in a task-general way.
- Borrow from `harness_round01_5` into Action the commit-ledger pattern so stateful tasks can gate `complete_task` on observed mutations and terminal blockers.
- Borrow from `harness_round01_2` into Planning and Action the evidence-chain pattern so retrieval answers are tied to decisive observations and question qualifiers.
- Borrow from `harness_round01_3` into Action the error-class taxonomy so unknown tools, schema mismatches, missing entities, permission errors, validation failures, empty outputs, and contradictions trigger different repairs.
- Borrow from `harness_round01_4` into Action the rare non-acting critic discipline so `status_packet_check` becomes a decisive uncertainty tool rather than a loop target.
- Borrow from `harness_round01_7` into Action lightweight read-only versus mutating tool routing so mutating calls remain sequential and read-only evidence can be gathered more flexibly.
- Borrow from `dynamic_cheatsheet_provider_lite` and `agent_workflow_memory_provider_lite` into Memory only the compact relevance-filtered procedural-note idea, not their full storage behavior.
- Borrow from `harness3` into Action only the cost-control principle that repeated-call guards should stop loops early by forcing a new strategy.

#### Avoid

- Avoid copying `harness5` heavy multi-agent orchestration because it has high token cost, high max-step rate, and weak transfer evidence for Qwen3-8B; this is a complexity risk.
- Avoid frequent checker or critic calls from checkpoint-style harnesses because the winner already shows that advisory checkers can be ignored or looped; this is a regression and cost risk.
- Avoid `harness3` or `harness6` retrieval routing because their SearchQA `used_search` is zero despite low cost; this is an irrelevance and quality risk.
- Avoid copying `harness_round01_3` as a whole because its repair concept is useful but measured ToolHop, cost, and max-step behavior are weak; this is a weak-transfer risk.
- Avoid unconditional state verification after every write because extra calls can consume budget and create loops; this is a complexity and regression risk.
- Avoid dataset-specific fixes for observed entities, IDs, dates, names, or benchmark item patterns because they would not transfer to unseen tasks; this is an overfitting risk.
- Avoid multiple environment actors for mutable tasks because parallel state mutation can corrupt task state and make observations harder to attribute; this is a correctness risk.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Promote STATUS_PACKET into an Observation-Backed Execution Ledger]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Stateful completion without invariant-level verification; ToolHop chain repair and intermediate variable binding failure
- **Current Weakness:** The status packet is text-like guidance and does not become an Action-consumed ledger that gates finalization or `complete_task`.
- **Desired Behavior:** Planning should emit compact structured fields for required mutations, required evidence, answer variables, unresolved blockers, and final criteria; Action should update those fields only from observations and use them before terminal actions.
- **Borrowed Pattern:** `harness_round01_5` commit ledger and `harness_round01_2` evidence chain, adapted to the winner's compact status-packet style.
- **Preserved Behavior:** Keep the winner's concise planning and single-executor handoff.
- **Implementation Shape:** Use short ledger fields such as `required_predicates`, `bindings`, `observed_success`, `observed_failure`, `terminal_blockers`, and `final_ready_when`. The ledger may be text or JSON-like, but the prompt and action policy must treat it as the authoritative checklist for readiness.
- **Generalization Rationale:** Required predicates and bindings are generic abstractions for stateful workflows, retrieval QA, and multi-hop tool chains.
- **Complexity:** Medium
- **Expected Impact:** Fewer EnvScaler partial completions, fewer ToolHop lost-variable failures, and better final-readiness decisions.
- **Regression Risk:** A too-large ledger may slow simple one-hop tasks; keep the fields compact and allow direct finalization when one decisive observation satisfies the task.

**[Direction 2: Add Action-Side Error-Class Repair, Blocked-Call State, and Argument Provenance]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Failed-call repair collapses into repeated low-value loops; tool/schema hallucination and placeholder identifier use
- **Current Weakness:** The prompt says not to repeat failed calls, but there is no durable blocked-call state, error class, or ID provenance check before execution.
- **Desired Behavior:** Before each tool call, Action should verify that the tool and argument keys exist in the current schema, ID-like values are user-provided, observed, or schema-authorized as newly generated, and repeated failed calls force a different repair route.
- **Borrowed Pattern:** `harness_round01_3` error taxonomy plus `harness3` low-cost repeated-call guard.
- **Preserved Behavior:** Keep strict JSON tool calls and guard advisories from the winner.
- **Implementation Shape:** Maintain a compact per-task registry keyed by normalized tool name and arguments. Classify failures as unknown tool, invalid schema, not found, already exists, permission/authentication, validation/precondition, empty retrieval, contradiction, or low-yield search. After repeated failure, require a different schema-listed tool, different observed ID, changed precondition, or explicit impossible-state reasoning.
- **Generalization Rationale:** Tool errors and placeholder IDs occur across administrative APIs, search tools, database lookups, and multi-hop tool environments.
- **Complexity:** Medium
- **Expected Impact:** Lower max-step rate, fewer unknown-tool errors, fewer zero-score EnvScaler traces, and fewer long SearchQA/ToolHop loops.
- **Regression Risk:** Over-blocking may prevent a valid retry after a successful state change; the policy must allow retry when a new observation changes preconditions.

**[Direction 3: Gate Stateful Completion with Sequential Commit Discipline]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Stateful completion without invariant-level verification
- **Current Weakness:** Local `success: true` observations can be treated as sufficient even when other requested mutations or hidden predicates remain unsatisfied.
- **Desired Behavior:** For mutable tasks, Action should execute state-changing calls sequentially, record each required mutation and verification observation, and call `complete_task` only when no ledger predicate is failed, missing, or blocked.
- **Borrowed Pattern:** `harness_round01_5` commit ledger and `harness_round01_7` mutability routing.
- **Preserved Behavior:** Keep direct execution and prompt-level speed on obvious stateful tasks where required predicates are already satisfied.
- **Implementation Shape:** Classify tools as mutating or read-only from names, descriptions, and schemas. For mutating tools, prefer one write at a time, then read or use the returned observation to mark the corresponding predicate. If a required predicate is missing, repair or gather the specific missing evidence instead of calling `complete_task`.
- **Generalization Rationale:** Sequential commit with observed predicates applies to appointments, orders, billing, disputes, inventory, patient records, support tickets, and other unseen stateful APIs.
- **Complexity:** Medium
- **Expected Impact:** Higher EnvScaler average score by reducing partial terminal completions and non-terminal zero scores.
- **Regression Risk:** The harness may over-verify and waste tool calls; verification should be tied only to requested predicates and available schemas.

**[Direction 4: Add Candidate Evidence Arbitration and Multi-Hop Binding]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** SearchQA evidence arbitration and answer extraction weakness; ToolHop chain repair and intermediate variable binding failure
- **Current Weakness:** The executor can accept distractors, ignore qualifier mismatch, lose intermediate variables, or hallucinate fallback values after failed hops.
- **Desired Behavior:** Action should track candidate answers and intermediate variables with source observation, confidence, qualifier match, contradiction status, and unresolved blockers. It should not finalize while a required binding is missing or contradicted.
- **Borrowed Pattern:** `harness_round01_2` evidence slots and the winner's successful ToolHop status-packet behavior.
- **Preserved Behavior:** Keep the single-executor path that succeeds when each hop returns a clean value.
- **Implementation Shape:** For SearchQA, maintain a small candidate table and choose the candidate supported by decisive evidence matching the question qualifiers. For ToolHop, maintain a binding table for each intermediate variable, including value, source tool, source snippet, and next dependent operation. Failed hops should trigger alternate valid lookup/search arguments rather than ungrounded fallback values.
- **Generalization Rationale:** Evidence arbitration and variable binding transfer to aliases, dates, genealogy, films, publications, arithmetic transformations, and future multi-hop tasks.
- **Complexity:** Medium
- **Expected Impact:** Better SearchQA correctness, fewer ToolHop no-substring failures, and fewer unsupported "cannot determine" finalizations.
- **Regression Risk:** Too much arbitration can inflate context; limit tables to active candidates and required variables.

**[Direction 5: Enforce Raw Final-Answer Canonicalization at Commit Time]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Final-answer canonicalization failure
- **Current Weakness:** The final prompt asks for raw values, but the model still rephrases ISO dates, lists, names, yes/no answers, and calculated outputs.
- **Desired Behavior:** Before `final_answer`, Action should infer the requested answer type and copy the decisive raw observed field exactly, applying only generic, task-requested transformations.
- **Borrowed Pattern:** `harness_round01_6` canonical answer binding.
- **Preserved Behavior:** Keep the winner's rule that final answers must be observation-supported and concise.
- **Implementation Shape:** Add a finalization checklist for answer type, decisive observation, raw field, allowed transformation, and final answer string. Preserve ISO dates, numeric strings, binary strings, IDs, extracted names, and calculator outputs exactly unless the task explicitly asks for a different format. Join sorted-letter list outputs only when the task asks for a string, not because of a training example.
- **Generalization Rationale:** Exact answer formats are a general evaluation requirement across QA and deterministic tool chains.
- **Complexity:** Low
- **Expected Impact:** Recover many SearchQA and ToolHop subEM-only losses with little architecture change.
- **Regression Risk:** Over-normalization can strip necessary context; canonicalization must be driven by task wording and decisive observations.

**[Direction 6: Make Verification and Memory Procedural, Rare, and Action-Binding]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Optional checker is not action-binding and sometimes becomes a distraction; repeated failures ignore memory reminders
- **Current Weakness:** Memory reminders are safe but generic, and `status_packet_check` produces advisory text that may not change the next action.
- **Desired Behavior:** Memory should provide compact phase-aware reminders for provenance, repeated-call repair, ledger readiness, and raw final copying. The checker should be used only at genuine uncertainty points, and its `missing_or_risk` must constrain the next real action or block unsupported finalization.
- **Borrowed Pattern:** Winner memory style, `dynamic_cheatsheet_provider_lite` relevance-filtered cheatsheets, `agent_workflow_memory_provider_lite` successful-workflow distillation, and `harness_round01_4` rare non-acting critic discipline.
- **Preserved Behavior:** Keep memory low-noise and never let planned actions become observed facts.
- **Implementation Shape:** Add short memory messages at `BEGIN` and error-triggered `IN` phases. If persistent trajectory lessons are available, retrieve at most one or two relevant procedural notes and format them as hints, not facts. Throttle checker calls to one per uncertainty episode and require new evidence before finalizing the same warned-against answer.
- **Generalization Rationale:** Procedural reminders about provenance, retries, and final copying transfer across tasks while avoiding stale factual leakage.
- **Complexity:** Low
- **Expected Impact:** Fewer repeated checker loops, fewer ignored verifier warnings, and better execution discipline without heavy orchestration.
- **Regression Risk:** Irrelevant retrieved memory can distract the executor; retrieval should be lexical, compact, phase-aware, and subordinate to current observations.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The next harness should be a planning-guided single executor with verification-aware execution. It should feel like the winner with a firmer spine: compact status packets remain the central note-taking device, but Action now consumes them as ledgers for required state, evidence, variables, and final readiness. The style should be direct, schema-grounded, repair-aware, and cautious only at commit points. It should not become a broad committee or debate system.

#### 6.2 Module-Level Blueprint

##### Planning Blueprint

Implement compact planning fields that make the STATUS_PACKET actionable: target, task type or mutability hint, required predicates or evidence targets, answer variables, planned_or_pending, observed_success, observed_failure, remaining, terminal_blockers, and final_criteria. Preserve the current short initial planning and prohibition on invented tools, placeholders, authentication helpers, or executable-looking calls. Avoid verbose decomposition and avoid benchmark-specific labels. The evidence comes from Stage 1's ToolHop binding failures, SearchQA qualifier failures, and EnvScaler partial completions. The design is task-general because it records reusable obligations rather than domain entities.

##### Action Blueprint

Implement one primary ToolCallingAgent with stronger internal execution policy. Add schema preflight before tool calls, ID provenance checks for mutable arguments, blocked-call registry for repeated failures, error-class repair, mutability-aware sequential commit discipline, candidate-evidence arbitration for retrieval tasks, binding tables for ToolHop-style variables, raw final-answer canonicalization, and a `complete_task` gate tied to observed ledger predicates. Preserve strict JSON output, closed-set schema copying, direct execution, guarded tools, and low overhead on easy tasks. Avoid multiple environment actors, heavy debate, unconditional verification, and checker loops. Stage 1 evidence shows Action owns failed calls, placeholder IDs, final formatting, unsupported answers, and premature completion. The design is task-general because these controls operate over tool schemas, observations, failure classes, and answer types.

##### Memory Blueprint

Keep memory phase-aware and compact. At `BEGIN`, remind the executor to treat status fields as a ledger, preserve argument provenance, and copy raw final values. At `IN`, trigger only on intervals or error markers with targeted reminders: repeated identical failures require a new strategy; ID-like arguments must be observed or schema-authorized; final answers must be copied from decisive observations. If trajectory storage is used, borrow only lightweight relevance-filtered procedural notes from successful trajectories, capped to one or two short hints. Preserve the winner's no-factual-contamination rule. Avoid rich memory fusion, long retrieved histories, or task-specific facts. Stage 1 shows memory is secondary but can support Action discipline. The design is task-general because it supplies procedures, not answers.

##### Builder / Wiring Blueprint

Preserve local harness factory compatibility: `builder.py`, `__init__.py`, `Description.md`, `planning_module/provider.py`, `action_module/provider.py`, and `memory_module/provider.py`. Keep `PlanningClass` injection, selected-tool binding, project-root setup, vector-tool memory connection, and `max_tool_calls_per_step` default behavior unless a narrow change is needed. Update harness metadata so the new candidate identity, round, planning system, action system, memory system, and pairing reason match the generated harness. Avoid changing the benchmark loop, evaluator, dataset, model, or external services. The evidence is the Stage 1 note that builder wiring is compatible and only metadata drift is misleading.

##### Interface Blueprint

Implement a simple Planning -> Action state handoff through compact status fields and prompt contracts, not a new orchestration layer. Action observations should update observed_success, observed_failure, bindings, terminal_blockers, and final_readiness. Verifier output, when used, should map to a next-action constraint: gather a named missing evidence item, repair a named failure class, block finalization of an unsupported candidate, or stop checking if no new evidence is possible. Preserve the winner's optional checker as a non-environment helper, but make it rare and binding. Avoid adding whole-agent state machines beyond concise checklists. The design is task-general because it transmits obligations and evidence status across modules.

#### 6.3 Minimal Required Changes

- Add a compact Planning -> Action ledger for required predicates, evidence targets, bindings, observed successes, observed failures, terminal blockers, and final criteria.
- Add Action-side schema preflight and ID-like argument provenance checks before mutable calls.
- Add a blocked-call registry and error-class repair policy that prevents repeated identical failed calls unless preconditions changed.
- Gate `complete_task` on observed state predicates for mutable tasks.
- Add candidate-evidence arbitration for SearchQA-style retrieval and binding tables for ToolHop-style chains.
- Add raw final-answer canonicalization with exact observed-field copying.
- Make `status_packet_check` rare, throttled, and action-binding when used.
- Update memory reminders to cover provenance, repeated-call repair, ledger readiness, and exact final copying.
- Preserve factory-compatible builder wiring and update metadata for the new round/candidate identity.

#### 6.4 Optional Enhancements

- Add a lightweight read-only versus mutating tool classifier to allow limited grouped evidence only for read-only calls.
- Add a small finalization helper inside Action that formats the finalization checklist before `final_answer`.
- Add top-k one or two procedural memory notes from successful trajectories if a local memory store is already available.
- Add compact observation summarization when context grows, but only if it preserves raw decisive fields needed for final answers.
- Add a checker throttle counter so repeated checker use requires new environment evidence first.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Keep STATUS_PACKET compact, but include required predicates, answer bindings, observed successes, observed failures, terminal blockers, and final criteria.
- [Planning] Do not mention unavailable tool names, invented authentication helpers, generic search helpers, placeholders, or benchmark-specific entities.
- [Planning] For one-hop tasks, keep the plan minimal and allow direct execution after decisive evidence.
- [Action] Before every tool call, validate tool name and argument keys against the current available schema block.
- [Action] For mutable calls, require ID-like arguments to be user-provided, observed from prior tool results, or explicitly schema-authorized as newly generated.
- [Action] Maintain blocked-call state for repeated failed tool calls and force a different repair path unless a successful observation changed preconditions.
- [Action] Classify failures into reusable classes such as unknown tool, invalid schema, not found, already exists, permission/authentication, validation/precondition, empty retrieval, contradiction, and low-yield search.
- [Action] Execute mutating operations sequentially and gate `complete_task` on observation-backed required predicates.
- [Action] For SearchQA-style tasks, bind final candidates to decisive observations and reject candidates with qualifier mismatch or contradictions.
- [Action] For ToolHop-style tasks, maintain intermediate variable bindings and do not hallucinate fallback values after failed hops.
- [Action] Before `final_answer`, infer answer type and copy the decisive raw observed field exactly unless the task explicitly asks for transformation.
- [Action] Treat `status_packet_check` as optional, rare, and action-binding; do not call it repeatedly without new environment evidence.
- [Memory] Keep reminders phase-aware, short, procedural, and subordinate to current observations.
- [Memory] Add targeted reminders for argument provenance, repeated-call repair, ledger readiness, and raw final-answer copying.
- [Memory] Do not persist or retrieve task-specific factual answers as memory guidance.
- [Builder] Preserve harness factory file structure, `PlanningClass` injection, project-root setup, selected-tool binding, vector-tool memory wiring, and tool compatibility.
- [Builder] Update generated harness metadata so name, round, systems, and pairing reason match the new candidate.
- [Interface] Pass compact ledger fields from Planning to Action and update them only from observations or explicit user-provided facts.
- [Interface] Map verifier warnings to concrete next-action constraints or finalization blocks.
- [Preserve] Keep direct single-executor execution for simple QA and clean deterministic ToolHop chains.
- [Preserve] Keep strict closed-set JSON tool calls and the winner's separation between pending intent and observed facts.
- [Avoid] Do not replace the benchmark loop, dataset, evaluator, model, or harness factory contract.
- [Avoid] Do not add heavy multi-agent orchestration, multiple mutable environment actors, broad debate, or rich memory fusion.
- [Avoid] Do not hard-code benchmark item IDs, answers, tool traces, names, dates, or golden values.
- [Avoid] Do not solve failures by unconditional verification calls; verification must target required predicates or unresolved evidence.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
