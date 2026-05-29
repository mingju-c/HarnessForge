### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

`base_harness` is assembled in a fixed way by `builder.py`:

- `HARNESS_NAME = "base_harness"`.
- `PLANNING_SYSTEM = "generic_planning"`, injected into `ActionContext.kwargs["planning_class"]` through `PlanningClass`.
- `ACTION_SYSTEM = "single_react"`, and `get_provider()` returns `ActionProvider`.
- `DEFAULT_BENCH_TYPE = "generic"`; if the caller does not pass a bench type, the builder only applies this generic default.
- `DEFAULT_MEMORY_SYSTEM = "lightweight_memory"`; the metadata recommends lightweight memory, but the builder itself does not directly instantiate a memory provider.
- The builder binds the `agent` reference of `process_tool`, `end_process_tool`, `delete_memory_tool`, `executor_tool`, and `refine_tool` to the final agent; if `vector_tool` exists, it is written into `agent.memory`.

The description file is broadly consistent with the implementation: this is a fallback combination of `generic_planning + single_react + lightweight_memory`. The important implementation fact is that the builder does not add task-type-specific execution control, schema prechecks, final-answer gating, or EnvScaler subtask completion checks; those behaviors fully depend on the planning/action/memory providers and the underlying `ToolCallingAgent`.

#### 1.2 Planning Module Implementation

`planning_module/provider.py` is a minimal `BasePlanning` subclass:

- `topology_initialize()` calls the model once to generate the initial plan and appends memory guidance to the planning input.
- The initial planning prompt asks for the "shortest executable plan" and explicitly instructs the model not to output the final answer during planning.
- `adaptation()` periodically writes historical action steps into a summary prompt, producing a short summary and next-step suggestions.
- Planning only writes the plan and summary into `AgentMemory.steps`; it does not maintain a structured checklist, unfinished subgoals, evidence provenance, tool-schema bindings, or preconditions for final answers.
- Planning influences action only indirectly: the action step sees the task, plan, memory, and historical observations, but there is no machine-readable boundary between "verified facts / unverified guesses / pending actions."

The trajectories show that the planning prompt's tendency toward "very short, finalize quickly" is over-executed by the model. In multiple SearchQA/ToolHop failures, the plan explicitly writes `final_answer: ...` or "Finalize ..." and supplies an unobserved answer, such as `460.json` and `1116.json`. This indicates that planning does not prevent premature commitment and does not encode the constraint "there must first be a tool observation" into an action-checkable state.

#### 1.3 Action Module Implementation

`action_module/provider.py` is a single-agent ReAct topology:

- `build_affordance()` loads task tools with `load_bench_tools(bench_type, db_path, context)`.
- `build_specification()` always uses the `single_react` prompt.
- `build_organization()` directly calls `create_agent(...)`; there is no coordinator/worker/verifier/repairer, no parallel execution management, and no independent verifier.
- The action prompt requires strict JSON, mostly one tool call at a time, exact schema matching, parameter repair after errors, and calling `final_answer` after evidence support or `complete_task` for EnvScaler.

The actual trajectories show that the action prompt has the right intent, but lacks hard execution-side constraints:

- There is no schema preflight; in EnvScaler, 172 files contain `Unknown tool`, 35 files contain `unexpected keyword argument`, and in ToolHop, 31 files contain schema/correct-input errors.
- There is no error-repair state machine; 423/659 EnvScaler tasks contain consecutive repeated calls, 497/659 contain any repeated calls, and 68/258 ToolHop tasks contain consecutive repeated calls.
- There is no evidence gate; 132 erroneous SearchQA samples and 31 erroneous ToolHop samples submit wrong answers without any non-terminal evidence tool call.
- There is no EnvScaler subgoal completion check; 198/659 EnvScaler tasks have no terminal action, and another 21 tasks call `complete_task` but receive a score of 0.
- There is no final-answer canonicalization layer; if a tool returns `01110100` while the gold answer expects `1110100`, the action module directly submits the tool format and lacks a final trimming step based on task specifications.

