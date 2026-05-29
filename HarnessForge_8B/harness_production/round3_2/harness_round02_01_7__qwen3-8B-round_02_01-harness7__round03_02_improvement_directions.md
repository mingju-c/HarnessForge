### PART 1: LOCALIZATION SUMMARY

The current winner under analysis is `harness_round02_01_7`, evaluated as `qwen3-8B-round_02_01-harness7` in `round03_02`. Its architecture is a direct single-executor ReAct harness with compact recovery-status planning, guarded task tools, a non-environment `recovery_contract_check`, and lightweight procedural memory. The useful baseline behavior is worth preserving: the harness keeps one actor in charge of the environment, calls terminal tools reliably in many QA tasks, and solves simple linear ToolHop chains when each observation directly supports the next hop.

Stage 1 localized the dominant failures to Action and the Planning -> Action interface. EnvScaler is the largest failure bucket: only 30/658 EnvScaler tasks reached full score, while `Task Completed` appeared in 584 EnvScaler outputs and 554 of those were not full-score. This indicates missing stateful side-effect tracking and missing terminal readiness gating rather than a lack of terminal calls. Tool-use repair is the second major issue: `success: false` observations appeared in 474/658 EnvScaler trajectories, repeated-failure advisories appeared in 258/658 EnvScaler trajectories, unknown tools appeared in 115/658 EnvScaler trajectories, and ToolHop wrong cases averaged 10.88 tool calls. The current guard and memory warn about failure but do not force materially changed repairs. SearchQA and ToolHop also show evidence-binding failures: SearchQA exact correctness is 129/325, ToolHop exact correctness is 131/258, and some wrong cases already contain enough partial evidence but submit the wrong relation, wrong slot, or wrong raw format.

The generalized capability gaps are: a shared stateful progress ledger, a hard retry and route-change protocol, tool schema and allowed-tool preflight, observation-grounded slot binding for multi-hop transformations, relation-specific evidence verification for retrieval tasks, terminal raw-answer canonicalization, and failure-class procedural memory. The highest-leverage repair target is a compact cross-module status contract consumed by the same single executor. Stage 3 should not add heavy multi-agent orchestration. It should evolve the winner into a direct but ledger-guided harness: planning emits compact obligations, action updates them only from observations, rare checkers enforce specific blockers, and memory supplies low-noise procedural reminders keyed to the current failure class.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round01_6`

- **Observed Structure:** Direct single executor with `CANONICAL_TARGET` planning, final observation binding in Action, and phase-aware canonicalization memory.
- **Relevant Strength:** It is the strongest round01 parent in the pool: fair-first200 mixed score 0.4983, EnvScaler score 0.5105, EnvScaler done 0.8, and the lowest fair-slice max-step rate among the top round01 candidates. Its action pattern binds answers to observed values and normalizes only according to requested answer type.
- **Relevant Weakness / Risk:** Its SearchQA trails `harness_round01_5`, and canonicalization alone does not solve stateful partial completion or repeated failed calls.
- **Related Winner Failure:** Final-answer canonicalization is underdeveloped; evidence can be present but final answer format is wrong.
- **Transferable Module Pattern:** Borrow the action-side raw-answer commit gate: requested answer type, decisive observation, allowed transformation, and exact terminal string.
- **Generalization Rationale:** Exact raw-value commitment is domain-agnostic because it depends on the terminal contract and observed evidence, not benchmark-specific facts.
- **Do Not Borrow:** Do not treat canonicalization as the only repair; it must be paired with stateful and repair controls.
- **Transfer Confidence:** High

#### Example: `harness_round01_5`

- **Observed Structure:** Direct single executor with `COMMIT_LEDGER` planning, sequential mutable-tool discipline, optional terminal preflight, and phase-aware commit memory.
- **Relevant Strength:** It has strong fair-first200 mixed performance, the best SearchQA score among round01 candidates, and a clear sequential commit pattern for mutable tools.
- **Relevant Weakness / Risk:** Full-run stability drops behind `harness_round01_6`; ToolHop is only moderate; cost and max-step rate remain non-trivial.
- **Related Winner Failure:** Stateful task checklist drift and premature completion.
- **Transferable Module Pattern:** Borrow compact commit rows for required mutations, target IDs, write success, verification status, and terminal blockers.
- **Generalization Rationale:** Any mutable API workflow requires successful writes and confirmed postconditions before terminal completion.
- **Do Not Borrow:** Do not borrow verbose or always-on preflight behavior that slows simple read-only tasks.
- **Transfer Confidence:** High

#### Example: `harness_round01_8`

- **Observed Structure:** Direct executor with a compact `STATUS_PACKET` separating planned or pending work from observed success, observed failure, remaining work, next step, and final criteria.
- **Relevant Strength:** It has the best fair-first200 ToolHop score among round01 candidates and a strong full-run mixed score. Its central transferable idea is the strict separation between intent and observation.
- **Relevant Weakness / Risk:** EnvScaler and SearchQA fair-slice performance are weaker, and status checks can be expensive if too frequent.
- **Related Winner Failure:** Planning/action interface failure; action cannot reliably consume plan obligations or distinguish planned rows from observed facts.
- **Transferable Module Pattern:** Borrow the compact status packet as the shared Planning -> Action contract.
- **Generalization Rationale:** All tool-use tasks need to distinguish what the agent intends from what the tools have actually confirmed.
- **Do Not Borrow:** Do not copy ToolHop-specialist verbosity or make status checking routine on every step.
- **Transfer Confidence:** High

#### Example: `harness_round01_3`

- **Observed Structure:** Single executor with `REPAIR_CONTROLLER` planning, explicit failure classification, duplicate-failure advisories, and phase-aware repair memory.
- **Relevant Strength:** It names the exact failure classes needed by the winner: unknown tool, schema mismatch, missing entity, empty output, execution error, and contradiction.
- **Relevant Weakness / Risk:** It underperforms overall, has high cost, and weak ToolHop performance. The failure taxonomy is more useful than the full harness.
- **Related Winner Failure:** Tool schema and tool-existence control remains too soft; recovery loops repeat failed routes.
- **Transferable Module Pattern:** Borrow the failure-class taxonomy and use it inside the action guard before blind retries.
- **Generalization Rationale:** Tool failures can be classified by execution semantics rather than by domain content.
- **Do Not Borrow:** Do not copy a costly repair-controller transcript or model-call-heavy repair cycle.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_01_2`

