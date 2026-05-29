### PART 1: HARNESS IMPLEMENTATION ANALYSIS

**Round01 correction note:** Any future harness produced from this analysis must render action-side schemas with Jinja variables `{{tool_functions_json}}` and `{{task}}`, not single-brace placeholders. Planning may mention tools only by exact schema names and should otherwise use plain-language pending items. Guard, status, checker, preflight, and retry controls must remain advisory: they should not hide available tools, force nonexistent auth/search/check probes, block legitimate retries after changed preconditions, or gate terminal completion when required observations are already present. Repeated identical failures should produce a soft strategy-switch advisory, and final-answer prompts should require exact copying from decisive result fields for dates, numbers, names, and calculated outputs.

#### 1.1 Builder / Wiring Implementation

The analyzed harness is `base_harness` evaluated with local `Qwen3-8B` on `base_harness_1242_run`. The builder wires a minimal fixed pairing: `PLANNING_SYSTEM = "generic_planning"`, `ACTION_SYSTEM = "single_react"`, `DEFAULT_MEMORY_SYSTEM = "lightweight_memory"`, and `PAIRING_REASON = "fallback_single_react"`. `prepare_context` injects `PlanningClass` into `context.kwargs`, normalizes `bench_type` and `prompts_type`, and points `project_root` at the harness directory.

`build_agent_from_context` creates one `ToolCallingAgent` through `action_module.provider.get_provider()`, annotates metadata, binds selected tool references back to the agent, and attaches vector memory if present. There is no evidence of a wrong provider or metadata mismatch. The main wiring limitation is architectural: the builder passes the planning class, but it does not create a structured plan state, task ledger, execution contract, or verification channel between planning, action, and memory.

The description matches the implementation: generic planning, single ReAct action, lightweight memory, and generic benchmark default. The run metadata shows `model = Qwen3-8B`, `model_backend = local`; the local model wrapper is not directly implicated by the evidence, because the dominant failures occur after valid model outputs and tool observations are already available.

#### 1.2 Planning Module Implementation

The planning provider implements one initial planning call and periodic summary/adaptation. `topology_initialize` renders a short initial-plan prompt, optionally appends memory guidance, asks the model for a plan, stores a `PlanningStep`, and returns unstructured text or JSON-like content as the plan. The plan is not parsed into required subtasks, checklist items, dependencies, or completion criteria.

`adaptation` summarizes progress using the agent memory transcript and asks for `current_task_state`, `latest_error_or_result`, `retry_or_repair_guidance`, and `next_step`. This can help when the model follows it, but the summary is also unstructured and cannot force the action loop to repair an error, mark a subtask incomplete, or prevent finalization.

Planning influences action only through memory transcript text. It does not own tool execution and does not enforce schema use, but it does contribute to failures when it produces premature or executable-looking plans without a durable state ledger. In EnvScaler, plans frequently contained concrete tool calls that were not executed; downstream memory/action sometimes treated those planned calls as if they had happened.

#### 1.3 Action Module Implementation

The action module is a single-agent ReAct topology. `action_module/provider.py` loads benchmark tools, loads the `single_react` prompt templates, and returns one `ToolCallingAgent`. There are no worker, verifier, repairer, debate, or coordinator roles. There is no aggregation or arbitration layer because only one action-side agent exists.

The underlying `ToolCallingAgent` builds a tool schema list at every step and asks the action model for strict JSON. It normalizes several malformed output shapes into tool calls, executes `final_answer` locally, and sends non-final calls to `execute_tool_call`. If the model emits multiple tool calls, the implementation executes them through a `ThreadPoolExecutor`, which is risky for stateful environments unless all calls are independent. In the run, EnvScaler had 230 tasks with multi-call action steps and 717 multi-call steps.

Tool errors are recorded as observations, but there is no schema-visible repair policy, no bounded retry advisory, no consecutive-repeat detector, no empty-action recovery, and no completion gate. Empty action steps are accepted as "No observations" rather than converted into a repair request. Terminal behavior is also permissive: `final_answer` or a terminal tool can end execution without a structured verification pass over remaining requirements.

#### 1.4 Memory Module Implementation