#### 1.4 Memory Module Implementation

`memory_module/provider.py` implements lightweight two-level memory:

- The BEGIN phase can retrieve long-term memory, but `enable_longterm_provision = False` by default; evaluation trajectories still show memory guidance, indicating that the runtime configuration may have enabled begin guidance or that an upper framework injected memory.
- During the IN phase, short-term key facts are automatically extracted at every step, and short-term memory is provided every 3 steps.
- Long-term memory is extracted only from successful trajectories; failed trajectories are not added as long-term experience.
- Short-term extraction summarizes "key information" from the current context delta, but it does not separate tool observations, model thoughts, and planning guesses into sources with different trust levels.

Memory guidance introduces two risks. First, cold-start strategic memory contains "Execute directly rather than over-planning," which may amplify premature finalization on short-answer tasks. Second, short-term memory can compress the model's own unverified reasoning into "Key Information & Constraints"; in `460.json`, the action module claimed an incorrect movie and person without calling any evidence tool, and the subsequent memory guidance also recorded those false facts. Memory is not the main cause of most failures, but because it lacks provenance labels, it can solidify action-side erroneous commitments into later context.

### PART 2: FAILURE MODE ANALYSIS

**Name:** Unobserved plan/memory content treated as sufficient evidence

- **Frequency / importance:** High. Among 325 SearchQA samples, 146 have no non-terminal tool call, of which 132 are wrong; among 258 ToolHop samples, 38 have no non-terminal tool call, of which 31 are wrong. In SearchQA, 117 plans mention `final_answer/complete_task`; in ToolHop, 68 plans do so.
- **Symptom:** The agent directly submits a short answer without calling search or evidence tools; the answer is often a hallucinated entity or a commonsense sentence.
- **Mechanism:** Planning is instructed to produce a short plan and finish quickly, but it has no structured "evidence gap"; after action sees a candidate answer in plan/memory, it does not check whether that answer came from a tool observation.
- **Generalized capability gap:** Missing Planning -> Action evidence-provenance interface and action-side final-answer evidence gate.
- **Primary module owner:** Cross-Module Interface.
- **Secondary contributor:** Planning, Action, Memory.
- **Evidence:** In `460.json`, the plan writes `Final_answer: Tom`, after which action directly calls `final_answer("Tom")`; the gold answer is `Saoirse`. In `1116.json`, the agent likewise submits `Robert B. Mercer` without any tool call, while the gold answer is `Peter F. Paul`.
- **Generalization rationale:** Any task requiring external evidence, database queries, or multi-hop retrieval faces the risk that a "planning guess" looks like an answer; this is not limited to the current QA prompts.
- **Confidence:** High.

**Name:** Tool schema and tool-name repair is prompt-only, not stateful

- **Frequency / importance:** High. In EnvScaler, 172 files contain `Unknown tool` and 35 contain `unexpected keyword argument`; in ToolHop, 31 files contain schema/correct-input errors and 14 contain missing required parameters.
- **Symptom:** The agent invents tool names, passes wrong parameter names, or repeats the same error pattern even after the error message gives the correct schema.
- **Mechanism:** The action prompt asks for schema discipline, but the provider does not check tool names/arguments before invocation and does not parse error observations into a "contract delta that must be fixed next."
- **Generalized capability gap:** The action module lacks a general schema preflight and tool-error repair loop.
- **Primary module owner:** Action.
- **Secondary contributor:** Planning.
- **Evidence:** In `398.json`, the first step calls the nonexistent `check_counselor_availability`, and later `cancel_appointment` repeatedly carries the illegal `new_status` argument. In `1103.json`, the first call to `monarch_reign_analyzer` lacks `monarchs_data`.
- **Generalization rationale:** All schema-rich tool environments will encounter similar tool names, similar parameter names, or missing required fields.
- **Confidence:** High.