- **Observed Structure:** Generated repair-ledger direct executor with `REPAIR_LEDGER` planning, failed-call tracking, repaired arguments, changed preconditions, and optional `repair_triage_check`.
- **Relevant Strength:** It directly targets repeated failed calls while preserving the single-executor flow.
- **Relevant Weakness / Risk:** It is pending evaluation in the registry, so its implementation quality is unproven. Repair bookkeeping can become expensive if invoked too often.
- **Related Winner Failure:** Failed calls trigger textual recovery status but not a different executable route.
- **Transferable Module Pattern:** Borrow the compact repair ledger: `last_failure`, `failure_class`, `changed_precondition`, `repaired_arguments`, and `next_valid_route`.
- **Generalization Rationale:** A failed-call registry transfers across APIs because it records tool behavior and argument provenance, not benchmark entities.
- **Do Not Borrow:** Do not add a separate repair agent or call the checker for every ordinary failure.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_01_3`

- **Observed Structure:** Generated retrieval-arbitration direct executor with `EVIDENCE_ARBITER` planning, target predicate, candidate evidence, rejected distractors, and final criteria.
- **Relevant Strength:** It directly addresses SearchQA candidate confusion and near-match finalization without adding parallel actors.
- **Relevant Weakness / Risk:** It is unevaluated and may add unnecessary overhead outside read-only retrieval tasks.
- **Related Winner Failure:** SearchQA evidence sufficiency is shallow and relation verification is weak.
- **Transferable Module Pattern:** Borrow relation-specific evidence rows: requested relation, answer type, supporting snippet, rejected nearby relation, and final readiness.
- **Generalization Rationale:** Distractor control and predicate support are general retrieval requirements across open-domain search, database lookup, and document QA.
- **Do Not Borrow:** Do not force detailed retrieval arbitration on stateful mutation tasks.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_01_4`

