### PART 1: LOCALIZATION SUMMARY

The current winner under analysis is `harness_round02_02_7`, evaluated as `qwen3-8B-round_02_02-harness7` in `round03_04`. Its architecture is a direct single-executor ReAct harness with a compact `VERIFIER_CONTRACT` planning prompt, guarded task tools, a rare non-environment verifier tool, and lightweight procedural memory. The useful behavior to preserve is the efficient single-agent chain: it solves simple ToolHop and SearchQA cases cleanly when observations directly support each next hop, and it already calls `final_answer` reliably for QA tasks.

Stage 1 localized the dominant failures to Action and the Planning -> Action interface. EnvScaler failures are the largest structural problem: only 26 of 658 EnvScaler tasks reached full score, while 413 `complete_task` calls happened in non-full-score trajectories. This shows missing stateful side-effect tracking and missing terminal readiness gates. Tool schema errors are also high: 430 EnvScaler tool errors and 134 ToolHop tool errors indicate that the existing guard repairs some aliases but does not preflight required arguments, nested fields, enums, or unavailable tools before execution. The verifier is useful in concept but weak in enforcement: it can return missing-evidence warnings and still leave `next_safe_move: no_blocker`, which lets the executor finalize impossibility answers. SearchQA and ToolHop also show evidence-chain breaks and final raw-answer losses: 32 SearchQA examples had `subem=1.0` but `answer_correct=0.0`, meaning correct evidence often reached the trajectory but the final answer was not canonical.

