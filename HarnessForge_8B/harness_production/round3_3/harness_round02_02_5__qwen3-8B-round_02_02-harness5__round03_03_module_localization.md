### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness under analysis is `harness_round02_02_5`, evaluated as model/run `qwen3-8B-round_02_02-harness5` in `round03_03`. The inspected snapshot is `harness_factory/rounds/round_03_03/base harness`, and the trajectory evidence comes from `output/exp_4_three_rounds/round03_03/harness_seed_run`.

`builder.py` assembles one `ToolCallingAgent` through `action_module/provider.py`. It wires `PlanningClass` into `context.kwargs["planning_class"]`, sets `planning_system` to `round02_02_raw_answer_planning`, sets `action_system` to `round02_02_raw_answer_react`, sets `project_root` to the base harness directory, and defaults `max_tool_calls_per_step` to 2. It also sets `harness_status_contract` to `RAW_ANSWER`.

The builder binds the created agent back into process, end-process, delete-memory, executor, and refine tools when those tools expose an `agent` field. If a vector tool is present, it assigns `prepared_context.vector_tool.memory = agent.memory`. These are useful factory-compatibility behaviors and should be preserved.

The important metadata mismatch is bookkeeping rather than a direct execution fault: this base harness is evaluated in `round_03_03`, but `HARNESS_NAME`, module names, `PAIRING_REASON`, and `harness_metadata["round"]` still identify it as a `round_02_02` raw-final-canonicalization harness. The implementation is therefore not a native round03_03 design; it is a round02_02 raw-answer harness reused as the current round03_03 base.

#### 1.2 Planning Module Implementation

`planning_module/provider.py` implements `PlanningProvider`, a free-form compact planner for the `RAW_ANSWER` contract. At initialization, it renders a planning prompt that lists available tool schemas and asks the model to produce fields such as `target`, `answer_type`, `decisive_observation_needed`, `allowed_transformation`, `observed_success`, `observed_failure`, `remaining`, and `final_criteria`. The module appends memory guidance to the system-side input, calls the model once, stores the resulting plan in memory, and logs it.

Adaptation is implemented as periodic summarization. The summary prompt asks the model to update `observed_success`, `observed_failure`, `bindings_or_ledger`, `terminal_blockers`, `remaining`, `retry_or_repair_guidance`, `next_step`, and `final_readiness` using prior memory messages. The action provider sets the summary interval to 8 unless another interval is already configured.

Planning influences action only through natural-language memory content. It does not emit a parsed object, does not enforce that the model follows the required fields, and does not provide an action-readable obligation ledger. This matters sharply on EnvScaler: 644 of 658 EnvScaler initial planning steps became executable-looking tool-call JSON rather than the required status contract, while all 325 SearchQA and all 258 ToolHop plans followed the target/evidence-style contract. This indicates that long stateful task prompts with their own strict output contract can override the planning prompt.

#### 1.3 Action Module Implementation

`action_module/provider.py` uses a single-executor topology. There is no coordinator-worker split, no separate verifier agent, no debate topology, and no parallel worker aggregation. The only added action-side helper is `RawAnswerCheckTool`, exposed as `raw_answer_check`.

The action provider wraps primary task tools with `guard_task_tools(..., policy_label="round02_02_raw_answer")`, adds `raw_answer_check`, normalizes the tool list, and creates one `ToolCallingAgent`. The checker can inspect recent history and a draft answer using the same backend model. It returns free text with fields such as `verdict`, `evidence`, `missing_or_risk`, and `next_safe_move`. Although the checker has code for exact-repeat throttling, `_throttle_exact_repeats` is initialized to `False`, so exact repeated checker drafts are not actually throttled.

The action prompt is a closed-set ReAct prompt. It tells the model to copy exact tool names and argument keys from current schemas, avoid invented tools, use `raw_answer_check` only when answer type or transformation is ambiguous, and call `final_answer` when evidence is sufficient. For EnvScaler, the original task instructions tell the agent to call `complete_task` after required state changes. The harness does not add a state-diff checker, mutation ledger, or terminal readiness gate before `complete_task`.

