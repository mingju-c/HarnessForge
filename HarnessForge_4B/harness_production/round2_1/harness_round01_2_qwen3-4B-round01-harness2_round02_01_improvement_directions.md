### PART 1: LOCALIZATION SUMMARY

The current winner is `harness_round01_2` evaluated in the Qwen3-4B round02_01 seed run. Its architecture is a compact single-executor harness: `builder.py` wires a compact planning provider, `ACTION_SYSTEM = "schema_cooldown_react"`, and `MEMORY_SYSTEM = "schema_hint_memory"`. Planning produces a short packet with task type, evidence slots, required mutations, answer format, terminal criteria, and next tool intent. Action is a guarded ReAct executor with schema preflight, repeated-call blocking, low-value-repeat blocking, shallow evidence-before-final checks, and answer canonicalization. Memory provides phase-aware procedural guidance and retrieves a small number of successful prior procedures.

Stage 1 identifies five dominant transferable failure modes. First, SearchQA failures often have evidence present but commit an answer span from the wrong snippet or entity. Second, ToolHop multi-hop chains break after failed intermediate lookups because no ordered provenance ledger forces the agent to preserve source entity, relation result, transformed field, and final computation. Third, guard observations block bad repeats but do not route recovery, so repeated failures lead to loops or unsupported fallbacks. Fourth, EnvScaler stateful tasks get partial progress but lack a complete mutation checklist, causing premature `complete_task`, empty continuation, or partial-only completion. Fifth, terminal policy and answer-format confusion appear across mixed task families, especially when short-answer tasks are misclassified as stateful workflows.


#### SearchQA Calibration Note for Regeneration

A later round02_01 pilot on the first 200 shared tasks showed that the new evidence/mutation ledger improves ToolHop and some EnvScaler behavior, but can regress SearchQA if it over-controls simple retrieval. On those 46 SearchQA items, the seed `harness_round01_2` scored 0.4565, while the eight round02_01 variants ranged from 0.2826 to 0.4348 before the lightweight SearchQA patch. The observed regressions are task-general: first-query paraphrases drift away from the raw question, date canonicalization changes evidence surface forms such as `April 1, 1996` into `1996-04-01`, weak token-overlap support accepts distractor snippets, and memory retrieval can inject stale query/answer patterns from unrelated SearchQA tasks.

Future regeneration must therefore preserve a SearchQA-specific fast path inside the broader round02 design. SearchQA should begin with a raw-question search, refine only after the first evidence misses a key entity or relation, preserve final span/date/title surface forms from evidence, require answer support in one current evidence record, and suppress old SearchQA answer/query memories. This is not a task-specific patch; it is a benchmark-family routing rule for short-answer retrieval tasks.