The memory provider is a lightweight short-term plus long-term system. BEGIN phase may retrieve and synthesize long-term strategic/operational memories if enabled. IN phase auto-extracts key facts from the current transcript and provides short-term memory every configured interval. It stores lessons only from successful trajectories.

The observed memory guidance is compact and often useful for direct execution, but it is not phase-safe enough. It can synthesize broad guidance such as providing a likely answer when direct evidence is lacking, which contributes to unsupported QA finalization. More importantly, the short-term extractor reads the full transcript and can convert planned or intended actions into "already done" facts. In trajectory `20.json`, memory states that maintenance record `MR-006` was added even though the action trace only queried history and never executed the add-record call.

Memory is a secondary contributor rather than the dominant owner. The dominant failures come from unstructured action execution, missing verification gates, and weak plan/action state transfer.

### PART 2: FAILURE MODE ANALYSIS

#### Failure Mode 1: Planned Actions Are Not Executed But Become Apparent Facts

- **Name:** Planning-to-action execution gap with memory contamination
- **Frequency / importance:** High for EnvScaler; 654 of 659 EnvScaler tasks had a plan containing tool calls, 597 had at least one plan tool call not executed as written, and 626 had a first actual call different from the first planned call.
- **Symptom:** The agent skips planned state-changing calls, later acts as if they succeeded, and completes with partial state.
- **Mechanism:** Planning emits executable-looking JSON/tool calls, but the action loop treats the plan only as transcript text. Memory then extracts from the plan/history as if intended actions were completed.
- **Generalized capability gap:** No typed `required_action -> observed_completion` interface between Planning, Action, and Memory.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Memory
- **Evidence:** `20.json` planned a maintenance-record creation for `EB128A`; the action trace instead queried history, saw only `MR-001`, never added `MR-006`, and memory later said `MR-006` had been added. The run completed at EnvScaler score `0.5789`.
- **Generalization rationale:** Any stateful or multi-step task can fail when intended actions and observed state changes are not separated.
- **Confidence:** High

#### Failure Mode 2: No Stateful Task Ledger Or Completion Gate

- **Name:** Premature completion after partial state mutation
- **Frequency / importance:** Dominant EnvScaler failure. Only 30 of 659 EnvScaler tasks reached exact score `1.0`; 480 were partial and 149 scored zero. `complete_task` was called in 510 EnvScaler tasks, including 480 below exact success.
- **Symptom:** The agent calls `complete_task` or reports completion while required updates remain undone.
- **Mechanism:** The action loop relies on the model's self-assessment rather than a structured checklist of requested state mutations and confirmed tool observations.
- **Generalized capability gap:** Missing stateful execution ledger with required operations, dependencies, confirmation observations, and final preflight.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** `20.json` missed `RW490Z` usage update, `BK202` location move, and `EB128A` record creation before `complete_task`. `752.json` made many correct edits but continued into unrelated checks and still scored `0.0`.
- **Generalization rationale:** Stateful APIs, workflow automation, shopping, scheduling, and database-update tasks all need a completion gate independent of model confidence.
- **Confidence:** High

#### Failure Mode 3: Error Repair Loops Repeat Failed Calls Or Invent Tools

- **Name:** Weak schema-aware repair and low-value retry control
- **Frequency / importance:** High. EnvScaler had 162 tasks with unknown-tool errors, 513 with `success: false` observations, 497 with repeated identical calls, and 122 with empty action steps. ToolHop had schema/error observations in 66 tasks and repeated calls in 58 tasks.
- **Symptom:** After failures, the agent repeats the same call, invents unavailable tools, or ends without using a useful alternative.
- **Mechanism:** The prompt asks for repair, but the action module has no closed-set schema visibility in planning, no retry budget advisory, no consecutive-repeat detector, and no reliable strategy switch after equivalent failures.
- **Generalized capability gap:** Missing execution-level error taxonomy and repair policy.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** `480.json` repeatedly called `get_location_by_address` and `create_incident`, invented `create_location`, and ended with a task-failed message. `175.json` repeated the same invalid `date_calculator` call many times after the tool said the date format was invalid.
- **Generalization rationale:** Tool-rich tasks frequently include missing entities, schema quirks, and unavailable affordances; robust harnesses need general error arbitration, not task-specific fixes.
- **Confidence:** High