**Name:** Low-value repeated exploration after failed or sufficient observations

- **Frequency / importance:** High. 423/659 EnvScaler tasks contain consecutive repeated calls, 497/659 contain repeated calls, and 68/258 ToolHop tasks contain consecutive repeated calls.
- **Symptom:** The agent repeatedly calls the same validation tool, the same failing tool, or the same already-completed operation, exhausting the step budget while still not completing the main task.
- **Mechanism:** The action loop does not record recent failed call signatures, already satisfied constraints, or completed state mutations; the summary only provides short textual suggestions and cannot prevent repetition.
- **Generalized capability gap:** The action module lacks an observation-to-state ledger and repetition guard.
- **Primary module owner:** Action.
- **Secondary contributor:** Planning.
- **Evidence:** In `1142.json`, during a dispute task, the agent repeatedly alternates between `validate_dispute_billing_item_relation` and `get_operator_by_id`, makes 32 non-terminal calls, and never calls `complete_task`. In `480.json`, it repeatedly tries multiple already-existing incident IDs, then repeatedly calls unknown or low-value incident-listing tools.
- **Generalization rationale:** Long-horizon database mutation, API orchestration, and multi-hop tool chains all need to track "what is already known, what already failed, and what is already complete."
- **Confidence:** High.

**Name:** EnvScaler long-horizon tasks lack explicit completion ledger

- **Frequency / importance:** High. EnvScaler's average score is 0.3978, with only 15/659 full-score tasks; 198/659 have no terminal action, and 21 call `complete_task` but score 0.
- **Symptom:** The agent either fails to call `complete_task` or calls it too early; even when local operations succeed, the final state still misses key mutations.
- **Mechanism:** Planning does not decompose complex tasks into a verifiable checklist, action does not maintain a mutation ledger, and there is no item-by-item state confirmation before termination.
- **Generalized capability gap:** Planning + Action lack subgoal tracking and terminal readiness checks for state-change tasks.
- **Primary module owner:** Cross-Module Interface.
- **Secondary contributor:** Planning, Action.
- **Evidence:** In `398.json`, the agent successfully books an appointment, cancels part of an appointment, and updates contact information, but omits or mishandles the availability slot and cancellation status, then calls `complete_task` and receives 0. In `480.json`, it falls entirely into a loop around incident IDs and unknown listing tools and never reaches a terminal action.
- **Generalization rationale:** All multi-step environment state-change tasks require an explicit "requirement -> tool action -> observation confirmation -> termination condition" mapping.
- **Confidence:** High.

**Name:** Final-answer canonicalization is under-specified

- **Frequency / importance:** Medium. SearchQA has 17 wrong samples with `subem=1.0`; ToolHop has 3 wrong samples with `subem=1.0`.
- **Symptom:** The agent finds content containing the correct short answer, but the final answer is too long, incorrectly formatted, or preserves the tool's default format.
- **Mechanism:** The action prompt asks for a raw answer, but there is no final format trimmer; planning also does not set a canonicalization checklist for answer type.
- **Generalized capability gap:** The action module lacks final-answer normalization based on task wording and observed value.
- **Primary module owner:** Action.
- **Secondary contributor:** Planning.
- **Evidence:** In `461.json`, the agent submits `Cognizant Technology Solutions Corporation` while the gold answer is `Cognizant`; in `1103.json`, it submits `hip` while the gold answer is `hi`; in `1092.json` and `828.json`, it submits 8-bit binary while the gold answer removes the leading 0.
- **Generalization rationale:** Short-answer benchmarks, API argument extraction, and numeric/unit answers can all lose credit because of extra text, aliases, leading zeros, or formatting requirements.
- **Confidence:** Medium.

**Name:** Empty action steps / no-op trajectories are not repaired