The module attribution is therefore not "replace the harness." The highest-leverage fixes are Action-side evidence attribution and recovery routing, Cross-Module evidence/mutation ledgers, Planning-side executable slot summaries, Memory-side task-signature routing, and Builder/Wiring instrumentation for empty or zero-token runs. The harness should preserve its direct single-executor path, hard schema preflight, repeated-call blocking, compact planning, provenance language, local canonicalization, and direct read-only multi-call support. These strengths already support exact successes in SearchQA and ToolHop and partial progress in EnvScaler; the repair target is to make those behaviors more accountable and recoverable.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness1`

- **Observed Structure:** Direct single-executor ReAct with flash planning and ExpeL-style memory. It uses compact search-oriented planning and keeps execution as one serial chain.
- **Relevant Strength:** Strongest non-trivial all-available mixed score in the 8B pool, high EnvScaler score, and reliable SearchQA search use. Its direct execution discipline supports continuity without role handoff overhead.
- **Relevant Weakness / Risk:** It is expensive, with high token usage and long wall time. It can accumulate long context before stopping when recovery is weak.
- **Related Winner Failure:** Helps preserve the winner's direct single-executor strength while repairing EnvScaler and multi-hop state tracking.
- **Transferable Module Pattern:** Borrow direct execution discipline and compact plan refresh, not the full cost profile. Use this as evidence that a single executor can remain the default if stronger ledgers and stop criteria are added.
- **Generalization Rationale:** Many unseen tool tasks benefit from continuity of observations and decisions, especially when state mutation must avoid conflicting actors.
- **Do Not Borrow:** Do not borrow unbounded context growth, long reflection transcripts, or expensive repeated deliberation.
- **Transfer Confidence:** High

#### Example: `harness2`

- **Observed Structure:** Concise reflection harness with short planning, one executor, periodic compact reflection, final verifier, and Agent-KB memory.
- **Relevant Strength:** The concise reflection idea is simple and fits the winner's architecture. SearchQA has strong small-sample subEM and reliable search use in the pool.
- **Relevant Weakness / Risk:** Weak ToolHop correctness, high EnvScaler max-step rate, and repeated failed calls inflate runtime. This is close to the winner's current failure pattern.
- **Related Winner Failure:** Guard blocks without recovery routing, shallow verifier behavior, and weak multi-hop chain preservation.
- **Transferable Module Pattern:** Borrow only the idea of bounded progress reflection after failure clusters, and make it ledger-aware rather than generic.
- **Generalization Rationale:** A short reflection checkpoint after repeated failures can help unseen tool schemas if it is tied to concrete slots, failed calls, and next valid alternatives.
- **Do Not Borrow:** Do not borrow generic periodic reflection that does not update evidence or mutation state. Do not copy Agent-KB retrieval if it amplifies bad patterns.
- **Transfer Confidence:** Medium

#### Example: `harness3`

- **Observed Structure:** Guarded JoyAgent-style low-token harness with terse planning, whitelist checks, repeated-call detection, early-stop guards, and MEMP memory.
- **Relevant Strength:** Very low token footprint, low max-step rate, and strong ToolHop correctness on the fair first-100 slice.
- **Relevant Weakness / Risk:** SearchQA used_search is zero, and EnvScaler completion does not translate into high score. It may stop after shallow or incomplete state updates.
- **Related Winner Failure:** Useful for cost control and guard preservation, but risky for SearchQA routing and stateful completion.
- **Transferable Module Pattern:** Borrow budget-aware guard style and early stop discipline only after terminal readiness is ledger-based.
- **Generalization Rationale:** Unseen tasks need bounded execution, but bounded execution must be tied to evidence sufficiency rather than early commitment.
- **Do Not Borrow:** Do not borrow no-search behavior, shallow completion, or early stopping without evidence/mutation completeness.
- **Transfer Confidence:** Medium

#### Example: `harness4`

- **Observed Structure:** Light reflection harness with a short planner, one acting executor, non-acting critic checkpoints, final answer handling, and workflow memory.
- **Relevant Strength:** Best speed-quality balance in the 8B pool, reliable SearchQA search use, reasonable ToolHop path quality, and lower orchestration burden than heavy multi-agent designs.
- **Relevant Weakness / Risk:** EnvScaler still trails the best score, and max-step failures remain on stateful tasks.
- **Related Winner Failure:** Guard recovery, final-answer readiness, and stateful stop/retry decisions.
- **Transferable Module Pattern:** Borrow a non-acting verifier/critic pattern that checks tool existence, argument plausibility, repeated failures, evidence-slot completion, and terminal readiness. Keep the executor as the only environment actor.
- **Generalization Rationale:** A non-acting critic can improve read-only and stateful tasks without introducing conflicting state mutations or heavy handoffs.
- **Do Not Borrow:** Do not borrow critic checks that remain generic or detached from the ledger. Do not allow the critic to become a second acting agent.
- **Transfer Confidence:** High

#### Example: `harness5`

- **Observed Structure:** AgentOrchestra-style heavier multi-agent harness with broader role coordination and Cerebra fusion memory.
- **Relevant Strength:** Moderate EnvScaler score and reliable SearchQA search use. It demonstrates that richer checking can improve coverage.
- **Relevant Weakness / Risk:** Highest token cost, highest max-step rate, and orchestration appears too heavy for the model. It often adds handoff overhead and repeated work.
- **Related Winner Failure:** Mostly a negative control for agent-collaboration transfer. The winner needs verification, not broad orchestration.
- **Transferable Module Pattern:** Borrow only the concept of separating executor and verifier responsibilities. Compress it to one executor plus a small non-acting verifier.
- **Generalization Rationale:** The role distinction transfers, but the full architecture is not needed for unseen mixed tasks and may harm stateful reliability.
- **Do Not Borrow:** Do not borrow heavy multi-agent execution, broad fusion memory exposure, or multiple actors that can operate the environment.
- **Transfer Confidence:** Low

#### Example: `harness6`

- **Observed Structure:** Guarded small-committee harness with strict budget discipline, whitelist/repeat/max-step/failure guards, and SkillWeaver memory.
- **Relevant Strength:** Lowest runtime and token cost, zero max-step rate, and useful minimal guard baseline.
- **Relevant Weakness / Risk:** Very low EnvScaler score and done rate, weak ToolHop correctness, and SearchQA does not use search.
- **Related Winner Failure:** Useful only for budget and stop discipline; not a quality parent for routing, evidence attribution, or mutation completeness.
- **Transferable Module Pattern:** Borrow strict budget accounting and concise procedural memory formatting, but only as guardrails around the winner's stronger execution path.
- **Generalization Rationale:** Cost control matters across unseen tasks, but under-acting should not be mistaken for robust completion.
- **Do Not Borrow:** Do not borrow the small-committee acting topology, no-search SearchQA behavior, or aggressive under-action.
- **Transfer Confidence:** Low

#### Example: `harness7`

- **Observed Structure:** Router/debate harness for read-only tasks with stateful fallback to single executor plus critic, and dynamic cheatsheet memory.
- **Relevant Strength:** Reliable SearchQA search use, strong early ToolHop correctness, and a useful distinction between read-only debate and stateful single-executor execution.
- **Relevant Weakness / Risk:** EnvScaler max-step rate is high, all-available ToolHop score drops with more samples, and stateful fallback still needs stronger verifier rules.
- **Related Winner Failure:** Evidence-present but wrong span, final-answer arbitration, and terminal policy separation by active toolset.
- **Transferable Module Pattern:** Borrow task-route policy: read-only tasks may use lightweight candidate arbitration, while stateful tasks must stay single-executor with non-acting verification.
- **Generalization Rationale:** The read-only versus stateful distinction is domain-agnostic and maps to whether parallel reasoning can safely happen without mutating external state.
- **Do Not Borrow:** Do not borrow open-ended debate, parallel acting, or costly route-level discussion on simple direct tasks.
- **Transfer Confidence:** Medium

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Planning | Compact packets are useful but not executable; ToolHop can be misclassified as stateful | Missing explicit ordered evidence and mutation slots that action can update | `harness1`, `harness4` | Compact plan plus light progress checkpoints tied to slots | Unseen tasks benefit when the plan names evidence dependencies, terminal policy, and verification questions without long transcripts | `harness5` broad orchestration planning | High | Medium |
| Action - tool-use repair | Guard blocks repeated or malformed calls but does not route recovery | Missing failure-type recovery router for schema, repeat, not-found, unauthorized, and empty-action classes | `harness4`, with budget discipline from `harness3` | Non-acting critic checks failed-call class and recommends the next valid repair path | Tool errors recur across schemas; routing by error class transfers better than memorizing entities | `harness2` generic reflection after failures, `harness5` heavy handoffs | High | Medium |
| Action - answer arbitration | Final answers pass after any evidence, even when the answer span is wrong | Missing answer-to-evidence support record and candidate arbitration | `harness7`, `harness4` | Read-only candidate arbitration plus non-acting verifier before final answer | Retrieval and multi-hop tasks often include distractors, aliases, and adjacent facts | Open-ended debate from `harness7`; multiple acting agents from `harness5` | High | Medium |
| Action - orchestration | Single executor lacks verification, but full multi-agent execution is too costly | Need one executor plus bounded non-acting verifier, not heavy collaboration | `harness4`, compressed lesson from `harness5` | Keep executor as only actor; add verifier as critic of readiness and support | This preserves state safety while adding independent checks for finalization | `harness5` full AgentOrchestra | High | Medium |
| Memory | Retrieval is broad, long, and successful-only | Missing task-signature routing and compact failure lessons | `harness7`, `harness6` | Dynamic cheatsheet route memory plus concise skill/procedure formatting | Memories should transfer by workflow, tool family, and failure class rather than wrapper text | Cerebra-style broad memory exposure from `harness5`; noisy Agent-KB retrieval from `harness2` | Medium | Medium |
| Cross-Module Interface | Planning text is appended to memory but not enforced by action | Missing shared evidence/mutation ledger and terminal policy contract | None; repair within winner pattern | Convert the winner's existing plan fields into runtime ledger entries | Multi-hop QA and stateful workflows both require durable progress state independent of domain | Whole-architecture transfer from any peer | High | High |
| Builder/Wiring | Zero-token and empty-step episodes can be conflated with reasoning failures | Missing run-status metadata and bounded empty-output retry | None; repair within winner pattern | Surface model-call abort, parser-empty output, and normal reasoning status | Infrastructure no-op failures are benchmark-independent and should not steer harness evolution | Retrying without bounds or duplicating mutations | Medium | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve hard schema preflight in Action because it prevents invalid tool calls and unsafe state changes from passing silently.
- Preserve repeated-call and low-value-repeat blocking in Action because Stage 1 shows guard feedback can help when paired with a valid next move.
- Preserve the direct single-executor base path in Action because it already solves many SearchQA and ToolHop examples and avoids state conflicts in EnvScaler.
- Preserve compact planning packets in Planning because they keep simple lookup tasks efficient while exposing evidence, mutation, answer-format, and terminal fields.
- Preserve provenance language in Memory because separating observations, derived facts, and hypotheses directly matches the Stage 1 failure analysis.
- Preserve local answer canonicalization in Action because exact-answer benchmarks benefit from concise final answers, but expand it with format-specific rules.
- Preserve direct read-only multi-call support in Action because successful comparison tasks can gather independent evidence efficiently in one step.

#### Borrow

- Borrow from `harness4` into Action: a non-acting verifier/critic that checks failed-call class, argument plausibility, support records, and terminal readiness; expected benefit is fewer unsupported final answers and fewer loops; it generalizes because the verifier reasons over tool contracts and ledgers rather than task entities.
- Borrow from `harness1` into Planning and Action: direct execution discipline with compact progress refresh; expected benefit is maintaining continuity while adding stronger state checks; it generalizes because many tool tasks need one coherent executor.
- Borrow from `harness7` into Action: read-only candidate arbitration before final answer while keeping stateful tasks on a single acting executor; expected benefit is better SearchQA span selection and ToolHop final support; it generalizes because read-only arbitration is safe across domains.
- Borrow from `harness3` into Action: low-token guard style and early stop discipline after ledger-backed readiness checks; expected benefit is lower max-step and token growth; it generalizes because budgets apply to all tool-rich tasks.
- Borrow from `harness7` into Memory: dynamic route-style task signatures; expected benefit is less wrapper-driven memory noise; it generalizes because workflow and tool-family signatures transfer across unseen prompts.
- Borrow from `harness6` into Memory: concise procedural memory formatting; expected benefit is compact reminders that do not crowd evidence; it generalizes because short lessons are easier to apply across tasks.

#### Avoid

- Avoid copying `harness5` full AgentOrchestra because heavy orchestration increases tokens and max-step failures; it should not enter Stage 3 as a full design due to complexity and regression risk.
- Avoid open-ended debate from `harness7` because it can inflate cost and is unsafe for stateful tasks; only bounded read-only arbitration should be used due to complexity risk.
- Avoid generic periodic reflection from `harness2` because it does not by itself fix repeated failed calls or broken chains; this is weak transfer evidence unless tied to ledgers.
- Avoid no-search behavior from `harness3` and `harness6` because it regresses SearchQA; this is a direct quality regression risk.
- Avoid shallow early completion from `harness3` because it can raise done proxy while lowering EnvScaler score; this is a weak-transfer and regression risk.
- Avoid broad memory exposure from `harness5` and noisy Agent-KB retrieval from `harness2` because Stage 1 shows unrelated memories already distract the winner; this is irrelevance and cost risk.
- Avoid task-specific patches for observed entities such as queen bed sizes, paternal-grandmother relations, Big Picture Magazine, Samira Patel, or Alice Chan because they would not transfer.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Evidence-Supported Final Answer Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Evidence-present but answer extracted from the wrong evidence span
- **Current Weakness:** `final_answer` can proceed after any prior evidence tool call, even if the candidate answer is tied to the wrong snippet, entity, relation, or field.
- **Desired Behavior:** Before finalizing, the action loop should create a compact support record with answer candidate, source observation id or tool, relevant question slot, copied-or-derived status, and a short contradiction check against nearby distractors.
- **Borrowed Pattern:** `harness4` non-acting verifier plus `harness7` read-only candidate arbitration
- **Preserved Behavior:** Keep the winner's single executor and local answer canonicalization.
- **Implementation Shape:** Add a pre-finalization verifier pass that inspects the ledger and current observations. For read-only tasks, allow one lightweight alternative-candidate comparison when multiple plausible spans exist. The verifier may approve, request one more targeted evidence call, or force answer canonicalization; it must not call tools itself.
- **Generalization Rationale:** Retrieval, lookup, and multi-hop tasks in unseen domains all require linking final values to the requested slot rather than to any observed text.
- **Complexity:** Medium
- **Expected Impact:** Reduces SearchQA path-correct but answer-wrong failures and unsupported ToolHop finalizations.
- **Regression Risk:** If too strict, it may increase no-final cases on simple direct-answer tasks; allow fast approval when one direct observation uniquely answers the slot.


**[Direction 1A: SearchQA Lightweight Retrieval Fast Path]**
- **Target Module:** Planning, Action, Memory
- **Stage 1 / Pilot Failure Addressed:** SearchQA evidence is often available, but regenerated round02-style guards can lower accuracy by over-paraphrasing queries, normalizing date surfaces, accepting distractor evidence, or injecting stale memory.
- **Current Weakness:** A generic ledger/verifier treats SearchQA like multi-hop evidence arbitration even when the task needs one direct retrieval and exact span copying. This adds cost and can move the model away from the raw question wording.
- **Desired Behavior:** Detect SearchQA from the task wrapper or data-source metadata. Plan `search(raw current question)` as the first action. Only split into candidate-generation and candidate-verification searches if the first evidence lacks a key entity/relation or presents multiple plausible candidates. Copy the final answer in the evidence surface form; do not convert dates to ISO unless explicitly requested.
- **Borrowed Pattern:** Preserve the winner's direct lookup behavior and combine it with a narrow support record from Direction 1.
- **Preserved Behavior:** Keep schema preflight, repeated-call blocking, and raw-answer formatting, but avoid heavy verifier loops on simple SearchQA.
- **Implementation Shape:** Add a SearchQA route flag in Action, a raw-query repair guard for the first `search` call, a SearchQA-specific final support check requiring answer surface or all answer tokens in one current evidence record, date-surface restoration before final return, and memory filtering that skips old SearchQA answer/query retrieval and ingestion.
- **Generalization Rationale:** Short-answer retrieval benchmarks reward exact evidence span selection; this transfers across questions without encoding any item id, entity, or answer.
- **Complexity:** Low to Medium
- **Expected Impact:** Restores seed-level SearchQA direct-search behavior while retaining round02 gains on ToolHop/EnvScaler.
- **Regression Risk:** Too aggressive raw-query repair could block useful decomposed searches; only apply it before any evidence exists and allow refinement after ambiguous or missing evidence.

**[Direction 2: Shared Evidence and Mutation Ledger]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Multi-hop evidence chain break after a failed intermediate lookup; stateful task progress is not tracked as a complete checklist
- **Current Weakness:** Planning emits evidence slots and required mutations as text, but Action does not maintain enforceable slot status or dependency order.
- **Desired Behavior:** The harness should maintain a small runtime ledger containing required evidence slots, dependency links, observed values, source tools, confidence or blocker status, required mutations, verification observations, terminal policy, and current readiness.
- **Borrowed Pattern:** None; repair within winner pattern
- **Preserved Behavior:** Keep compact initial planning and direct execution.
- **Implementation Shape:** Parse or normalize the planning packet into simple ledger entries. After each observation, Action updates completed slots, blocked slots, mutation status, and terminal readiness. Final-answer and `complete_task` gates consult this ledger before committing.
- **Generalization Rationale:** Multi-hop QA, scheduling, account updates, file operations, and commerce workflows all require persistent provenance and completion state independent of the domain vocabulary.
- **Complexity:** High
- **Expected Impact:** Reduces ToolHop wrong-entity transformations and improves EnvScaler full-score completion by making partial progress visible and auditable.
- **Regression Risk:** Overly heavy ledger logic may slow simple tasks; use a minimal default with only one evidence slot for direct lookup tasks.

**[Direction 3: Failure-Type Recovery Router]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Guard observations stop repeats but do not route recovery
- **Current Weakness:** Guard blocks identify repeated, malformed, not-found, or low-value calls, but the model must infer recovery from text alone.
- **Desired Behavior:** Each guard class should map to a bounded recovery route: repair schema keys, drop unsupported extras, choose a listed close match, query list/get tools, change identifier source, search for an alternative relation path, escalate to verifier, or stop only under the active terminal policy.
- **Borrowed Pattern:** `harness4` non-acting critic checks; `harness3` budget-aware guard discipline
- **Preserved Behavior:** Keep hard schema preflight and repeated-call blocking.
- **Implementation Shape:** Add a small recovery state object with failure type, failed tool, failed arguments, observation summary, retry count, and recommended next action class. If the same recovery route fails twice, require strategy change or controlled partial-stop policy for stateful tasks only.
- **Generalization Rationale:** Tool schemas across unseen tasks produce recurring error classes even when tool names and domains change.
- **Complexity:** Medium
- **Expected Impact:** Converts `ROUND01_GUARD_BLOCK` from a blocker into useful control flow, reducing repeated failed calls and unsupported guesses.
- **Regression Risk:** A generic router may choose bad fallbacks if it ignores the current ledger; recovery recommendations must reference pending slots.

**[Direction 4: Active Terminal and Format Contract]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Terminal and format contract confusion across benchmark families
- **Current Weakness:** Planning can misclassify short-answer tasks as stateful, and Action prompt text can mention partial completion even when the active toolset does not support `complete_task`.
- **Desired Behavior:** The harness should derive terminal policy from active tools and planning task type, then expose it to Action as a contract: allowed terminal tool, required final format, whether partial completion is allowed, and exact readiness criteria.
- **Borrowed Pattern:** `harness7` route separation between read-only and stateful tasks
- **Preserved Behavior:** Keep answer canonicalization and direct final-answer path for short-answer tasks.
- **Implementation Shape:** At setup, classify the active toolset as read-only QA, multi-hop transform, or stateful mutation. Short-answer tasks may only use `final_answer`. Stateful tasks may use `complete_task` only when the mutation ledger is complete, with explicit partial mode separated from normal completion.
- **Generalization Rationale:** Mixed unseen task families require terminal behavior to follow tool affordances and output contracts, not generic prompt habits.
- **Complexity:** Medium
- **Expected Impact:** Reduces invalid `complete_task` attempts in ToolHop, no-terminal SearchQA cases, and date/name format mismatches.
- **Regression Risk:** Misclassification can block valid terminals; allow correction when the active tool list contradicts the initial plan.

**[Direction 5: Task-Signature Memory and Failure Lessons]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Memory retrieval is broad, long, and not failure-aware
- **Current Weakness:** Retrieval is dominated by shared wrapper text and stores successful procedures only, so unrelated examples consume prompt budget while repeated failure patterns remain unlearned.
- **Desired Behavior:** Memory should retrieve compact procedural notes by benchmark family, active tool family, workflow type, relation/lookup/transform signature, and failure class. It should store short reusable failure lessons for schema errors, invalid relations, not-found loops, repeated guards, and empty actions.
- **Borrowed Pattern:** `harness7` dynamic cheatsheet routing plus `harness6` concise procedural formatting
- **Preserved Behavior:** Keep phase-aware provenance reminders and successful-procedure reuse.
- **Implementation Shape:** Add a task-signature extractor and memory scoring features that downweight benchmark boilerplate. Limit retrieved memories to short, relevant reminders. Store failure lessons as "when failure class appears, recover by..." rather than as trajectory transcripts.
- **Generalization Rationale:** Workflow signatures and failure classes transfer across unseen tasks better than surface prompt overlap.
- **Complexity:** Medium
- **Expected Impact:** Reduces prompt noise and provides targeted recovery hints for repeated schema, relation, and not-found patterns.
- **Regression Risk:** Over-filtering can hide useful generic guidance; always include a small fixed provenance reminder independent of retrieval.

**[Direction 6: Empty-Step and Zero-Token Run Classification]**
- **Target Module:** Builder/Wiring
- **Stage 1 Failure Addressed:** Empty or zero-token execution episodes
- **Current Weakness:** Some failed runs show zero API calls, zero tokens, no plan, and repeated empty action records, which should not be treated as ordinary reasoning failures.
- **Desired Behavior:** The harness should surface run-status metadata for model-call abort, parser-empty output, planning-not-started, and normal reasoning failure. It should retry a parser-empty action once when no mutation has occurred.
- **Borrowed Pattern:** None
- **Preserved Behavior:** Keep bounded execution and avoid unbounded retries.
- **Implementation Shape:** Add lightweight status flags at planning/action boundaries. If an action output is empty after a successful model call, produce a recovery prompt once. If zero tokens or no model call occurs, classify the run as external/model-call abort rather than adapting harness logic around it.
- **Generalization Rationale:** Infrastructure no-op episodes are benchmark-independent and should be separated from transferable harness weaknesses.
- **Complexity:** Low
- **Expected Impact:** Prevents overfitting Stage 3 to external artifacts and may recover simple empty parsed outputs.
- **Regression Risk:** Retrying after a state mutation could duplicate work; retry only when no tool execution or mutation occurred.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The Stage 3 candidate should be a planning-guided, direct single-executor harness with verification-aware commitment. It should feel like the current winner with a sturdier spine: compact plans, one environment actor, hard schema guards, and concise memory, plus an operational evidence/mutation ledger, a non-acting verifier for final readiness, and a bounded recovery router after tool failures. It should not become a heavy multi-agent system.

#### 6.2 Module-Level Blueprint

##### Planning Blueprint

- Implement compact plan packets that explicitly separate read-only evidence slots, multi-hop dependency slots, stateful mutation slots, answer format, terminal tool policy, verification questions, and first safe tool intent.
- For SearchQA, first-tool intent should be `search` with the raw current question; query decomposition is a fallback only after missing or ambiguous first evidence.
- Preserve short planning and periodic adaptation; avoid long deliberative plans and broad role decomposition.
- Ensure ToolHop-style short-answer transformations are not labeled as stateful unless the active toolset contains a real mutation workflow.
- Evidence motivation: Stage 1 shows planning can name evidence needs but does not make them enforceable, causing broken chains and terminal confusion.
- Task-general reason: unseen tasks need small executable plans that identify what must be observed, transformed, mutated, verified, and finally submitted.

##### Action Blueprint

- Implement one acting executor with hard schema preflight, repeated-call blocking, low-value-repeat blocking, and direct tool execution.
- Add a non-acting verifier/critic that runs at bounded checkpoints: before final answer, before `complete_task`, and after repeated guard failures. The verifier checks ledger completeness, answer support, terminal policy, and recovery route quality; it must not call tools or mutate state.
- Add the failure-type recovery router for schema errors, repeated failed calls, low-value repeats, not-found observations, authorization errors, and empty parsed actions.
- Add SearchQA fast-path guards: preserve the raw first query, restore date/title/name surface forms from evidence, and require answer support in one current evidence record rather than loose token overlap.
- Preserve direct read-only multi-call support and local canonicalization; avoid multiple acting agents, broad debate on stateful tasks, and unbounded reflection.
- Evidence motivation: Stage 1 shows guard blocks are useful but insufficient, and final answers can be unsupported even after relevant observations.
- Task-general reason: tool-rich unseen tasks need reliable repair and commitment criteria independent of domain names.

##### Memory Blueprint

- Implement task-signature memory retrieval using active tool family, workflow type, relation/lookup/transform signature, and failure class.
- Keep compact phase-aware reminders about observations versus hypotheses, exact schema keys, deterministic derivation, and terminal discipline.
- Store concise failure lessons for repeated schema errors, invalid relation paths, not-found loops, unsupported finalization, and empty actions.
- For SearchQA, provide only fixed procedural reminders at BEGIN; do not retrieve or store old SearchQA answer/query trajectories because they can leak stale entities and rewritten queries.
- Preserve successful reusable procedures when they match the task signature; avoid long unrelated trajectory excerpts and wrapper-text matching.
- Evidence motivation: Stage 1 shows unrelated memory examples were retrieved for SearchQA and ToolHop and did not help recovery.
- Task-general reason: procedural lessons transfer when keyed by workflow and failure class rather than by entity or prompt boilerplate.

##### Builder / Wiring Blueprint

- Wire planning output into a shared runtime ledger accessible to Action and visible to Memory summaries.
- Add run-status instrumentation for planning-not-started, model-call abort, parser-empty output, normal guard block, and normal terminal completion.
- Preserve the current harness factory file structure and compatibility with `builder.py`, `__init__.py`, `Description.md`, and the provider modules.
- Avoid replacing the benchmark loop, evaluator, dataset, or external services.
- Evidence motivation: Stage 1 found zero-token traces and a weak plan-to-action contract.
- Task-general reason: clean status and shared state prevent the generator from mistaking infrastructure artifacts for reasoning failures.

##### Interface Blueprint

- Implement a simple Planning-to-Action contract: `task_type`, `terminal_policy`, `answer_format`, `evidence_slots`, `dependency_edges`, `required_mutations`, `verification_questions`, and `first_tool_intent`.
- Implement an Action-to-Planning/Memory update summary: completed slots, blocked slots, failed calls, mutation status, candidate answer support, and next safe move.
- Use checklists and short structured notes rather than new orchestration layers.
- Preserve the distinction between observed facts, deterministic derivations, hypotheses, and memory hints.
- Evidence motivation: Stage 1's highest-confidence failures occur at the interface between planned slots and action commitment.
- Task-general reason: every mixed tool environment benefits from knowing what information moved across modules and whether it is complete enough to commit.

#### 6.3 Minimal Required Changes

- Add a runtime evidence/mutation ledger derived from the compact planning packet.
- Gate `final_answer` through an answer support record tied to a relevant observation and requested slot.
- Gate `complete_task` through active tool availability and a complete mutation checklist.
- Add a failure-type recovery router for schema, repeat, low-value-repeat, not-found, authorization, and empty-action cases.
- Add a bounded non-acting verifier before final answer, before completion, and after repeated guard failures.
- Add a SearchQA lightweight fast path: raw-question first search, span-surface preservation, stricter same-record support, and SearchQA memory no-leakage.
- Add task-signature memory retrieval and compact failure lessons.
- Add run-status metadata for zero-token and empty-step classification.

#### 6.4 Optional Enhancements

- Add read-only candidate arbitration when multiple plausible answer spans exist, limited to one verifier pass.
- Add format-specific canonicalizers for dates, names, lists, and numeric deterministic transforms when requested by the plan.
- Add close-match suggestions for invalid enum or relation errors when tool observations expose valid alternatives.
- Add a compact observation compressor that preserves source tool, entity, field, and slot relevance before memory insertion.
- Add a cost budget that triggers verifier review when repeated guards or long context threaten max-step failure.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Keep initial plans compact but make evidence slots, dependency order, required mutations, answer format, and terminal policy explicit.
- [Planning] Do not classify short-answer ToolHop transformations as stateful workflows unless the active toolset proves a state-changing terminal path exists.
- [Planning] Include verification questions that can be checked from observations, not vague self-reflection prompts.
- [Planning] For SearchQA, preserve the current question wording for the first search and only decompose after ambiguous or missing evidence.
- [Action] Keep a single acting executor as the only component allowed to call tools or mutate state.
- [Action] Preserve hard schema preflight, repeated-call blocking, and low-value-repeat blocking.
- [Action] Pair every guard block with a recovery route or controlled stop condition keyed to the current ledger.
- [Action] Require a support record before `final_answer`: candidate, source observation/tool, relevant slot, copied-or-derived status, and contradiction check.
- [Action] For SearchQA, make support stricter than generic token overlap: answer surface or all answer tokens must appear in one current evidence record.
- [Action] Allow read-only candidate arbitration only when it is bounded and does not introduce tool-acting parallel agents.
- [Action] Permit `complete_task` only when it exists in the active toolset and the mutation ledger is complete, except for an explicit stateful partial mode.
- [Action] Canonicalize final answers according to the active answer-format contract without adding unsupported prose.
- [Action] For SearchQA, do not canonicalize evidence dates into ISO form unless explicitly requested; return the evidence surface form.
- [Memory] Retrieve memories by task workflow, tool family, and failure class rather than shared benchmark wrapper text.
- [Memory] Store compact reusable failure lessons for schema errors, invalid relations, not-found loops, repeated guard blocks, unsupported finalization, and empty actions.
- [Memory] Keep fixed provenance reminders concise and separate from retrieved memories.
- [Memory] For SearchQA, suppress retrieval and ingestion of old answer/query traces; retain only fixed procedural guidance.
- [Builder] Surface run-status metadata for model-call abort, planning-not-started, parser-empty output, guard block, and normal terminal completion.
- [Builder] Preserve harness factory compatibility and the existing module file boundaries.
- [Interface] Convert the plan packet into an Action-updated evidence/mutation ledger; prompt text alone is insufficient.
- [Interface] Share terminal policy and final-answer criteria across Planning and Action before any terminal call.
- [Interface] Feed Action observations back into short ledger summaries for adaptation and memory, without adding a heavy orchestration layer.
- [Preserve] Preserve direct read-only multi-call support for independent evidence gathering.
- [Preserve] Preserve the winner's compact planning, single-executor execution, schema guards, provenance reminders, and answer canonicalization.
- [Avoid] Do not replace the benchmark loop, evaluator, dataset, or model, and do not add external services or neural retraining.
- [Avoid] Do not copy a whole peer harness; borrow only module-level patterns that address Stage 1 failures.
- [Avoid] Do not add heavy multi-agent orchestration, multiple acting agents, broad debate on stateful tasks, or broad fusion memory exposure.
- [Avoid] Do not hard-code benchmark item ids, entities, answers, tool traces, relation names, meeting ids, or golden values.
- [Avoid] Do not optimize for done proxy by allowing shallow completion without verified evidence or mutation completeness.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
