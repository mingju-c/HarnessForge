### PART 1: LOCALIZATION SUMMARY

The current winner is `harness_round01_6` for `qwen3-8B-round01-harness6` in `round02_01`. Its architecture is a conservative, answer-focused single-ReAct harness: `builder.py` constructs one `ToolCallingAgent`, injects `round01_canonical_planning` into the action context, runs `round01_canonical_react`, preserves a guarded task-tool wrapper, exposes an optional `canonicalize_answer` helper, and uses lightweight `round01_canonical_memory` reminders. The harness's main strength is a low-overhead direct executor with strong answer-type and exact-observation discipline relative to other round01 candidates.

Stage 1 attributes the dominant failures to missing durable execution state and weak runtime control, not to the evaluator, dataset, model, or benchmark loop. The highest-impact failure is stateful subtask ledger collapse in EnvScaler: the agent often performs some correct mutations, then loses which object, incident, folder, or subtask the next operation belongs to and calls `complete_task` before the whole state is correct. The second major failure is that soft failure advisories do not become repair control: repeated invalid calls, wrong IDs, schema errors, and precondition errors continue after the harness already has evidence that a different strategy is required. SearchQA failures are dominated by distractor and near-match arbitration errors, where a gold answer or decisive evidence appears in observations but the final answer comes from a nearby entity, wrong title, or partial predicate. ToolHop failures show multi-hop slot binding collapse before transformations, such as extracting from a father when the task asked for a paternal grandfather. Final-answer canonicalization remains only partially effective: correct raw observations are sometimes rewritten into non-raw dates, sentences, padded binary strings, or over-specific aliases. A smaller but still important failure class is unsupported impossibility and empty-action termination.

The Stage 1 module attribution is clear. Cross-Module Interface owns the missing stateful ledger and typed slot contract because Planning emits only conversational status while Action must update task state from observations. Action owns runtime repair control, evidence arbitration, final-answer binding, empty-action recovery, and terminal submission. Planning contributes by under-specifying evidence chains, transformation prerequisites, and final-readiness questions. Memory is mostly safe and non-distracting, but too generic to reinforce the most recurrent repair and canonicalization procedures. Builder/Wiring should mainly preserve factory compatibility while supporting simple status handoff.

The generalized capability gaps are: durable progress-state management for mutable multi-operation tasks; action-side error arbitration and precondition repair; candidate evidence arbitration under distractors; typed intermediate-state binding for multi-hop reasoning; mandatory final observation binding for machine-graded answers; and hard non-empty/terminal contract discipline. The highest-leverage repair targets are a compact updateable ledger, a mandatory but bounded repair branch after repeated failures, evidence and slot arbitration before transformations or final answers, and a final answer gate that copies decisive raw fields exactly. The next harness must preserve the winner's direct single-executor topology, compact planning, strict schema prompting, useful guard signals, phase-safe memory, factory wiring, low coordination overhead, and the ability to solve simple one-hop tasks without heavy verifier cost.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round01_5`

- **Observed Structure:** Direct single executor with `round01_commit_planning`, `round01_commit_react`, and phase-aware commit memory. It builds a `COMMIT_LEDGER`, emphasizes sequential state-changing calls, read-after-write reminders, and optional terminal preflight.
- **Relevant Strength:** It is the best fair-first200 SearchQA scorer among round01 candidates and has strong EnvScaler score/done metrics. Its sequential commit discipline directly addresses partial state mutation and premature completion.
- **Relevant Weakness / Risk:** Full-run stability drops behind `harness_round01_6`; ToolHop correctness is only moderate; cost and max-step rate remain high. Its commit focus alone does not solve multi-hop typed-slot transformations.
- **Related Winner Failure:** Stateful subtask ledger collapse, final completion with incomplete environment state, and SearchQA evidence selection trailing the best peer.
- **Transferable Module Pattern:** Borrow the compact commit ledger and read-after-write completion discipline: each required mutation should be closed only by a successful observation, and terminal completion should review unresolved ledger rows.
- **Generalization Rationale:** Sequential observed commits are domain-agnostic for calendars, files, incidents, records, messaging, and any mutable API environment where intended writes are not facts until the tool confirms them.
- **Do Not Borrow:** Do not copy the whole harness or add costly preflight calls on every step; avoid weakening the winner's lower-cost canonical answer path.
- **Transfer Confidence:** High

#### Example: `harness_round01_8`