- **Frequency / importance:** Medium to high. EnvScaler has 72 no-plan/no-tool samples, SearchQA has 14, and ToolHop has 10; these trajectories contain only 3 empty action steps.
- **Symptom:** In `agent_trajectory`, the action step has `tool_calls=[]`, `obs=None`, and `think=None`, with no final answer and no error record.
- **Mechanism:** `ToolCallingAgent` or the action provider does not force JSON repair, retry with an explicit format reminder, or a terminal fallback when the model output is empty or unparsable.
- **Generalized capability gap:** The action module lacks output-contract violation recovery.
- **Primary module owner:** Action.
- **Secondary contributor:** Builder/Wiring.
- **Evidence:** `362.json`, `336.json`, `328.json`, and `307.json` are all complex EnvScaler tasks that receive 0 after 3 empty action steps; `332.json` and `356.json` show the same no-op trajectory pattern in QA/ToolHop.
- **Generalization rationale:** Small models or format-unstable models can produce empty responses, non-JSON, or unparsable outputs in all strict JSON agent loops.
- **Confidence:** High.

**Name:** Memory guidance lacks provenance and phase-aware caution

- **Frequency / importance:** Medium. In direct statistics, memory is not the main failure bucket, but representative trajectories show that memory can write unverified reasoning as key facts.
- **Symptom:** Memory guidance encourages direct execution and stores the model's own incorrect assertions in short-term memory.
- **Mechanism:** Memory extraction does not distinguish observation-backed facts from think/plan guesses and does not strengthen "verify before final" guidance in the BEGIN phase for evidence-required QA.
- **Generalized capability gap:** The memory module lacks provenance-aware summarization and task-phase routing.
- **Primary module owner:** Memory.
- **Secondary contributor:** Cross-Module Interface.
- **Evidence:** In `460.json`, action has no evidence-tool observation, yet memory guidance lists the incorrect movie and person as "Key Information & Constraints."
- **Generalization rationale:** Once unverified information is compressed into memory as fact, later multi-step tasks become harder to correct.
- **Confidence:** Medium.

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Unobserved plan/memory content treated as sufficient evidence | Cross-Module Interface | Planning, Action, Memory | `planning_module/provider.py -> action_module/provider.py`, memory injection boundary | SearchQA 132 wrong zero-evidence finals; ToolHop 31 wrong zero-evidence finals; `460.json`, `1116.json` | Any evidence-dependent task can confuse plan guesses with verified observations | High | Add evidence provenance state and forbid final answer unless answer value is grounded in tool observation or explicitly self-contained task |
| Tool schema and tool-name repair is prompt-only | Action | Planning | `action_module/provider.py`, `single_react` prompt/tool-call loop | EnvScaler 172 files with `Unknown tool`, 35 with `unexpected keyword`; ToolHop 31 schema errors | Tool/API-heavy environments always require contract repair beyond prompt instructions | High | Add schema preflight, nearest valid tool suggestion use, and structured repair after tool errors |
| Low-value repeated exploration after failed or sufficient observations | Action | Planning | `action_module/provider.py`, action loop state | EnvScaler 423 consecutive-repeat tasks; ToolHop 68 consecutive-repeat tasks; `1142.json`, `480.json` | Multi-step tool work needs a ledger of failed calls, known facts, and completed actions | High | Add recent-call signature memory, failed-call cooldown, and observation-to-state ledger |
| EnvScaler long-horizon tasks lack explicit completion ledger | Cross-Module Interface | Planning, Action | Planning checklist -> Action mutation ledger -> terminal readiness | EnvScaler avg 0.3978, only 15/659 full score; 198 no terminal; 21 terminal score 0 | Long-horizon state mutation tasks require explicit subgoal completion checks | High | Generate task checklist and require terminal only after each required mutation has success evidence |
| Final-answer canonicalization under-specified | Action | Planning | `action_module/prompts/toolcalling_agent.yaml`, final answer path | SearchQA 17 wrong with `subem=1.0`; ToolHop 3 wrong with `subem=1.0`; `461.json`, `1092.json`, `828.json` | Short-answer tasks often require exact normalized spans, units, or binary/string formatting | Medium | Add final-answer normalization checklist and compact transform step before final submission |
| Empty action steps / no-op trajectories are not repaired | Action | Builder/Wiring | `action_module/provider.py`, ToolCallingAgent output parsing boundary | EnvScaler 72 no-plan/no-tool cases; SearchQA 14; ToolHop 10; `362.json`, `332.json`, `356.json` | Strict JSON loops with small models need recovery from unparsable or empty model outputs | High | Add output-contract retry with schema reminder and fail-open final/tool fallback where applicable |
| Memory guidance lacks provenance and phase-aware caution | Memory | Cross-Module Interface | `memory_module/provider.py`, memory injection into planning/action | `460.json` memory records unsupported false facts as key information | Memory can amplify any unverified model guess across later steps | Medium | Tag memory items by source and only promote tool-observed facts as key constraints |

