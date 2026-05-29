### PART 1: LOCALIZATION SUMMARY

The current winner under analysis is `harness_round02_01_2` evaluated as `qwen3-8B-round_02_01-harness2` in round 03.01. It is a direct single-executor ReAct harness with a repair-ledger planner, one non-environmental `repair_triage_check` helper, and lightweight phase-aware memory reminders. Stage 1 found that the provider wiring is functional, but the round metadata still says round 02.01. This mismatch should be cleaned up only if Stage 3 touches metadata; it is not the main cause of failure.

The dominant failures are transferable control failures, not dataset-specific misses. EnvScaler is the highest-leverage target: only 21/658 stateful tasks reach full score, while 429 runs call `complete_task` after partial completion and 208 never complete. The primary Stage 1 diagnosis is that Action lacks a terminal-readiness gate and treats `complete_task` as an ordinary tool call. The second major Action failure is low-value repair looping after schema, permission, unavailable-tool, or missing-data errors. ToolHop failures come from Planning and Action failing to verify intermediate slots before downstream transformations. SearchQA failures come from Action selecting distractor spans from search results without predicate and answer-type arbitration. A smaller but still important failure is final-answer canonicalization: 31 incorrect QA cases have `subem=1.0`, showing that the harness often reaches a related value but submits a non-canonical answer.

The improvement brief should preserve the winner's strengths: one acting executor, closed-set schema discipline, direct tool-chain execution on simple tasks, compact phase-aware memory, and the useful repair-ledger idea. The highest-leverage repairs are a machine-readable Planning -> Action ledger, an Action-side terminal gate for mutable workflows, bounded failure arbitration, typed slot/evidence verification for multi-hop tasks, and a narrow final-answer canonicalization preflight. Peer harness examples should be used as targeted module references, not as whole-harness templates.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round01_5`

- **Observed Structure:** Direct single executor with `COMMIT_LEDGER` planning, sequential mutable commits, read-after-write reminders, and optional terminal preflight.
- **Relevant Strength:** It is the strongest evaluated reference for stateful commit discipline and has the best fair-first200 SearchQA score among round01 candidates. It scored 0.5036 EnvScaler and 0.7455 EnvScaler done on the fair slice.
- **Relevant Weakness / Risk:** It remains expensive and still has non-trivial max-step rate. Its ToolHop correctness is only moderate.
- **Related Winner Failure:** Premature `complete_task` after partial EnvScaler completion.
- **Transferable Module Pattern:** Borrow the sequential observed-commit row discipline: each required mutation remains open until a success observation closes it, and terminal completion requires all rows to be closed.
- **Generalization Rationale:** The commit-row pattern applies to any mutable workflow with multiple required writes, independent of the concrete environment schema.
- **Do Not Borrow:** Do not copy any broad SearchQA-specific behavior or add heavy routine preflight calls to every step.
- **Transfer Confidence:** High

#### Example: `harness_round01_6`

- **Observed Structure:** Direct single executor with target-type planning, final observation binding, cautious canonicalization, and phase-aware canonical memory.
- **Relevant Strength:** It is the best evaluated round01 generalist, with 0.4983 fair-first200 mixed score, 0.5105 EnvScaler score, 0.8 EnvScaler done, and the lowest fair-slice max-step rate among top round01 candidates.
- **Relevant Weakness / Risk:** SearchQA trails `harness_round01_5`, and ToolHop is solid but not benchmark-leading.
- **Related Winner Failure:** Final-answer canonicalization failure and raw-answer contract violations.
- **Transferable Module Pattern:** Borrow answer-type detection plus observation-bound finalization: final answers should be copied or transformed only from decisive observations, with normalization limited to the requested answer type.
- **Generalization Rationale:** Raw-answer binding transfers across short answers, dates, numbers, IDs, binary strings, lists, and transformed values.
- **Do Not Borrow:** Do not over-normalize values or rewrite observed raw fields when the task asks for exact copying.
- **Transfer Confidence:** High

#### Example: `harness_round01_8`