Observation handling is model-mediated. Failed tool calls produce text observations and repeated-failure advisories, but there is no structured failure-class parser that blocks repeated calls or forces a specific repair. Tool-call errors, unknown tools, invalid enum values, empty results, and partial state mutations are therefore handled by the same single executor that made the call.

#### 1.4 Memory Module Implementation

`memory_module/provider.py` implements a lightweight procedural memory named `round02_02_raw_answer_memory`. At `BEGIN`, it injects one reminder to maintain an `answer_type` slot and to final-answer with a raw observed field or task-requested transformation rather than a paraphrase. During `IN`, it scans context for error markers and finalization-risk markers. On errors, it reminds the agent not to guess after a failed lookup or transformation. Near finalization or every configured interval, it reminds the agent to copy ISO dates, numeric strings, IDs, names, counts, and calculator outputs exactly.

Memory stores no task facts, IDs, answers, or domain-specific lessons. `take_in_memory` always reports success but explicitly says that only procedural reminders are stored. This keeps memory low-noise and reduces overfitting risk, but the reminders are advisory only. In observed failures, the action loop often receives relevant memory warnings and still repeats failed calls, marks failures as non-failures in summaries, or finalizes with an over-formatted answer.

### PART 2: FAILURE MODE ANALYSIS

#### Failure Mode 1: Stateful task prompts collapse the initial planning contract

- **Name:** EnvScaler initial plans become executable tool calls instead of structured status contracts.
- **Frequency / importance:** High for EnvScaler and important for downstream stateful failures. 644 of 658 EnvScaler initial plans were JSON-like tool actions, while 325 of 325 SearchQA and 258 of 258 ToolHop plans followed the target/evidence contract.
- **Symptom:** The first planning step in stateful tasks often says what tool to call first rather than listing all required obligations, bindings, blockers, and final readiness criteria.
- **Mechanism:** The planner embeds the full task prompt, including the benchmark-level strict output contract, inside the planning request. Because the planner output is free-form and unparsed, the model often follows the task-level tool-use contract instead of the planning prompt. The resulting "plan" lacks a durable checklist for multi-mutation tasks.
- **Generalized capability gap:** Prompt-injection-resistant planning contract and stateful obligation decomposition.
- **Primary module owner:** Planning
- **Secondary contributor:** Cross-Module Interface
- **Evidence:** In trajectory 460, the plan is `update_patient_info` rather than a ledger covering all four medical-record changes. In trajectory 99, the plan jumps directly to `register_new_device` and omits the later inventory audit ledger. In successful trajectory 1123, the plan also starts as a tool call, and success comes from later action recovery rather than a robust initial plan.
- **Generalization rationale:** Any task family that includes long instructions, embedded output contracts, or stateful subtasks can dilute a free-form planner unless the planning module enforces its own schema.
- **Confidence:** High

#### Failure Mode 2: Stateful completion is not gated by a verified side-effect ledger

