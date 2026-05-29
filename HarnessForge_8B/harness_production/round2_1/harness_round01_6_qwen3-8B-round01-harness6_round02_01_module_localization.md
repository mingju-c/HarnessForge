# Module-Localized Failure Analysis Report

Harness under analysis: `harness_round01_6`

Model/run label: `qwen3-8B-round01-harness6`

Round: `round02_01`

Evidence root: `output/exp_4_three_rounds/round02_01/harness_seed_run`

### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

`builder.py` assembles a single `ToolCallingAgent` through the action provider. It sets `planning_system` to `round01_canonical_planning`, `action_system` to `round01_canonical_react`, `HARNESS_NAME` to `harness_round01_6`, and injects `PlanningClass` into `ActionContext.kwargs`. It also sets `max_tool_calls_per_step` to 2 by default and binds the built agent back into several factory tools when those tool handles exist.

The harness metadata says the recommended memory system is `round01_canonical_memory` and records `"round": "round_01"`. That is not a direct execution failure, but it is a metadata mismatch with the current evaluation folder `round02_01`. The implementation matches the description in its main architectural claim: it is a conservative single-ReAct harness with canonical answer reminders, soft guardrails, and no committee topology.

The builder does not add an independent verifier, a state ledger, or a hard terminal gate. Therefore, the main correctness burden remains inside the single action loop.

#### 1.2 Planning Module Implementation

`planning_module/provider.py` implements `PlanningProvider`, a compact planner that renders `planning_module/prompts/toolcalling_agent.yaml`. The initial plan is a textual status contract with fields for `target`, `planned_or_pending`, `observed_success`, `observed_failure`, `remaining`, and `final_criteria`.

The initial plan receives memory guidance through `append_memory_guidance`, but the plan is not transformed into a machine-readable execution ledger. The action loop sees the plan as conversational context rather than as enforced state. The adaptation method can summarize progress every summary interval, but it only asks the model to update status from memory messages. It does not enforce prerequisite satisfaction, completed subtask accounting, slot binding, or terminal-readiness checks.

Planning helps simple tasks by naming the requested answer and the main evidence chain. It does not currently control tool choice, argument repair, repeated-call suppression, final answer canonicalization, or stateful completion validation.

#### 1.3 Action Module Implementation

`action_module/provider.py` builds a single-agent ReAct executor. It wraps task tools with `guard_task_tools`, adds a non-environment `canonicalize_answer` checker, loads the `round01_canonical_react` prompt, and creates one root `ToolCallingAgent`. There is no coordinator-worker topology, debate, verifier-repairer pipeline, or parallel role separation.

The action prompt strongly instructs the model to use strict JSON, copy exact schema names, avoid empty tool lists, avoid repeated failed calls, and call `final_answer` or `complete_task` only after observation-backed completion. These are prompt-level controls rather than hard controls.

Tool errors are handled mostly through observations. The guard can repair some alias-like argument keys and can append repeated-failure advisories after exact failed calls, but it still executes repeated calls and does not force a strategy change. The optional `canonicalize_answer` tool reads recent history and returns a textual verdict, but the action prompt says it is optional. In the observed trajectories, failures often occur because the executor does not call it, ignores its intended discipline, or finalizes in a non-raw form despite a correct raw observation.

Final answers are submitted through `final_answer` for SearchQA and ToolHop and through `complete_task` for EnvScaler when the agent decides it is done. There is no deterministic final gate that checks all stateful mutations, all prerequisite slots, or exact raw answer formatting.

#### 1.4 Memory Module Implementation

`memory_module/provider.py` implements lightweight phase-aware procedural reminders. At `BEGIN`, it reminds the agent to track answer type and avoid nearby entities, partial names, or explanatory paragraphs. At `IN`, it emits a reminder every configured interval or after detected errors: stop searching when evidence is sufficient and canonicalize the observed value.

The memory module deliberately avoids persisting trajectory facts. That is a strength against memory contamination, but it also means recurrent lessons from the same run family are not stored as reusable procedures. The observed failures do not show memory actively distracting the agent. The larger issue is that memory guidance is too generic and too weakly routed to prevent repeated failed calls, relation-chain slot drift, or final answer rewrites.