- **Observed Structure:** Direct single executor with a compact `STATUS_PACKET` that separates planned/pending items, observed successes, observed failures, remaining work, next step, and final criteria.
- **Relevant Strength:** It is the best evaluated round01 ToolHop specialist, with 0.5263 ToolHop correctness and 0.5526 ToolHop path score on fair-first200, and strong full-run mixed score.
- **Relevant Weakness / Risk:** It is expensive, has the highest max-step rate among selected top4 round01 candidates, and is weaker on EnvScaler and SearchQA outside ToolHop.
- **Related Winner Failure:** Planning-output contract drift and unverified intermediate ToolHop slots.
- **Transferable Module Pattern:** Borrow the compact status packet as the Planning -> Action handoff format, especially its separation of pending intent from observed facts.
- **Generalization Rationale:** A compact status packet can support stateful tasks, retrieval tasks, and multi-hop transformations without encoding benchmark-specific labels.
- **Do Not Borrow:** Do not make the status checker frequent or verbose; the winner already suffers when advisory checks become loops.
- **Transfer Confidence:** High

#### Example: `harness_round02_01_3`

- **Observed Structure:** Generated direct executor with an `EVIDENCE_ARBITER` contract for target, predicate, title, answer type, candidate evidence, rejected distractors, and final criteria.
- **Relevant Strength:** It directly targets SearchQA candidate confusion and near-match answer errors while keeping debate and parallel actors out of stateful tasks.
- **Relevant Weakness / Risk:** It has no recorded evaluation metrics, so transfer confidence depends on design fit rather than measured quality.
- **Related Winner Failure:** SearchQA distractor selection and final-answer extraction failure.
- **Transferable Module Pattern:** Borrow predicate and answer-type arbitration before `final_answer` only when retrieval evidence contains multiple candidate entities or near matches.
- **Generalization Rationale:** Any retrieval task can produce distractors; predicate-aware candidate checks are domain-agnostic.
- **Do Not Borrow:** Do not run an arbitration checker on every final answer or on stateful tasks where the problem is mutation completion.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_01_4`

- **Observed Structure:** Generated direct executor with a `SLOT_CHAIN_LEDGER` for typed slots, prerequisites, observed bindings, unresolved slots, and final criteria.
- **Relevant Strength:** It directly targets ToolHop prerequisite and transformation failures by separating raw observed values from derived values.
- **Relevant Weakness / Risk:** It has no recorded metrics and may overfit read-only multi-hop tasks if applied globally.
- **Related Winner Failure:** Multi-hop evidence-chain break and unverified intermediate slots.
- **Transferable Module Pattern:** Borrow typed slot closure: a downstream transformation may consume a slot only after an observation satisfies the slot's relation, entity identity, and expected value type.
- **Generalization Rationale:** Slot closure transfers to genealogy, dates, publications, locations, arithmetic, string transforms, and any multi-hop chain.
- **Do Not Borrow:** Do not create a large table for trivial one-hop tasks; keep slot tracking compact and task-shape-triggered.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_7`