The generalized capability gaps are: an action-owned stateful commit ledger, schema preflight before real tool execution, enforced verifier constraints, relation-grounded evidence binding from planning to action, final-answer canonicalization, and failure-class memory routing. The highest-leverage repair target is not a new heavy multi-agent architecture. The next harness should remain a direct single executor, but it should become ledger-guided and commit-aware: planning emits compact obligations, action updates them from observations, rare checkers enforce only high-risk blockers, and memory injects short phase-aware reminders keyed to the current failure class.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round01_6`

- **Observed Structure:** Single executor with `CANONICAL_TARGET` planning, final observation binding in Action, and phase-aware canonicalization memory.
- **Relevant Strength:** It has the best fair-first200 mixed score among round01 candidates, strong EnvScaler score, strong done proxy, and low max-step rate among top candidates. Its action pattern binds final answers to exact observations and normalizes only when the task asks for a date, number, unit, name, list, capitalization, or raw value.
- **Relevant Weakness / Risk:** SearchQA trails `harness_round01_5`, and the raw-answer discipline alone does not solve empty-result recovery or stateful postcondition failures.
- **Related Winner Failure:** Final-answer canonicalization failure; path-correct but final-wrong cases; partial SearchQA/ToolHop exactness losses.
- **Transferable Module Pattern:** Add an action-side raw-answer commit gate that extracts a minimal supported value from observations and rejects explanatory final prose.
- **Generalization Rationale:** Machine-graded short-answer tasks across domains need exact raw values, not explanations. Observation-bound canonicalization is domain-agnostic because it reasons over answer type and observed text, not benchmark-specific values.
- **Do Not Borrow:** Do not make canonicalization the only repair; it should be combined with stateful and schema controls.
- **Transfer Confidence:** High

#### Example: `harness_round01_5`

- **Observed Structure:** Direct single executor with `COMMIT_LEDGER` planning, sequential mutable-tool discipline, optional terminal preflight, and phase-aware commit memory.
- **Relevant Strength:** It is a strong SearchQA fair-slice candidate and demonstrates state-changing calls performed sequentially with observed results before terminal completion.
- **Relevant Weakness / Risk:** Full-run stability is lower than `harness_round01_6`; ToolHop correctness is moderate; cost and max-step rate remain high.
- **Related Winner Failure:** EnvScaler transactional completion without a verified side-effect ledger; premature `complete_task` after failed or partial mutations.
- **Transferable Module Pattern:** Borrow the commit-ledger idea: one compact row per required mutation or verification, with read-after-write confirmation and terminal blockers.
- **Generalization Rationale:** Any stateful API workflow requires confirmed entity IDs, successful writes, and postconditions before completion, independent of the specific domain.
- **Do Not Borrow:** Do not borrow high-frequency preflight checks or verbose ledger text that would slow simple QA tasks.
- **Transfer Confidence:** High

#### Example: `harness_round01_2`

- **Observed Structure:** QA-oriented single executor with an `EVIDENCE_CHAIN` plan, explicit evidence slots, observation arbitration, and support checks.
- **Relevant Strength:** Stable full-run mixed score among round01 candidates, consistent SearchQA tool use, and a planning contract that ties answer candidates to observed evidence.
- **Relevant Weakness / Risk:** ToolHop correctness does not improve over base, and it does not directly solve stateful completion failures.
- **Related Winner Failure:** SearchQA and multi-hop evidence chains stop on plausible but unverified snippets.
- **Transferable Module Pattern:** Use relation-specific evidence slots: target relation, required predicate, observed supporting snippet, rejected distractor, and final readiness.
- **Generalization Rationale:** Distractor snippets and relation drift appear in open-domain QA, database lookup, and ToolHop-style entity chains. Evidence slots transfer because they encode predicate support rather than domain facts.
- **Do Not Borrow:** Do not add broad debate or multiple answer solvers; keep arbitration rare and observation-bound.
- **Transfer Confidence:** High

#### Example: `harness_round01_3`

- **Observed Structure:** Single executor with `REPAIR_CONTROLLER` planning, explicit failure classification, soft duplicate-failure advisories, and phase-aware repair memory.
- **Relevant Strength:** It directly targets schema-aware repair and classifies failed calls as unknown tool, schema mismatch, missing entity, empty output, execution error, or contradiction.
- **Relevant Weakness / Risk:** It underperforms overall, has high token cost, and has weak ToolHop performance. The idea is useful, but the implementation is too expensive if used constantly.
- **Related Winner Failure:** Soft schema guard does not prevent malformed or under-specified tool calls; low-value exploration after empty or failed observations.
- **Transferable Module Pattern:** Borrow the failure-class taxonomy and make it trigger earlier and cheaper inside the action guard, before blind retries.
- **Generalization Rationale:** Tool failures across domains can be classified by execution semantics rather than task content, enabling generic repair moves.
- **Do Not Borrow:** Do not copy the costly repair-controller transcript or make every failure invoke a model checker.
- **Transfer Confidence:** Medium

#### Example: `harness_round01_8`

- **Observed Structure:** Direct executor with a compact `STATUS_PACKET` separating planned or pending items from observed successes, observed failures, remaining work, next step, and final criteria.
- **Relevant Strength:** Best fair-first200 ToolHop score among round01 candidates and strong full-run mixed score. It gives a concise cross-module status packet without adding acting subagents.
- **Relevant Weakness / Risk:** EnvScaler and SearchQA are weaker on the fair slice, and status-packet checks can be expensive if too frequent.
- **Related Winner Failure:** Planning/action interface failure; dependent-hop variables and final criteria are not visible to Action in a structured way.
- **Transferable Module Pattern:** Borrow the compact status packet, especially the separation between pending intent and observed facts.
- **Generalization Rationale:** All tool-use families need to distinguish what the agent plans from what the environment actually confirmed.
- **Do Not Borrow:** Do not borrow an always-on status checker or ToolHop-specialist verbosity.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_1`

- **Observed Structure:** Generated direct executor where `LEDGER_COMMIT` planning becomes a small execution ledger consumed by one ReAct executor, with rare non-environment readiness checking.
- **Relevant Strength:** It is close to the current winner's architecture but targets observation-backed finalization and commit readiness more directly.
- **Relevant Weakness / Risk:** It is not evaluated, and commit gates may slow easy read-only tasks if applied universally.
- **Related Winner Failure:** EnvScaler completion without a verified side-effect ledger; verifier not grounded in actual ledger rows.
- **Transferable Module Pattern:** Use a ledger-commit contract as the interface between planning and action, then call a readiness checker only when blockers remain or terminal completion is risky.
- **Generalization Rationale:** A compact observed ledger works for stateful APIs, ToolHop slots, and SearchQA evidence because it is just a structured view of obligations and observations.
- **Do Not Borrow:** Do not assume its unevaluated implementation is correct; borrow the design pattern only.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_2`

- **Observed Structure:** Generated repair-first direct executor with `REPAIR_REGISTRY` rows for obligations, bindings, blockers, failed-call classes, and final readiness.
- **Relevant Strength:** It makes failed-call provenance explicit and prevents blind repetition of identical bad calls.
- **Relevant Weakness / Risk:** It is not evaluated and may increase prompt footprint.
- **Related Winner Failure:** Schema/tool-call failures and low-value exploration after empty or failed observations.
- **Transferable Module Pattern:** Borrow a compact failed-call registry with `failure_class`, `last_arguments`, `changed_precondition`, and `required_repair` fields.
- **Generalization Rationale:** The repair registry is based on tool-call behavior, so it transfers across task domains and tool sets.
- **Do Not Borrow:** Do not add a separate repair actor or verbose registry if a simple guard observation can carry the needed fields.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_3`