### PART 2: FAILURE MODE ANALYSIS

#### Failure Mode 1

- **Name:** Stateful subtask ledger collapse under multi-operation environments
- **Frequency / importance:** Very high. EnvScaler has 658 tasks, 638 below full score, only 20 full-score completions, and average `envscaler_score` 0.4867.
- **Symptom:** The agent performs some correct mutations, then loses which object or subtask the next operation belongs to, loops, or claims completion with an incomplete environment state.
- **Mechanism:** Planning emits a plain-text checklist, but action does not maintain a structured state ledger keyed by requested operation, target object, observed IDs, success status, and remaining dependencies. After an ID lookup or mutation succeeds, the executor may bind later work to the wrong object or repeat a stale action.
- **Generalized capability gap:** Missing durable progress-state management for stateful tool-use tasks.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Action
- **Evidence:** In `1005.json`, the agent correctly finds and completes the arrived stroke incident, then assigns `AMB-7de0` back to that completed incident instead of to the requested allergic reaction at `LOC4`, causing repeated failed assignments. In EnvScaler, 494/658 tasks reached `done=1`, but only 20/658 reached full score, showing terminal completion often arrives without complete state correctness.
- **Generalization rationale:** Any unseen workflow with multiple target entities and dependent writes can fail if observations are not bound to a persistent subtask ledger.
- **Confidence:** High

#### Failure Mode 2

- **Name:** Soft failure advisories do not become repair control
- **Frequency / importance:** High. Among failed EnvScaler tasks, 443/638 contain `success:false`, 236/638 contain repeated-failure advisories, and 113/638 contain tool exceptions. Among failed ToolHop tasks, 30/108 contain repeated-failure advisories and 21/108 contain tool exceptions.
- **Symptom:** The executor repeats the same invalid call, retries with the same wrong ID or format, or continues after a guard advisory without a real repair.
- **Mechanism:** `_harness_guards.py` appends useful warnings, but the action module has no controller that blocks repeated exact failures, parses the error into a required precondition, or forces a different schema-listed strategy. Prompt instructions are insufficient when the model is already stuck.
- **Generalized capability gap:** Missing tool-error arbitration and precondition-repair protocol.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** In `1059.json`, `get_folder_by_name` returns the real folder ID `F2`, but the agent keeps calling `create_folder` with parent ID `"Work"` and receives repeated "Parent folder does not exist" errors. In `1025.json`, repeated unauthorized `update_sleep_log` and `get_sleep_log_by_id` calls continue after advisories.
- **Generalization rationale:** Tool APIs in unseen tasks will produce not-found, authorization, format, and precondition errors; a harness needs a reusable repair loop rather than a textual warning.
- **Confidence:** High

#### Failure Mode 3

- **Name:** Retrieval evidence arbitration fails on distractors and near matches
- **Frequency / importance:** High for SearchQA. SearchQA average score is 0.4462, with 195/325 below full score. A heuristic string check found that 94/195 failed SearchQA trajectories contained a gold answer string somewhere in observations but still finalized incorrectly.
- **Symptom:** The agent finalizes an answer supported by a nearby snippet, a wrong document title, a related entity, or a plausible prior instead of the requested target.
- **Mechanism:** The action prompt asks the agent to bind answers to observations, but there is no explicit candidate arbitration protocol: title match, entity match, question predicate match, distractor rejection, and answer-type fit are not evaluated before finalization.
- **Generalized capability gap:** Missing evidence arbitration for retrieval QA when observations contain multiple plausible candidates.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** In `460.json`, the search results include a bed-size document and a pillow-size document; the agent answers `20x30 inches`, the queen pillow size, instead of the queen bed/mattress size. In `1021.json`, it chooses Van Stephenson because he plays electric guitar, while the question also asks who helped write "Days of America"; the correct answer is Henry Paul. In `1023.json`, it returns the film title instead of the requested cast list.
- **Generalization rationale:** Retrieval tasks across domains often include adjacent entities and ambiguous snippets; the failure is not specific to any one question topic.
- **Confidence:** High