### PART 4: STRENGTHS TO PRESERVE

- Preserve the single-agent ReAct loop in Action for simple QA, because successful SearchQA examples such as `30.json` solve the task with one search plus `final_answer`, and adding heavy orchestration to every task could reduce efficiency.
- Preserve the action prompt's strict JSON and one-tool-by-default contract, because successful ToolHop examples such as `559.json` and `772.json` use compact sequential calls without unnecessary parallelism.
- Preserve the planning module's short decomposition for simple multi-hop tasks, because `772.json` cleanly follows identify-author -> education -> count letters, and generation should not regress into verbose speculative plans.
- Preserve Action's ability to adapt after a failed lookup, because `772.json` recovers from two failed `author_lookup` calls and switches to a biographical retriever before finalizing correctly.
- Preserve the EnvScaler terminal convention in Action, because full-score examples such as `167.json` and `438.json` call `complete_task` after successful state updates, and replacing the terminal contract would break evaluator compatibility.
- Preserve the lightweight memory module's compactness, because prompt bloat is already a risk for qwen3-4b-base, and repairs should add provenance rather than long generic guidance.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Evidence-Gated Finalization Interface]**

- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py -> action_module/provider.py`, plus memory injection boundary
- **Problem:** SearchQA/ToolHop frequently submit answers from plan or model prior without evidence.
- **Mechanism:** Represent candidate answers with provenance labels: `tool_observed`, `computed_from_observation`, `plan_guess`, `memory_hint`, `model_prior`. Permit `final_answer` only for `tool_observed` or `computed_from_observation`, except explicitly self-contained deterministic tasks.
- **Why This Module Owns It:** The failure emerges because planning/memory text is visible to action but not distinguished from observations.
- **Generalization Rationale:** Evidence provenance transfers across search, database, API, and state-change tasks.
- **Complexity:** Medium
- **Expected Impact:** Should reduce the 163 wrong zero-evidence QA/ToolHop finals and prevent memory-amplified hallucinations.
- **Risk:** If too strict, agent may over-search on genuinely self-contained format/conversion tasks.

**[Priority 2: Action Schema Preflight and Error Repair Loop]**

- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`, `action_module/prompts/toolcalling_agent.yaml`, ToolCallingAgent tool-call boundary
- **Problem:** Wrong tool names, wrong argument names, and missing required parameters repeatedly cause failures.
- **Mechanism:** Before executing, validate tool name and argument keys against loaded schemas; when a tool error reports valid schema, inject a compact repair message and block identical invalid signatures.
- **Why This Module Owns It:** Tool selection and concrete argument emission are action responsibilities.
- **Generalization Rationale:** All tool/API environments benefit from contract validation.
- **Complexity:** Medium
- **Expected Impact:** Should reduce EnvScaler `Unknown tool` and `unexpected keyword` failures and ToolHop schema loops.
- **Risk:** Overzealous correction may map a semantically wrong tool to a superficially similar valid tool.

**[Priority 3: EnvScaler Subgoal and Mutation Ledger]**