#### Failure Mode 4: Short QA Stops Before Evidence Is Sufficient

- **Name:** Under-decomposed evidence chain and unsupported finalization
- **Frequency / importance:** High for SearchQA and meaningful for ToolHop. SearchQA had 215 wrong answers out of 325; 154 wrong SearchQA cases used at most one tool call, and 195 used at most two. ToolHop had 116 wrong out of 258; 17 wrong cases used at most two tool calls.
- **Symptom:** The agent performs one broad lookup or weak relation query, then finalizes a guessed or hedged answer.
- **Mechanism:** Planning does not require an explicit evidence-chain target or "known/unknown/next" checkpoint, and action has no evidence sufficiency test before final answer.
- **Generalized capability gap:** Missing multi-hop evidence plan with stop criteria tied to observed facts.
- **Primary module owner:** Planning
- **Secondary contributor:** Action
- **Evidence:** `210.json` used one broad search for translation counts and answered with a hedge instead of the raw gold name. `332.json` searched a wrong/ambiguous Deanna/Koleen Brooks path and answered `141` instead of the hometown population `15,023`. `1015.json` stopped after two failed relationship queries and answered that the information was unavailable.
- **Generalization rationale:** Multi-hop QA, entity disambiguation, and lookup-plus-transform tasks transfer across domains and require explicit evidence chain management.
- **Confidence:** High

#### Failure Mode 5: Useful Observations Are Not Arbitrated Before Final Answer

- **Name:** Observation handling loses or overrides decisive evidence
- **Frequency / importance:** Medium-high. ToolHop wrong cases include many long traces with useful partial observations; 62 wrong ToolHop cases used at least five tool calls and 18 used at least ten.
- **Symptom:** The agent obtains the right intermediate or final value, then finalizes a contradictory answer or transforms the wrong entity.
- **Mechanism:** The action module has no evidence table, no contradiction check, and no final-answer arbitration over latest successful observations.
- **Generalized capability gap:** Missing observation arbitration protocol for selecting the supported value from a trace.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** `151.json` observed `date_calculator -> 1878-12-28`, then produced "cannot be determined." `171.json` failed to find the sibling and sorted the original person's first name. `889.json` failed to retrieve the paternal grandmother and sorted the father's title-derived last name instead.
- **Generalization rationale:** Any multi-step task with lookup failures and transformations can drift to a nearby but unsupported entity unless observations are explicitly bound to the target variable.
- **Confidence:** High

#### Failure Mode 6: Final Answer Canonicalization Is Too Weak

- **Name:** Raw-answer formatting and canonical form mismatch
- **Frequency / importance:** Medium. SearchQA had 38 wrong cases with partial/subanswer match (`subem > 0` but exact answer incorrect); ToolHop had 10 such cases.
- **Symptom:** The content is close or partially correct but not in the evaluator-required raw canonical form.
- **Mechanism:** Final-answer policy says raw answer only, but no canonicalization step checks aliases, required granularity, number words, units, capitalization, dates, or full-name requirements against the question.
- **Generalized capability gap:** Missing final-answer normalizer and question-specific answer-type check.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** `660.json` answered `USA` for gold `United States`; `153.json` answered `2` for gold `two`; `208.json` answered only `Taylor Swift` when the expected answer included Taylor Swift on vocals and Keith Urban on guitar.
- **Generalization rationale:** Canonical answer forms vary across QA datasets and domains; a general answer-type check transfers better than hard-coded aliases.
- **Confidence:** Medium

#### Failure Mode 7: Parallel Execution Is Unsafe For Stateful Operations