#### Failure Mode 4

- **Name:** Multi-hop slot binding breaks before transformations
- **Frequency / importance:** Medium to high. ToolHop average score is 0.6004, with 108/259 below full score. Failures concentrate in chained relationship, date, string, and arithmetic tasks.
- **Symptom:** The agent transforms the wrong intermediate value, accepts a placeholder as an entity, or finalizes after only part of the relation chain is resolved.
- **Mechanism:** The plan names high-level steps, but action does not preserve typed slots such as `target_person`, `father`, `paternal_grandfather`, `raw_date`, and `transformed_answer`. There is no enforced prerequisite check before extraction or arithmetic.
- **Generalized capability gap:** Missing typed intermediate-state binding for multi-hop tool reasoning.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Planning
- **Evidence:** In `1016.json`, the task asks for the last name of the paternal grandfather of Chiang Hsiao-Wu, but the agent queries only the father and extracts the father's last name. In `1027.json`, after failing to retrieve a father, it extracts a last name from the literal placeholder phrase `"Chiang Hsiao-chang's father's other child"` and computes over `child`.
- **Generalization rationale:** Any compositional task requiring relationship traversal plus transformation can fail if intermediate slots are not validated before downstream operations.
- **Confidence:** High

#### Failure Mode 5

- **Name:** Final-answer canonicalization rewrites correct observations
- **Frequency / importance:** Medium. In SearchQA, `subem` is 160/325 while `answer_correct` is 130/325. In ToolHop, `subem` is 160/259 while `answer_correct` is 151/259. This gap shows many cases where the needed value is partly present but the submitted answer form is wrong.
- **Symptom:** The agent observes the correct raw value but submits a sentence, reformatted date, padded binary string, or over-specific alias.
- **Mechanism:** `canonicalize_answer` is optional and model-mediated. The final prompt says to copy exact structured fields, but there is no hard extraction rule for dates, numbers, binary outputs, or result fields.
- **Generalized capability gap:** Missing deterministic or mandatory final-answer binding to decisive observations.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** In `900.json`, `date_calculator` returns `1943-04-05`, but the final answer is `5 April 1943`. In `1173.json`, `date_calculator` returns `1321-11-27`, but the final answer is a full sentence. In `206.json`, the binary answer is returned as `01110011` while the expected raw form is `1110011`.
- **Generalization rationale:** Many unseen tasks require exact machine-graded formats; preserving raw observed values is a general harness requirement, not a task-specific patch.
- **Confidence:** High

#### Failure Mode 6