- **Target Module:** Cross-Module Interface
- **Owner Path:** Planning checklist in `planning_module/provider.py`; action ledger in `action_module/provider.py`
- **Problem:** EnvScaler tasks end incomplete, loop without terminal, or call `complete_task` with missing mutations.
- **Mechanism:** Planning emits a flat checklist of required state changes; action updates each item with `pending/succeeded/failed/blocked` based on tool observations; `complete_task` is allowed only after all required items are succeeded or explicitly impossible with evidence.
- **Why This Module Owns It:** Planning must decompose requirements, while Action must bind observations to completion state.
- **Generalization Rationale:** Any long-horizon state mutation benchmark requires durable progress tracking.
- **Complexity:** Medium
- **Expected Impact:** Should improve EnvScaler full-score rate and reduce both no-terminal and terminal-score-zero cases.
- **Risk:** Checklist extraction errors could cause the agent to ignore implicit constraints if the checklist becomes the only source of truth.

**[Priority 4: Repetition Guard and Observation Triage]**

- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** Repeated failed calls and repeated verification consume step budget.
- **Mechanism:** Track recent call signatures, failure reasons, and facts already retrieved; after one identical failure, force a different argument/tool or summarize why the task is blocked; after sufficient observation, move to finalization or next checklist item.
- **Why This Module Owns It:** Repetition occurs during action execution and observation handling.
- **Generalization Rationale:** Reduces wasted steps in retrieval, API mutation, and multi-hop tool tasks.
- **Complexity:** Low
- **Expected Impact:** Should address the 423 EnvScaler consecutive-repeat cases and many ToolHop repeated schema/data lookups.
- **Risk:** Some idempotent state updates are safe to repeat; the guard should allow repetition only when observation explicitly says retry is needed.

**[Priority 5: Final Answer Canonicalization Gate]**

- **Target Module:** Action
- **Owner Path:** `action_module/prompts/toolcalling_agent.yaml`, final-answer generation path
- **Problem:** Correct evidence is found but final string is not canonical.
- **Mechanism:** Add a short final transform step: read task wording, choose requested granularity, strip explanatory text, normalize aliases/leading zeros/units only when task asks.
- **Why This Module Owns It:** The final answer is submitted by the action loop.
- **Generalization Rationale:** Exact-match tasks across QA, calculation, and API extraction all need answer normalization.
- **Complexity:** Low
- **Expected Impact:** Should recover many `subem=1.0` but `answer_correct=0` cases.
- **Risk:** Incorrect normalization could remove required context or leading zeros when they are semantically meaningful.

**[Priority 6: Provenance-Aware Lightweight Memory]**

- **Target Module:** Memory
- **Owner Path:** `memory_module/provider.py`
- **Problem:** Memory can turn unverified model guesses into "key facts" and reinforce premature finalization.
- **Mechanism:** During short-term extraction, only mark tool observations as facts; label plan/think content as hypotheses; in BEGIN guidance, avoid "execute directly" wording for evidence-required QA unless paired with "first obtain one supporting observation."
- **Why This Module Owns It:** Memory selects and injects guidance, and short-term extraction currently lacks source labels.
- **Generalization Rationale:** Provenance protects all future tasks from stale or hallucinated context.
- **Complexity:** Medium
- **Expected Impact:** Should reduce hallucination reinforcement and improve recovery after wrong intermediate thoughts.
- **Risk:** Over-filtering may omit useful inferred intermediate computations.

### PART 6: REPRESENTATIVE EVIDENCE