- **Observed Structure:** Generated retrieval and multi-hop direct executor with `EVIDENCE_BINDING` rows for obligations, evidence bindings, blockers, intermediate variables, and final readiness.
- **Relevant Strength:** It directly targets SearchQA candidate arbitration and ToolHop intermediate-variable binding.
- **Relevant Weakness / Risk:** It is not evaluated, and evidence tables can become verbose; value for EnvScaler is uncertain.
- **Related Winner Failure:** Evidence-chain break and distractor-snippet finalization.
- **Transferable Module Pattern:** Borrow intermediate-variable binding: every downstream hop must reference an observed source value, and final answers must cite a decisive observation.
- **Generalization Rationale:** Variable binding is a domain-agnostic property of multi-step tool use.
- **Do Not Borrow:** Do not force detailed evidence tables on simple stateful API tasks where mutation ledgers matter more.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_4`

- **Observed Structure:** Generated stateful-workflow direct executor with `STATEFUL_GATE` planning, sequential commit rows, mutable commits, blockers, and final readiness.
- **Relevant Strength:** It directly targets mutation order, terminal blockers, and read-after-write verification while preserving direct execution on read-only tasks.
- **Relevant Weakness / Risk:** It is not evaluated, and overused gate checks can delay terminal completion.
- **Related Winner Failure:** EnvScaler false completion and missing stateful postcondition checks.
- **Transferable Module Pattern:** Borrow stateful gate checks only before risky state-changing calls or terminal completion, keyed to unresolved mutable rows.
- **Generalization Rationale:** The same stateful gate applies to any workflow with create, update, delete, reserve, enroll, assign, or cancel operations.
- **Do Not Borrow:** Do not make every action pass through the gate; keep it rare and risk-triggered.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_5`

- **Observed Structure:** Generated raw-answer specialist with `RAW_ANSWER` planning, answer type, raw field, final readiness, and rare `raw_answer_check`.
- **Relevant Strength:** It targets exact finalization losses for dates, numbers, lists, IDs, yes/no, and short raw values.
- **Relevant Weakness / Risk:** It does not repair exploration, retrieval relation errors, or stateful workflows by itself.
- **Related Winner Failure:** Final-answer canonicalization failure.
- **Transferable Module Pattern:** Borrow a narrow raw-field row: requested answer type, decisive observation, allowed transformation, and exact final string.
- **Generalization Rationale:** Final rawness is a terminal contract across short-answer task families and structured API outputs.
- **Do Not Borrow:** Do not use the checker for every final answer; use it when final text contains prose, multiple candidates, or transformed values.
- **Transfer Confidence:** High

#### Example: `harness5`