- **Name:** Unsupported impossibility and empty-action termination
- **Frequency / importance:** Medium. Failed EnvScaler trajectories contain empty/no-observation action steps in 589/638 cases, and 139/638 failed EnvScaler tasks never call `final_answer` or `complete_task`. Failed ToolHop has 42/108 empty/no-observation steps and 2/108 without a terminal tool.
- **Symptom:** The agent emits empty action steps despite the prompt forbidding empty tool lists, gives "cannot determine" answers too early, or ends without a terminal tool.
- **Mechanism:** The action loop does not enforce the JSON/tool contract after the model produces an empty step. It also lacks a structured "impossible only if all available repair routes failed" criterion.
- **Generalized capability gap:** Missing hard contract enforcement for non-final actions and impossibility decisions.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** In `507.json`, the agent repeats the same search for "who plays Violet in Saved by the Bell" and then finalizes that the information is unavailable instead of changing query strategy. In `1088.json`, failed legislative sponsor queries lead to a broad impossibility answer. In EnvScaler, many failed tasks end with no terminal tool even while `agent_result` is populated.
- **Generalization rationale:** Empty action and premature impossibility are domain-independent execution failures that will recur whenever the first tool path is incomplete.
- **Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Stateful subtask ledger collapse under multi-operation environments | Cross-Module Interface | Action | `planning_module/provider.py -> action_module/provider.py` | EnvScaler: 638/658 below full score; `1005.json` binds later ambulance assignment to the completed stroke incident; only 20/658 full-score tasks | Multi-object workflows require durable observed-state tracking beyond a conversational plan | High | Add a structured execution ledger that maps requested writes to observed IDs, success status, and remaining dependencies |
| Soft failure advisories do not become repair control | Action | Memory | `action_module/provider.py`, `_harness_guards.py` | Failed EnvScaler: 236 repeated-failure advisories; `1059.json` repeats parent folder `"Work"` after observing folder ID `F2` | Any API task can produce repairable errors; advisories must alter control flow | High | Convert repeated-failure and schema/error observations into a mandatory repair branch or block |
| Retrieval evidence arbitration fails on distractors and near matches | Action | Planning | `action_module/prompts/toolcalling_agent.yaml` | SearchQA: 195/325 below full score; `460.json` selects queen pillow size from a bed-size query; `1021.json` selects the wrong Blackhawk member | Retrieval observations often include adjacent entities; answer selection needs target-consistency checks | High | Add an evidence arbitration checklist before final answer: title/entity match, predicate match, answer type, and distractor rejection |
| Multi-hop slot binding breaks before transformations | Cross-Module Interface | Planning | `planning_module/provider.py -> action_module/prompts/toolcalling_agent.yaml` | `1016.json` extracts father's last name instead of paternal grandfather's; `1027.json` extracts from a placeholder phrase | Compositional tool tasks need validated typed slots before transformation tools | High | Emit and maintain typed slots with prerequisites and block transformations until required slots are observed |
| Final-answer canonicalization rewrites correct observations | Action | Memory | `action_module/provider.py`, `action_module/prompts/toolcalling_agent.yaml` | `900.json` observes `1943-04-05` but answers `5 April 1943`; `1173.json` observes `1321-11-27` but answers a sentence | Machine-graded tasks require exact observed raw values across domains | High | Make final-answer binding mandatory for structured results and short answers; use exact field copying or a deterministic canonicalization gate |
| Unsupported impossibility and empty-action termination | Action | Planning | `action_module/prompts/toolcalling_agent.yaml`, base agent loop contract | Failed EnvScaler: 589/638 empty/no-observation steps, 139/638 no terminal tool; `507.json` finalizes unavailable after repeated same query | Empty action and premature impossibility are generic execution-control failures | Medium | Add hard handling for empty tool lists and require an explicit exhausted-repair ledger before impossibility answers |

### PART 4: STRENGTHS TO PRESERVE

- The single-agent ReAct topology in Action should be preserved because successful SearchQA `20.json` and ToolHop `1116.json` solve direct evidence chains without coordination overhead; generation should not regress the low-latency simple-task path.
- The closed-set schema prompting in Action should be preserved because many successful trajectories use exact listed tool names and arguments; generation should strengthen schema use without adding broad invented tools.
- The soft guard wrapper in Action should be preserved because it exposes repeated-failure advisories and some argument-key repair; generation should turn those signals into control rather than removing them.
- The compact planning contract in Planning should be preserved because it gives clear target, pending work, and final criteria for simple tasks such as `1116.json`; generation should make it more actionable rather than replacing it with verbose free-form planning.
- The phase-safe memory policy in Memory should be preserved because it avoids storing planned actions as facts; generation should add compact procedural lessons without persisting task-specific answers.
- The prompt discipline to call `final_answer` for short-answer QA should be preserved because all SearchQA tasks called `final_answer`; generation should improve correctness and formatting while keeping this terminal habit.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Add a Stateful Execution Ledger]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py -> action_module/provider.py`
- **Problem:** EnvScaler failures show partial progress, wrong object binding, and premature completion.
- **Mechanism:** Convert the plan into a compact ledger with one row per requested operation: target entity, required observation, chosen tool, observed ID, success/failure, and remaining dependency.
- **Why This Module Owns It:** Planning currently names subtasks, but Action must consume and update them during execution; the missing capability is the interface between them.
- **Generalization Rationale:** Any unseen stateful workflow with multiple entities needs persistent progress accounting.
- **Complexity:** Medium
- **Expected Impact:** Higher full-state completion and fewer wrong-object mutations.
- **Risk:** If the ledger is too verbose, it may increase prompt bloat and distract the single executor.

**[Priority 2: Turn Tool Failure Advisories Into Mandatory Repair Control]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`, `_harness_guards.py`
- **Problem:** Repeated failed calls continue after guard advisories and known precondition errors.
- **Mechanism:** Track exact failed call keys and require a different tool, changed arguments, or a cited precondition-changing observation before allowing the same call again.
- **Why This Module Owns It:** The action loop selects tools and observes errors; planning and memory cannot enforce runtime repair.
- **Generalization Rationale:** Schema, ID, authorization, date-format, and not-found errors appear across many tool families.
- **Complexity:** Medium
- **Expected Impact:** Fewer low-value loops and more recovery from repairable API errors.
- **Risk:** A too-strict block could prevent valid retries after a real state change, so the controller must recognize changed preconditions.

