### PART 1: LOCALIZATION SUMMARY

The current winner under analysis is `harness_round02_02_5`, evaluated as `qwen3-8B-round_02_02-harness5` in `round03_03`. It is a direct single-executor ReAct harness with a `RAW_ANSWER` planner, guarded task tools, one optional same-model `raw_answer_check` helper, and lightweight phase-aware procedural memory. Builder wiring is functional and should be preserved: it injects `PlanningClass`, sets project root, binds selected tools back to the agent, and connects vector memory when present. The main wiring issue is only metadata drift: the harness is used as a round03_03 base but still identifies itself as round02_02.

Stage 1 found that the dominant failures are transferable harness-control failures. EnvScaler is the highest-leverage target: only 21/658 tasks reached full score, 503 actual `complete_task` calls occurred in non-full-score runs, and 555 non-full-score runs ended with `Task Completed`. The planner also collapses on stateful tasks: 644/658 EnvScaler initial plans became executable-looking tool-call JSON instead of the required status contract. Action failures include missing stateful side-effect ledger, missing terminal completion gate, reactive rather than preventive schema repair, repeated failed calls, and advisory checker output that does not become enforceable constraints. SearchQA and ToolHop failures come from relation-chain breaks, distractor or alias acceptance, unverified intermediate slots, and final answers in the wrong canonical form. Memory is compact and relevant but advisory only.

The highest-leverage repair targets are: a prompt-injection-resistant Planning -> Action status packet, action-owned stateful commit ledger and `complete_task` gate, preventive schema preflight plus failure-classified repair, relation-grounded evidence and typed-slot verification, raw final-answer commit preflight, and sparse risk-aware memory cues. The next harness should preserve the current winner's useful behaviors: one acting executor, simple direct tool use on easy tasks, raw-answer focus, closed-set tool discipline, guarded tool layer, compact procedural memory, and factory-compatible builder wiring.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round01_6`

- **Observed Structure:** Direct single executor with `CANONICAL_TARGET` planning, target answer type tracking, final observation binding, cautious answer canonicalization, and phase-aware canonical memory.
- **Relevant Strength:** It is the best evaluated round01 generalist in the pool, with 0.4983 fair-first200 mixed score, 0.5105 EnvScaler score, 0.8 EnvScaler done, and the lowest fair-slice max-step rate among top round01 candidates.
- **Relevant Weakness / Risk:** SearchQA trails `harness_round01_5`, and ToolHop is solid but not the strongest ToolHop specialist.
- **Related Winner Failure:** Final-answer canonicalization is still not enforced in the current raw-answer harness.
- **Transferable Module Pattern:** Borrow observation-bound finalization: identify the requested answer type, bind the final value to a decisive observation, and normalize only when the task explicitly requests it.
- **Generalization Rationale:** Dates, numbers, IDs, binary strings, booleans, lists, names, and short raw strings all need exact terminal discipline across task families.
- **Do Not Borrow:** Do not over-normalize raw fields, strip meaningful leading zeros, or rewrite observed values when exact copying is requested.
- **Transfer Confidence:** High

#### Example: `harness_round01_8`

- **Observed Structure:** Direct single executor with a compact `STATUS_PACKET` that separates pending intent, observed success, observed failure, remaining work, next step, and final criteria.
- **Relevant Strength:** It is the strongest evaluated ToolHop specialist in round01, with 0.5263 fair-first200 ToolHop correctness and 0.5526 ToolHop path score, plus a strong full-run mixed score.
- **Relevant Weakness / Risk:** It is relatively expensive and has the highest max-step rate among selected top4 round01 candidates.
- **Related Winner Failure:** Stateful planning collapses into a first tool call, and ToolHop consumes intermediate values before verifying that they satisfy the requested relation.
- **Transferable Module Pattern:** Borrow the status-packet handoff, especially the separation of planned or pending rows from observation-backed rows.
- **Generalization Rationale:** Pending-versus-observed separation is domain-agnostic and useful for stateful workflows, retrieval QA, and multi-hop transformations.
- **Do Not Borrow:** Do not make the status checker frequent or verbose; Stage 1 shows that advisory checks can become loops.
- **Transfer Confidence:** High