- **Observed Structure:** Direct single executor with `round01_status_packet_planning`, `round01_status_packet_react`, and status-packet memory. It keeps `planned_or_pending`, `observed_success`, `observed_failure`, `remaining`, `next step`, and `final criteria` separated.
- **Relevant Strength:** It is the best ToolHop specialist in the pool, with the strongest fair-first200 ToolHop correctness and path score among round01 candidates. Its status packet cleanly separates intent from observed facts.
- **Relevant Weakness / Risk:** It is weaker than the winner on fair-slice EnvScaler and SearchQA, has a higher max-step rate among selected top-4 candidates, and is more expensive. The status checker must remain rare and decisive.
- **Related Winner Failure:** Multi-hop slot binding breaks before transformations; planning state is not enforced as an updateable contract; Action treats the plan as conversational context rather than durable state.
- **Transferable Module Pattern:** Borrow the observed-vs-pending status packet and adapt it into typed slots for relationship chains, raw values, transformed values, and terminal criteria.
- **Generalization Rationale:** Any compositional task needs to know which intermediate values are observed, failed, pending, or transformed; this applies across genealogy, films, dates, arithmetic, strings, search, and APIs.
- **Do Not Borrow:** Do not borrow extra cost, frequent status checks, or any behavior that slows obvious direct answers.
- **Transfer Confidence:** High

#### Example: `harness_round01_3`

- **Observed Structure:** Direct single executor with `round01_repair_planning`, `round01_repair_react`, and phase-aware repair memory. It classifies failed calls as unknown tool, schema mismatch, missing entity, empty output, execution error, or contradiction, then prefers changed arguments or alternate tools.
- **Relevant Strength:** It demonstrates the exact repair vocabulary needed for the winner's repeated-failure bucket: failed calls must be interpreted as precondition, schema, ID, authorization, or empty-result signals rather than retried blindly.
- **Relevant Weakness / Risk:** Its measured mixed score is weaker, ToolHop correctness is poor, max-step rate is high, and repair can be too costly if invoked late or too often.
- **Related Winner Failure:** Soft failure advisories do not become repair control; repeated failures continue after known wrong IDs, wrong parent values, unauthorized calls, and tool exceptions.
- **Transferable Module Pattern:** Borrow failure classification and mandatory strategy-change prompts after repeated identical failures, but keep the controller bounded and compatible with the winner's single executor.
- **Generalization Rationale:** Tool schemas and runtime errors vary by task family, but the need to classify not-found, bad-ID, bad-schema, unauthorized, and contradiction errors is reusable across all tool-use environments.
- **Do Not Borrow:** Do not borrow the full repair-heavy architecture, high-cost looping, or any hard block that prevents a valid retry after a new observation changes the precondition.
- **Transfer Confidence:** High for the repair pattern; Medium for measured transfer without adaptation

#### Example: `harness_round01_2`

- **Observed Structure:** QA-oriented single executor with `round01_evidence_chain_planning`, `round01_evidence_chain_react`, and evidence memory. It builds an `EVIDENCE_CHAIN` contract with target answer type, pending evidence, observed evidence, remaining hops, and final criteria.
- **Relevant Strength:** It is a stable full-run candidate with reliable search use and stronger SearchQA subEM than the winner on the fair-first200 slice. It demonstrates observation-tied answer candidates and support checks.
- **Relevant Weakness / Risk:** It does not improve ToolHop over the winner and still reaches max steps on a meaningful fraction of aligned tasks. Evidence arbitration alone will not repair stateful workflow failures.
- **Related Winner Failure:** Retrieval evidence arbitration fails on distractors and near matches; final answers are sometimes based on adjacent snippets rather than the requested entity, predicate, title, and answer type.
- **Transferable Module Pattern:** Borrow target-answer-type slots, candidate-support checks, and limited observe-arbitrate behavior for ambiguous retrieval candidates.
- **Generalization Rationale:** Distractor-rich retrieval is domain-independent; candidate answers should be checked against target entity, predicate, document/title context, answer type, and contradiction cues before finalization.
- **Do Not Borrow:** Do not convert all tasks into QA arbitration; avoid extra arbitration when a structured tool result already decisively answers a non-retrieval task.
- **Transfer Confidence:** High

#### Example: `harness_round01_1`

- **Observed Structure:** Direct single executor with an observation-grounded work ledger, soft schema/retry guidance, and lightweight preflight critic. Its plan is an `OBSERVED_LEDGER` with target, pending items, observed evidence, remaining work, and final criteria.
- **Relevant Strength:** The observation ledger improves ToolHop relative to base behavior and reinforces the principle that planned calls are not facts before successful observations.
- **Relevant Weakness / Risk:** It is below the winner on overall mixed score, weak on SearchQA, expensive, and still has non-trivial max-step failures.
- **Related Winner Failure:** Missing durable progress-state management and weak separation between intended work, observed success, observed failure, and remaining requirements.
- **Transferable Module Pattern:** Borrow the ledger semantics, not the full implementation: planned work remains pending; only observations close rows; failures stay visible until repaired or declared impossible with evidence.
- **Generalization Rationale:** This state separation is reusable for multi-hop QA, read-after-write API tasks, and any workflow where a later step depends on a verified earlier result.
- **Do Not Borrow:** Do not borrow high prompt cost, weak SearchQA handling, or advisory checks that do not change later decisions.
- **Transfer Confidence:** Medium