- **Name:** Unverified multi-tool parallelism on mutable state
- **Frequency / importance:** Medium for EnvScaler. 230 EnvScaler tasks had at least one multi-call action step, with 717 multi-call steps total.
- **Symptom:** Multiple stateful calls are issued in one action step without confirming dependencies or intermediate state.
- **Mechanism:** `ToolCallingAgent.step` executes all emitted non-final tool calls concurrently. The prompt says one tool call by default, but the implementation permits parallel execution without independence checks.
- **Generalized capability gap:** Missing action-side sequential commit discipline for mutable environments.
- **Primary module owner:** Action
- **Secondary contributor:** Builder/Wiring
- **Evidence:** `690.json` issued category add/remove in the same step and scored `0.0`; `420.json` issued multiple preference mutations together, some failing because IDs were invalid. Some multi-call steps are harmless reads, but no module distinguishes reads from state mutations.
- **Generalization rationale:** Stateful APIs often require read-after-write verification and dependency ordering; unsafe parallelism can corrupt or skip intermediate checks across domains.
- **Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Planning-to-action execution gap with memory contamination | Cross-Module Interface | Memory | `planning_module/provider.py -> action_module/provider.py -> memory_module/provider.py` | EnvScaler plan tools not executed in 597/654 plan-with-tool cases; `20.json` memory says `MR-006` was added when it was only planned | Planned intent and observed state are distinct in all tool/state tasks | High | Add typed plan items and only let memory mark facts from successful observations |
| Premature completion after partial state mutation | Action | Planning | `action_module/provider.py`, `Agents/agents.py`, `single_react` prompt boundary | EnvScaler exact success only 30/659; 480 partial; `complete_task` called below exact success in 480 cases | Stateful tasks require a completion ledger independent of model confidence | High | Add required-operation ledger and final preflight before terminal tools |
| Weak schema-aware repair and low-value retry control | Action | Planning | `Agents/agents.py::step`, `execute_tool_call`, action prompt | EnvScaler unknown tool in 162 tasks, repeated calls in 497; ToolHop schema/error in 66 and repeated calls in 58 | Tool APIs always produce recoverable failures that need structured repair while preserving valid retries after changed preconditions | High | Add closed-set schema visibility, soft repeat advisory, error taxonomy, and bounded repair strategy |
| Under-decomposed evidence chain and unsupported finalization | Planning | Action | `planning_module/provider.py`, planning prompt, final-answer boundary | SearchQA 215/325 wrong; 154 wrong with <=1 tool call; `210.json`, `332.json`, `1015.json` | Multi-hop lookup tasks need explicit known/unknown chains across domains | High | Require evidence targets, disambiguation checkpoints, and answer sufficiency tests |
| Observation handling loses or overrides decisive evidence | Action | Planning | `Agents/agents.py::step`, action prompt, final-answer prompt | `151.json` observed `1878-12-28` then answered unknown; `171.json` and `889.json` transformed wrong entities | Transform tasks require binding observations to target variables | High | Maintain evidence table and final arbitration over latest successful observations |
| Raw-answer formatting and canonical form mismatch | Action | Planning | `action_module/prompts/toolcalling_agent.yaml`, final-answer prompt | SearchQA 38 subanswer-only wrong cases; ToolHop 10; `660.json`, `153.json`, `208.json` | Evaluators and users expect answer-type-specific forms beyond semantic closeness | Medium | Add final answer-type/canonicalization check without broad rewriting |
| Unverified multi-tool parallelism on mutable state | Action | Builder/Wiring | `Agents/agents.py::step`, `action_module/provider.py` | 230 EnvScaler tasks had multi-call steps; `690.json` scored zero after same-step state mutations | Mutable APIs need dependency-aware sequencing across environments | Medium | Default state-changing tools to sequential execution unless independence is proven |

### PART 4: STRENGTHS TO PRESERVE