- **Observed Structure:** AgentOrchestra-style heavier multi-agent harness with richer planning, multiple role-like components, and Cerebra fusion memory.
- **Relevant Strength:** It shows that broader coordination can improve coverage in some cases and maintains reliable SearchQA tool use.
- **Relevant Weakness / Risk:** It has the highest token cost, high max-step rate, and the pool explicitly notes that multi-agent orchestration is too heavy for Qwen3-8B.
- **Related Winner Failure:** This is mainly a negative control for action orchestration choices.
- **Transferable Module Pattern:** Borrow only the principle that checking should be separate from acting; do not borrow the heavy orchestration.
- **Generalization Rationale:** Non-acting checks can help, but parallel or role-heavy acting agents create cost and handoff risk in stateful environments.
- **Do Not Borrow:** Do not add multi-agent debate, multiple acting workers, or broad memory fusion.
- **Transfer Confidence:** Low

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Action | EnvScaler `complete_task` often occurs before full state completion | Stateful side-effect ledger and terminal readiness gate | `harness_round01_5`, `harness_round02_02_4`, `harness_round02_02_1` | Sequential commit rows, read-after-write checks, rare terminal readiness checker | Any mutable workflow needs confirmed IDs, successful writes, and postconditions | Always-on gates and verbose ledgers | High | Medium |
| Action | Malformed or under-specified real tool calls reach the environment | Schema preflight and structured repair before execution | `harness_round01_3`, `harness_round02_02_2` | Failure-class registry plus changed-argument requirement before retry | Schema mismatch, unknown tools, invalid enums, and empty results are cross-domain failure classes | Costly repair-controller loops | High | Medium |
| Action | Verifier can report missing evidence but still permit finalization | Enforced verifier contract | Winner pattern plus `harness_round01_4` non-acting critic discipline | Parse checker output into blockers and require the next action to resolve them | Non-acting checkers transfer if they constrain action without operating the environment | Heavy critic use or second acting agent | High | Low |
| Planning | Plans are useful but too free-form for relation grounding | Structured evidence and obligation contract | `harness_round01_2`, `harness_round02_02_3`, `harness_round01_8` | Target relation, evidence slot, observed binding, rejected distractor, final readiness | Predicate-specific evidence prevents distractor answers across QA and lookup tasks | Large evidence tables on simple tasks | High | Medium |
| Action | Correct evidence is often submitted as prose or wrong format | Raw final-answer canonicalization | `harness_round01_6`, `harness_round02_02_5` | Raw field, answer type, decisive observation, allowed transformation | Exact raw values are required by many terminal contracts | Over-normalization and redundant final checks | High | Low |
| Memory | Generic reminders do not route by failure class | Phase-aware, failure-class procedural guidance | Winner memory plus dynamic cheatsheet/provider-lite style relevance filtering | Short reminders selected by current markers: schema error, empty result, verifier blocker, raw final risk, stateful postcondition | Procedural routing transfers without storing task facts or answers | Persistent task-fact memory and verbose retrieved workflows | Medium | Low |
| Cross-Module Interface | Action cannot reliably consume planning obligations | Compact Planning -> Action status packet | `harness_round01_8`, `harness_round02_02_1` | Pending vs observed rows, blockers, final criteria, next safe action | All tool-use tasks need a shared distinction between intent and evidence | Complex multi-agent handoff | High | Medium |
| Builder/Wiring | Metadata still identifies the harness as round02_02 inside round03_04 | Clear identity and compatibility metadata | None; repair within winner pattern | Preserve `PlanningClass` injection and tool binding while updating harness name, round, and focus | Correct identity helps tracking without changing benchmark behavior | Changing evaluator, dataset, or factory contracts | High | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve the direct single-executor topology in Action because successful ToolHop and SearchQA trajectories show it is sufficient for clean serial evidence chains.
- Preserve rare non-environment checking in Action because it avoids state corruption from multiple acting agents while still allowing high-risk readiness review.
- Preserve compact initial plans in Planning because target, required evidence, remaining work, and final criteria already help simple tasks stay ordered.
- Preserve low-noise procedural memory in Memory because it avoids storing benchmark facts, IDs, or answers and therefore reduces overfitting risk.
- Preserve builder compatibility in Builder/Wiring because `PlanningClass` injection, project-root setup, vector-memory wiring, and tool-agent binding are required by the local harness factory.
- Preserve the existing guard's useful alias repair and scalar-to-array coercion in Action while strengthening it with true preflight.

#### Borrow