#### Example: `harness4`

- **Observed Structure:** Light reflection harness with short planning, one acting executor, a non-acting critic, and workflow memory. The critic checks tool existence, argument plausibility, repeated failures, and stopping readiness without acting in the environment.
- **Relevant Strength:** The non-acting critic is architecturally clean: it can review readiness and repair needs without corrupting mutable state or creating parallel actors. The seed has good speed-quality balance and reliable SearchQA tool use.
- **Relevant Weakness / Risk:** EnvScaler still trails stronger direct candidates and max-step failures remain. A critic that only restates the transcript without enforcing a decision is not enough.
- **Related Winner Failure:** Missing final gate, weak repeated-failure escalation, unsupported impossibility, and completion before all stateful requirements are satisfied.
- **Transferable Module Pattern:** Borrow a lightweight non-acting verifier/checklist used only at uncertainty points: before terminal completion, after repeated failures, or before finalizing an ambiguous candidate.
- **Generalization Rationale:** A non-acting verifier can inspect evidence, slots, and unresolved work across task families while preserving single-executor state discipline.
- **Do Not Borrow:** Do not borrow frequent reflection, broad second-agent reasoning, or any verifier that becomes another acting executor.
- **Transfer Confidence:** Medium

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style harness with broader orchestration, multiple role-like components, and Cerebra fusion memory.
- **Relevant Strength:** It shows that explicit subtask tracking and synthesis after resolved work can improve coverage in principle.
- **Relevant Weakness / Risk:** It is the highest-cost seed, has the highest max-step rate among active candidates, and the pool explicitly marks its orchestration as too heavy for `Qwen3-8B`.
- **Related Winner Failure:** Conceptually related to missing task ledger and plan/action synchronization, but the implementation is too costly for direct transfer.
- **Transferable Module Pattern:** Use only as a negative-control reminder: borrow the idea of tracked work items if needed, compressed into the winner's single-executor ledger.
- **Generalization Rationale:** Tracking unresolved work is general, but heavy role orchestration is not necessary to get that benefit and may reduce robustness on unseen tasks.
- **Do Not Borrow:** Do not borrow the whole hierarchy, broad multi-agent coordination, rich fusion memory, high token exposure, or extra acting roles.
- **Transfer Confidence:** Low as an architecture; Medium as a conceptual source for minimal work-item tracking

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Cross-Module Interface | EnvScaler partial mutations, wrong-object binding, and terminal completion before full state correctness | Missing updateable execution ledger connecting planned work to observed success/failure | `harness_round01_5`, `harness_round01_1`, selective `harness5` concept | Compact work/commit ledger where rows close only from successful observations and terminal completion reviews unresolved rows | Mutable multi-operation workflows in unseen tasks require durable object IDs, dependencies, status, and remaining work | Avoid full AgentOrchestra hierarchy from `harness5`; avoid verbose ledger bloat | High | Medium |
| Action | Repeated invalid tool calls continue after guard advisories and tool exceptions | Missing mandatory tool-error arbitration and precondition-repair protocol | `harness_round01_3`, `harness4` | Classify error type, require changed argument/tool/strategy after repeated identical failures, and allow retry only after changed preconditions | Not-found, bad-ID, authorization, schema, and execution errors recur across tool APIs | Avoid high-cost repair loops and hard permanent failed-call quarantine from `harness_round01_3` | High | Medium |
| Action | No hard terminal gate or runtime reviewer when evidence is ambiguous, failures repeat, or ledger rows remain | Missing lightweight non-acting verification without changing execution topology | `harness4` | Use a non-acting checklist/verifier only before terminal completion, after repeated failures, or during answer ambiguity | A verifier that cannot mutate state can improve readiness decisions across task families while preserving the single executor | Avoid heavy multi-agent orchestration, frequent reflection, and acting critics from `harness5`-style designs | Medium | Low |
| Action | SearchQA finalizes distractor snippets, nearby entities, wrong titles, or partial predicates | Missing retrieval candidate arbitration before final answer | `harness_round01_2`, `harness_round01_5` | Target-answer-type and support checks: entity/title match, predicate match, answer type, contradiction, and distractor rejection | Retrieval tasks across domains contain adjacent plausible snippets and require answer support, not plausibility | Avoid applying QA arbitration to clear stateful tool results or over-searching simple questions | High | Low |
| Cross-Module Interface | ToolHop transforms wrong intermediate values or placeholders | Missing typed intermediate-state binding and prerequisite checks | `harness_round01_8`, `harness_round01_2` | Status packet with task-derived slots such as source entity, relation result, raw value, transformed value, and final criteria | Relationship traversal plus transformation is a reusable task pattern across genealogy, film, date, string, and arithmetic tasks | Avoid fixed benchmark-specific slot names and frequent status checks | High | Medium |
| Action | Correct raw observations are rewritten into wrong final forms | Missing mandatory final observation binding and exact raw-field copying | Winner pattern plus `harness_round01_5` commit preflight and `harness4` verifier | Mandatory final gate that binds candidate answer to decisive observation and copies structured fields exactly unless task asks otherwise | Machine-graded tasks in many domains require exact dates, numbers, names, IDs, binary strings, and short raw values | Avoid over-normalization or sentence generation when a raw field is available | High | Low |
| Memory | Memory reminders are safe but too generic to prevent repeated failures, ID drift, or canonicalization errors | Missing compact phase-aware procedural reminders triggered by current trajectory risk | `harness_round01_8`, `harness_round01_3`, winner memory pattern | Add short IN-phase reminders for repeated failure, observed-ID mismatch, unresolved ledger rows, and final raw-field copying | Procedural reminders transfer without storing benchmark facts or contaminating current observations | Avoid verbose memory, task-specific answer storage, and broad likely-answer hints | Medium | Low |
| Planning | Plans name high-level work but do not control evidence chains, typed slots, or final readiness | Missing task decomposition into evidence targets, slot prerequisites, verification questions, and commit criteria | `harness_round01_2`, `harness_round01_8` | Compact target/evidence/slot/final-check plan passed to Action as an updateable contract | Unseen multi-step tasks need dependency order and target criteria before execution | Avoid verbose free-form planning or planned calls that look like completed observations | High | Low |
| Builder/Wiring | The harness has no hard verifier, ledger handoff, or metadata alignment for round02 context | Missing simple wiring for shared status without changing factory structure | None; repair within winner pattern | Preserve existing provider files and `PlanningClass` injection; add only lightweight context/status configuration | Factory-compatible status handoff is reusable and does not alter benchmark semantics | Avoid changing dataset, evaluator, benchmark loop, external services, or neural retraining | High | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve the single primary ReAct executor in Action because it keeps dependency continuity and avoids costly handoff noise on simple and medium tasks.
- Preserve the winner's canonical answer discipline in Action because exact observation binding is already a comparative strength and should become mandatory rather than discarded.
- Preserve closed-set schema prompting and guarded task-tool wrapping in Action because these signals already expose invalid calls and repeated-failure advisories.
- Preserve compact `CANONICAL_TARGET` planning in Planning because it gives target answer type and final criteria without heavy coordinator overhead.
- Preserve phase-safe procedural memory in Memory because it avoids storing planned actions or task-specific answers as durable facts.
- Preserve direct terminal-tool habits in Action because SearchQA already consistently calls `final_answer`; the repair should improve correctness and formatting, not remove terminal discipline.
- Preserve Builder/Wiring compatibility with `builder.py`, `ActionContext`, provider modules, factory tool binding, and the local harness structure because Stage 3 must remain factory-compatible.