#### Example: `harness_round01_5`

- **Observed Structure:** Direct single executor with `COMMIT_LEDGER` planning, sequential state-changing commits, read-after-write reminders, and optional terminal preflight.
- **Relevant Strength:** It is the best fair-first200 SearchQA candidate and a strong stateful commit reference, with 0.5036 EnvScaler score and 0.7455 EnvScaler done.
- **Relevant Weakness / Risk:** It remains expensive, has a non-trivial max-step rate, and only moderate ToolHop correctness.
- **Related Winner Failure:** EnvScaler tasks are marked complete after partial, failed, or unverified state mutations.
- **Transferable Module Pattern:** Borrow sequential observed-commit rows: each required mutation stays open until a successful observation closes it, and terminal completion requires row closure.
- **Generalization Rationale:** Any mutable workflow with multiple writes can be represented as commit rows closed by observations.
- **Do Not Borrow:** Do not add heavy routine preflight on every action or stateful bookkeeping to one-hop read-only tasks.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_2`

- **Observed Structure:** Generated direct executor with a `REPAIR_REGISTRY` contract for obligations, bindings, blockers, failed-call classes, and final readiness.
- **Relevant Strength:** It directly targets repeated failed calls by making failed-call provenance explicit and constraining blind repetition.
- **Relevant Weakness / Risk:** It has no recorded metrics, and a full repair registry can increase prompt footprint.
- **Related Winner Failure:** The current action loop is reactive: unknown tools, invalid arguments, repeated failures, and no-data loops still reach real execution.
- **Transferable Module Pattern:** Borrow failure-class rows for unknown tool, schema mismatch, missing binding, permission or auth failure, empty result, execution error, and repeated identical call.
- **Generalization Rationale:** Tool-rich environments repeatedly expose schema and precondition failures independent of domain.
- **Do Not Borrow:** Do not build a large registry that dominates the prompt or blocks valid retries after a genuine precondition change.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_3`

- **Observed Structure:** Generated direct executor with an `EVIDENCE_BINDING` contract for obligations, evidence bindings, blockers, intermediate variables, and final readiness.
- **Relevant Strength:** It targets SearchQA candidate arbitration and ToolHop dependent-hop evidence by requiring candidates and intermediate variables to be tied to observations.
- **Relevant Weakness / Risk:** It has no recorded metrics, and evidence tables can become verbose.
- **Related Winner Failure:** SearchQA and ToolHop finalize plausible nearby values without verifying the exact requested relation, predicate, or target field.
- **Transferable Module Pattern:** Borrow relation-specific evidence binding: each candidate answer or intermediate slot must name its source observation and why it satisfies the requested relation.
- **Generalization Rationale:** Distractors, aliases, adjacent relations, and partial chains occur in search, knowledge-base lookup, genealogy tools, and API chains.
- **Do Not Borrow:** Do not run evidence arbitration on every easy answer or on stateful tasks whose dominant risk is mutation completion.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_4`

- **Observed Structure:** Generated direct executor with `STATEFUL_GATE` planning and action behavior for obligations, observed bindings, blockers, mutable commits, and final readiness.
- **Relevant Strength:** It is the closest pool design to the Stage 1 EnvScaler failure: sequential mutable commits plus terminal blockers while preserving direct execution on read-only tasks.
- **Relevant Weakness / Risk:** It has no metrics, and gate checks could delay terminal completion if overused.
- **Related Winner Failure:** The current harness has no state-diff checker or terminal readiness gate before `complete_task`.
- **Transferable Module Pattern:** Borrow a rare stateful gate before risky terminal calls and state-changing decisions.
- **Generalization Rationale:** Read-after-write and postcondition readiness checks transfer to any stateful API domain.
- **Do Not Borrow:** Do not blindly delay `complete_task`; the gate must be based on explicit unresolved rows or failed postconditions.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_7`

