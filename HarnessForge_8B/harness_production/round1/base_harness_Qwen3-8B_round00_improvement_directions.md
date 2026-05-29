### PART 1: LOCALIZATION SUMMARY

The current winner under analysis is `base_harness` with local `Qwen3-8B`. Its architecture is a minimal `generic_planning + single_react + lightweight_memory` harness: one short planning call, one single ReAct executor, and compact memory guidance. Stage 1 attributes the dominant failures to missing structure around execution rather than to benchmark or model replacement issues. EnvScaler failures are dominated by incomplete state mutation, plan-as-fact contamination, unsafe completion, repeated failed calls, and unsafe multi-call execution. SearchQA and ToolHop failures are dominated by under-decomposed evidence chains, unsupported final answers, weak observation arbitration, and final-answer canonicalization errors.

The highest-leverage capability gaps are: an observation-grounded state ledger, a typed Planning-to-Action contract, action-side schema/error repair, evidence-chain planning for QA and ToolHop, final observation arbitration, answer-type canonicalization, and sequential commit discipline for mutable tools. The next harness should preserve the base harness's useful behaviors: simple single-executor continuity, strict JSON tool-call contract, concise planning, compact memory, benchmark-tool compatibility, and low coordination overhead on easy tasks.

**Round01 correction note:** Subsequent harness generation must expose the closed-set available tool names and input schemas to both Planning and Action before they choose or mention tools. Action prompts must use the runtime Jinja variables `{{tool_functions_json}}` and `{{task}}`; single-brace placeholders such as `{tool_functions_json}` leave schemas invisible and cause invented tools. Schema/retry controls, status ledgers, and checker/preflight tools should be soft repair aids, not hard execution locks or mandatory gates: do not permanently quarantine a failed tool signature, do not force auth/search/check probes that are not in the schema, and allow the same real tool call after an intervening successful observation changes state or preconditions. Repeated identical failures should append a soft advisory that pushes the model to switch tools, arguments, or strategy. For short-answer QA/ToolHop, final answers should copy decisive structured tool fields exactly rather than paraphrasing dates, numbers, names, or calculated outputs.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness1`

- **Observed Structure:** Direct single-executor ReAct with `flash_searcher` planning and ExpeL-style soft memory.
- **Relevant Strength:** The pool identifies it as a strong quality reference with the best non-trivial all-available mixed primary score and the best EnvScaler score. Its direct serial loop is well matched to dependency-heavy work.
- **Relevant Weakness / Risk:** It is expensive, with high token cost and long contexts in failures. It can keep exploring when a repair or stop decision is needed.
- **Related Winner Failure:** Helps with under-decomposed evidence chains and preserves single-agent continuity for ToolHop and stateful tasks.
- **Transferable Module Pattern:** Borrow compact serial planning plus direct execution continuity, not the high-cost context accumulation.
- **Generalization Rationale:** Many unseen tasks require carrying exact upstream entities through downstream tool calls; a direct executor avoids handoff loss.
- **Do Not Borrow:** Do not borrow unbounded persistence, long-context accumulation, or weak stop rules.
- **Transfer Confidence:** High

#### Example: `harness2`

- **Observed Structure:** Concise reflection harness with a short plan, one executor, periodic reflection, and a final verifier idea.
- **Relevant Strength:** The concept of concise reflection directly maps to Stage 1's need for bounded repair and final readiness checks. The pool notes strong SearchQA subEM in the small sample and reliable search use.
- **Relevant Weakness / Risk:** The pool reports weak mixed quality, high max-step rate, weak ToolHop correctness, and repeated failed calls.
- **Related Winner Failure:** Helps with premature finalization, repeated-call failures, and missing final verification if adapted carefully.
- **Transferable Module Pattern:** Borrow the lightweight reflection/checkpoint shape, but make it action-grounded and repeat-aware.
- **Generalization Rationale:** Compact checkpoints can improve stop/repair decisions across API, search, and transformation tasks without introducing a heavy team.
- **Do Not Borrow:** Do not borrow its current weak repeated-call behavior or any verifier that only restates the transcript without enforcing evidence.
- **Transfer Confidence:** Medium

#### Example: `harness3`

- **Observed Structure:** Guarded JoyAgent-style augmented ReAct with whitelist checks, repeated-call detection, early-stop guards, and compact MEMP memory.
- **Relevant Strength:** The pool shows very low token footprint, low max-step rate, and explicit guard discipline. This directly addresses Stage 1's repeated-call and unknown-tool failures.
- **Relevant Weakness / Risk:** SearchQA route is broken in the pool, and EnvScaler completion does not translate into high score. Guarding can become under-acting.
- **Related Winner Failure:** Helps with weak schema-aware repair, repeated-call loops, empty action steps, and cost control.
- **Transferable Module Pattern:** Borrow tool whitelist checks, schema-visible repair hints, consecutive-repeat detection, and compact failure summaries as action-level controls; avoid permanent failed-call blocking.
- **Generalization Rationale:** Tool-name validity, duplicate failed calls, and empty action outputs are task-general execution risks.
- **Do Not Borrow:** Do not borrow early completion behavior or any policy that suppresses necessary search/retrieval.
- **Transfer Confidence:** High for guards, Low for overall architecture

#### Example: `harness4`

- **Observed Structure:** Light reflection harness with short planning, one executor, a non-acting critic, and workflow memory.
- **Relevant Strength:** The pool calls it the best speed-quality balance, with reliable SearchQA tool use and a lighter critic than heavy multi-agent designs.
- **Relevant Weakness / Risk:** EnvScaler still trails stronger direct execution, and max-step failures remain on stateful tasks.
- **Related Winner Failure:** Helps with final readiness checks, tool existence checks, argument plausibility, repeated-failure detection, and stop/repair decisions.
- **Transferable Module Pattern:** Borrow a non-acting critic/checker role as a compact action-side verifier, not as a second executor.
- **Generalization Rationale:** A non-acting verifier can inspect evidence, schema, and completion state without corrupting mutable environments.
- **Do Not Borrow:** Do not borrow parallel investigation or shallow coordinator synthesis for dependency-heavy tasks.
- **Transfer Confidence:** High

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style decomposition with tracked subtasks, hierarchical coordination, and richer memory.
- **Relevant Strength:** It demonstrates explicit tracked work items and progress synchronization, which directly match Stage 1's missing state ledger.
- **Relevant Weakness / Risk:** The pool marks it as high-cost, high max-step, and too heavy for `Qwen3-8B`. Its orchestration cost is disproportionate to the quality gain.
- **Related Winner Failure:** Helps conceptually with missing task ledger and plan/action synchronization.
- **Transferable Module Pattern:** Borrow only the idea of tracked work items and "synthesize after resolved items," compressed into the current single-executor harness.
- **Generalization Rationale:** A lightweight checklist of unresolved items transfers to stateful APIs, multi-hop QA, scheduling, and workflow tasks.
- **Do Not Borrow:** Do not borrow the whole hierarchical coordinator, graph-style heavy memory, or broad multi-agent orchestration.
- **Transfer Confidence:** Medium

#### Example: `harness6`

- **Observed Structure:** Guarded small-committee harness with strict budget discipline and SkillWeaver memory.
- **Relevant Strength:** It is the lowest-cost baseline with zero max-step rate in the pool. It is useful as a budget and guard reference.
- **Relevant Weakness / Risk:** Quality is too low, EnvScaler done and score are weak, ToolHop is weak, and SearchQA does not use search.
- **Related Winner Failure:** Helps with budget discipline, repeated-call caps, and avoiding long failed traces.
- **Transferable Module Pattern:** Borrow strict budgets and low-cost guard thresholds, but apply them only after evidence-aware repair has had a fair chance.
- **Generalization Rationale:** Every tool benchmark benefits from avoiding endless retries, but budget guards must not replace task completion checks.
- **Do Not Borrow:** Do not borrow shallow worker delegation, weak dependency readiness, or no-search routing.
- **Transfer Confidence:** Medium for budget guards, Low for architecture

#### Example: `harness7`

- **Observed Structure:** Router/debate harness with debate intended for read-only tasks and single-executor fallback for stateful tasks.
- **Relevant Strength:** The pool shows reliable SearchQA search use and good early ToolHop signal. Its most transferable idea is route awareness: read-only tasks can tolerate more comparison than mutable tasks.
- **Relevant Weakness / Risk:** Stateful tasks still run long, all-available ToolHop drops, and parallel solver reports are not sufficiently grounded.
- **Related Winner Failure:** Helps with unsafe parallel execution and task-type-sensitive routing.
- **Transferable Module Pattern:** Borrow the routing rule that debate/parallelism is allowed only for read-only evidence gathering, while state-changing tools remain single-executor and sequential.
- **Generalization Rationale:** The distinction between read-only lookup and mutable commit is domain-agnostic across tools.
- **Do Not Borrow:** Do not borrow loose parallel debate, branch summaries as evidence, or early synthesis from unvalidated reports.
- **Transfer Confidence:** Medium

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Planning | SearchQA and ToolHop stop after shallow or ambiguous evidence | Missing target-variable and evidence-chain planning | `harness1`, `harness2` | Compact serial plan with explicit target, hops, disambiguation, and final transformation | Serial dependency planning transfers across lookup, relation, date, string, and numeric tasks | Avoid verbose heavy planning from `harness5` | High | Low |
| Action | EnvScaler completes with partial state | Missing observation-grounded task ledger and completion gate | `harness5`, `harness4` | Lightweight tracked work items plus non-acting completion critic | Mutable workflows need confirmed operations before terminal commit | Avoid full AgentOrchestra hierarchy from `harness5` | High | Medium |
| Action | Repeated failed calls, invented tools, empty action steps | Missing schema/error repair controller | `harness3`, `harness6`, `harness4` | Closed-set tool schema visibility, duplicate-failure advisory, bounded repair, and critic check | Tool-name, schema, and repeated-call errors are domain-general, but legitimate retries after changed preconditions must remain possible | Avoid under-acting early stops and hard failed-call locks from `harness3` and `harness6` | High | Medium |
| Action | Correct observations are ignored or wrong entity is transformed | Missing evidence arbitration before final answer | `harness4`, selective `harness3` candidate comparison idea | Non-acting verifier binds proposed answer to observed evidence and target variable | Final answers should be trace-grounded across QA, ToolHop, and API tasks | Avoid loose vote-and-synthesize from `harness3` | High | Low |
| Memory | Memory treats planned or intended actions as completed facts | Missing observation-grounded, phase-aware memory extraction | `harness7`, `harness1` | Compact cheatsheet/procedural hints, but extracted only from successful observations | Memory should guide without overriding live evidence in all domains | Avoid broad likely-answer guidance and heavy memory from `harness5` | Medium | Medium |
| Cross-Module Interface | Plans, action observations, and memory facts are not separated | No typed status handoff between plan items and observed completions | `harness5`, `harness2` | Minimal checklist/status object shared through transcript summaries | Intention-vs-observation separation transfers to any multi-step task | Avoid heavyweight progress tools or extra hierarchy | High | Medium |
| Builder/Wiring | Unsafe parallel execution in mutable environments | Missing task/tool execution-mode guard | `harness7`, `harness3` | Read-only vs state-changing route awareness; default stateful route to sequential single executor | Mutability is a general execution property independent of benchmark labels | Avoid broad parallel debate for stateful tasks | Medium | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve the single primary executor in Action because it maintains serial dependency continuity and avoids handoff noise.
- Preserve strict JSON tool-call formatting in Action because valid output rates are already high and this supports local tool parsing.
- Preserve concise initial planning in Planning because simple tasks should not pay heavy coordination cost.
- Preserve compact memory guidance in Memory because soft procedural hints help without requiring external services.
- Preserve existing Builder/Wiring compatibility with `ActionContext`, benchmark tool loading, provider names, and metadata.
- Preserve direct finalization for clearly supported one-hop answers because over-verification would regress easy tasks.

#### Borrow

- Borrow from `harness1` into Planning and Action: direct serial execution with compact progress refresh, expected to improve dependency-heavy QA and ToolHop because one executor carries the entity chain.
- Borrow from `harness2` into Action: concise reflection checkpoints, expected to improve final readiness and repair decisions because they force a compact known/unknown/next review.
- Borrow from `harness3` into Action: closed-set tool/schema visibility plus soft repeated-call advisories, expected to reduce unknown-tool, duplicate retry, and empty-action failure buckets without blocking legitimate retries after state changes.
- Borrow from `harness4` into Action: non-acting critic/verifier, expected to improve completion gating and final-answer arbitration because it checks evidence without mutating state.
- Borrow from `harness5` into Cross-Module Interface: tracked work-item concept, expected to prevent skipped subtasks because items can only close from successful observations.
- Borrow from `harness7` into Builder/Wiring and Action: read-only versus state-changing routing, expected to keep safe parallelism for independent lookup while forcing sequential commit for mutable tools.

#### Avoid

- Avoid copying `harness5` whole-hierarchy orchestration because it is high-cost, high max-step, and too heavy for the current model; this is a complexity and efficiency risk.
- Avoid `harness7` loose parallel debate for ToolHop/stateful execution because branch reports can become plausible but ungrounded; this is a weak transfer and correctness risk.
- Avoid `harness3` and `harness6` shallow early-stop behavior because it can raise done rates while lowering exact task success; this is a regression risk.
- Avoid treating memory as authoritative task state because Stage 1 shows planned actions can become false facts; this is a correctness risk.
- Avoid benchmark-specific fixes for observed entity names, dates, IDs, or tool traces because they will not transfer to unseen tasks; this is an overfitting risk.
- Avoid broad external services, neural retraining, dataset changes, or evaluator changes because they are outside the harness boundary; this is an irrelevance risk.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Observation-Grounded Work Ledger]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Premature completion after partial state mutation
- **Current Weakness:** The executor decides completion from model confidence rather than confirmed requested operations.
- **Desired Behavior:** Track required work items, attempted calls, successful observations, failed observations, and remaining items; block terminal stateful completion until all required items are observation-confirmed or explicitly impossible.
- **Borrowed Pattern:** `harness5` tracked work items plus `harness4` non-acting completion critic.
- **Preserved Behavior:** Keep one primary executor and strict JSON tool calls.
- **Implementation Shape:** Add a compact action-side ledger and a final preflight prompt/check that reviews remaining requirements before `complete_task` or `final_answer`.
- **Generalization Rationale:** Any mutable workflow, scheduling task, database edit, or multi-step API task needs observed completion rather than intended completion.
- **Complexity:** Medium
- **Expected Impact:** Largest expected EnvScaler gain; should reduce partial-score and false-completion failures.
- **Regression Risk:** A bloated ledger could slow simple tasks or over-block valid terminal actions.

**[Direction 2: Typed Planning-to-Action Evidence Contract]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Planning-to-action execution gap with memory contamination
- **Current Weakness:** Plans can look like executed tool calls, and memory/action consume them as transcript text.
- **Desired Behavior:** Planning outputs compact goals, evidence targets, and pending actions; Action marks completion only from successful observations; Memory records only observed facts.
- **Borrowed Pattern:** `harness5` resolved-work-item idea and `harness2` concise status summaries.
- **Preserved Behavior:** Keep short initial planning and avoid heavy coordinator machinery.
- **Implementation Shape:** Use a small structured status note with fields like `target`, `pending`, `observed_done`, `failed`, and `next`; keep it textual/JSON-compatible inside existing modules.
- **Generalization Rationale:** Separating intention from observation transfers to stateful tasks, retrieval tasks, and transformations.
- **Complexity:** Medium
- **Expected Impact:** Reduces plan-as-fact errors and improves summaries used by the executor.
- **Regression Risk:** If the contract becomes too rigid, it may add overhead to one-hop tasks.

**[Direction 3: Schema-Aware Repair And Retry Controller]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Weak schema-aware repair and low-value retry control
- **Current Weakness:** Unknown tools, identical failed retries, malformed arguments, and empty actions are only recorded, not actively controlled.
- **Desired Behavior:** Classify execution failures, warn on consecutive identical failed calls, prefer valid schema repair from the current available tool schemas, and treat empty action output as a repairable contract violation. Do not permanently block a failed signature; allow the same real tool call after new evidence or state changes make it valid.
- **Borrowed Pattern:** `harness3` whitelist/repeat awareness, `harness6` budget discipline, and `harness4` critic checks, softened so guards advise repair rather than suppress necessary retries.
- **Preserved Behavior:** Preserve useful retries that change arguments or strategy based on observations.
- **Implementation Shape:** Maintain a small call history and error summary; before choosing a call, show closed-set tool names and argument schemas, check for invented tools or malformed keys, flag consecutive duplicate failures, and keep retry budget advisory rather than permanently blocking execution.
- **Generalization Rationale:** Tool-call validity and repair are domain-general for any local or external tool environment.
- **Complexity:** Medium
- **Expected Impact:** Reduces EnvScaler repeated failures and ToolHop schema/error loops.
- **Regression Risk:** Any hard duplicate guard can block legitimate repeated verification, polling, or stateful recovery; keep duplicate handling advisory and reset it after successful precondition-changing observations.

**[Direction 4: Evidence-Chain Planner For QA And ToolHop]**
- **Target Module:** Planning
- **Stage 1 Failure Addressed:** Under-decomposed evidence chain and unsupported finalization
- **Current Weakness:** The plan does not consistently state target variable, required hops, disambiguation criteria, and final transformation.
- **Desired Behavior:** For read-only QA/tool reasoning tasks, produce a compact evidence chain: target answer type, required facts, dependency order, disambiguation check, and final transformation.
- **Borrowed Pattern:** `harness1` direct serial roadmap and `harness2` clearer planning/checkpoint style.
- **Preserved Behavior:** Preserve concise planning and direct execution.
- **Implementation Shape:** Modify planning prompts/provider behavior to produce short structured plans and summaries with `known`, `unknown`, `next`, and `final_check`.
- **Generalization Rationale:** Entity-chain and lookup-transform tasks recur across domains and require dependency-aware evidence collection.
- **Complexity:** Low
- **Expected Impact:** Should improve SearchQA and ToolHop exact correctness by reducing shallow finalization.
- **Regression Risk:** Over-planning could slow obvious one-hop lookups.

**[Direction 5: Final Observation Arbitration And Canonicalization]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Observation handling loses decisive evidence; final-answer canonicalization is too weak
- **Current Weakness:** The final answer can ignore a decisive observation or return an answer in the wrong granularity/form.
- **Desired Behavior:** Before final answer, bind the candidate answer to supporting observations, verify it matches the target variable, check contradictions, and normalize only the requested answer type.
- **Borrowed Pattern:** `harness4` non-acting verifier; avoid loose voting from `harness3`.
- **Preserved Behavior:** Preserve raw concise answers when evidence is already sufficient.
- **Implementation Shape:** Add a lightweight final-answer checklist in the action final prompt or a non-acting verifier pass for uncertain/multi-step traces.
- **Generalization Rationale:** Trace-grounded answer selection and answer-type checking are reusable across short QA, ToolHop, and API-status tasks.
- **Complexity:** Low
- **Expected Impact:** Reduces subanswer-only failures and cases where correct intermediate values are ignored.
- **Regression Risk:** Over-normalization could damage acceptable aliases or casing.

**[Direction 6: Mutability-Aware Sequential Commit Discipline]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Unverified multi-tool parallelism on mutable state
- **Current Weakness:** Multiple emitted calls may execute concurrently even when they mutate shared state.
- **Desired Behavior:** Default mutable/state-changing tools to one call per step with read-after-write verification; allow parallelism only for independent read-only evidence gathering.
- **Borrowed Pattern:** `harness7` route distinction between read-only debate and stateful fallback, plus `harness3` schema-aware but soft guarded execution.
- **Preserved Behavior:** Preserve efficient direct tool use and allow independent read-only lookup where safe.
- **Implementation Shape:** Add an execution-mode helper that classifies calls by likely mutability using tool names/descriptions and benchmark terminal rules; sequence mutating batches but do not hide available tools or forbid needed retries.
- **Generalization Rationale:** Read-only versus mutable operation is a general tool property across environments.
- **Complexity:** Medium
- **Expected Impact:** Reduces EnvScaler dependency-order and partial-state failures.
- **Regression Risk:** May increase latency on tasks where parallel independent updates would be safe.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The next harness should be a direct but verification-aware single-executor harness. It should keep the base harness's low coordination overhead and strict JSON ReAct loop, while adding compact structure around planning targets, observation-grounded state, schema repair, final verification, and memory safety. It should feel like a disciplined operator rather than a large committee: one actor performs tool calls, one lightweight non-acting checker may inspect readiness, and memory remains a soft hint source.

#### 6.2 Module-Level Blueprint

##### Planning Blueprint

Implement compact structured planning that names the target answer/state, required evidence or operations, dependency order, and final commit criteria. Preserve short plans for simple tasks. Avoid executable-looking planned tool calls unless they are clearly marked as pending. Stage 1 evidence from SearchQA and ToolHop shows shallow finalization after one or two calls; a structured evidence chain is task-general because most unseen tasks still need target-variable tracking and dependency order.

##### Action Blueprint

Implement a single primary executor with three lightweight soft controls: a work ledger for stateful/multi-step tasks, a schema-aware repair controller with visible tool schemas, and a final observation arbitration check. A non-acting verifier may be used at checkpoints or before terminal actions, but it must not perform environment mutations. Preserve direct tool use and strict JSON. Avoid heavy worker pools, broad debate, or multiple acting agents on stateful tasks. Stage 1 evidence shows premature `complete_task`, repeated failed calls, ignored observations, and unsafe concurrent state mutations.

##### Memory Blueprint

Implement phase-aware compact memory that distinguishes reminders from facts. BEGIN memory should provide short procedural hints. IN memory should extract only from successful tool observations and should label facts as observed, not inferred from plans. Preserve compact guidance. Avoid "most likely" answer suggestions unless the task explicitly permits non-raw uncertain answers. Stage 1 evidence shows memory contamination when planned actions were recorded as completed state.

##### Builder / Wiring Blueprint

Keep the harness compatible with the local factory structure and `ActionContext`. Preserve provider names, metadata wiring, benchmark tool loading, and memory-provider attachment. Add only lightweight configuration or metadata needed for execution-mode guards. Avoid changing the benchmark loop, evaluator, dataset, model backend, or external services.

##### Interface Blueprint

Add a minimal status handoff between Planning, Action, and Memory. The handoff should separate `planned_or_pending`, `observed_success`, `observed_failure`, `remaining`, and `final_criteria`. Action observations should update the status; Memory should consume the status but not overwrite observed truth. This is motivated by Stage 1's plan-as-fact failures and should transfer because all multi-step tasks benefit from separating intended work from observed completion.

#### 6.3 Minimal Required Changes

- Add a compact structured plan/status format with target, pending work, known evidence, unknown evidence, and final check.
- Add an action-side ledger that marks work complete only from successful tool observations.
- Add schema/error repair support for unknown tools, bad arguments, duplicate failed calls, and empty action outputs; the tool schemas must be visible before action selection and duplicate handling must be advisory.
- Add a final preflight before `complete_task` and before multi-step `final_answer`.
- Make memory extraction observation-grounded and phase-aware.
- Default state-changing tool batches to sequential execution unless read-only independence is clear.

#### 6.4 Optional Enhancements

- Add a non-acting verifier pass only when the ledger is non-empty, repeated failures occurred, or the task is multi-hop.
- Add lightweight answer-type canonicalization heuristics for date, number, name, list, and raw string outputs.
- Add compact call-history summaries to reduce repeated context without losing error signals.
- Add read-only route awareness so independent lookup tasks can still use safe parallel evidence gathering.
- Add a budget advisory that triggers strategy change before max steps rather than immediate failure or forced finalization.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Produce compact structured plans that separate target, evidence chain, pending work, and final criteria.
- [Planning] Do not emit executable-looking tool calls as if they were completed actions.
- [Action] Keep one primary acting executor; any verifier or critic must be non-acting.
- [Action] Maintain an observation-grounded ledger for stateful and multi-step tasks.
- [Action] Block terminal completion when ledger items remain unresolved.
- [Action] Add schema-aware repair with visible tool schemas, duplicate failed-call advisory, and empty-output recovery.
- [Action] Bind final answers to supporting observations and verify the answer type before final submission.
- [Action] Execute mutable/state-changing tools sequentially unless independence is explicit.
- [Memory] Treat memory as soft guidance, not authoritative task state.
- [Memory] Extract facts only from successful observations, not from plans or intentions.
- [Builder] Preserve local harness factory compatibility, `ActionContext` flow, tool loading, and metadata wiring.
- [Interface] Share a minimal status object or structured note across Planning, Action, and Memory.
- [Preserve] Keep the base harness's concise ReAct style, strict JSON contract, and direct execution for easy tasks.
- [Avoid] Do not copy an entire peer harness, add heavy multi-agent orchestration, change the evaluator, or hard-code benchmark IDs, entities, answers, or tool traces.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