#### Borrow

- Borrow from `harness_round01_5` into Cross-Module Interface and Action: compact commit ledger plus read-after-write verification; expected benefit is fewer partial EnvScaler completions and wrong-object mutations; it should generalize because mutable API tasks require observed commit state.
- Borrow from `harness_round01_8` into Planning and Cross-Module Interface: status-packet separation of pending intent, observed success, observed failure, remaining work, next step, and final criteria; expected benefit is stronger ToolHop slot tracking; it should generalize because compositional tasks need typed intermediate state.
- Borrow from `harness_round01_3` into Action: failure classification and strategy-change protocol after repeated failed calls; expected benefit is fewer low-value retries and better recovery from schema, ID, authorization, and precondition errors; it should generalize across tool APIs.
- Borrow from `harness_round01_2` into Action and Planning: evidence-chain target typing and candidate support checks; expected benefit is fewer SearchQA distractor answers; it should generalize because retrieval domains often contain adjacent plausible candidates.
- Borrow from `harness4` into Action: a non-acting verifier used only before terminal completion, after repeated failures, or under candidate ambiguity; expected benefit is stronger readiness checks without mutating state; it should generalize because checking evidence and unresolved work is task-general.
- Borrow from `harness_round01_1` into Memory and Interface only as a lightweight principle: planned work stays pending until observations close it; expected benefit is reduced plan-as-fact drift; it should generalize to both mutable workflows and multi-hop lookup tasks.

#### Avoid