**[Priority 3: Add Typed Slot Binding for Multi-Hop Tool Reasoning]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py -> action_module/prompts/toolcalling_agent.yaml`
- **Problem:** ToolHop failures transform the wrong intermediate value or treat placeholders as evidence.
- **Mechanism:** Require named slots such as `source_entity`, `relation_result`, `target_entity`, `raw_value`, and `transformed_value`, with a prerequisite check before each transformation tool.
- **Why This Module Owns It:** Planning must expose the slots, and Action must update them from observations before continuing.
- **Generalization Rationale:** Relation traversal plus transformation recurs in genealogy, film, date, string, math, and entity lookup tasks.
- **Complexity:** Medium
- **Expected Impact:** Better multi-hop path correctness and fewer early wrong extractions.
- **Risk:** Overly rigid slot names could underfit unusual tasks; the implementation should keep slot labels task-derived.

**[Priority 4: Require Evidence Arbitration Before Retrieval QA Finalization]**
- **Target Module:** Action
- **Owner Path:** `action_module/prompts/toolcalling_agent.yaml`
- **Problem:** SearchQA final answers often come from distractor snippets, related titles, or partial predicate matches.
- **Mechanism:** Before `final_answer`, score each candidate against requested entity, document title, predicate, answer type, and contradiction/distractor cues. If the top evidence fails a target check, change the query instead of finalizing.
- **Why This Module Owns It:** The action executor reads search observations and chooses the final answer.
- **Generalization Rationale:** Distractor-rich retrieval is domain-independent.
- **Complexity:** Low
- **Expected Impact:** Better answer selection on SearchQA-like tasks without changing tools or adding committees.
- **Risk:** Too much arbitration could cause unnecessary extra searches on already-clear one-hop questions.

**[Priority 5: Make Final Observation Binding Mandatory for Short Answers]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`, `action_module/prompts/toolcalling_agent.yaml`
- **Problem:** Correct raw tool outputs are reformatted into wrong final answers.
- **Mechanism:** Add a final gate: when the decisive observation has `result`, `answer`, `value`, `date`, count, binary, or raw text output, the final `answer` must copy that value exactly unless the task explicitly requests a different format.
- **Why This Module Owns It:** Final answer construction and optional canonicalizer use live in Action.
- **Generalization Rationale:** Exact canonical form matters across dates, numbers, names, strings, and state summaries.
- **Complexity:** Low
- **Expected Impact:** Close the gap between `subem` and `answer_correct`, especially for ToolHop and SearchQA.
- **Risk:** Exact copying can preserve a wrong intermediate value if evidence arbitration and slot binding are not also improved.