- `460.json` / ToolHop / score 0.0: The task asks for the first name of the person opposite Billy Howle in an upcoming Dominic Cooke drama. The plan itself writes `Final_answer: Tom`; action immediately calls `final_answer` with `Tom` without any evidence tool call. Gold is `Saoirse`. This is a Planning -> Action evidence-boundary failure.
- `1116.json` / SearchQA / score 0.0: The task asks for the former lawyer and entrepreneur involved in a civil suit against Bill and Hillary Clinton. The agent performs zero searches and submits `Robert B. Mercer`; gold is `Peter F. Paul`. This supports the zero-evidence finalization diagnosis.
- `398.json` / EnvScaler / score 0.0 with `envscaler_done=1.0`: The agent first calls an unknown tool `check_counselor_availability`, later repeats `cancel_appointment` with illegal `new_status`, eventually repairs part of the call and submits `complete_task`. The terminal call succeeds mechanically, but evaluator score is 0 because required state conditions were not all satisfied.
- `480.json` / EnvScaler / score 0.0 and no terminal: The agent validates location, then repeatedly attempts `create_incident` with existing IDs, calls unknown listing tools, and never reaches `complete_task`. This shows both schema/tool-name failure and missing state ledger.
- `1142.json` / EnvScaler / score 0.0 and no terminal: The agent repeatedly validates the same dispute relation and operator authorization, making 32 non-terminal calls without completing required dispute updates. This is a low-value exploration loop.
- `1103.json` / ToolHop / score 0.5: The agent partially reaches the right entity chain but after relationship lookup failures relies on prior knowledge and submits `hip`; gold is `hi`. This shows both tool repair weakness and final transform/canonicalization weakness.
- `1092.json` and `828.json` / ToolHop / score 0.5 each: The agent obtains binary strings with leading zero from conversion tools and submits the tool format (`01110100`, `01100011`), while gold omits the leading zero (`1110100`, `1100011`). This supports a final-answer canonicalization gate.
- `158.json` / SearchQA / score 1.0: The agent searches native areas for Elodea and Pinellia, compares observations, and answers `no`. This is the behavior to preserve: minimal tool use followed by grounded finalization.
- `772.json` / ToolHop / score 1.0: The agent recovers from failed author lookup attempts, uses biographical tools, counts unique letters, and submits `8`. This shows the single-agent ReAct loop can solve multi-hop tasks when it keeps changing strategy and grounds each step.
- Bucket-level statistics: overall avg score is 0.3737 across 1242 tasks; EnvScaler avg score 0.3978 with only 15/659 full-score; SearchQA answer correctness 75/325; ToolHop answer correctness 117/258. These metrics make EnvScaler state tracking and short-answer evidence gating the highest-impact repairs.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Keep plans short, but require an explicit `missing_evidence` field for every answer candidate not yet supported by observation.
- [Planning] For EnvScaler/state mutation tasks, emit a flat checklist of required state changes and terminal conditions before action begins.
- [Action] Never call `final_answer` for evidence-required QA unless the submitted value is copied from or computed from a prior tool observation.
- [Action] Add schema preflight for tool name and argument keys before execution, and repair invalid calls using the tool error text rather than repeating them.
- [Action] Track recent failed call signatures and block identical retries unless the latest observation gives a concrete reason the retry can now succeed.
- [Action] For `complete_task`, require a checklist readiness check that each requested state mutation has success evidence.
- [Action] Add a final canonicalization pass that strips explanation and normalizes the answer to the granularity requested by the task.
- [Memory] Distinguish tool-observed facts from plan/think hypotheses in short-term memory guidance.
- [Memory] Avoid begin-phase guidance that only says to execute directly; pair directness with an evidence-first caution for QA and multi-hop lookup tasks.
- [Builder] Preserve existing provider names and metadata compatibility with the harness factory.
- [Interface] Pass planning checklist and evidence provenance in a form action can inspect, not only as free text.
- [Preserve] Preserve the efficient single-agent path for simple tasks that need one or two evidence calls.
- [Preserve] Preserve successful adaptive behavior where the agent switches tools after a failed lookup.
- [Avoid] Do not add patches for specific entity names, task IDs, incident IDs, binary examples, or benchmark-specific gold strings.
- [Avoid] Do not solve EnvScaler by blindly calling more tools; add progress tracking and terminal readiness instead.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