- Avoid copying `harness5` whole-architecture orchestration because it is expensive, high max-step, and too heavy for `Qwen3-8B`; it should not enter Stage 3 as a complexity and efficiency risk.
- Avoid frequent or mandatory critic calls from any reflection harness because the winner's cost-quality advantage depends on direct execution; this is a complexity and regression risk.
- Avoid hard permanent failed-call blocking from repair-oriented examples because a repeated call can become valid after a successful precondition-changing observation; this is a correctness regression risk.
- Avoid early-stop budget discipline from low-cost harnesses when unresolved ledger items remain because cheap termination can raise done-like behavior while lowering exact success; this is a regression risk.
- Avoid applying retrieval debate or multi-candidate arbitration to state-changing tasks because parallel or speculative acting can corrupt mutable environments; this is a weak-transfer and correctness risk.
- Avoid storing task-specific entities, IDs, answers, or observed golden-like values in memory because the improvement must transfer to unseen tasks; this is an overfitting risk.
- Avoid benchmark-specific patches for `1005.json`, `1059.json`, `460.json`, `1016.json`, `1027.json`, `900.json`, folder names, historical figures, or answer strings because Stage 3 must implement module behavior, not memorized traces; this is an irrelevance and overfitting risk.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Observation-Grounded Execution Ledger]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Stateful subtask ledger collapse under multi-operation environments
- **Current Weakness:** Planning emits a textual status contract, but Action does not maintain durable rows for requested operations, target objects, observed IDs, success/failure, dependencies, and remaining work.
- **Desired Behavior:** The new harness should maintain a compact task-derived ledger for stateful and multi-step tasks. Each row should track the required operation or evidence target, target entity, observed identifier/value, status, dependency, and terminal-readiness contribution. Rows may close only from successful observations, not from intended tool calls.
- **Borrowed Pattern:** `harness_round01_5` commit ledger and read-after-write discipline, with the observation-grounded semantics of `harness_round01_1`; use `harness5` only as a negative-control reminder to keep tracking minimal.
- **Preserved Behavior:** Preserve the winner's single executor, compact planning, and direct completion path for simple tasks with no unresolved ledger rows.
- **Implementation Shape:** Planning should emit a short initial ledger skeleton when the task contains multiple targets, mutations, or dependent hops. Action should update the ledger from observations after each relevant tool call, cite unresolved rows before further action, and require a ledger review before `complete_task` or a multi-step `final_answer`.
- **Generalization Rationale:** Multi-object workflows, scheduling, file operations, CRM-like APIs, incident dispatch, and stateful environments all require observed progress accounting independent of benchmark labels.
- **Complexity:** Medium
- **Expected Impact:** Highest expected gain on EnvScaler full-score completion and reduced wrong-object mutations, while also helping ToolHop dependency tracking.
- **Regression Risk:** A verbose ledger could distract the executor or slow one-hop tasks; Stage 3 should keep it compact and activate it only when task structure warrants it.

**[Direction 2: Mandatory Bounded Repair Control After Tool Failures]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Soft failure advisories do not become repair control
- **Current Weakness:** Guard warnings and tool exceptions remain textual observations; the agent can repeat the same bad call, wrong ID, wrong parent value, or malformed argument without a required strategy change.
- **Desired Behavior:** The action loop should classify failures, preserve a short failed-call history, and require a different argument, different valid tool, new precondition-changing observation, or explicit impossibility rationale before repeating an identical failed call.
- **Borrowed Pattern:** `harness_round01_3` failure classification and repair vocabulary plus `harness4` non-acting check at uncertainty points.
- **Preserved Behavior:** Preserve the existing guard wrapper, schema discipline, and ability to retry the same real tool after a meaningful state or evidence change.
- **Implementation Shape:** Add an action-side repair protocol that recognizes schema mismatch, unknown tool, bad ID, missing entity, unauthorized/precondition failure, empty result, contradiction, and execution exception. On repeated exact failure, the next step must explain the changed precondition or choose a changed strategy before continuing. Empty action outputs should be treated as contract violations requiring a tool call, final tool, or explicit impossible-with-evidence branch.
- **Generalization Rationale:** API and tool environments commonly fail through invalid IDs, wrong formats, missing permissions, unavailable entities, and empty results; a reusable repair controller improves unseen tool families without knowing their content.
- **Complexity:** Medium
- **Expected Impact:** Fewer repeated-failure loops in EnvScaler and ToolHop, fewer max-step cases, and more recovery from repairable tool errors.
- **Regression Risk:** Overly hard blocking can prevent valid retries after state changes or polling-like tasks; the controller must reset or soften duplicate warnings after successful observations that alter preconditions.