- **Observed Structure:** Generated direct executor with `VERIFIER_CONTRACT` planning and a rare non-environmental checker that returns concrete next-action constraints.
- **Relevant Strength:** It addresses a failure in the current winner: verifier/checker output should constrain the next action rather than remain vague advisory text.
- **Relevant Weakness / Risk:** It has no metrics, and verifier calls can still increase token cost or become loops.
- **Related Winner Failure:** Low-value repair loops after tool failures and overuse of `repair_triage_check`.
- **Transferable Module Pattern:** Borrow checker throttling and constraint-shaped verifier output: each check should produce a small next-action constraint, not broad advice.
- **Generalization Rationale:** Tool-rich environments repeatedly expose schema and precondition failures; enforcing concrete repair constraints is independent of domain.
- **Do Not Borrow:** Do not add a second acting agent or let the verifier propose unavailable tools.
- **Transfer Confidence:** Medium

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style multi-agent harness with broader coordination and Cerebra fusion memory.
- **Relevant Strength:** It can improve coverage in principle and has moderate EnvScaler score despite high complexity.
- **Relevant Weakness / Risk:** It is the highest-cost active seed, with the highest max-step rate, 292k average tokens on fair-first100, and notes that orchestration is too heavy for Qwen3-8B.
- **Related Winner Failure:** It is mainly a negative control for agent collaboration and orchestration.
- **Transferable Module Pattern:** Borrow only the negative lesson: when the current failure is terminal gating and verifier discipline, use one executor plus rare non-acting checks rather than broad multi-agent orchestration.
- **Generalization Rationale:** The same state ownership problem appears in any mutable environment; multiple acting agents would increase handoff risk and cost.
- **Do Not Borrow:** Do not copy the multi-agent coordinator, broad role decomposition, or frequent fusion memory exposure.
- **Transfer Confidence:** High as a negative control

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Action | Partial EnvScaler completion followed by `complete_task` | Missing terminal-readiness gate for mutable workflows | `harness_round01_5`; `harness_round02_01_5` concept | Sequential observed commit rows plus rare terminal readiness check | Multi-operation state tasks require observed row closure before terminal completion | Frequent preflight on every step; stateful bookkeeping on trivial read-only tasks | High | Medium |
| Cross-Module Interface | Plan text does not become durable executable state | Missing machine-readable Planning -> Action contract | `harness_round01_8`; `harness_round02_02_1` concept | Compact status packet with obligations, observed bindings, blockers, and final criteria | The same contract can guide stateful, retrieval, and multi-hop tasks | Verbose status packets and frequent checker calls | High | Medium |
| Action | Repeated failed calls, invented unavailable tools, vague repair advice | Missing bounded failure arbitration | `harness_round02_02_7`; `harness_round02_02_2` concept | Checker output must be concrete next-action constraints with throttled checker reuse | Schema and precondition failures are common across tool environments | Heavy repair registry, second acting verifier, or verifier-suggested unavailable tools | Medium | Medium |
| Planning | ToolHop computes from wrong or unverified intermediate entity | Missing typed slot closure before downstream transformation | `harness_round01_8`; `harness_round02_01_4` concept | Slot-chain ledger with prerequisite, observed binding, unresolved status, and final criterion | Multi-hop tasks across domains require verified intermediate variables | Large slot tables for one-hop tasks | Medium | Medium |
| Action | SearchQA chooses distractor entity from search evidence | Missing predicate and answer-type arbitration | `harness_round01_5`; `harness_round02_01_3` concept | Candidate answer must match target predicate, entity role, and answer type before `final_answer` | Retrieval snippets often contain distractors in any domain | Routine debate or arbitration on every answer | Medium | Low |
| Action | Correct or related value found but submitted in wrong canonical form | Missing final-answer canonicalization preflight | `harness_round01_6`; `harness_round02_02_5` concept | Observation-bound raw-answer contract with limited type-aware normalization | Exact-answer grading applies to dates, numbers, IDs, binary, names, and short values | Over-normalization that removes meaningful formatting | High | Low |
| Memory | Memory reminders are advisory, sometimes broad, and not relevance-gated enough | Missing compact risk-aware memory cues | `harness_round01_6`; `dynamic_cheatsheet_provider_lite` reference | Sparse phase-aware cues selected by current risk and lexical relevance | Procedural memory should nudge without replacing live observations | Storing task facts, IDs, answers, or verbose global cheatsheets | Medium | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve the single acting executor in Action because it maintains state ownership for mutable tasks and avoids multi-agent handoff errors.
- Preserve closed-set schema discipline in Action because the winner succeeds on many simple QA and ToolHop tasks when it copies valid tool names and arguments.
- Preserve compact repair-ledger intent in Planning because the failure is missing enforcement, not the concept of tracking failures and preconditions.
- Preserve direct tool-chain execution for simple read-only tasks because successful trajectories show that one executor can solve linear evidence chains without extra roles.
- Preserve lightweight phase-aware memory in Memory because broad memory or rich trajectory storage is not needed for the dominant failures and may add distraction.
- Preserve builder compatibility and provider wiring because Stage 1 found no evidence that the current failures come from disconnected modules.