- **Observed Structure:** Generated typed slot-chain direct executor with `SLOT_CHAIN_LEDGER` planning, prerequisite slots, observed bindings, unresolved slots, and optional `slot_chain_check`.
- **Relevant Strength:** It directly targets ToolHop prerequisite failures and prevents transformation tools from consuming unresolved placeholders.
- **Relevant Weakness / Risk:** It is unevaluated and may overfit read-only multi-hop tasks if applied too broadly.
- **Related Winner Failure:** Evidence-chain slot binding breaks under failed or ambiguous lookups.
- **Transferable Module Pattern:** Borrow typed slot rows and a rule that extraction, arithmetic, date, encoding, or string transformation must consume observed prerequisite slots.
- **Generalization Rationale:** Any multi-hop tool chain depends on passing observed values, not task wording or source entities, into downstream tools.
- **Do Not Borrow:** Do not create large slot tables for simple direct-answer searches or stateful write tasks.
- **Transfer Confidence:** High

#### Example: `harness_round02_01_5`

- **Observed Structure:** Generated stateful commit specialist with `STATEFUL_COMMIT_LEDGER` planning, one row per required mutation or verification, target IDs, write status, read-after-write checks, and optional `commit_readiness_check`.
- **Relevant Strength:** It is the closest pool example to the winner's dominant EnvScaler failure.
- **Relevant Weakness / Risk:** It is unevaluated and may add unnecessary bookkeeping to read-only tasks.
- **Related Winner Failure:** EnvScaler false completion and missing postcondition checks.
- **Transferable Module Pattern:** Borrow the stateful commit ledger but activate it only when tool schemas or task text imply mutable operations.
- **Generalization Rationale:** Sequential observed commits apply to all domains with create, update, delete, assign, reserve, enroll, or cancel operations.
- **Do Not Borrow:** Do not make read-only QA follow the full stateful ledger.
- **Transfer Confidence:** High

#### Example: `harness_round02_01_8`