**[Direction 3: Retrieval Evidence Arbitration Before Final Answer]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Retrieval evidence arbitration fails on distractors and near matches
- **Current Weakness:** The executor can answer from a nearby snippet, wrong title, related entity, plausible prior, or partial predicate even when the correct answer appears elsewhere in observations.
- **Desired Behavior:** Before finalizing retrieval QA, the harness should compare candidate answers against the requested entity, title/document context, predicate/relation, answer type, contradiction cues, and distractor proximity. If the top candidate fails a target check, Action should search again or inspect a more specific result rather than finalize.
- **Borrowed Pattern:** `harness_round01_2` evidence-chain target typing and candidate support checks; `harness_round01_5` SearchQA evidence discipline as a performance-backed reference.
- **Preserved Behavior:** Preserve the winner's direct search use and concise final-answer habit when one candidate is decisively supported.
- **Implementation Shape:** Add a lightweight finalization checklist inside the Action prompt or optional checker: candidate, supporting observation, target match, predicate match, answer-type match, rejected distractor, exact output. Use it only for retrieval-like or ambiguous observation sets.
- **Generalization Rationale:** Unseen retrieval tasks routinely contain adjacent entities, ambiguous snippets, and near-matching document titles; answer support checks are domain-agnostic.
- **Complexity:** Low
- **Expected Impact:** Better SearchQA answer correctness and fewer cases where gold evidence exists in observations but finalization selects the wrong candidate.
- **Regression Risk:** Excessive arbitration could waste calls on simple one-hop questions; the checklist should be short and should allow immediate finalization when evidence is unambiguous.

**[Direction 4: Typed Slot Binding For Multi-Hop Transformations]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Multi-hop slot binding breaks before transformations
- **Current Weakness:** Planning names high-level steps, but Action does not preserve typed slots such as source entity, relation result, target entity, raw value, and transformed answer, so it can transform the wrong intermediate value or a placeholder phrase.
- **Desired Behavior:** The new harness should create task-derived typed slots for multi-hop tasks and require prerequisite slots to be observed before downstream extraction, arithmetic, date, string, or formatting transformations.
- **Borrowed Pattern:** `harness_round01_8` status packet and `harness_round01_2` evidence chain.
- **Preserved Behavior:** Preserve flexible task-derived labels and the winner's canonical answer type tracking; do not impose benchmark-specific slot names.
- **Implementation Shape:** Planning should expose a compact slot chain only when the task has relation traversal or transformations. Action should update slots from observations, mark failed slots, refuse transformation over placeholders or unresolved descriptions, and verify that the final transformed value derives from the intended observed slot.
- **Generalization Rationale:** Relationship traversal plus transformation occurs across people, organizations, films, dates, strings, counts, arithmetic, and structured APIs; typed slots keep dependencies explicit without knowing the domain.
- **Complexity:** Medium
- **Expected Impact:** Higher ToolHop correctness and fewer early wrong extractions from partial relation chains.
- **Regression Risk:** Rigid slot templates may underfit unusual tasks; Stage 3 should derive slot names from the task wording and keep the representation concise.