#### Borrow

- Borrow from `harness_round01_5` into Action: sequential observed commit rows and terminal preflight for mutable tasks; expected benefit is fewer partial EnvScaler completions; it generalizes to any multi-write workflow.
- Borrow from `harness_round01_8` into Cross-Module Interface: compact status packet separating pending intent from observed facts; expected benefit is stronger Planning -> Action handoff; it generalizes across stateful and read-only tasks.
- Borrow from `harness_round01_6` into Action: cautious final observation binding and answer-type canonicalization; expected benefit is fewer raw-answer exactness losses; it generalizes to all short-answer formats.
- Borrow from `harness_round02_01_4` into Planning: typed slot closure before downstream transformation; expected benefit is fewer ToolHop wrong-chain answers; it generalizes to any multi-hop variable chain.
- Borrow from `harness_round02_01_3` into Action: predicate and answer-type arbitration for ambiguous retrieval evidence; expected benefit is fewer SearchQA distractor answers; it generalizes to any search or retrieval QA setting.
- Borrow from `harness_round02_02_7` into Action: rare verifier calls that return concrete next-action constraints; expected benefit is fewer checker loops and repeated invalid calls; it generalizes to schema-rich tool environments.
- Borrow from lightweight memory references into Memory: risk-triggered, compact, phase-aware reminders with relevance filtering; expected benefit is lower prompt noise; it generalizes because memory remains procedural rather than factual.

#### Avoid

- Avoid copying `harness5` heavy multi-agent orchestration; the risk is complexity and cost, and it should not enter Stage 3 because the Stage 1 failures need stronger gates, not more acting roles.
- Avoid copying `harness3` or `harness6` early-stop guard style wholesale; the risk is regression, because their low cost comes with weak EnvScaler score or missing SearchQA search use.
- Avoid turning `repair_triage_check` into a frequently used second reasoning loop; the risk is repeated checker loops and token overhead, not reliable repair.
- Avoid broad memory systems that store task facts or answer candidates; the risk is stale or contaminating guidance, while Stage 1 needs procedural risk cues only.
- Avoid benchmark-specific patches for observed entities, IDs, folder names, historical figures, or specific answer strings; the risk is weak transfer and overfitting.
- Avoid final-answer normalization that strips meaningful formatting by default; the risk is exact-match regression when leading zeros, capitalization, or separators are semantically requested.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Stateful Commit Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Premature terminal completion on partially completed state-change tasks
- **Current Weakness:** `complete_task` is available as an ordinary terminal tool even when required mutation rows are failed, omitted, or unverified.
- **Desired Behavior:** For mutable or EnvScaler-like tasks, maintain compact commit rows and block `complete_task` unless every required row has a successful observation or a valid evidence-backed blocker that the task permits.
- **Borrowed Pattern:** `harness_round01_5` commit ledger and `harness_round02_01_5` stateful commit concept.
- **Preserved Behavior:** Keep the winner's single executor and direct sequential tool use.
- **Implementation Shape:** Add an action-side terminal preflight prompt/checklist that reads the current status packet before terminal calls; it should identify open rows, failed rows, and missing read-after-write support. It should be rare and terminal-risk-triggered.
- **Generalization Rationale:** Any multi-operation workflow can be represented as obligation rows closed by observations; the pattern is independent of domain-specific schemas.
- **Complexity:** Medium
- **Expected Impact:** Directly targets the 429 partial EnvScaler completions and should raise EnvScaler score more than done rate.
- **Regression Risk:** Overblocking terminal calls on simple tasks or treating genuine impossible states as endless work.