- Borrow from `harness_round01_5` into Action: sequential commit rows and read-after-write readiness checks, expected to reduce false EnvScaler completion and generalize to all mutable API workflows.
- Borrow from `harness_round01_6` and `harness_round02_02_5` into Action: raw answer type, decisive observation, and exact final string binding, expected to recover path-correct but final-wrong QA cases across short-answer tasks.
- Borrow from `harness_round01_2` and `harness_round02_02_3` into Planning and the Planning -> Action interface: relation-specific evidence slots and intermediate-variable bindings, expected to reduce distractor snippet answers across retrieval and ToolHop chains.
- Borrow from `harness_round01_3` and `harness_round02_02_2` into Action: failure-class registry and changed-argument retry discipline, expected to reduce malformed calls, blind retries, and empty-result loops across tool schemas.
- Borrow from `harness_round01_8` and `harness_round02_02_1` into Cross-Module Interface: compact status packet separating pending intent from observed facts, expected to make final readiness visible without adding a second acting agent.
- Borrow from lightweight memory provider references into Memory: lexical or marker-based relevance filtering and short procedural notes, expected to keep reminders targeted without storing task facts.

#### Avoid

- Avoid copying `harness5` heavy orchestration because its token cost, max-step rate, and role handoff risk are poor fits for the Stage 1 failures; the risk is complexity and stateful-task regression.
- Avoid always-on checkers from any example because Stage 1 shows the winner already spends many calls and some verifier loops reach 20 or 24 calls; the risk is complexity and cost regression.
- Avoid benchmark-specific fallback values, fixed date ranges, entity aliases, or answer lists because Stage 2 must produce transferable harness behavior rather than trajectory-specific patches; the risk is weak transfer and contamination.
- Avoid making memory store task facts, IDs, or answers because the current memory's procedural-only design is a preservation target; the risk is stale or overfit guidance.
- Avoid replacing the existing single executor with multiple acting workers because stateful EnvScaler tasks require one owner of environment state; the risk is conflicting mutations and hard-to-arbitrate observations.
- Avoid large evidence tables on every task because simple QA and direct ToolHop chains should stay cheap; the risk is prompt bloat and slower easy-task completion.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Ledger-Guided Stateful Completion Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Transactional completion without a verified side-effect ledger
- **Current Weakness:** The executor calls `complete_task` after partial progress, failed mutations, or unresolved postconditions.
- **Desired Behavior:** The new harness should maintain compact mutable-commit rows for required state changes, observed target IDs, write success, verification status, blockers, and terminal readiness. `complete_task` should be allowed only when all required mutable rows are closed by successful observations or explicitly marked not required by current evidence.
- **Borrowed Pattern:** `harness_round01_5` commit discipline plus `harness_round02_02_4` stateful gate pattern.
- **Preserved Behavior:** Keep one executor as the only environment actor.
- **Implementation Shape:** Add an action-side status helper and prompt contract that tracks `obligation`, `bound_id`, `mutation_tool`, `success_observation`, `postcondition_check`, and `blocker`. Add a rare non-environment readiness check only when the next action is terminal or a state-changing call conflicts with open blockers.
- **Generalization Rationale:** Stateful workflows in booking, healthcare, finance, education, and account management all require confirmed mutations before completion.
- **Complexity:** Medium
- **Expected Impact:** Improve EnvScaler full-score rate, reduce false `Task Completed` endings, and reduce partial-score completions.
- **Regression Risk:** A too-strict gate may prevent completion when the environment does not expose a direct verification tool.

**[Direction 2: Hard Schema Preflight and Repair Registry]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Soft schema guard does not prevent malformed or under-specified real tool calls
- **Current Weakness:** The current guard repairs some extra keys but still lets missing required fields, invalid enum values, unavailable tools, and bad nested objects reach execution.
- **Desired Behavior:** Before a real tool is called, validate tool existence, allowed keys, required keys, nested required fields, enum values, nullable object shape, and obvious placeholder IDs. If validation fails, return a structured repair observation instead of calling the environment.
- **Borrowed Pattern:** `harness_round01_3` failure classification and `harness_round02_02_2` repair registry.
- **Preserved Behavior:** Preserve existing alias repair and scalar-to-array coercion when they clearly map to the schema.
- **Implementation Shape:** Extend the guard with deterministic schema validation and a compact failed-call registry containing `failure_class`, `tool`, `bad_arguments`, `allowed_schema`, and `required_change`. After two failures in the same class, require a changed argument, changed tool, or newly observed precondition before retry.
- **Generalization Rationale:** Schema errors are caused by tool contracts rather than domain content, so preflight and repair transfer across any tool set.
- **Complexity:** Medium
- **Expected Impact:** Reduce TypeError traces, invalid relationship calls, unknown-tool attempts, and low-value retry loops in EnvScaler and ToolHop.
- **Regression Risk:** Over-aggressive validation may block permissive tools that accept optional or partially specified arguments.