**[Direction 5: Mandatory Final Observation Binding And Raw-Value Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Final-answer canonicalization rewrites correct observations
- **Current Weakness:** `canonicalize_answer` is optional and model-mediated; the agent sometimes observes the exact raw value but submits a sentence, reformatted date, padded binary string, alias, or over-specific answer.
- **Desired Behavior:** Before any short-answer `final_answer`, Action should bind the candidate to the decisive observation and copy the exact structured field or raw value when available, unless the task explicitly requests a different format or transformation.
- **Borrowed Pattern:** None; strengthen the winner's own canonical answer pattern, with `harness4` verifier style only for ambiguous or multi-step traces.
- **Preserved Behavior:** Preserve `harness_round01_6`'s answer-focused personality and target-type planning; make its existing intended discipline reliable.
- **Implementation Shape:** Add a final gate that extracts the decisive `result`, `answer`, `value`, `date`, count, binary/string field, name, list, or status field from the latest supporting observation. The gate should reject explanatory sentences for raw-value tasks and should run before terminal submission, not merely as an optional helper the model may skip.
- **Generalization Rationale:** Exact formatting matters across dates, numbers, IDs, names, binary strings, lists, and structured tool results in unseen machine-graded tasks.
- **Complexity:** Low
- **Expected Impact:** Narrows the gap between observed subanswer/evidence and answer correctness in SearchQA and ToolHop, with minimal architectural risk.
- **Regression Risk:** Exact copying can preserve a wrong intermediate if evidence arbitration or slot binding failed; the gate must depend on the decisive validated observation, not the most recent arbitrary value.

**[Direction 6: Compact Phase-Aware Memory For Repair And Canonicalization]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Memory guidance is safe but too generic to prevent repeated failures, relation-chain drift, or final-answer rewrites
- **Current Weakness:** Memory reminds the agent to track answer type and copy observed values, but it does not adapt strongly enough to repeated failed calls, observed ID mismatches, unresolved ledger rows, placeholder slots, or raw-field finalization risk.
- **Desired Behavior:** Memory should emit short procedural reminders keyed to the current phase and risk pattern, while never storing task-specific answers, entity IDs, or planned actions as facts.
- **Borrowed Pattern:** `harness_round01_8` pending-vs-observed memory discipline and `harness_round01_3` repair-oriented reminders, adapted into the winner's lightweight memory style.
- **Preserved Behavior:** Preserve phase-safe memory, no trajectory-fact persistence, and compact reminders.
- **Implementation Shape:** BEGIN guidance should remind the executor to maintain ledger/slots and final raw-answer criteria. IN guidance should trigger only on repeated failure, unresolved ledger entries, observed ID not used in a later call, placeholder transformation risk, or a structured raw result available for final answer. Keep each reminder procedural and no longer than a few lines.
- **Generalization Rationale:** These are reusable execution lessons rather than benchmark facts, so they can transfer to unseen tools and domains without contamination.
- **Complexity:** Low
- **Expected Impact:** Better adherence to the new repair, slot, and final-answer controls with small token overhead.
- **Regression Risk:** Too many reminders can become prompt noise; triggers should be sparse and tied to visible trajectory evidence.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The Stage 3 candidate should be a direct but state-aware canonical executor: one acting agent, compact planning, observation-grounded ledger/slot state, bounded tool-error repair, lightweight evidence arbitration, and mandatory raw-value final binding. It should feel like a disciplined single operator with a small checklist, not a committee. The winner's answer-focused style should remain visible, but it should now treat observations, failed calls, unresolved subtasks, and final criteria as enforceable state rather than soft reminders.

#### 6.2 Module-Level Blueprint

##### Planning Blueprint

Implement compact task-derived planning that emits `target`, `answer_or_state_type`, `planned_or_pending`, `evidence_or_operation_slots`, `remaining`, and `final_criteria`. For stateful tasks, planning should initialize ledger rows for required mutations or verifications. For multi-hop tasks, it should initialize typed slots and prerequisite order. For retrieval tasks, it should state the entity/predicate/title/answer-type checks needed before finalization. Preserve the winner's concise `CANONICAL_TARGET` behavior and avoid verbose chain-of-thought-like plans. Avoid planned tool calls that look like completed observations. Stage 1 evidence from EnvScaler, ToolHop, and SearchQA motivates this because the existing plan is useful but not enforceable. The design is task-general because it represents dependencies, slots, and final criteria without encoding benchmark-specific names or answers.

##### Action Blueprint

Implement one primary acting executor with four lightweight controls. First, maintain a visible ledger/slot note updated only from observations. Second, add mandatory bounded repair after repeated or classified tool failures. Third, add retrieval evidence arbitration before SearchQA-like final answers. Fourth, add mandatory final observation binding and raw-value copying before terminal submission. Preserve strict JSON, closed-set tool schema use, the existing guard wrapper, direct tool calls, and low-overhead simple-task execution. Avoid heavy multi-agent orchestration, parallel acting on mutable tasks, permanent failed-call locks, and mandatory verifier calls on every step. Stage 1 evidence shows repeated failed calls, wrong-object mutations, distractor answers, placeholder transformations, and raw-value rewrites. The design is task-general because it operates on tool errors, observations, slots, and answer types rather than task IDs or memorized answers.

##### Memory Blueprint

Implement compact phase-aware memory that supports the new ledger, repair, slot, and final-answer disciplines. BEGIN guidance should be a short procedural reminder about observed-vs-pending state, target answer type, and raw final copying. IN guidance should be sparse and triggered by current trajectory risks: repeated failure, observed ID mismatch, unresolved ledger rows, placeholder slot use, empty action, or structured final value availability. Preserve the winner's no-contamination policy and do not persist task-specific entities, IDs, or answers. Avoid verbose memory, likely-answer suggestions, and stale prior facts. Stage 1 evidence shows memory is not the primary failure source but is too weakly routed to reinforce repair behavior. The design is task-general because it stores procedures and phase cues, not benchmark content.

##### Builder / Wiring Blueprint

Preserve the local harness structure: `builder.py`, `__init__.py`, `Description.md`, and the three provider modules. Keep the single `ToolCallingAgent`, factory tool binding, `PlanningClass` injection, action context flow, and benchmark compatibility. Add only lightweight configuration needed for ledger/slot summaries, repair thresholds, and optional checker availability. Fix metadata if needed so the candidate identity and round are consistent with round02 generation, but do not change the benchmark loop, evaluator, dataset, model backend, or external services. Stage 1 shows Builder/Wiring is mostly sound; the needed changes are status handoff and control hooks. The design is task-general because it preserves factory interfaces while making module contracts clearer.

##### Interface Blueprint

Implement a simple Planning-to-Action-to-Memory status contract. It should separate `planned_or_pending`, `observed_success`, `observed_failure`, `slots_or_ledger`, `remaining`, and `final_criteria`. Action observations should update this status before transformations and terminal completion. Memory should read the status as guidance but must not overwrite observed truth. Preserve text/JSON-compatible notes rather than adding a new orchestration layer. Avoid any interface that requires external state stores, new benchmark APIs, or task-specific parsers. Stage 1 identifies Cross-Module Interface as the owner of ledger collapse and slot binding failures. The design is task-general because all multi-step tasks benefit from distinguishing intended work from observed completion.

#### 6.3 Minimal Required Changes

- Add a compact updateable ledger/status contract that separates pending work, observed success, observed failure, remaining work, and final criteria.
- Add task-derived typed slots for multi-hop transformation tasks, with prerequisite checks before extraction, arithmetic, date, string, or final transformations.
- Add mandatory bounded repair control for repeated exact failed calls, schema errors, bad IDs, missing entities, authorization/precondition failures, empty results, and empty action outputs.
- Add retrieval evidence arbitration before final answers when observations contain multiple plausible candidates or near matches.
- Make final observation binding mandatory for short answers: copy decisive raw structured fields exactly unless the task explicitly asks for a transformation.
- Add sparse phase-aware memory reminders for repeated failure, unresolved ledger rows, observed-ID mismatch, placeholder-slot risk, and raw final-value availability.
- Preserve factory compatibility, single acting executor, existing guard signals, and direct low-cost execution for simple tasks.

#### 6.4 Optional Enhancements

- Add a non-acting verifier/checklist only before terminal completion, after repeated failures, or when retrieval candidates conflict.
- Add a small mutability heuristic so state-changing tools default to sequential read-after-write execution while independent read-only lookups can remain efficient.
- Add compact call-history summaries that keep failed-call signatures and successful precondition-changing observations visible without growing the prompt.
- Add answer-type-specific final checks for dates, numbers, binary strings, names, lists, IDs, and raw text values.
- Add a low-cost budget advisory that forces strategy review before max-step exhaustion but does not terminate unresolved tasks prematurely.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Preserve concise canonical target planning, but include task-derived ledger rows or typed slots when the task has multiple operations, mutable state, relation chains, or transformations.
- [Planning] Include final-readiness criteria that distinguish observed success from attempted or planned work.
- [Planning] For retrieval tasks, state the requested entity, predicate, context/title cue if present, and answer type needed for candidate arbitration.
- [Planning] For ToolHop-like tasks, expose prerequisite slots before downstream transformation tools may be used.
- [Action] Keep one primary acting executor; any verifier/checker must be non-acting and used only at uncertainty, repeated-failure, or terminal-readiness points.
- [Action] Update ledger rows and typed slots only from successful observations, never from planned calls or memory hints.
- [Action] Before `complete_task`, require all stateful ledger rows to be observed complete or explicitly impossible with exhausted repair evidence.
- [Action] After repeated identical failed calls, require changed arguments, changed valid tool, a precondition-changing observation, or an evidence-backed impossibility branch before retry.
- [Action] Preserve useful retries after a successful observation changes the state or precondition; do not permanently quarantine a failed call signature.
- [Action] Treat empty action output as a contract failure requiring a valid tool call, terminal tool, or explicit impossible-with-evidence decision.
- [Action] Before retrieval QA finalization, check candidate support against target entity, predicate, answer type, and distractor/contradiction cues.
- [Action] Before multi-hop transformations, verify that required typed slots are observed and not placeholders or unresolved descriptions.
- [Action] Before short-answer submission, bind the answer to a decisive observation and copy raw structured fields exactly unless the task explicitly requests a different format.
- [Memory] Keep memory procedural, compact, and phase-aware; do not store task-specific IDs, entities, answers, or planned actions as facts.
- [Memory] Trigger IN-phase reminders only for visible trajectory risks such as repeated failures, unresolved ledger rows, observed-ID mismatch, placeholder-slot risk, or raw-value finalization risk.
- [Builder] Preserve local harness factory compatibility, provider file structure, `ActionContext` flow, `PlanningClass` injection, and benchmark tool binding.
- [Interface] Share a minimal status note across Planning, Action, and Memory with pending work, observed success, observed failure, remaining work, slots/ledger, and final criteria.
- [Preserve] Keep the winner's single-executor low-overhead behavior, strict JSON/schema discipline, guard wrapper, and answer-focused canonicalization personality.
- [Avoid] Do not copy whole peer harnesses, add heavy multi-agent orchestration, change the benchmark/evaluator/dataset, use external services, retrain the model, or hard-code benchmark item IDs, traces, entities, answers, or golden values.
- [Avoid] Do not add broad debate or parallel acting for mutable stateful tasks; use sequential read-after-write discipline unless independence is explicit.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