**[Direction 2: Structured Planning-to-Action Status Packet]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Planning-output contract drift and weak Planning -> Action handoff
- **Current Weakness:** Planning output can become a first-action JSON object or prose ledger that Action cannot enforce.
- **Desired Behavior:** Planning should produce a compact, parseable status packet with task type, obligations, observed successes, observed failures, blockers, remaining work, typed slots when needed, and final criteria. Action should reference this packet in every high-risk step.
- **Borrowed Pattern:** `harness_round01_8` status packet and `harness_round02_02_1` ledger commit concept.
- **Preserved Behavior:** Keep planning compact; do not add a full planner-worker architecture.
- **Implementation Shape:** Strengthen planning prompts and summaries so malformed plans are converted into a minimal status packet. The action prompt should explicitly carry forward the packet and update it only from observations.
- **Generalization Rationale:** A shared status packet supports stateful commits, SearchQA evidence binding, and ToolHop slot closure without benchmark-specific code.
- **Complexity:** Medium
- **Expected Impact:** Should reduce missed subtasks, premature terminals, and wrong downstream transformations.
- **Regression Risk:** Status text could become verbose and increase cost if every simple task receives a large ledger.

**[Direction 3: Bounded Repair Registry]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Low-value repair loops after tool failures, schema mismatches, or unavailable actions
- **Current Weakness:** `repair_triage_check` is advisory and can lead to repeated invalid calls or unavailable-tool attempts.
- **Desired Behavior:** After a failed tool call, record failure class, tool name, arguments, and whether the next attempt changes tool, arguments, or observed precondition. Repeating the same failed call should be disallowed unless a later observation changes the relevant state.
- **Borrowed Pattern:** `harness_round02_02_7` verifier contract and `harness_round02_02_2` repair registry concept.
- **Preserved Behavior:** Keep repair inside the single-executor flow; do not add another acting agent.
- **Implementation Shape:** Replace vague triage advice with a compact repair registry and a checker that returns one of: valid schema repair, alternate available tool, wait for observed precondition, non-terminal blocker, or stop-and-answer only for read-only QA when evidence supports it.
- **Generalization Rationale:** Tool schema and precondition errors recur across all tool environments; a small repair registry is domain-agnostic.
- **Complexity:** Medium
- **Expected Impact:** Should reduce repeated-call loops, max-step failures, and no-final QA endings.
- **Regression Risk:** Too strict a registry may prevent necessary retry after transient or hidden state changes.

**[Direction 4: Typed Slot and Evidence Verification]**
- **Target Module:** Planning
- **Stage 1 Failure Addressed:** Multi-hop evidence-chain break and SearchQA distractor selection
- **Current Weakness:** Intermediate values are consumed before the harness verifies that they satisfy the requested relation, predicate, entity role, or answer type.
- **Desired Behavior:** For multi-hop or retrieval tasks, each intermediate slot should have a required relation, expected value type, observation source, and closure condition. Final candidates should be rejected if they are subject-name distractors, near matches, or unsupported transformations.
- **Borrowed Pattern:** `harness_round02_01_4` typed slot chain and `harness_round02_01_3` evidence arbitration.
- **Preserved Behavior:** Keep simple one-hop tasks lightweight and avoid debate for read-only tasks unless evidence is genuinely ambiguous.
- **Implementation Shape:** Add slot rows only when the task has dependent hops or transformations. Add a final candidate check for predicate and answer type when search evidence contains multiple candidate entities.
- **Generalization Rationale:** Relation and predicate verification are general requirements for entity chains, search QA, date arithmetic, string transforms, and publication or geography lookup.
- **Complexity:** Medium
- **Expected Impact:** Should improve ToolHop correctness and reduce SearchQA wrong-entity answers.
- **Regression Risk:** Extra slot checks could slow easy tasks or cause overcautious refusal when evidence is actually sufficient.