- The single-agent ReAct loop in Action is simple and often efficient; ToolHop success `460.json` solved a lookup-transform-finalize chain in three tool calls, so generation should preserve low overhead for straightforward tasks.
- The action prompt's strict JSON schema guidance is valuable; most SearchQA and ToolHop trajectories produced valid final answers (`has_valid_answer = 1.0`), so generation should not replace it with looser free-form output.
- The planning prompt encourages concise execution; successful SearchQA `302.json` used two targeted searches and finalized the raw year, so generation should keep short plans for simple QA while adding structured checkpoints only where needed.
- The memory module provides compact reusable guidance; successful traces show it can reinforce literal instruction following, so generation should preserve compact memory injection while making extraction observation-grounded.
- The current tool loader/wiring works across EnvScaler, SearchQA, and ToolHop with no run-level crashes; generation should preserve compatibility with `ActionContext`, benchmark tool loading, and existing provider names.
- The action loop can recover from some tool errors by switching behavior; EnvScaler `860.json` recovered from a wrong journal-entry ID by listing entries and using the discovered UUID, so generation should strengthen this behavior rather than suppressing all retries.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Observation-Grounded Stateful Task Ledger]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`, `Agents/agents.py`, action prompt boundary
- **Problem:** EnvScaler tasks often complete after partial state mutation.
- **Mechanism:** Maintain a compact ledger of required operations, dependencies, attempted tool calls, successful observations, failed observations, and remaining items; require a final preflight before `complete_task`.
- **Why This Module Owns It:** The action loop sees every tool call and observation and owns terminal tool submission.
- **Generalization Rationale:** Any mutable environment needs confirmation that requested changes actually occurred.
- **Complexity:** Medium
- **Expected Impact:** Largest expected gain on EnvScaler and any future stateful benchmark.
- **Risk:** A poorly implemented ledger could over-constrain simple tasks or add token bloat.

**[Priority 2: Typed Planning-To-Action Contract]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py -> Agents/agents.py`
- **Problem:** Plans can contain executable-looking actions that are not executed but later treated as facts.
- **Mechanism:** Convert planning output into typed goals or checklist items, not raw tool calls; mark items complete only from action observations.
- **Why This Module Owns It:** Planning creates intended steps, but Action and Memory consume them through untyped transcript text.
- **Generalization Rationale:** Separating intention from observation is reusable across stateful, search, and transform tasks.
- **Complexity:** Medium
- **Expected Impact:** Reduces plan-as-fact errors and improves progress summaries.
- **Risk:** Too much structure could make easy one-hop tasks slower if not optional/compact.

**[Priority 3: Error Taxonomy And Repair Controller]**
- **Target Module:** Action
- **Owner Path:** `Agents/agents.py::step`, `execute_tool_call`
- **Problem:** Repeated failed calls, invented tools, schema mismatches, and empty action steps waste budgets and cause wrong finals.
- **Mechanism:** Classify errors as unknown tool, schema/argument error, entity-not-found, empty model output, or execution failure; flag consecutive identical retries, but allow the same real tool call after new evidence or state changes make it valid; ask for a schema-aware repair step using visible available tool schemas.
- **Why This Module Owns It:** Tool execution and error observations are produced inside Action.
- **Generalization Rationale:** Tool schema and entity errors recur in every tool-using domain.
- **Complexity:** Medium
- **Expected Impact:** Improves EnvScaler and ToolHop robustness, especially long failure traces.
- **Risk:** Over-aggressive retry blocking could prevent valid repeated polling, confirmation calls, or EnvScaler recovery after preconditions are repaired; keep repeat handling advisory.

**[Priority 4: Evidence Chain Planner For QA And ToolHop]**
- **Target Module:** Planning
- **Owner Path:** `planning_module/provider.py`, planning prompt
- **Problem:** Short QA often finalizes after one broad or ambiguous lookup.
- **Mechanism:** Require plans to name target variable, required supporting facts, disambiguation needs, and final transformation; summaries should explicitly list known, unknown, and next.
- **Why This Module Owns It:** The first missing-hop structure is a planning responsibility.
- **Generalization Rationale:** Multi-hop evidence decomposition transfers across people, dates, geography, numeric, and relation questions.
- **Complexity:** Low
- **Expected Impact:** Raises SearchQA and ToolHop correctness without changing tool APIs.
- **Risk:** If too verbose, it could increase cost and reduce directness on trivial questions.

**[Priority 5: Final Observation Arbitration And Canonicalization]**
- **Target Module:** Action
- **Owner Path:** `action_module/prompts/toolcalling_agent.yaml`, final-answer prompt
- **Problem:** The agent sometimes ignores decisive observations or returns a non-canonical answer.
- **Mechanism:** Before final answer, bind the proposed answer to the exact observation(s), check whether a later observation contradicts it, and normalize only the requested answer type.
- **Why This Module Owns It:** Final answer submission and observation transcript reading happen in Action.
- **Generalization Rationale:** Supported-answer checks apply to all short-answer and transform tasks.
- **Complexity:** Low
- **Expected Impact:** Fixes cases like `151.json` and reduces subanswer-only failures.
- **Risk:** Excessive normalization could damage evaluator-accepted variants.