- **Observed Structure:** Generated direct executor with `VERIFIER_CONTRACT` planning and a rare non-environmental checker that returns concrete next-action constraints, with checker-loop throttling.
- **Relevant Strength:** It addresses a direct weakness of the current winner: checker output should constrain the next action instead of remaining free-text advice.
- **Relevant Weakness / Risk:** It has no metrics, and verifier calls can add token cost or become another loop if not strictly triggered.
- **Related Winner Failure:** `raw_answer_check` and memory warnings remain advisory and sometimes reinforce impossibility answers.
- **Transferable Module Pattern:** Borrow constraint-shaped checker output: each check should return a concrete blocker, required next move, or finalization permission, and repeated checker drafts should be throttled.
- **Generalization Rationale:** Same-model checkers need enforceable interfaces in any task family where missing evidence or failed calls must constrain action.
- **Do Not Borrow:** Do not add a second acting verifier, and do not let checker text count as environment evidence.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_8`

- **Observed Structure:** Generated low-noise blend with compact status rows, a small snapshot checker, and sparse procedural reminders.
- **Relevant Strength:** It preserves a recognizable direct-execution baseline while adding only small risk-triggered controls.
- **Relevant Weakness / Risk:** Its conservative changes may be too small to fix the severe EnvScaler and schema-repair failures.
- **Related Winner Failure:** The current harness needs stronger gates, but it must not regress easy SearchQA and ToolHop paths with heavy overhead.
- **Transferable Module Pattern:** Borrow the low-noise activation principle: detail and checking should activate only at high-risk states.
- **Generalization Rationale:** Risk-triggered controls keep simple tasks cheap while still providing stronger behavior on complex tasks.
- **Do Not Borrow:** Do not make changes so minimal that the stateful gate and schema preflight remain advisory only.
- **Transfer Confidence:** Medium

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style multi-agent harness with broader role coordination and Cerebra fusion memory.
- **Relevant Strength:** It is useful mainly as a negative control: broader coverage is possible in principle, and it has moderate EnvScaler score despite high cost.
- **Relevant Weakness / Risk:** It has the highest token cost and max-step rate among active seeds, and the pool notes that orchestration is too heavy for Qwen3-8B.
- **Related Winner Failure:** The current winner needs terminal gating and repair discipline, not more acting roles.
- **Transferable Module Pattern:** Borrow only the negative lesson: use one executor plus rare non-acting checks instead of broad multi-agent orchestration.
- **Generalization Rationale:** Mutable environments need clear state ownership; multiple acting agents increase handoff risk and cost across domains.
- **Do Not Borrow:** Do not copy the coordinator, broad role decomposition, frequent fusion memory, or multiple acting agents.
- **Transfer Confidence:** High

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Planning | EnvScaler plans become first-action JSON instead of durable status contracts | Prompt-injection-resistant stateful obligation decomposition | `harness_round01_8`; `harness_round02_02_1` | Compact status packet with obligations, observed success, observed failure, blockers, remaining work, and final criteria | Long embedded task instructions occur across stateful and agentic tasks | Verbose status packets and frequent status checks | High | Low |
| Action | Partial EnvScaler mutation followed by `complete_task` | Stateful terminal-readiness gate and side-effect ledger | `harness_round01_5`; `harness_round02_02_4` | Sequential observed commit rows plus rare terminal gate | Any multi-write API workflow requires observed row closure before terminal completion | Blindly delaying completion or adding gates to trivial read-only tasks | High | Medium |
| Action | Unknown tools, invalid arguments, repeated failures, and no-data loops reach real execution | Preventive schema preflight and failure-classified repair | `harness_round02_02_2` | Failure-class rows plus blocked repeated-call registry | Schema and precondition failures recur across all tool-use domains | Large repair registry that dominates prompt context | Medium | Medium |
| Cross-Module Interface | Plans and memory warnings do not constrain action choices | Enforceable Planning -> Action and checker -> Action constraints | `harness_round02_02_7`; `harness_round02_02_8` | Rare constraint-shaped checker output and risk-triggered activation | Advisory checks must become blockers or next moves in any evidence-sensitive task | Same-model checker loops or checker text used as evidence | Medium | Medium |
| Cross-Module Interface | SearchQA and ToolHop consume plausible nearby values | Relation-specific evidence and typed-slot closure | `harness_round02_02_3`; `harness_round01_8` | Evidence bindings and observed intermediate variables tied to exact requested relations | Distractors and adjacent relations are common across retrieval and multi-hop tasks | Routine arbitration on every easy final answer | High | Medium |
| Action | Correct evidence is submitted in wrong answer form | Raw final-answer canonicalization gate | `harness_round01_6`; current `harness_round02_02_5` | Answer type, decisive observation, raw field, allowed transformation, exact output string | Exact terminal values are required across QA, ToolHop, and structured API fields | Over-normalization that drops meaningful formatting | High | Low |
| Memory | Memory warnings are relevant but advisory and broad | Sparse risk-aware procedural guidance | `harness_round01_6`; `harness_round02_02_8` | Phase-aware cues keyed to schema, stateful, evidence, and raw-final risk | Procedural reminders transfer without storing task facts | Rich factual memory or verbose global checklists | Medium | Low |
| Builder/Wiring | Round metadata still names round02_02 inside round03_03 base | Accurate harness identity without changing runtime behavior | None; repair within winner pattern | Update metadata only if Stage 3 changes names and module constants | Clean identity helps registry comparison and future reports | Treating metadata cleanup as a behavioral fix | High | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve the single acting executor in Action because mutable tasks need one owner for environment state and simple ToolHop chains already work with direct execution.
- Preserve closed-set tool discipline in Action because the winner succeeds when it copies current schema-listed tool names and argument keys.
- Preserve the guarded task tool layer in Action because repeated-failure advisories and soft repairs are useful foundations for stronger preflight.
- Preserve raw-answer focus in Action because SearchQA and ToolHop include many terminal exactness failures that require better finalization, not a different architecture.
- Preserve compact phase-aware procedural memory in Memory because Stage 1 did not show a need for factual memory, task IDs, or answer storage.
- Preserve builder wiring in Builder/Wiring because PlanningClass injection, project-root setup, vector memory wiring, and tool-agent back binding are factory-compatible and not failure causes.
- Preserve low-overhead direct behavior on one-hop read-only tasks because the new controls should activate only when risk is visible.

#### Borrow

- Borrow from `harness_round01_8` into Planning and Interface: a compact status packet that separates pending intent from observed facts; expected benefit is stable stateful and multi-hop handoff; it generalizes because all task families can represent obligations and final criteria.
- Borrow from `harness_round01_5` and `harness_round02_02_4` into Action: sequential observed commit rows and a rare terminal stateful gate; expected benefit is fewer partial `complete_task` calls; it generalizes to any multi-operation API workflow.
- Borrow from `harness_round02_02_2` into Action: failure-class repair rows and blocked identical retry logic; expected benefit is fewer unknown-tool, invalid-argument, and repeated-failure loops; it generalizes across schema-rich tools.
- Borrow from `harness_round02_02_3` into Interface: evidence binding for candidate answers and intermediate variables; expected benefit is fewer distractor and wrong-relation answers; it generalizes to retrieval, knowledge-base, and ToolHop chains.
- Borrow from `harness_round01_6` into Action: observation-bound raw-answer canonicalization; expected benefit is fewer exact-match losses after correct evidence; it generalizes to dates, booleans, numbers, IDs, names, binary strings, and lists.
- Borrow from `harness_round02_02_7` into Action and Interface: constraint-shaped checker output and checker throttling; expected benefit is fewer advisory loops and impossible-answer finals; it generalizes when checkers are same-model and non-environmental.
- Borrow from `harness_round02_02_8` into Memory: low-noise risk-triggering; expected benefit is preserving easy-task efficiency while strengthening high-risk behavior; it generalizes because cue selection is based on failure class, not domain.

#### Avoid

- Avoid copying `harness5` heavy multi-agent orchestration; the risk is complexity and cost, and it should not enter Stage 3 because Stage 1 calls for gates and contracts rather than additional acting roles.
- Avoid copying low-cost early-stop designs such as `harness3` or `harness6` wholesale; the risk is regression, because low max-step rate can come from under-acting or not using search.
- Avoid making `raw_answer_check` a routine step; the risk is repeated same-model checker loops and false confidence, not better evidence.
- Avoid using checker output as environment evidence; the risk is weak transfer and premature impossibility answers.
- Avoid large ledgers on every easy task; the risk is complexity and token overhead, while one-hop SearchQA and clean ToolHop chains need speed.
- Avoid storing task facts, IDs, answer candidates, or golden-like values in memory; the risk is stale or benchmark-specific contamination.
- Avoid hard-coded fixes for observed trajectory IDs, entity names, task domains, or expected answer strings; the risk is overfitting and weak unseen-task transfer.
- Avoid final-answer normalization that rewrites requested raw forms by default; the risk is exact-match regression on leading zeros, `.0`, yes/no conventions, date formats, and aliases.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Robust Status Packet Planning]**
- **Target Module:** Planning
- **Stage 1 Failure Addressed:** Stateful task prompts collapse the initial planning contract
- **Current Weakness:** EnvScaler plans often become executable tool-call JSON and do not preserve all obligations, blockers, and final criteria.
- **Desired Behavior:** Planning should emit a compact status packet with task type, obligations, required bindings, observed successes, observed failures, blockers, remaining work, and final criteria. If the model emits `tools` or an executable-looking action, the planner should repair it into status rows.
- **Borrowed Pattern:** `harness_round01_8` status packet and `harness_round02_02_1` ledger-commit contract.
- **Preserved Behavior:** Keep the winner's compact planning style and avoid long strategic essays.
- **Implementation Shape:** Use a strict planning prompt and a lightweight validation rule: accepted plans must contain status fields and must not contain a top-level `tools` action object. For stateful tasks, each requested mutation or verification should become one obligation row. For read-only tasks, use one or a few evidence rows.
- **Generalization Rationale:** Embedded task-level output contracts and long instructions appear across agentic tasks; a validated status packet keeps planning stable without domain-specific rules.
- **Complexity:** Low
- **Expected Impact:** Better EnvScaler decomposition, stronger action handoff, and fewer missed subtasks.
- **Regression Risk:** Overly rigid plan validation could add overhead or reject useful concise plans for easy tasks.

**[Direction 2: Stateful Commit Ledger and Completion Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Stateful completion is not gated by a verified side-effect ledger
- **Current Weakness:** `complete_task` can be called after failed writes, unresolved blockers, or unverified postconditions.
- **Desired Behavior:** The action module should maintain compact commit rows for mutable tasks. A row closes only after a successful observation or an evidence-backed impossible blocker. `complete_task` should be blocked when any required row is open, failed, stale, or missing postcondition evidence.
- **Borrowed Pattern:** `harness_round01_5` commit ledger and `harness_round02_02_4` stateful gate.
- **Preserved Behavior:** Keep one acting executor and sequential tool use for mutations.
- **Implementation Shape:** Add a terminal-risk preflight before `complete_task` that reads the status packet, recent observations, and failed-call registry. The preflight should return `ready`, `open_rows`, or `blocked`, and only `ready` permits terminal completion.
- **Generalization Rationale:** Multi-write workflows in any domain need observed row closure and postcondition readiness before terminal completion.
- **Complexity:** Medium
- **Expected Impact:** Directly targets the 503 non-full-score EnvScaler `complete_task` calls and should improve stateful score more than raw done rate.
- **Regression Risk:** If the gate is too strict, it may prevent completion after all required changes are actually done.

**[Direction 3: Preventive Schema Preflight and Bounded Repair]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Tool schema and failed-call repair remain reactive rather than preventive
- **Current Weakness:** Unknown tools, invalid arguments, repeated identical failures, and broad no-data retries still reach real execution.
- **Desired Behavior:** Before real tool execution, validate tool existence, required keys, obvious enum-like values, ID/name fit when schema descriptions expose it, array/scalar shape, and repeated identical failed calls. After a failure, classify the failure and require the next attempt to change tool, arguments, or observed precondition.
- **Borrowed Pattern:** `harness_round02_02_2` repair registry, adapted to stay compact.
- **Preserved Behavior:** Preserve the current guarded tool layer and direct executor; strengthen it instead of replacing it.
- **Implementation Shape:** Add a preflight wrapper or prompt-side repair rule that returns structured repair observations for invalid calls before environment execution. Track a small failed-call registry with recent tool name, arguments, class, and allowed next repair.
- **Generalization Rationale:** Schema and precondition failures are tool-interface problems, not benchmark-specific problems.
- **Complexity:** Medium
- **Expected Impact:** Fewer unknown-tool episodes, invalid-argument errors, repeated-failure advisories, and low-value loops.
- **Regression Risk:** Over-aggressive preflight may reject permissive tool calls or prevent valid retry after state changes.

**[Direction 4: Relation-Grounded Evidence and Slot Closure]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Relation-specific evidence chains break on plausible nearby observations
- **Current Weakness:** Action can consume a candidate answer or intermediate value without proving it satisfies the requested relation, predicate, or slot type.
- **Desired Behavior:** For SearchQA and ToolHop-like tasks, status rows should include relation targets, expected answer type, intermediate slots, source observations, rejected distractors, and closure criteria. A downstream transformation or final answer may use a slot only after closure.
- **Borrowed Pattern:** `harness_round02_02_3` evidence binding and `harness_round01_8` pending/observed separation.
- **Preserved Behavior:** Keep easy one-hop read-only tasks lightweight and do not add debate by default.
- **Implementation Shape:** Activate slot/evidence rows only when the task contains dependent hops, relation chains, multiple candidates, or transformations. Before finalization, require a short "candidate satisfies target relation" check using observed evidence.
- **Generalization Rationale:** Relation drift, aliases, distractors, and partial chains occur across retrieval QA, genealogy, date math, string transforms, and structured lookups.
- **Complexity:** Medium
- **Expected Impact:** Better ToolHop correctness and fewer SearchQA wrong-entity or alias-only answers.
- **Regression Risk:** Extra checks could slow simple tasks or make the agent overcautious when evidence is already decisive.

**[Direction 5: Raw Final-Answer Commit Preflight]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Final-answer canonicalization is still not enforced
- **Current Weakness:** The final answer can be a related alias, prose explanation, true/false instead of yes/no, ISO date instead of observed date style, integer instead of float string, or binary string with unintended padding.
- **Desired Behavior:** Immediately before `final_answer`, classify answer type, identify decisive observation, identify raw field, identify allowed transformation, and commit the exact output string with no explanation.
- **Borrowed Pattern:** `harness_round01_6` canonical target behavior and the current `harness_round02_02_5` raw-answer focus.
- **Preserved Behavior:** Preserve direct finalization when the decisive observation and raw format are obvious.
- **Implementation Shape:** Replace broad `raw_answer_check` use with a terminal-only final-answer checklist. Use checker calls only when raw format or allowed transformation is ambiguous; otherwise rely on the checklist.
- **Generalization Rationale:** Exact raw values are required across short-answer QA, ToolHop transformations, and structured terminal fields.
- **Complexity:** Low
- **Expected Impact:** Should recover path-correct but exact-wrong cases, especially `subem=1.0` failures.
- **Regression Risk:** The gate may over-normalize or choose the wrong alias if it ignores task-requested answer conventions.

**[Direction 6: Enforced Sparse Checker and Memory Signals]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** The optional checker and memory reminders do not become enforceable constraints
- **Current Weakness:** `raw_answer_check` and memory guidance are free-text advisories. They can be ignored or treated as evidence for impossibility.
- **Desired Behavior:** Checker and memory risk signals should become normalized constraints: missing evidence blocks finalization, repeated failed calls require changed repair, stateful unresolved rows block `complete_task`, and checker text never substitutes for environment observations.
- **Borrowed Pattern:** `harness_round02_02_7` constraint-shaped verifier output and `harness_round02_02_8` low-noise activation.
- **Preserved Behavior:** Preserve compact procedural memory and rare non-environmental checking.
- **Implementation Shape:** Make checker output structured with fields such as `verdict`, `blocker`, `required_next_move`, and `final_allowed`. Trigger it only for terminal-risk, repeated-failure, unresolved-slot, or ambiguous raw-final states. Memory should emit at most one high-risk cue at a time.
- **Generalization Rationale:** Same-model checkers and memory reminders need enforceable interfaces in any task with incomplete evidence or failed tool calls.
- **Complexity:** Medium
- **Expected Impact:** Fewer checker loops, fewer premature impossibility answers, and better alignment between reminders and action.
- **Regression Risk:** Poorly calibrated blockers can make the agent unable to finish after sufficient evidence.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The next harness should be a planning-guided, single-executor harness with compact risk-triggered gates. It should preserve the current winner's direct ReAct feel and raw-answer discipline, but make the status contract executable: Planning creates a small packet, Action updates it from observations, Memory supplies sparse risk cues, and rare non-environmental checks constrain terminal, repair, evidence, or final-answer decisions. The style should be direct on easy tasks and verification-aware only when the trajectory shows risk.

#### 6.2 Module-Level Blueprint

**Planning Blueprint**

Implement a validated status packet. It should include task type, obligations, required bindings, observed success, observed failure, blockers, remaining work, final criteria, and optional typed slots for multi-hop tasks. Preserve compact planning and the existing answer-type orientation. Avoid executable-looking `tools` plans, long prose plans, and treating planned actions as observed facts. Evidence comes from Stage 1's 644/658 EnvScaler planning-contract collapses. The design is task-general because obligations, bindings, and final criteria apply across stateful, retrieval, and transformation tasks.

**Action Blueprint**

Keep one acting executor. Add three compact action-side controls: stateful commit gate, schema preflight with failed-call registry, and final-answer commit preflight. Mutable calls should be sequential and close commit rows only on successful observations. Real tool calls should pass basic schema and repetition preflight. `complete_task` should require readiness; `final_answer` should require raw-value support. Preserve direct execution for simple chains and the existing guarded tool layer. Avoid parallel acting agents, broad debate, routine checker use, and environment completion from model confidence alone. Stage 1 evidence includes 503 non-full-score `complete_task` calls, 3008 EnvScaler failed observations, repeated-failure advisories, and exact-wrong final answers.

**Memory Blueprint**

Keep memory lightweight, procedural, and phase-aware. BEGIN memory should remind the model about status packets, observed-versus-pending separation, and raw final values. IN memory should trigger at sparse intervals or risk states and emit at most one cue: stateful terminal risk, repeated failed-call risk, unresolved slot risk, retrieval distractor risk, or raw-answer risk. Preserve the current rule that memory stores no task facts, IDs, answers, or benchmark-specific lessons. Avoid verbose global checklists and factual memory retrieval. This is task-general because reminders are selected by failure class rather than domain.

**Builder / Wiring Blueprint**

Preserve factory compatibility: `PlanningClass` injection, provider imports, project-root setup, optional vector memory wiring, and agent back-binding for tools. Update harness name, metadata round, module constants, and pairing reason only if Stage 3 creates a new candidate identity. Avoid changing benchmark loop, dataset, model backend, or evaluator behavior. Stage 1 found no evidence that builder wiring caused the failures.

**Interface Blueprint**

Make Planning -> Action and checker/memory -> Action interfaces concrete. Planning should hand off a compact status packet. Action should update the packet only from observations. Checker output should be structured as constraints, not advice. Memory should signal risk class, not facts. Final readiness should combine status packet rows, recent observations, failed-call registry, and raw-answer criteria. This interface remains simple because it is a checklist/status packet, not a new orchestration layer.

#### 6.3 Minimal Required Changes

- Add status-packet validation so Planning repairs executable-looking plans into obligation rows.
- Add action-owned stateful commit rows and block `complete_task` when required rows are unresolved or failed.
- Add schema and repeated-failure preflight before real tool execution.
- Add a compact failed-call registry with failure class and required changed repair.
- Add relation/evidence slot closure for multi-hop or ambiguous retrieval tasks.
- Add terminal raw-answer commit preflight before `final_answer`.
- Make checker output structured and enforceable, with throttled use at risk points only.
- Keep Memory procedural, sparse, and risk-aware without storing task facts or answers.
- Preserve builder wiring and single-executor ownership.

#### 6.4 Optional Enhancements

- Add read-only versus mutable task-shape routing if it can be inferred cheaply from tool names, descriptions, and terminal tool availability.
- Add a rare state snapshot check for long stateful tasks after multiple successful writes, provided it does not replace the final commit gate.
- Add a small answer-type canonicalization helper for common raw forms such as yes/no, date string, number string, binary string, list-to-string, and alias extraction.
- Add compact observation compression for long EnvScaler traces if it preserves failed-call and commit-row details.
- Add a checker-call counter to prevent repeated same-draft or same-risk checker loops.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] The generated harness must emit a compact status packet, not an executable first action, during initial planning.
- [Planning] If the plan contains top-level `tools` or planned calls as facts, the planner must repair it into obligations, bindings, blockers, remaining work, and final criteria.
- [Planning] Stateful tasks must get one row per required mutation or verification; read-only tasks should keep the packet minimal.
- [Action] The generated harness must preserve one acting executor for all real environment tools.
- [Action] The harness must block `complete_task` unless all required stateful rows are observation-closed or evidence-backed blocked.
- [Action] The harness must add preventive schema preflight for tool existence, required keys, obvious value-shape mismatches, and repeated identical failed calls.
- [Action] Failed calls must be classified before retry, and identical retries must require a later successful observation that changes the relevant precondition.
- [Action] Multi-hop transformations must consume only closed slots whose source observation satisfies the requested relation and value type.
- [Action] `final_answer` must pass a raw-answer commit check: answer type, decisive observation, raw field, allowed transformation, exact output string.
- [Memory] Memory must remain procedural and must not store task facts, item IDs, entity names, answers, golden values, or observed trajectory-specific facts as reusable memory.
- [Memory] IN-phase memory should emit at most one high-risk cue at a time and should be triggered by schema, repeated-failure, stateful-terminal, slot, distractor, or raw-answer risk.
- [Builder] Preserve provider wiring, `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent back binding.
- [Builder] Update harness metadata and module constants for the new candidate identity, but do not treat metadata cleanup as the main behavioral repair.
- [Interface] Planning status, action observations, memory risks, and checker constraints must share the same compact vocabulary: obligations, observed success, observed failure, blockers, remaining work, final criteria.
- [Interface] Checker output must be structured as constraints and must never be treated as environment evidence.
- [Preserve] Preserve direct execution on easy one-hop SearchQA and clean ToolHop chains; added gates should activate only at visible risk points.
- [Preserve] Preserve the current raw-answer focus and closed-set tool discipline.
- [Avoid] Do not add heavy multi-agent orchestration, parallel acting agents, or debate for mutable tasks.
- [Avoid] Do not hard-code benchmark item IDs, entity names, task domains, expected answers, or trajectory-specific tool traces.
- [Avoid] Do not solve stateful failures by blindly delaying terminal completion; use explicit unresolved rows and failed postconditions.
- [Avoid] Do not over-normalize final answers; preserve task-requested raw formatting, including leading zeros, `.0`, yes/no conventions, aliases, and date styles.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