- **Name:** EnvScaler tasks are marked complete after partial, failed, or unverified mutations.
- **Frequency / importance:** Dominant for EnvScaler. EnvScaler averaged 0.4685 score over 658 tasks, with only 21 full-score tasks, 451 partial-score tasks, and 186 zero-score tasks. `complete_task` appeared in 524 EnvScaler trajectories, and 503 of those were still not full-score. 555 non-full-score EnvScaler runs ended with `agent_result` equal to `Task Completed`.
- **Symptom:** The agent often performs some correct mutations, sees failed observations, then calls `complete_task` or otherwise reports completion while required state changes remain unresolved.
- **Mechanism:** The action loop has no structured side-effect ledger, no postcondition checker, and no terminal gate that blocks `complete_task` when recent failures affect required mutations. Periodic summaries are also unreliable: 505 EnvScaler summaries marked `observed_failure` as false despite earlier failed observations.
- **Generalized capability gap:** Transactional progress tracking and completion readiness for stateful tool environments.
- **Primary module owner:** Action
- **Secondary contributor:** Planning and Cross-Module Interface
- **Evidence:** Trajectory 460 updated patient and provider contact information but failed to add and edit medical records due to permission errors, then called `complete_task` and scored 0.2222. Trajectory 99 created and registered some device objects, then looped on one maintenance schedule and ended without completing the inventory audit, scoring 0.0. EnvScaler had 480 episodes with at least one `"success": false` observation and 3008 such failed observations overall.
- **Generalization rationale:** Stateful API tasks in healthcare, inventory, reservations, finance, or any other domain require confirmed object identity, mutation success, and terminal postcondition checks. The weakness is not specific to one EnvScaler domain.
- **Confidence:** High

#### Failure Mode 3: Tool schema and failed-call repair remain reactive rather than preventive

- **Name:** Malformed, unavailable, or low-value tool calls still reach the real environment.
- **Frequency / importance:** High. EnvScaler had 94 unknown-tool episodes, 115 `Error for tool call` episodes, 58 invalid-argument episodes, and 279 episodes with repeated-failure advisories. ToolHop had 54 `Error for tool call` episodes, 46 invalid-argument episodes, 20 no-data episodes, and 49 repeated-failure-advisory episodes.
- **Symptom:** The agent invents unavailable tools, supplies invalid enum values, repeats the same failed call, or tries broad parameter changes without a classified recovery hypothesis.
- **Mechanism:** The guard wrapper gives soft repair and repeated-failure advisories after execution, but the action module does not fully preflight required arguments, valid enum values, tool existence, ID-vs-name requirements, or nested shapes before execution. Repeated-failure advisories are observations, not hard constraints.
- **Generalized capability gap:** Schema preflight plus failure-classified recovery before real tool execution.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** In trajectory 460, after permission failures the agent invented `get_current_authenticated_user_role`, which was not in the available tool set. In trajectory 99, it invented `get_all_maintenance_schedules` and then repeatedly queried the same schedule for `DEV-BH-0001` instead of progressing through the inventory. In trajectory 203, it tried invalid genealogy arguments and then finalized an impossibility answer.
- **Generalization rationale:** Tool schemas with similar names, constrained arguments, and ID/name distinctions occur across tool-use benchmarks and real APIs. A post-hoc advisory cannot reliably prevent repeated low-value execution.
- **Confidence:** High

#### Failure Mode 4: Relation-specific evidence chains break on plausible nearby observations

- **Name:** The agent finalizes a plausible answer without verifying that it satisfies the exact requested relation.
- **Frequency / importance:** High for SearchQA and meaningful for ToolHop. SearchQA had 124 full-score, 19 partial-score, and 182 zero-score cases. ToolHop had 139 full-score, 11 partial-score, and 108 zero-score cases.
- **Symptom:** The trajectory obtains a related entity, date, name, or value and treats it as the requested answer even when the requested relation requires another hop or a narrower field.
- **Mechanism:** Planning usually names the target relation for SearchQA and ToolHop, but action does not maintain a relation-specific evidence ledger. It does not require a "does this observation answer the exact relation?" check before finalization, and it lacks arbitration when an observation contains multiple plausible spans.
- **Generalized capability gap:** Relation-grounded evidence targeting and exact-hop verification before final answer.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Planning and Action
- **Evidence:** Trajectory 752 asks for the full name of the leader of the band Tommy Duncan was part of. The search result points to Bob Wills, but the gold full name is `James Robert Wills`; the agent finalizes the shorter alias without verifying the requested full-name form. Trajectory 1116 asks for a count in the first name of a paternal grandfather; the agent accepts a nearby genealogy result and counts in `Kanezawa`, producing `0` instead of `2`. Trajectory 1171 fails to find the paternal grandfather, falls back to the subject's own last name, and still completes a binary conversion.
- **Generalization rationale:** Distractor snippets, aliases, adjacent relations, and partial chains occur in open-domain QA, knowledge-base lookup, genealogy-style tools, and multi-hop API workflows.
- **Confidence:** High