**[Direction 5: Raw Final-Answer Commit Preflight]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Final-answer canonicalization and raw-answer contract violations
- **Current Weakness:** The final answer can include prose, a padded or transformed value, or a related value not requested by the task.
- **Desired Behavior:** Before `final_answer`, classify the requested answer type and commit only the raw supported value or explicitly requested transformation. The answer field should contain no explanation.
- **Borrowed Pattern:** `harness_round01_6` canonical target behavior and `harness_round02_02_5` raw answer concept.
- **Preserved Behavior:** Preserve direct finalization when the decisive observation is obvious.
- **Implementation Shape:** Add a short final-answer checklist: requested type, decisive observation, raw field, allowed transformation, exact output string. Use it only at finalization.
- **Generalization Rationale:** Exact raw-value submission is required across short-answer task families and does not depend on any specific benchmark entity.
- **Complexity:** Low
- **Expected Impact:** Should recover some `subem=1.0` but exact-wrong cases and reduce formatting errors.
- **Regression Risk:** Over-normalization may remove meaningful leading zeros or task-required formatting.

**[Direction 6: Sparse Risk-Aware Memory Cues]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Memory distraction or weak memory guidance as a secondary contributor to repair loops
- **Current Weakness:** Memory provides broad procedural reminders but cannot distinguish terminal-risk, slot-risk, schema-risk, and raw-answer-risk with enough precision.
- **Desired Behavior:** Keep memory procedural and compact, but route reminders by current risk: terminal gate risk, repeated failed-call risk, unresolved slot risk, distractor risk, or raw-answer risk.
- **Borrowed Pattern:** `harness_round01_6` phase-aware canonical memory; lightweight memory provider references for BEGIN/IN throttling and relevance filtering.
- **Preserved Behavior:** Do not store task facts, IDs, answers, or current trajectory state as long-term memory.
- **Implementation Shape:** Use short, mutually exclusive reminders at BEGIN and sparse IN intervals. Prefer one high-risk cue over multiple generic reminders.
- **Generalization Rationale:** Risk-aware memory nudges transfer across environments while leaving live observations authoritative.
- **Complexity:** Low
- **Expected Impact:** Should reduce prompt noise and help the action loop apply the right checklist at the right phase.
- **Regression Risk:** If too sparse, memory may no longer remind the model about repeated-failure or raw-answer risks when needed.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The next harness should be a planning-guided single executor with compact verification gates. It should feel like the current repair-ledger winner, but with the ledger made executable: one actor owns all environment actions, a small status packet carries obligations and evidence, and rare non-environmental checks are used only at terminal, repair, slot, or final-answer risk points. The design should be direct on easy tasks and verification-aware on high-risk tasks.

#### 6.2 Module-Level Blueprint

**Planning Blueprint**

Implement a compact status packet rather than free-form repair notes. The packet should include task type, obligations, observed successes, observed failures, blockers, remaining work, final criteria, and typed slots only when the task has dependent hops or transformations. Preserve the winner's short planning style and repair-ledger concepts. Avoid long plans, benchmark-specific rows, or planned calls treated as facts. Stage 1 evidence from items 460 and 212 motivates this: incomplete first-step plans left Action without a durable list of required mutations. The design is task-general because all tasks can be summarized as obligations and final criteria, while slot rows activate only when needed.

**Action Blueprint**

Keep one acting executor. Add three action-side commit controls: a stateful terminal gate before `complete_task`, a bounded repair registry after failed tool calls, and a final-answer commit preflight before `final_answer`. For SearchQA and ToolHop, add lightweight evidence/slot verification only when candidate ambiguity or dependent transformation exists. Preserve direct valid tool execution and closed-set schema copying. Avoid heavy multi-agent orchestration, frequent checker loops, and verifier output that suggests unavailable tools. Stage 1 evidence from EnvScaler partial completions, repeated failures, item 752, and item 1171 motivates these controls. The design is task-general because it governs when to commit, retry, transform, or finalize rather than what domain answer to choose.

**Memory Blueprint**

Keep memory lightweight, procedural, and phase-aware. Add risk routing so at most one or two reminders are injected for the current risk class: terminal readiness, repeated failure, schema repair, unresolved slot, distractor candidate, or raw-answer finalization. Preserve the current rule that no task facts, IDs, or answers are stored. Avoid broad global cheatsheets, stale factual memories, and multiple simultaneous generic reminders. Stage 1 evidence shows memory was not the primary failure owner, so memory should support the new action/planning contracts rather than replace them. The design is task-general because it nudges reusable behaviors while leaving live observations authoritative.