**[Direction 3: Enforced Verifier Constraint Protocol]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Verifier output becomes a substitute for evidence instead of a constraint on next action
- **Current Weakness:** The verifier emits free text and can produce contradictory signals, such as missing evidence plus `no_blocker`, without constraining the executor.
- **Desired Behavior:** The verifier should return strict fields and the action loop should treat unresolved `missing_or_risk` as a blocker. A verifier call should either authorize finalization with observed support or name exactly one next-action constraint that the executor must satisfy.
- **Borrowed Pattern:** Keep the winner's rare verifier, adapted with `harness_round01_4` non-acting critic discipline and `harness_round02_02_1` ledger-readiness framing.
- **Preserved Behavior:** Preserve rare checker use and exact-repeat throttling.
- **Implementation Shape:** Make verifier outputs parseable with fields `verdict`, `blocker`, `required_observation`, `allowed_next_action`, and `final_ready`. Add a rule that `final_ready` is false if the verifier names missing evidence, empty results, unknown entity, schema risk, or unresolved stateful rows.
- **Generalization Rationale:** A checker that constrains action rather than replacing evidence can help any domain with ambiguous retrieval, failed tools, or risky terminal decisions.
- **Complexity:** Low
- **Expected Impact:** Reduce premature impossibility answers and repeated verifier loops, especially ToolHop/SearchQA cases with empty or noisy observations.
- **Regression Risk:** If checker output parsing is brittle, the executor may ignore useful warnings or become stuck behind false blockers.

**[Direction 4: Evidence Binding and Relation-Specific Planning Contract]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Search and multi-hop evidence chains stop on plausible but unverified snippets
- **Current Weakness:** Planning lists evidence requirements in prose, but Action does not receive a structured target relation or an explicit way to reject distractors.
- **Desired Behavior:** Planning should emit compact obligations for target relation, required predicates, intermediate variables, acceptable answer type, and final criteria. Action should update observed bindings only from tool observations and verify that the final answer satisfies the target relation rather than a nearby relation.
- **Borrowed Pattern:** `harness_round01_2` evidence chain, `harness_round02_02_3` evidence binding, and `harness_round01_8` status packet separation.
- **Preserved Behavior:** Preserve concise planning and avoid multi-agent debate for ordinary QA.
- **Implementation Shape:** Add a shared status section with rows such as `slot`, `source_observation`, `relation_supported`, `distractor_risk`, `remaining_hop`, and `final_raw_form`. Use a rare evidence check only when multiple candidates, near-match snippets, or unsupported transformations appear.
- **Generalization Rationale:** Predicate binding is a domain-agnostic guard against distractor snippets and wrong-hop variable use.
- **Complexity:** Medium
- **Expected Impact:** Improve SearchQA exactness and ToolHop correctness by reducing relation drift and unsupported dependent hops.
- **Regression Risk:** Too much evidence bookkeeping can slow simple tasks where one observation directly answers the question.