#### Failure Mode 5: Final-answer canonicalization is still not enforced

- **Name:** Correct or partially correct evidence is submitted in the wrong raw-answer form.
- **Frequency / importance:** Medium-high. SearchQA had 19 cases where `subem=1.0` but `answer_correct=0.0`; ToolHop had 11 cases with the same pattern. Additional exact-match failures include at least 6 SearchQA boolean yes/no conversions to true/false, at least 3 SearchQA date-format conversions, at least 6 ToolHop integer-vs-float formatting losses, and 9 ToolHop binary-string mismatches.
- **Symptom:** The final answer is an alias, a boolean in the wrong convention, an ISO date when the expected raw answer is prose date format, a number with `.0` dropped, an explanatory expression, or a binary string with an unwanted leading zero.
- **Mechanism:** The action module relies on the executor model to produce the terminal answer. Memory reminds the model to copy raw fields, but there is no final-answer gate that extracts the minimal supported span, preserves requested formatting, or rejects extra context.
- **Generalized capability gap:** Terminal raw-value extraction and answer-type-specific canonicalization.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Trajectory 768 correctly determines that Henry Green was English and Richard Wright was American, but answers `false` while the gold answer is `no`. Trajectory 848 observes "August 29, 1949" but finalizes `1949-08-29` while the gold answer is `29 August 1949`. Trajectory 975 observes `480i or 576i` and asks for max resolution, but returns both rather than the maximal `576i`. Trajectory 680 obtains calculator result `12167` but the expected answer is `12167.0`.
- **Generalization rationale:** Exact raw output is a terminal contract across short-answer QA, ToolHop transformations, form-filling tasks, and evaluator-facing APIs. This is a harness finalization weakness, not a domain-specific knowledge problem.
- **Confidence:** High

#### Failure Mode 6: The optional checker and memory reminders do not become enforceable constraints