**[Priority 6: Add Compact Error-Phase Memory Procedures]**
- **Target Module:** Memory
- **Owner Path:** `memory_module/provider.py`
- **Problem:** Memory reminders are safe but too generic for recurring failure patterns.
- **Mechanism:** Add phase-aware procedural reminders only when matching evidence appears: repeated failed call, observed ID not used, structured result available, or empty action risk.
- **Why This Module Owns It:** Memory already routes BEGIN and IN guidance and can add reusable procedures without storing task facts.
- **Generalization Rationale:** These are reusable execution lessons, not benchmark answers.
- **Complexity:** Low
- **Expected Impact:** Better adherence to repair and canonicalization rules with little architectural risk.
- **Risk:** Too many reminders could bloat prompts and reduce attention to current observations.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory `1005.json` (EnvScaler): after a successful lookup and completion of the arrived stroke incident, the action loop assigns ambulances to the already completed incident instead of locating the requested pending incidents. This supports the state ledger and object-binding diagnosis.
- Failed trajectory `1059.json` (EnvScaler): the agent observes that the `Work` folder has ID `F2`, but keeps calling `create_folder` with parent ID `"Work"`, triggering repeated "Parent folder does not exist" errors. This supports the missing repair-control diagnosis.
- Failed trajectory `460.json` (SearchQA): the agent answers `20x30 inches` from a pillow-size document even though the question asks for a queen bed measurement. This supports the evidence arbitration diagnosis.
- Failed trajectory `1016.json` (ToolHop): the agent retrieves Chiang Hsiao-Wu's father, extracts the father's last name, and finalizes, even though the task asks for the paternal grandfather. This supports the slot-binding diagnosis.
- Failed trajectory `900.json` (ToolHop): the date tool returns `1943-04-05`, but the final answer is `5 April 1943`. This supports the final-answer canonicalization diagnosis.
- Successful trajectory `1116.json` (ToolHop): the agent follows a clean chain from father lookup to grandmother lookup to last-name extraction to vowel counting, then finalizes `3`. This shows that the single-executor design works when each intermediate observation is unambiguous and immediately transformed.
- Successful trajectory `241.json` (EnvScaler): the agent resolves duplicate participant records, updates a meeting, registers participants, joins them, and calls `complete_task` with EnvScaler score 1.0. This shows that the existing design can complete stateful workflows when object IDs and operation sequence remain aligned.
- Bucket-level statistic: overall average score is 0.4998 across 1242 tasks. EnvScaler is the largest and weakest full-completion area: 658 tasks, average score 0.4867, only 20 full-score tasks. SearchQA has 130/325 answer-correct and 160/325 subEM; ToolHop has 151/259 answer-correct and 160/259 subEM. The subEM gaps make final canonicalization materially relevant.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Keep the compact status contract, but expose task-derived slots and subtask rows that Action can update from observations.
- [Planning] Include final-readiness conditions that distinguish observed success from planned or attempted work.
- [Action] Preserve the single executor, closed-set tool schema discipline, and direct final-answer path for simple tasks.
- [Action] Add a hard repeated-failure repair rule: the same failed tool and arguments require a changed precondition, changed arguments, or changed strategy before retry.
- [Action] For stateful tasks, maintain a visible ledger of required mutations and successful observations before `complete_task`.
- [Action] For retrieval QA, require candidate evidence to match the requested entity, predicate, and answer type before `final_answer`.
- [Action] For short-answer tasks, copy decisive structured tool fields exactly unless the user asks for a different format.
- [Memory] Keep memories procedural and phase-safe; do not persist task-specific entities or answers.
- [Memory] Add only compact IN-phase reminders triggered by repeated failure, observed-ID mismatch, or final-answer canonicalization risk.
- [Builder] Preserve factory compatibility, context preparation, `PlanningClass` injection, and tool reference binding.
- [Interface] Treat planning state as an updateable contract, not just a conversational preface.
- [Interface] Require Action observations to update Planning slots or ledger entries before transformations and terminal completion.
- [Avoid] Do not add benchmark-specific patches for queen bed sizes, particular historical figures, folder names, or individual EnvScaler domains.
- [Avoid] Do not replace the architecture with a heavy multi-agent committee unless a specific module-level mechanism cannot be implemented in the single executor.
- [Preserve] Keep the soft guard signals, but make the next harness consume them as control signals.
- [Preserve] Keep successful direct execution behavior for one-hop and clear multi-hop tasks.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