- **Observed Structure:** Generated compact hybrid direct executor with `COMPACT_STATUS_FUSION`, integrating pending rows, successes, failures, slots/evidence, remaining work, and final criteria.
- **Relevant Strength:** It fuses the main repair ideas in one compact contract and activates detail only when the task shape warrants it.
- **Relevant Weakness / Risk:** It is unevaluated, and hybrid controls may dilute specialist gains if the contract becomes vague.
- **Related Winner Failure:** Multiple high-priority winner failures require one shared but compact interface rather than disconnected prompts.
- **Transferable Module Pattern:** Borrow the compact fusion idea, but make the fields concrete: mutable rows, evidence/slot rows, failed-call registry, and terminal readiness.
- **Generalization Rationale:** A single compact status packet can cover stateful, retrieval, and ToolHop risks while preserving the direct executor.
- **Do Not Borrow:** Do not create a broad checklist that lacks enforceable ownership or hard stop rules.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_7`

- **Observed Structure:** Generated verifier-contract direct executor with compact verifier constraints, checker throttling, and phase-aware verifier memory.
- **Relevant Strength:** It preserves one acting executor while forcing verifier output into concrete next-action constraints.
- **Relevant Weakness / Risk:** It is unevaluated in the registry, and checker calls can still add token cost if triggered too often.
- **Related Winner Failure:** The current `recovery_contract_check` is advisory and can become a substitute for evidence.
- **Transferable Module Pattern:** Borrow parseable verifier fields and next-action constraints, not broader verification frequency.
- **Generalization Rationale:** A non-acting checker transfers when it constrains finalization and retries based on observed blockers rather than domain content.
- **Do Not Borrow:** Do not add a second acting agent or allow repeated checker loops.
- **Transfer Confidence:** Medium

#### Example: `harness5`

- **Observed Structure:** AgentOrchestra-style heavy orchestration with multiple role-like components and Cerebra fusion memory.
- **Relevant Strength:** It demonstrates broader coordination and maintains reliable SearchQA tool use in the pool.
- **Relevant Weakness / Risk:** It has the highest token cost, high max-step rate, and the pool notes that multi-agent orchestration is too heavy for Qwen3-8B.
- **Related Winner Failure:** Mainly a negative control for orchestration choices.
- **Transferable Module Pattern:** Borrow only the principle that checking should be non-acting and separated from environment mutation.
- **Generalization Rationale:** State ownership matters in mutable environments; multiple acting workers would increase conflict risk.
- **Do Not Borrow:** Do not add heavy multi-agent debate, multiple environment actors, or broad memory fusion.
- **Transfer Confidence:** Low

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Cross-Module Interface | Planning obligations remain prose and Action can finalize with open rows | Compact shared status contract with pending vs observed facts | `harness_round01_8`, `harness_round02_01_8` | Status packet with pending rows, observed success, observed failure, blockers, final criteria | Every tool-use task needs a shared distinction between intent and observed evidence | Always-on status checker and verbose packets | High | Medium |
| Action, tool-use repair | Unknown tools, malformed arguments, and repeated failed calls consume budget | Schema preflight plus failed-call repair registry | `harness_round01_3`, `harness_round02_01_2` | Failure-class taxonomy, changed-precondition requirement, repaired-argument row | Tool schema and retry failures are cross-domain execution errors | Costly repair-controller loops | High | Medium |
| Action, stateful execution | EnvScaler tasks call `complete_task` after partial or failed writes | Stateful commit ledger and terminal readiness gate | `harness_round01_5`, `harness_round02_01_5` | Sequential commit rows, target ID binding, read-after-write status, terminal blockers | Mutable workflows require confirmed postconditions across domains | Full stateful ledger on read-only QA | High | Medium |
| Action, evidence/slot execution | ToolHop transformations use unresolved or wrong entities | Observation-grounded slot ledger | `harness_round02_01_4`, `harness_round01_8` | Prerequisite slots, observed bindings, unresolved-slot blockers | Multi-hop transformations must consume observed intermediate values | Large slot tables on direct tasks | High | Medium |
| Planning | SearchQA finalizes from nearby but wrong relation | Relation-specific evidence target and verification question | `harness_round02_01_3`, `harness_round01_2` | Requested predicate, answer type, supporting evidence, rejected distractor | Relation drift is common in retrieval and lookup tasks | Multi-solver debate for simple retrieval | High | Low |
| Action, finalization | Correct evidence is submitted in non-canonical form | Raw-answer commit discipline | `harness_round01_6`, `harness_round02_01_6` | Answer type, decisive observation, allowed transformation, exact final string | Machine-graded tasks require exact terminal values | Over-normalization and redundant final checks | High | Low |
| Action, orchestration | Heavy collaboration would risk state conflicts | Single executor with rare non-acting checks | Winner pattern; negative control `harness5` | Keep one environment actor; checker only constrains high-risk next actions | Stateful environments need one owner of mutations | AgentOrchestra-style multiple acting roles | High | Low |
| Memory | Generic reminders do not force the right repair class | Failure-class, phase-aware procedural reminders | Winner memory; lightweight provider patterns | Marker-based routing for schema, repeat, slot, raw final, and stateful risks | Execution-signal reminders transfer without storing facts | Persistent task-fact memory and verbose workflow recall | Medium | Low |
| Builder/Wiring | Metadata and wiring must remain factory-compatible | Preserve compatibility while updating identity | None; repair within winner pattern | Keep `PlanningClass` injection, project root, tool binding, and metadata | Correct wiring is required for every generated candidate | Changing evaluator, dataset, or harness factory contracts | High | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve direct single-executor environment ownership in Action because successful trajectories show it is efficient and safe for simple serial tool chains.
- Preserve rare non-environment checking in Action because the checker should constrain risky decisions without becoming a second actor.
- Preserve compact planning in Planning because the winner already benefits from short target, remaining-work, and final-criteria descriptions.
- Preserve low-noise procedural memory in Memory because it avoids task facts, entity IDs, answers, and benchmark contamination.
- Preserve existing guard repairs in Action, including safe alias mapping and scalar-to-array coercion, because they are useful low-cost schema aids.
- Preserve Builder/Wiring compatibility, including local `PlanningClass` injection, `project_root` assignment, vector-memory connection, and tool-agent binding.

#### Borrow

- Borrow from `harness_round02_01_5` into Cross-Module Interface and Action: stateful commit rows and terminal readiness blockers, expected to reduce false `Task Completed` outputs and generalize to any mutable workflow.
- Borrow from `harness_round02_01_2` into Action: repair ledger fields for failure class, changed precondition, and repaired arguments, expected to reduce repeated failed calls across APIs.
- Borrow from `harness_round02_01_4` into Action: typed slot prerequisites before transformations, expected to reduce ToolHop wrong-slot answers across multi-hop chains.
- Borrow from `harness_round02_01_3` into Planning: relation-specific evidence targets and rejected distractor notes, expected to reduce SearchQA nearby-relation mistakes.
- Borrow from `harness_round01_6` and `harness_round02_01_6` into Action: raw final-answer binding, expected to recover path-correct but final-format-wrong cases.
- Borrow from `harness_round01_8` into the Planning -> Action interface: pending versus observed status packet discipline, expected to make all later checks observation-grounded.
- Borrow from `harness_round02_02_7` into Action: parseable verifier constraints, expected to keep `recovery_contract_check` from substituting for real evidence.
- Borrow from lightweight memory provider patterns into Memory: marker-based relevance filtering and short procedural reminders, expected to improve reminder precision without storing facts.

#### Avoid

- Avoid `harness5` heavy orchestration because multiple role-like agents and fusion memory create cost and handoff risk; the risk is complexity and stateful regression.
- Avoid always-on checker calls from any example because Stage 1 already shows repeated loops and checker-as-evidence risk; the risk is cost and weak transfer.
- Avoid benchmark-specific patches for medical permissions, dispute statuses, specific films, names, tag IDs, or date formats because they do not transfer; the risk is overfitting.
- Avoid storing task facts, IDs, answers, or golden values in Memory because the current procedural-only memory is a preservation target; the risk is stale or contaminating guidance.
- Avoid applying a full stateful commit ledger to read-only QA because it would slow simple SearchQA and ToolHop tasks; the risk is irrelevance and prompt bloat.
- Avoid broad multi-solver debate for SearchQA because Stage 1 attributes failures to relation verification and final commitment, not lack of independent workers; the risk is unnecessary complexity.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Compact Status Fusion Contract]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Stateful task checklist drift and premature completion; evidence-chain slot binding breaks
- **Current Weakness:** Planning produces useful prose, but Action does not have enforceable rows for obligations, observed facts, failures, blockers, or final readiness.
- **Desired Behavior:** The new harness should carry one compact status packet that separates pending intent from observed success, observed failure, unresolved blockers, evidence/slot bindings, stateful commits, and terminal criteria.
- **Borrowed Pattern:** `harness_round01_8` status packet plus `harness_round02_01_8` compact fusion concept.
- **Preserved Behavior:** Keep the winner's direct single executor and concise planning style.
- **Implementation Shape:** Planning emits a small structured contract with rows for `obligation`, `status`, `observed_value`, `failure_or_blocker`, and `final_condition`. Action updates rows only from tool observations and uses the packet before risky retry or finalization.
- **Generalization Rationale:** A compact observed-status contract supports stateful APIs, retrieval tasks, and multi-hop transformations without encoding domain facts.
- **Complexity:** Medium
- **Expected Impact:** Reduce partial EnvScaler completions, unsupported ToolHop transformations, and finals with unresolved evidence.
- **Regression Risk:** If the packet becomes verbose, easy tasks may become slower and more brittle.

**[Direction 2: Stateful Commit Gate for Mutable Workflows]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Stateful task checklist drift and premature completion
- **Current Weakness:** `complete_task` can be called after failed or unverified writes, and prose impossibility can replace the required stateful terminal action.
- **Desired Behavior:** For mutable tasks, Action should maintain required mutation rows, bind target IDs from observations, keep failed writes open, and allow `complete_task` only after all required rows are closed or evidence proves they are impossible.
- **Borrowed Pattern:** `harness_round01_5` commit discipline and `harness_round02_01_5` stateful commit ledger.
- **Preserved Behavior:** Preserve sequential state mutation by one executor.
- **Implementation Shape:** Add prompt-level and helper-level fields for `required_write`, `target_id`, `tool_call`, `success_observation`, `postcondition`, and `terminal_blocker`. Trigger a rare readiness check only before `complete_task` or after conflicting stateful observations.
- **Generalization Rationale:** Mutable workflows in any domain require confirmed side effects before terminal completion.
- **Complexity:** Medium
- **Expected Impact:** Improve EnvScaler full-score rate and reduce zero-score `Task Completed` outputs.
- **Regression Risk:** If too strict, the gate may leave tasks unfinished when no explicit read-after-write tool exists.

**[Direction 3: Hard Repair Registry and Schema Preflight]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Recovery loops repeat failed routes instead of changing state, tool, or hypothesis; tool schema and tool-existence control remains too soft
- **Current Weakness:** The guard gives advisories but still allows invented tools, repeated failed calls, missing required fields, invalid arguments, and stale retries.
- **Desired Behavior:** Action should validate tool existence and argument schemas before real execution, classify failed observations, and require a materially changed route after repeated failures.
- **Borrowed Pattern:** `harness_round01_3` failure taxonomy and `harness_round02_01_2` repair ledger.
- **Preserved Behavior:** Preserve the existing guard's low-cost alias and scalar repair behavior.
- **Implementation Shape:** Extend guarded tools with deterministic preflight where possible. Maintain a compact registry keyed by tool and arguments, with `failure_class`, `repeat_count`, `required_change`, and `changed_precondition`. Block identical failed retries unless an observation changes preconditions.
- **Generalization Rationale:** Tool-call correctness, failure classification, and retry discipline are general execution behaviors across tool sets.
- **Complexity:** Medium
- **Expected Impact:** Reduce unknown-tool failures, TypeError-style schema failures, repeated-failure advisories, and max-step loops.
- **Regression Risk:** Overly strict preflight could reject permissive or partially optional tool calls.

**[Direction 4: Observation-Grounded Evidence and Slot Binding]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Evidence-chain slot binding breaks under failed or ambiguous lookups; SearchQA evidence sufficiency is shallow
- **Current Weakness:** Action can transform source entities or finalize nearby-relation answers when the intended intermediate slot or predicate is unresolved.
- **Desired Behavior:** Planning should name required relations and typed slots, while Action should only mark slots observed after tool output and should block downstream transformations or final answers when prerequisite slots are unresolved.
- **Borrowed Pattern:** `harness_round02_01_4` slot-chain ledger and `harness_round02_01_3` evidence arbiter.
- **Preserved Behavior:** Preserve direct serial tool use for simple chains.
- **Implementation Shape:** Add rows for `slot_name`, `required_source`, `observed_binding`, `relation_supported`, `distractor_risk`, and `allowed_transformation`. Use an evidence/slot check only when a final answer or transformation depends on an unresolved or ambiguous row.
- **Generalization Rationale:** Multi-step lookup and retrieval tasks across domains require observed intermediate values and predicate support.
- **Complexity:** Medium
- **Expected Impact:** Improve ToolHop correctness and SearchQA exactness by reducing wrong-hop and distractor answers.
- **Regression Risk:** Too much slot bookkeeping may distract from straightforward one-hop answers.

**[Direction 5: Raw Terminal Answer Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Final-answer canonicalization is underdeveloped
- **Current Weakness:** The executor can submit prose, equivalent-but-wrong date formats, leading-zero binary strings, or numeric forms that do not match the expected raw answer.
- **Desired Behavior:** Before `final_answer`, Action should identify requested answer type, decisive observation, exact raw field, allowed transformation, and final string. It should reject explanatory clauses and unsupported reformatting.
- **Borrowed Pattern:** `harness_round01_6` canonical answer binding and `harness_round02_01_6` raw answer contract.
- **Preserved Behavior:** Preserve reliable terminal-tool usage in QA tasks.
- **Implementation Shape:** Add a lightweight terminal preflight in the action prompt or checker that normalizes only when requested, prefers observed spans, strips prose, and validates transformed outputs against the task's answer type.
- **Generalization Rationale:** Exact raw values are required by short-answer QA, ToolHop transformations, and structured API terminal contracts.
- **Complexity:** Low
- **Expected Impact:** Recover a meaningful subset of `subem=1.0` but exact-wrong SearchQA and ToolHop cases.
- **Regression Risk:** Over-normalization may remove valid disambiguating context.

**[Direction 6: Failure-Class Procedural Memory]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Low-value exploration after empty or failed observations; memory distraction or missing memory guidance
- **Current Weakness:** Memory is compact and relevant but too generic; it warns about stuck states without naming the exact failure class or required next behavior.
- **Desired Behavior:** Memory should remain procedural and non-factual, but emit at most one or two reminders keyed to current execution markers: schema preflight, repeated failed call, unresolved slot, stateful postcondition, verifier blocker, or raw final risk.
- **Borrowed Pattern:** Winner memory plus marker/relevance filtering from lightweight and dynamic-cheatsheet provider examples.
- **Preserved Behavior:** Preserve no storage of task facts, IDs, answers, or golden values.
- **Implementation Shape:** Route reminders by phase and context markers. BEGIN should describe the compact status contract. IN should emit failure-class guidance only when markers appear, such as `unknown tool`, `success: false`, `Repeated-failure advisory`, `placeholder`, `final_answer`, or `complete_task`.
- **Generalization Rationale:** Failure-class reminders use execution signals, so they transfer across unseen domains without memorizing tasks.
- **Complexity:** Low
- **Expected Impact:** Improve compliance with repair, slot, and terminal rules while keeping prompt overhead low.
- **Regression Risk:** Too many reminders can bloat the prompt or compete with fresh observations.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The Stage 3 candidate should be a compact, ledger-guided single executor. It should act directly and efficiently on simple tasks, but switch into explicit status tracking when it sees mutable operations, failed calls, unresolved evidence slots, contradictory observations, or risky final answers. The style should be conservative and observation-grounded: one actor owns the environment, non-environment checkers are rare and parseable, memory is procedural and low-noise, and final commitments are made only from observed evidence.

#### 6.2 Module-Level Blueprint

#### Planning Blueprint

Implement a compact status-fusion planning contract. It should include the task target, answer or state type, required obligations, mutable rows when relevant, evidence or slot rows when relevant, expected final form, and terminal criteria. Preserve the winner's concise initial plan and periodic summaries. Avoid domain-specific examples or large tables. The motivating evidence is EnvScaler incomplete terminalization, SearchQA relation drift, and ToolHop wrong-slot transformations. The design is task-general because obligations, slots, blockers, and final criteria are structural properties of tool-use tasks.

#### Action Blueprint

Keep a single executor as the only environment actor. Strengthen the guarded tool layer with allowed-tool/schema preflight, failure-class registry, changed-route requirements after repeated failure, and stateful commit gating before `complete_task`. Add an observation-grounded slot/evidence check before downstream transformations or final answers. Add a raw terminal answer gate before `final_answer`. Non-environment checkers should return parseable fields and should be used only for unresolved blockers, terminal readiness, contradictory observations, or risky final formatting. Preserve alias repair, scalar-to-array coercion, and direct execution on easy tasks. Avoid multi-agent orchestration, repeated checker loops, and stateful gates on read-only tasks. The design is motivated by 115 EnvScaler unknown-tool trajectories, 258 EnvScaler repeated-failure trajectories, and widespread partial stateful completion.

#### Memory Blueprint

Keep memory lightweight, procedural, and non-factual. BEGIN memory should introduce the status contract and the distinction between pending intent and observed facts. IN memory should route by context markers and emit only the highest-risk reminders: schema repair, repeated failed call, unresolved slot, stateful postcondition, verifier blocker, or raw final risk. Preserve the current no-task-facts storage policy. Avoid workflow memories that store benchmark entities, answers, or long traces. The design is motivated by Stage 1 evidence that memory warnings were relevant but too generic to redirect repeated failures.

#### Builder / Wiring Blueprint

Preserve local harness factory compatibility. Keep `PlanningClass` injection through `context.kwargs`, keep `project_root` assignment, preserve vector-memory wiring, and bind tool references back to the created agent when supported. Update harness metadata to the new round and improvement focus so later evaluation is traceable. Avoid changing benchmark loops, evaluator contracts, model backend, dataset, or external services.

#### Interface Blueprint

The Planning -> Action interface should be the compact status packet. Planning creates obligations and final criteria; Action updates rows only from observations; Memory reminds the executor not to treat planned rows as facts. Checker output should become an Action constraint, not evidence. Final-answer criteria should be shared through fields such as `final_ready`, `terminal_blocker`, `raw_answer_type`, and `required_observation`. This interface is necessary because Stage 1 showed that natural-language summaries alone did not prevent unresolved completion or wrong-slot finalization.

#### 6.3 Minimal Required Changes

- Add a compact status packet that separates pending obligations, observed successes, observed failures, blockers, evidence/slot bindings, and final criteria.
- Add action-side schema and allowed-tool preflight before real tool execution where tool schemas expose enough information.
- Add a failed-call registry that blocks identical failed retries unless a precondition changes.
- Add stateful commit gating before `complete_task` for mutable workflows.
- Add slot/evidence binding rules before transformations and final answers.
- Add raw terminal answer canonicalization before `final_answer`.
- Add failure-class memory routing while preserving procedural-only memory.
- Preserve single-executor environment ownership.

#### 6.4 Optional Enhancements

- Add a rare parseable checker for contradictory tool observations, such as allowed-value metadata disagreeing with mutation errors.
- Add a lightweight mutability detector from tool names and descriptions to decide when stateful commit rows are needed.
- Add a checker-call throttle that blocks semantically repeated checker drafts, not only exact repeated text.
- Add a short final-readiness summary every few steps only when unresolved blockers exist.
- Add a compact observation compressor for long trajectories if token cost rises.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Emit a compact status-fusion contract with obligations, observed rows, blockers, evidence or slot rows, and final criteria.
- [Planning] Include relation-specific verification targets for retrieval tasks and typed prerequisite slots for multi-hop transformations.
- [Planning] Keep plans concise and domain-agnostic; do not include benchmark item IDs, gold answers, or task-specific fallbacks.
- [Action] Preserve one acting executor as the only component that mutates the environment.
- [Action] Add allowed-tool and schema preflight before real tool execution when schemas are available.
- [Action] Maintain a failed-call registry and block identical failed retries until a changed precondition, changed argument, or changed tool is observed.
- [Action] Add stateful commit rows and block `complete_task` while required mutable rows remain unresolved.
- [Action] Do not treat checker output as environment evidence; checker output may only constrain the next action or final readiness.
- [Action] Block downstream transformations when prerequisite slots are unresolved or based only on task wording.
- [Action] Add a raw final-answer gate that submits only the requested value unless the task explicitly asks for a formatted list or explanation.
- [Memory] Keep memory procedural, phase-aware, and low-noise.
- [Memory] Route reminders by failure class rather than storing task facts, IDs, answers, or traces.
- [Builder] Preserve harness-factory wiring, `PlanningClass` injection, project root assignment, vector-memory wiring, and agent-tool binding.
- [Builder] Update harness metadata to reflect the new round and the compact status/commit/repair improvement focus.
- [Interface] Planning creates obligations; Action closes them only from observations; Memory reinforces this distinction.
- [Interface] Share terminal criteria through explicit fields such as `final_ready`, `terminal_blocker`, `raw_answer_type`, and `required_observation`.
- [Preserve] Keep the winner's efficient direct execution on simple SearchQA and ToolHop cases.
- [Preserve] Keep existing useful guard repairs such as alias mapping and scalar-to-array coercion.
- [Avoid] Do not add heavy multi-agent orchestration, debate for mutable tasks, or multiple acting workers.
- [Avoid] Do not solve EnvScaler by calling `complete_task` earlier; require observed completion instead.
- [Avoid] Do not add benchmark-specific patches for statuses, people, medical permissions, folders, films, or expected answers.
- [Avoid] Do not make checkers always-on or allow checker loops to replace real tool progress.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