- **Name:** `raw_answer_check` and procedural memory can confirm uncertainty without forcing recovery.
- **Frequency / importance:** Medium. `raw_answer_check` appeared in 120 EnvScaler trajectories, 12 SearchQA trajectories, and 23 ToolHop trajectories. It appeared in failed or non-full-score trajectories in 118 EnvScaler cases, 8 SearchQA cases, and 15 ToolHop cases. SearchQA had at least 5 "cannot be determined" style failed finals, and ToolHop had at least 14.
- **Symptom:** After empty, unknown, or failed observations, the checker often produces cautionary text, but the action loop either treats that text as enough evidence for impossibility or continues searching without a better recovery plan.
- **Mechanism:** `raw_answer_check` is a same-model, free-text, non-environment tool. Its output is not parsed into blockers, required next actions, or finalization permissions. Memory provides relevant warnings, but it is injected as text and cannot block a final answer or repeated call.
- **Generalized capability gap:** Enforced verifier/memory-to-action interface for missing evidence, repeated failures, and terminal readiness.
- **Primary module owner:** Action
- **Secondary contributor:** Cross-Module Interface and Memory
- **Evidence:** In trajectory 203, repeated genealogy failures lead to `raw_answer_check`, which reinforces an inability conclusion, and the agent finalizes an impossibility answer while the gold answer is `6`. In trajectory 460, memory warns not to guess after failed tools, but the agent still calls `complete_task` after unresolved permission failures. The checker is also misaligned with stateful tasks because it checks raw answer drafts, not environment postconditions.
- **Generalization rationale:** Same-model free-text checkers and advisory memories can fail in any task where missing evidence must constrain future action. The missing capability is enforcement, not a better wording for one task.
- **Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Stateful task prompts collapse the initial planning contract | Planning | Cross-Module Interface | `planning_module/provider.py`; Planning -> Action contract | 644/658 EnvScaler plans became tool-call JSON; SearchQA and ToolHop plans followed the contract; trajectories 460 and 99 | Long embedded task instructions and output contracts recur in stateful and agentic tasks | High | Make planning emit and validate a structured obligation contract that cannot be overwritten by task-level tool-use instructions |
| Stateful completion is not gated by a verified side-effect ledger | Action | Planning and Cross-Module Interface | `action_module/provider.py`; terminal `complete_task` behavior | EnvScaler full score 21/658; 503 actual `complete_task` calls occurred in non-full-score runs; 480 EnvScaler episodes had failed tool observations | All stateful APIs require confirmed mutations and postconditions before terminal completion | High | Add an action-owned side-effect ledger and block `complete_task` while required mutations or failure repairs remain unresolved |
| Tool schema and failed-call repair remain reactive rather than preventive | Action | Memory | `action_module/provider.py`; guarded task tools | EnvScaler: 94 unknown-tool episodes and 279 repeated-failure-advisory episodes; ToolHop: 54 tool-error episodes and 46 invalid-argument episodes | Schema mismatch and repeated low-value calls recur across all tool environments | High | Add required-field, enum, tool-existence, ID/name, and nested-shape preflight plus structured repair observations before real execution |
| Relation-specific evidence chains break on plausible nearby observations | Cross-Module Interface | Planning and Action | Planning -> Action evidence contract; `planning_module/provider.py`; `action_module/provider.py` | SearchQA 182 zero-score cases; ToolHop 108 zero-score cases; trajectories 752, 1116, and 1171 | Adjacent relations, aliases, and distractor evidence are common in open-domain and multi-hop tasks | High | Carry relation-specific evidence obligations from plan into action and require exact-relation verification before finalization |
| Final-answer canonicalization is still not enforced | Action | Memory | `action_module/provider.py`; `final_answer` path | 19 SearchQA and 11 ToolHop cases with `subem=1.0` but exact answer wrong; examples include boolean, date, float, and binary-string format errors | Exact raw-value terminal contracts appear across QA, ToolHop, and API tasks | High | Add a raw-answer extraction and canonicalization gate that preserves the evaluator-requested answer form |
| The optional checker and memory reminders do not become enforceable constraints | Action | Cross-Module Interface and Memory | `RawAnswerCheckTool` in `action_module/provider.py`; Memory -> Action boundary | `raw_answer_check` used in 155 total trajectories and mostly in non-full-score EnvScaler cases; trajectory 203 finalizes impossibility after checker text | Advisory same-model checks can amplify uncertainty unless converted into blockers and required next actions | Medium | Parse checker and memory risk signals into action constraints; prevent finalization from checker text alone |

### PART 4: STRENGTHS TO PRESERVE