**[Priority 6: State-Mutation Sequencing Guard]**
- **Target Module:** Action
- **Owner Path:** `Agents/agents.py::step`
- **Problem:** Multiple emitted calls are executed concurrently even in mutable environments.
- **Mechanism:** Execute one state-changing tool per step unless a tool is known read-only or the harness can prove independence; keep parallelism for read-only lookups.
- **Why This Module Owns It:** The action loop chooses execution mode for tool calls.
- **Generalization Rationale:** Sequential commit discipline is reusable for APIs, databases, scheduling, shopping, and simulated environments.
- **Complexity:** Medium
- **Expected Impact:** Reduces race-like and dependency-order failures on EnvScaler.
- **Risk:** May slow tasks that benefit from independent parallel reads.

### PART 6: REPRESENTATIVE EVIDENCE

- `20.json` failed partially on EnvScaler with score `0.5789`: the plan proposed adding `MR-006`, the action trace never executed that add-record call, memory later recorded it as completed, and the agent called `complete_task` while several required changes remained.
- `480.json` failed on EnvScaler with score `0.0`: the agent repeatedly queried the same missing address, invented unavailable `create_location`, retried failed `create_incident`, and ended with a task-failed message rather than a repaired valid workflow.
- `210.json` failed on SearchQA with score `0.0`: one broad search did not establish the translation-count comparison, but the agent finalized a hedged paragraph instead of raw `Paul Benjamin Auster`.
- `1015.json` failed on ToolHop with score `0.0`: two relationship queries failed and the agent answered that the information was unavailable, rather than changing relation wording or following an alternate evidence path to the parole date.
- `151.json` failed on ToolHop with score `0.0`: the trace observed the correct date calculation `1878-12-28`, then inserted an empty action step and finalized that the answer could not be determined.
- Successful `460.json` shows behavior to preserve: the agent identified the film with `film_search`, queried the co-star with `film_cast_query`, extracted the first name, and called `final_answer` with the supported raw value.
- Bucket-level statistics materially shape the diagnosis: EnvScaler average score was `0.4980` with exact score `1.0` in only 30 of 659 tasks; SearchQA answer correctness was `0.3385` with 154 wrong cases using at most one tool call; ToolHop answer correctness was `0.5504` with 66 schema/error traces and 58 repeated-call traces.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Plans must distinguish intended actions, required evidence, and final-answer criteria; do not emit executable-looking tool calls unless the action module can track them as pending, not completed.
- [Planning] For QA and ToolHop, include target variable, required hops, disambiguation checks, and final transformation in a compact known/unknown/next format.
- [Action] Maintain a task ledger for stateful tasks and require observation-backed completion before `complete_task` or `final_answer`.
- [Action] Add schema/error repair logic with visible available tool schemas and soft duplicate-failure advisories; allow identical real-tool retries after a new observation changes state, arguments, or strategy.
- [Action] Treat empty action outputs as repairable contract violations, not as valid "No observations" progress.
- [Action] Execute state-changing tools sequentially unless read-only independence is explicit.
- [Memory] Extract short-term facts only from successful observations, not from plans, model intentions, or unexecuted proposed calls.
- [Memory] Avoid guidance that encourages unsupported "most likely" answers unless it also requires labeling and only when the benchmark permits non-raw answers.
- [Builder] Preserve the existing provider names, metadata fields, and `ActionContext` compatibility.
- [Interface] Add an observation-grounded path from Action back to Planning summaries so progress state reflects completed, failed, and pending items.
- [Preserve] Keep the concise ReAct loop and strict JSON contract for simple tasks where one or two reliable tool calls are enough.
- [Avoid] Do not add task-specific patches for `MR-006`, Selena Quintanilla, Deanna Brooks, date calculators, or any observed benchmark entity; repair the general harness capabilities instead.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