**[Direction 5: Raw Final-Answer Commit Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Final-answer canonicalization is not enforced
- **Current Weakness:** The executor submits full sentences, extra context, leading zeros, over-specific dates, or explanations even when the raw answer appears in the observation.
- **Desired Behavior:** Before `final_answer`, identify the requested answer type, decisive observation, raw field, allowed transformation, and exact final string. The final answer should contain only the raw value unless the task explicitly requires a list or formatted transformation.
- **Borrowed Pattern:** `harness_round01_6` canonical answer binding and `harness_round02_02_5` raw-answer contract.
- **Preserved Behavior:** Preserve the high rate of successful `final_answer` calls in QA tasks.
- **Implementation Shape:** Add a lightweight finalization preflight inside the action prompt or checker: reject final text with explanatory clauses, unsupported aliases, extra dates, or unrequested context; prefer exact observed spans and task-requested transformations.
- **Generalization Rationale:** Exact final formatting is a reusable terminal discipline for SearchQA, ToolHop, API answer fields, and any machine-graded short-answer task.
- **Complexity:** Low
- **Expected Impact:** Convert many path-correct partial cases into exact-answer cases, especially the SearchQA `subem=1` but `answer_correct=0` bucket.
- **Regression Risk:** Over-normalization may remove necessary disambiguation when multiple aliases are valid.

**[Direction 6: Failure-Class Procedural Memory]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Low-value exploration after empty or failed observations; generic memory does not redirect recurring failures
- **Current Weakness:** Memory warnings are relevant but broad, so the executor can receive the warning and still repeat parameter guessing or premature finalization.
- **Desired Behavior:** Memory should remain procedural and non-factual, but route short reminders by current failure class: schema missing-required, empty result, repeated failed call, verifier blocker, raw final risk, and stateful postcondition risk.
- **Borrowed Pattern:** Winner memory plus lightweight provider relevance filtering from `dynamic_cheatsheet_provider_lite` and workflow-style procedural distillation from `agent_workflow_memory_provider_lite`, without storing task facts.
- **Preserved Behavior:** Keep memory low-noise and avoid persisted task answers, IDs, or benchmark traces.
- **Implementation Shape:** Use marker detection in the current context to emit at most one or two compact reminders per phase. Include instructions such as `classify empty result before broadening`, `do not repeat same failed call without changed precondition`, and `terminal claim requires observed support`.
- **Generalization Rationale:** Failure-class routing uses execution signals rather than task content, so it transfers across unseen domains and tool schemas.
- **Complexity:** Low
- **Expected Impact:** Reduce repeated repair loops, premature impossibility answers, and finalization despite unresolved blockers.
- **Regression Risk:** Too many memory messages could bloat prompts and compete with fresh observations.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The next harness should be a planning-guided single executor with strict execution hygiene: direct and efficient on simple tasks, but ledger-aware when mutations, schema errors, ambiguous evidence, or risky final answers appear. It should feel like a conservative evolution of the winner rather than a new architecture: one actor owns the environment, rare non-environment checks enforce specific blockers, and memory supplies compact procedural nudges keyed to the current risk.

#### 6.2 Module-Level Blueprint

Planning Blueprint

Implement a compact `LEDGER_EVIDENCE_COMMIT` style plan. It should preserve target, required evidence, remaining work, and final criteria, but add structured rows for `obligations`, `observed_bindings`, `blockers`, `answer_type`, and `final_readiness`. For stateful-looking tasks, include mutable obligations and postcondition expectations. For read-only QA or ToolHop tasks, include relation-specific evidence slots and intermediate variables. Avoid verbose chain-of-thought, benchmark labels, or planned actions treated as facts. The evidence comes from Stage 1 SearchQA relation drift, ToolHop variable errors, and EnvScaler terminal failures; the design is task-general because it represents obligations and observations rather than domain-specific entities.

Action Blueprint, including concrete agent collaboration / orchestration if applicable

Keep one acting executor. Strengthen the guarded task tools with deterministic schema preflight before execution. Add a compact action-side status ledger updated only from observations: successful bindings, failed calls, mutable commits, unresolved blockers, and final raw field. Keep the existing verifier idea but make it parseable and enforceable; use it only before terminal calls, repeated failures, risky state-changing calls, or ambiguous final answers. No parallel acting workers, no debate for mutable tasks, and no heavy coordinator-worker topology. The motivating evidence is high tool-error counts, false `complete_task` completions, and verifier outputs that failed to constrain action. This is task-general because it changes execution discipline rather than adding domain facts.

Memory Blueprint

Keep the memory provider lightweight and procedural. Add marker-based routing so BEGIN gives a short global rule and IN emits at most one or two reminders targeted to the current risk class. Suggested classes are schema repair, empty-result recovery, repeated failed call, verifier blocker, raw final answer, and stateful postcondition. Preserve the current prohibition on storing task facts, IDs, answers, or trace-specific shortcuts. Avoid SkillWeaver-style callable skill injection for this harness; it is unnecessary and could change the action surface. The evidence is Stage 1's observation that memory guidance was relevant but too generic to alter failures.

Builder / Wiring Blueprint

Preserve the winner's factory compatibility: `PlanningClass` injection, selected-tool binding, vector memory wiring, project-root setup, and `max_tool_calls_per_step` defaults. Update harness metadata so the generated candidate has a unique round03_04 identity, a new harness name, and accurate module names. Avoid changing benchmark, evaluator, dataset, model backend, or external tool contracts. The wiring change is low-risk but important for registry clarity because the current round03_04 base still identifies itself as round02_02.

Interface Blueprint, if needed

Use a simple Planning -> Action text contract rather than a new orchestration layer. The plan should expose rows that the action prompt can quote and update: obligation, observed binding, blocker, final readiness, and raw final form. Action observations should update the ledger in summaries or action reasoning, and verifier checks should refer to ledger rows by name. Memory should not override the ledger; it should only remind the executor how to handle the current failure class. This interface directly addresses Stage 1's finding that planning produced useful prose but action could not reliably consume it.

#### 6.3 Minimal Required Changes

- Add deterministic schema preflight to guarded tools before real execution.
- Add an action-visible status ledger separating pending obligations from observed successes and observed failures.
- Add mutable commit rows and a terminal gate before `complete_task`.
- Replace free-form verifier output with parseable blocker and final-readiness fields.
- Add raw final-answer binding before `final_answer`.
- Add relation-specific evidence slots for read-only and multi-hop tasks.
- Add failure-class procedural memory reminders without storing task facts.
- Update harness metadata to a unique round03_04 candidate identity.

#### 6.4 Optional Enhancements

- Add a rare evidence-binding checker only when multiple answer candidates or distractor snippets appear.
- Add a rare stateful-gate checker only when a terminal or state-changing call has unresolved mutable rows.
- Add a compact failed-call registry summary into periodic adaptation after repeated failures.
- Add simple tool mutability inference from tool names and schemas to decide whether to emphasize commit rows or evidence rows.
- Add a final raw-answer lint that flags prose, unsupported aliases, leading/trailing explanation, or unrequested formatting.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Generate a compact structured plan with obligations, observed bindings, blockers, answer type, and final readiness.
- [Planning] Keep planned actions separate from observed facts; only observations may close obligations.
- [Planning] Include relation-specific evidence targets for read-only QA and intermediate-variable tasks.
- [Action] Keep a single environment-acting executor; do not introduce multiple acting workers.
- [Action] Add deterministic schema preflight for tool existence, required keys, nested required fields, enum values, and placeholder-like arguments.
- [Action] Return structured repair observations without executing the real tool when schema preflight fails.
- [Action] Maintain a compact status ledger for successful observations, failed observations, mutable commits, blockers, and final raw fields.
- [Action] Block `complete_task` when mutable commit rows or postcondition checks remain unresolved.
- [Action] Before `final_answer`, bind the exact raw answer to a decisive observation and strip unsupported explanatory prose.
- [Action] Make verifier/checker output parseable and enforce it as a blocker or next-action constraint.
- [Memory] Keep reminders procedural, compact, phase-aware, and selected by current failure markers.
- [Memory] Do not store task-specific facts, IDs, answers, fixed examples, or benchmark-specific heuristics.
- [Builder] Preserve local harness factory compatibility, including `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent binding.
- [Builder] Update harness name, round metadata, module constants, and description so the candidate is not confused with `round02_02` or existing pool entries.
- [Interface] Pass planning obligations to action in a format that action can update after observations.
- [Interface] Let memory remind but never override observed ledger state.
- [Preserve] Preserve the winner's efficient direct execution on simple ToolHop and SearchQA chains.
- [Preserve] Preserve rare non-environment checking rather than broad multi-agent orchestration.
- [Avoid] Do not copy `harness5` heavy AgentOrchestra-style coordination.
- [Avoid] Do not hard-code benchmark item IDs, answers, date ranges, entity names, golden values, or trajectory-specific recovery scripts.
- [Avoid] Do not call checkers on every step; checks must be tied to terminal risk, repeated failure, schema risk, or ambiguous evidence.
- [Avoid] Do not treat empty results as proof of impossibility without classified recovery and an evidence-backed blocker.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