- The builder wiring in Builder/Wiring preserves harness-factory compatibility by injecting `PlanningClass`, setting `project_root`, binding tools back to the agent, and connecting vector memory; generation should not regress these integration behaviors because they keep modules usable in the local evaluation loop.
- The Planning module works well on shorter QA-style tasks: 325/325 SearchQA plans and 258/258 ToolHop plans followed the target/evidence contract, which helps simple retrieval and transformation tasks stay focused.
- The single-executor Action topology is efficient when the evidence chain is clean; trajectory 826 completes a multi-step ToolHop chain from publication to publisher founding year to digit extraction to raw final `91`, so generation should not impose heavy collaboration on every simple task.
- The Action module can recover from some tool errors when the repair is obvious; trajectory 190 repairs an invalid date input by converting `21 February 1986` to `1986-02-21`, then computes the correct date `1986-02-20`.
- The Memory module is compact and procedural, avoiding task facts, IDs, or hard-coded answers; this reduces overfitting risk and should be preserved while making its risk signals more actionable.
- The raw-answer focus already helps many terminal answers: SearchQA produced 124 full-score answers and ToolHop produced 139 full-score answers, so the next generation should strengthen exact finalization rather than replace the overall terminal-answer pathway.
- The guard layer in Action provides useful repeated-failure advisories and some soft schema repair; generation should harden this layer into preflight and recovery rather than discarding it.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Stateful Side-Effect Ledger and Completion Gate]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** EnvScaler tasks are often marked complete after partial or failed mutations.
- **Mechanism:** Track required mutations, bound entity IDs, successful side effects, failed side effects, postcondition checks, and unresolved blockers. Before `complete_task`, require every required mutation to be observed successful or explicitly impossible with evidence, and block completion after unresolved failures that affect the goal.
- **Why This Module Owns It:** The action module owns real tool execution, observation handling, and terminal tool calls.
- **Generalization Rationale:** Any stateful API task needs verified side effects before terminal completion, regardless of domain.
- **Complexity:** Medium
- **Expected Impact:** Fewer false `Task Completed` endings and higher EnvScaler full-score rate.
- **Risk:** If the gate is too strict or cannot recognize successful side effects, it may delay completion on tasks that are already done.

**[Priority 2: Structured Planning Contract Validation for Stateful Tasks]**
- **Target Module:** Planning
- **Owner Path:** `planning_module/provider.py` and `planning_module/prompts/toolcalling_agent.yaml`
- **Problem:** EnvScaler planning often collapses into a first tool call rather than a full obligation contract.
- **Mechanism:** Require the planner to output a compact structured object or schema-valid Markdown fields, validate that required fields are present, and repair the plan if it contains `tools`, executable calls, or missing stateful obligations. Add prompt wording that treats embedded task output contracts as task content, not planner output instructions.
- **Why This Module Owns It:** The planning module owns decomposition, evidence obligations, progress-state discipline, and final-readiness criteria.
- **Generalization Rationale:** Robust planning must resist long task prompts and embedded output contracts across unseen task families.
- **Complexity:** Low
- **Expected Impact:** Better stateful task decomposition and a usable input for the action ledger.
- **Risk:** Over-rigid planning schemas could add overhead or reduce flexibility on simple one-hop tasks.

**[Priority 3: Preventive Schema Preflight and Failure-Class Recovery]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py` and the guarded-tool boundary
- **Problem:** Unknown tools, invalid arguments, no-data loops, and repeated failed calls waste steps and sometimes mutate partial state.
- **Mechanism:** Validate tool existence, required keys, enum-like values, ID-vs-name requirements, array/scalar shape, and nested object requirements before real execution. When preflight fails, return a structured repair observation without calling the environment. Classify failures as schema error, missing binding, permission/auth error, empty result, unavailable tool, or terminal blocker, then choose bounded recovery moves.
- **Why This Module Owns It:** The action module owns tool selection, tool-call arguments, execution, observation handling, and repair behavior.
- **Generalization Rationale:** Schema and failed-observation recovery are core requirements for any tool-use harness.
- **Complexity:** Medium
- **Expected Impact:** Fewer unknown-tool calls, fewer repeated failures, and more productive recovery after empty observations.
- **Risk:** A brittle preflight layer might reject valid permissive inputs or overfit to observed tool schemas.

**[Priority 4: Relation-Grounded Evidence Contract Between Planning and Action]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** Planning -> Action boundary between `planning_module/provider.py` and `action_module/provider.py`
- **Problem:** The agent finalizes plausible nearby answers without checking the exact relation requested.
- **Mechanism:** Have planning expose relation-specific obligations such as subject, relation chain, target field, accepted raw answer type, and disallowed nearby fields. Have action update this contract after each observation and require a final check that the selected answer satisfies the target relation, not merely a related snippet.
- **Why This Module Owns It:** Planning defines the evidence target, while action owns observations and finalization.
- **Generalization Rationale:** Relation drift affects search QA, genealogy tools, knowledge-base chains, and multi-hop API tasks.
- **Complexity:** Medium
- **Expected Impact:** Fewer distractor-snippet answers and fewer partial chains that finalize early.
- **Risk:** Too much relation bookkeeping could slow simple retrieval tasks unless applied compactly.

**[Priority 5: Raw Final-Answer Canonicalization Gate]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`; terminal `final_answer` path
- **Problem:** Correct evidence is often submitted in an evaluator-wrong answer form.
- **Mechanism:** Before `final_answer`, run a lightweight terminal check that identifies answer type, selects the minimal supported raw span, preserves expected date/number/binary/boolean/list conventions, and rejects explanatory prose or extra alternatives unless requested.
- **Why This Module Owns It:** The action module controls final answer submission and can inspect the trajectory immediately before terminal output.
- **Generalization Rationale:** Exact raw terminal values are required across QA, ToolHop transformations, and downstream API fields.
- **Complexity:** Low
- **Expected Impact:** Recover many path-correct but final-wrong SearchQA and ToolHop cases.
- **Risk:** Over-normalization may remove necessary disambiguating context or choose the wrong alias when multiple answers are valid.