**Builder / Wiring Blueprint**

Preserve local provider wiring, project root assignment, task-tool binding, vector memory binding, and compatibility with the harness factory. Update metadata names and round labels only if the generated harness identity changes. Avoid changing benchmark loops, evaluator code, or external services. Stage 1 found no functional wiring failure, so Builder changes should remain minimal.

**Interface Blueprint**

Introduce a simple Planning -> Action status packet contract. Action should update the packet mentally or through summaries using only observations. The status packet should be visible before terminal calls and final answers. Memory -> Action should provide risk-specific cues that reference the same contract vocabulary: obligations, blockers, slots, decisive observation, raw answer. Avoid a complex shared-state architecture; a compact textual packet and checklist are enough. This directly addresses the Stage 1 cross-module failure where useful planning intent did not become enforceable terminal criteria.

#### 6.3 Minimal Required Changes

- Add a compact status packet in Planning with obligations, observations, blockers, remaining work, and final criteria.
- Add an Action-side `complete_task` gate for mutable/stateful tasks that blocks completion while any required row is open or failed.
- Add a bounded repair registry that prevents blind repetition of failed tool calls and forbids unavailable-tool repair suggestions.
- Add typed slot closure for dependent multi-hop tasks before downstream transformations.
- Add predicate and answer-type verification before finalizing ambiguous retrieval answers.
- Add a raw-answer finalization preflight that submits only the requested answer string.
- Keep memory lightweight but route reminders by current risk class.
- Preserve single-executor environment ownership.

#### 6.4 Optional Enhancements

- Add a rare non-environmental status checker that returns concrete next-action constraints only when terminal, repair, or final-answer risk is detected.
- Add read-after-write verification rows for stateful tasks when the environment exposes safe read tools.
- Add a low-cost mutability classifier from tool schemas to decide when stateful gates are required.
- Add checker-call throttling so the same checker cannot be called repeatedly without an intervening real tool observation.
- Add a concise answer-candidate rejection note for SearchQA when a distractor appears in evidence but does not match the predicate.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Produce a compact status packet with obligations, observed successes, observed failures, blockers, remaining work, and final criteria.
- [Planning] Add typed slots only for dependent multi-hop or transformation tasks; keep one-hop tasks lightweight.
- [Planning] Never mark a planned action, expected entity, or guessed answer as observed evidence.
- [Action] Keep exactly one environment-acting executor; any checker must be non-environmental and advisory or constraint-producing only.
- [Action] Before `complete_task`, require every mutable obligation row to be closed by successful observation or a valid task-permitted blocker.
- [Action] After a failed tool call, record the failed tool and arguments and require the next real move to change tool, change valid arguments, or cite an observed precondition change.
- [Action] Do not let a repair checker recommend or justify unavailable tool names or unsupported argument keys.
- [Action] Before downstream transformations, verify that the consumed slot matches the requested relation, entity, and value type.
- [Action] Before `final_answer`, verify predicate match, answer type, decisive observation, and raw output string.
- [Memory] Keep reminders procedural, compact, phase-aware, and risk-routed; do not store task facts, IDs, answers, or benchmark-specific lessons.
- [Builder] Preserve harness factory compatibility and local provider wiring; metadata cleanup is allowed but not a behavioral substitute.
- [Interface] Make the Planning -> Action status packet visible at terminal-risk and final-answer-risk moments.
- [Preserve] Preserve direct ReAct execution for simple tasks with decisive observations.
- [Preserve] Preserve closed-set schema copying and one-tool default behavior for mutable actions.
- [Avoid] Do not introduce heavy multi-agent orchestration, parallel mutable actors, broad debate, or full peer-harness copying.
- [Avoid] Do not hard-code benchmark item IDs, entity names, folder names, answer strings, or observed trajectory-specific routes.
- [Avoid] Do not over-normalize raw answers when exact formatting may be meaningful.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