**[Priority 6: Enforced Checker and Memory Risk Signals]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** Memory -> Action and checker -> Action boundaries in `memory_module/provider.py` and `action_module/provider.py`
- **Problem:** `raw_answer_check` and memory warnings remain advisory and can be ignored or used as evidence for impossibility.
- **Mechanism:** Parse checker output and memory-triggered risks into normalized blockers. Disallow finalization from checker text alone, require the next real action to resolve `missing_or_risk`, and route stateful tasks away from raw-answer checking toward side-effect postcondition checking.
- **Why This Module Owns It:** The failure is at the boundary where advisory guidance should constrain action choices.
- **Generalization Rationale:** Same-model verifiers and procedural memories need enforceable interfaces in any environment with incomplete evidence or failed calls.
- **Complexity:** Medium
- **Expected Impact:** Fewer premature impossibility answers, fewer repeated checker calls, and better response to memory warnings.
- **Risk:** If blockers are too broad, the agent may become unable to finish after genuinely sufficient evidence.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory 460, EnvScaler: The plan was a first `update_patient_info` tool call rather than a complete status contract. The agent updated patient and provider contact information, failed to add and edit medical records due to permission and authorization errors, invented `get_current_authenticated_user_role`, and still called `complete_task`. Score was 0.2222.
- Failed trajectory 99, EnvScaler: The agent created the manufacturer, registered the device, created a schedule, and moved the device, but then invented `get_all_maintenance_schedules`, repeatedly queried the same schedule for `DEV-BH-0001`, and ended without completing the maintenance audit. Score was 0.0.
- Failed trajectory 752, SearchQA: A search result identified Bob Wills as the bandleader, but the question asked for the full name. The agent finalized `Bob Wills`; the gold answer was `James Robert Wills`.
- Failed trajectory 768, SearchQA: The agent correctly determined that Henry Green was English and Richard Wright was American, but finalized `false` instead of the expected yes/no answer `no`.
- Failed trajectory 848, SearchQA: The observation supported the date August 29, 1949, but the agent converted it to `1949-08-29` while the gold answer was `29 August 1949`.
- Failed trajectory 1116, ToolHop: The agent accepted a nearby genealogy result, extracted `Kanezawa`, counted the target character there, and finalized `0` instead of the gold `2`, showing an evidence-chain relation break.
- Failed trajectory 1171, ToolHop: After failed father/grandparent lookups, the agent fell back to the subject's own last name, converted the last letter to ASCII binary, and finalized `01110100`; the gold answer was `1110100`.
- Failed trajectory 680, ToolHop: The agent followed a mostly correct calculation chain and obtained `12167`, but the expected final was `12167.0`, showing terminal numeric canonicalization failure.
- Failed trajectory 203, ToolHop: Invalid and unknown genealogy lookups led to `raw_answer_check`, then the agent finalized an impossibility answer while the gold answer was `6`.
- Successful trajectory 826, ToolHop: The agent found the publisher of `National Contest Journal`, retrieved the founding year `1914`, extracted digits 2 and 3, concatenated them, and finalized raw `91`. This shows that the single-executor topology works when each hop has clear evidence and the final raw value is copied.
- Successful trajectory 190, ToolHop: The agent recovered from an invalid date-calculator input by converting `21 February 1986` to ISO format, computed one day before, and finalized `1986-02-20`. This repair behavior should be preserved.
- Successful trajectory 1123, EnvScaler: Despite an initial wrong patient ID and a failed reservation tool caused by a tool implementation error, the agent eventually bound the right patient, created the reservation, assigned the bed, and completed with score 1.0. This shows that action-side recovery can succeed when it eventually creates missing state records and verifies the final mutation.
- Bucket-level statistic: Overall score was 0.4724 over 1241 tasks. EnvScaler averaged 0.4685, SearchQA averaged 0.4108, and ToolHop averaged 0.5601.
- Bucket-level statistic: EnvScaler had only 21 full-score tasks out of 658, while 503 actual `complete_task` calls appeared in non-full-score runs, making stateful terminal readiness the dominant failure.
- Bucket-level statistic: SearchQA had 19 cases and ToolHop had 11 cases with `subem=1.0` but `answer_correct=0.0`, making final-answer canonicalization distinct from evidence retrieval.
- Bucket-level statistic: EnvScaler had 3008 `"success": false` observations and 1561 repeated-failure-advisory observations; ToolHop had 134 `Error for tool call` observations and 154 repeated-failure-advisory observations, making failure repair a major Action-module issue.

### PART 7: GENERATION CONSTRAINTS

- [Planning] The next harness must make the initial plan robust against embedded task-level output contracts; if the planner emits a `tools` object or executable-looking call, it should repair the plan into obligation fields before action begins.
- [Planning] For stateful tasks, the plan must enumerate required mutations, entity bindings, postconditions, and terminal criteria rather than only the first action.
- [Action] The action module must own a side-effect ledger and must not call `complete_task` while required mutations, failed calls, or postconditions remain unresolved.
- [Action] The action module must preflight tool names and argument schemas before real execution, including required keys, enum-like values, ID/name distinctions, and nested shapes.
- [Action] Repeated-failure advisories must become constraints on the next action; the agent should not repeat identical failed calls unless a later successful observation changed the relevant precondition.
- [Action] `raw_answer_check` should remain rare and should not be used as evidence for stateful completion or impossibility.
- [Memory] Memory should stay procedural and low-noise, but route reminders by failure class: schema error, empty result, repeated failure, final rawness, and stateful postcondition.
- [Interface] Planning obligations must be visible to action as a compact state object or checklist that action updates from observations.
- [Interface] Final-answer readiness must combine planning target, observed evidence, memory risk signals, and action-side terminal checks rather than relying on model confidence alone.
- [Preserve] Preserve the simple single-executor path for one-hop SearchQA and clean ToolHop chains, because it solves many tasks efficiently when evidence is direct.
- [Preserve] Preserve builder compatibility behaviors: `PlanningClass` injection, `project_root` setup, vector memory wiring, and tool-agent back binding.
- [Avoid] Do not add hard-coded fixes for observed item IDs, entity names, domains, expected answers, or specific benchmark tools; repairs must target general planning contracts, schema preflight, evidence verification, and terminal readiness.
- [Avoid] Do not solve EnvScaler by blindly delaying `complete_task`; completion should be blocked only by explicit unresolved ledger items or failed postconditions.
- [Avoid] Do not replace raw-answer finalization with verbose explanation. The terminal answer must remain the requested raw value.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
