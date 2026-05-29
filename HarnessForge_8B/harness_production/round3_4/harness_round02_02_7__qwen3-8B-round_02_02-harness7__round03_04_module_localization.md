### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness under analysis is `harness_round02_02_7`, evaluated as model/run `qwen3-8B-round_02_02-harness7` in `round03_04`. The inspected snapshot is `harness_factory/rounds/round_03_04/base harness`, and the trajectory evidence comes from `output/exp_4_three_rounds/round03_04/harness_seed_run`.

`builder.py` assembles a single `ToolCallingAgent` through the action provider in `action_module/provider.py`. The builder injects `PlanningClass` through `context.kwargs["planning_class"]`, sets `planning_system` to `round02_02_verifier_contract_planning`, sets `action_system` to `round02_02_verifier_contract_react`, and sets the project root to the base harness directory. It also sets `max_tool_calls_per_step` to 2 and stores the harness status contract as `VERIFIER_CONTRACT`.

The builder binds the created agent back into process, end-process, delete-memory, executor, and refine tools when those tools expose an `agent` field. It also connects vector memory by assigning `prepared_context.vector_tool.memory = agent.memory` when a vector tool is present.

The important metadata mismatch is that the evaluated harness lives under `round_03_04`, while the harness name, module names, pairing reason, and metadata still identify it as `round_02_02`. This does not by itself explain the behavioral failures, but it can make run comparison and generation bookkeeping confusing. The actual implementation is a round02_02 verifier-contract harness reused as the base for round03_04.

#### 1.2 Planning Module Implementation

`planning_module/provider.py` implements `PlanningProvider`, a compact planner for the `VERIFIER_CONTRACT` format. At initialization, it renders the configured planning prompt with the available tools, task text, and planning system name, appends memory guidance to the system-side messages, and asks the model to produce a free-form plan. The observed plans usually contain target, required evidence or predicates, verification questions, remaining work, and final criteria.

Adaptation is implemented as a summarization step. It reads memory messages from the agent trajectory, renders summary pre/post prompts, calls the model, and appends a `SummaryStep`. The action provider sets the summary interval to 8 unless already configured, so summaries are periodic rather than enforced at every evidence transition.

Planning influences action mainly through natural-language plan text stored in memory. It does not produce a machine-readable state ledger, does not pre-bind tool schemas, does not enforce final-answer readiness, and does not require the action loop to update known/unknown evidence after each observation. It also does not distinguish transactional state tasks from short-answer tasks in its contract.

#### 1.3 Action Module Implementation

`action_module/provider.py` uses a single-executor topology. There is no coordinator-worker split, no independent verifier agent, no debate, and no parallel collaboration. The only additional action-side component is `VerifierContractTool`, exposed as `verifier_contract_check`.

The provider wraps primary task tools with `guard_task_tools(..., policy_label="round02_02_verifier_contract")`. The guard is a soft helper: it can drop extra keys, map a limited set of aliases, coerce scalar values to arrays for array schemas, and add repeated-failure advisories after failed observations. It does not fully preflight required arguments before execution, and it does not block all malformed calls. If a required argument is missing without extra-key repair, the wrapped call can still raise a tool execution error.

The verifier tool is non-environmental. It reads recent history, asks the same model to audit a draft, and returns fields such as verdict, evidence, missing_or_risk, and next_safe_move. Exact repeated verifier drafts are throttled, but there is no parser that enforces the verifier output as a hard constraint. The action loop can ignore a verifier warning, treat verifier text as sufficient evidence, or accept `no_blocker` even when the verifier evidence says that required information is missing.

Final answers are submitted by the model calling `final_answer` for QA tasks or `complete_task` for many EnvScaler stateful tasks. There is no dedicated raw-answer canonicalizer, no state-diff readiness checker before `complete_task`, and no final preflight that validates whether all plan obligations are satisfied by observed tool results.

#### 1.4 Memory Module Implementation

`memory_module/provider.py` implements a lightweight procedural memory. At BEGIN, it injects one reminder that verifier calls should be rare and should create next-action constraints rather than replace real evidence. During IN phases, it checks the context for error markers and finalization-risk markers. If an error appears, it reminds the agent to address the named missing evidence or failure class before repeating the same finalization or failed call. If finalization risk appears, or every configured interval, it reminds the agent not to finalize from verifier text alone and to copy exact raw values.

Memory stores no task facts, IDs, answers, or learned trajectory-specific lessons. `take_in_memory` always reports success but explicitly says it stores procedural reminders only. The memory guidance is relevant and low-noise, but it is too generic to prevent repeated schema guessing, premature impossibility answers, or transactional completion without a state ledger. In observed failures, the action loop often receives the right memory warning but still finalizes incorrectly.

### PART 2: FAILURE MODE ANALYSIS

#### Failure Mode 1: Transactional completion without a verified side-effect ledger

- **Name:** EnvScaler state changes are marked complete before the required world state is fully achieved.
- **Frequency / importance:** Dominant for EnvScaler. EnvScaler averaged 0.4545 score over 658 tasks, with only 26 full-score tasks, 412 partial-score tasks, and 220 zero-score tasks. `complete_task` appeared in 439 EnvScaler trajectories, and 413 of those were still not full-score.
- **Symptom:** The agent often performs some correct operations, receives one or more failed tool observations, and still calls `complete_task` or otherwise ends with `Task Completed`.
- **Mechanism:** The single action loop has no structured checklist of required state mutations, no explicit state-diff verification, and no terminal gate that blocks `complete_task` when recent tool failures or unresolved obligations remain. Planning lists goals in text, but action does not maintain a binding table of entity IDs, side effects, and confirmed success states.
- **Generalized capability gap:** Missing transactional progress ledger and terminal readiness check for stateful tool environments.
- **Primary module owner:** Action
- **Secondary contributor:** Planning and Cross-Module Interface
- **Evidence:** EnvScaler had 474 tasks with at least one `success: false` observation and 2974 failed observations overall. In trajectory 5, the agent first called `create_therapy_session` with a user name instead of a user ID, later repaired some calls, and still ended partial with score 0.7778. In trajectory 1239, it repeatedly attempted bed reservation calls after patient lookup problems and finished with score 0.0.
- **Generalization rationale:** Any stateful API task requires confirmed object identity, mutation success, and postcondition verification. This failure is not tied to a specific domain such as hospitals, carts, benefits, or counseling.
- **Confidence:** High

#### Failure Mode 2: Soft schema guard does not prevent malformed or under-specified real tool calls

- **Name:** Tool schema and argument repair happens after failure rather than before risky execution.
- **Frequency / importance:** High. EnvScaler produced 430 tool-call error observations, ToolHop produced 134, and missing-required-argument patterns appeared in 40 trajectories across EnvScaler, SearchQA, and ToolHop.
- **Symptom:** The agent calls tools with missing required parameters, wrong IDs, unsupported relationship values, or guessed argument objects. It then spends steps repairing by trial and error.
- **Mechanism:** `GuardedTool` repairs extra keys and some aliases, but it does not fully validate required keys, nested required fields, enum values, or nullable object requirements before the wrapped tool is called. Repeated-failure advisory is attached only after a failed real call, so the environment still absorbs failed actions.
- **Generalized capability gap:** Missing schema preflight and structured repair protocol before real tool execution.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Trajectory 100 calls `resolution_sponsor_finder` without required `date_range`, receives a TypeError, then guesses several broad date ranges. Trajectory 52 uses an invalid `relationship_type` for genealogy, then concludes the answer cannot be determined. Trajectory 1228 attempts an unavailable `list_users` tool after direct user lookup failures.
- **Generalization rationale:** Tool schema mismatch is a cross-domain harness behavior. It will recur whenever tools have required nested objects, constrained enums, or similar-but-not-identical argument names.
- **Confidence:** High

#### Failure Mode 3: Verifier output becomes a substitute for evidence instead of a constraint on next action

- **Name:** The verifier can license premature impossibility or repeated searching.
- **Frequency / importance:** Medium-high. The verifier was used in 143 trajectories and called 319 times. Some trajectories called it 20 or 24 times.
- **Symptom:** The verifier sometimes reports missing evidence but also returns `next_safe_move: no_blocker`, after which the agent finalizes an impossibility answer or continues low-value search loops.
- **Mechanism:** `verifier_contract_check` is only another tool call. Its output is free text and is not parsed into enforceable constraints. It uses the same model and recent history as the executor, so it can reproduce the executor's uncertainty. Exact-draft throttling does not prevent semantically repeated verifier calls with slightly different wording.
- **Generalized capability gap:** Missing verifier arbitration protocol and missing contract enforcement between verifier output and action selection.
- **Primary module owner:** Action
- **Secondary contributor:** Cross-Module Interface
- **Evidence:** In trajectory 100, repeated empty sponsor searches led the verifier to say no sponsors were found and `next_safe_move: no_blocker`; the agent then submitted a non-answer although the gold answer was `12`. In trajectory 1218, repeated film lookup failures and verifier checks ended with an impossibility answer instead of recovering the correct date. In trajectory 34, SearchQA ended with "insufficient evidence" for a Beatles-song question rather than a raw answer.
- **Generalization rationale:** A verifier that is not bound to a contract can amplify uncertainty in any task family, especially when evidence retrieval is noisy or one tool returns an empty result.
- **Confidence:** High

#### Failure Mode 4: Search and multi-hop evidence chains stop on plausible but unverified snippets

- **Name:** Evidence chain breaks after the first plausible answer-bearing observation.
- **Frequency / importance:** High for SearchQA and meaningful for ToolHop. SearchQA exact answer correctness was 130/325, with 163 zero-score cases and 32 partial cases. ToolHop exact correctness was 133/258.
- **Symptom:** The agent retrieves a snippet containing related entities, selects a plausible surface answer, and finalizes without checking whether it matches the actual relation asked by the question.
- **Mechanism:** Planning produces broad evidence requirements, but the action loop does not maintain relation-specific evidence targets or require a second verification query when the retrieved snippet answers a nearby but different question. The single executor also lacks an evidence arbitration step for distractor snippets.
- **Generalized capability gap:** Weak relation-grounded evidence targeting and verification before final answer.
- **Primary module owner:** Planning
- **Secondary contributor:** Action
- **Evidence:** Trajectory 12 asks for the city of the band that founded Royal Mountain Records but answers `Toronto`, apparently from the label location, while the gold answer is `Ottawa, Ontario`. Trajectory 24 answers `Constantine the Great` for a "first Roman to be baptized" question where the gold answer is `Cornelius`. Trajectory 1201 answers `Mavis Pugh` for a cast question whose gold answer is `Michael Knowles`.
- **Generalization rationale:** Distractor snippets and nearby relations occur in open-domain QA, database lookup, API chains, and entity linking tasks. The missing capability is relation verification, not knowledge about any one entity.
- **Confidence:** High

#### Failure Mode 5: Final-answer canonicalization is not enforced

- **Name:** Correct evidence is often converted into a non-raw or over-specific final answer.
- **Frequency / importance:** Medium. SearchQA had 32 cases where `subem` was 1.0 but `answer_correct` was 0.0. ToolHop had 5 partial cases with the same pattern.
- **Symptom:** The trajectory contains the gold string or enough evidence, but the final answer is a sentence, includes extra context, uses a different formatting convention, or returns an over-specific variant.
- **Mechanism:** The action loop relies on the executor model to call `final_answer` with the correct raw answer value. Memory reminds the agent to copy raw values, but there is no final-answer canonicalizer that extracts the minimal supported span from observations.
- **Generalized capability gap:** Missing raw-answer extraction and final formatting gate.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Trajectory 9 has gold `Pittsburgh suburb` but finalizes the full sentence "The Perks of Being a Wallflower takes place in a Pittsburgh suburb during the early 1990s." Trajectory 1220 has gold `Statue of Freedom` but finalizes a full sentence. Trajectory 395 has gold answers `PlayStation 4`, `Windows`, and `Xbox One`, while the final includes the same values with additional prose.
- **Generalization rationale:** Short-answer benchmarks, form-filling APIs, and downstream evaluators often require exact spans or canonical values. This is a harness formatting capability, not a domain-specific issue.
- **Confidence:** High

#### Failure Mode 6: Low-value exploration after empty or failed observations

- **Name:** Empty results trigger broad parameter guessing rather than principled recovery.
- **Frequency / importance:** Medium. ToolHop had 16 empty-list observations and 19 "cannot complete" style final outputs; SearchQA had 4 "cannot complete" style outputs.
- **Symptom:** After an empty result, the agent changes date ranges, wording, name variants, or search terms repeatedly without a clear hypothesis, then either gives up or finalizes from weak evidence.
- **Mechanism:** Planning does not represent alternate routes or discriminative recovery questions. Action does not classify failures into schema error, entity normalization error, no-data response, or wrong-tool response before deciding the next move.
- **Generalized capability gap:** Missing observation classification and recovery strategy selection.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** Trajectory 100 broadens date ranges after empty sponsor results without establishing the required historical date. Trajectory 55 repeatedly queries timezone information after an unknown timezone result and ends with an impossibility answer. Trajectory 1236 repeatedly searches for Grey's Anatomy episode release information and finalizes that the date is not provided.
- **Generalization rationale:** Empty or failed observations are common across search, database, and API environments. The harness needs general recovery policies rather than benchmark-specific fallback facts.
- **Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Transactional completion without a verified side-effect ledger | Action | Cross-Module Interface | `action_module/provider.py`; Planning -> Action contract | EnvScaler score 0.4545; 26/658 full score; 413 `complete_task` calls in non-full-score trajectories; trajectories 5 and 1239 | Stateful APIs in any domain require confirmed mutations and postcondition checks | High | Add an action-owned side-effect ledger and terminal readiness gate before `complete_task` |
| Soft schema guard does not prevent malformed or under-specified real tool calls | Action | Memory | `action_module/provider.py`; `_harness_guards.py` | 430 EnvScaler tool errors, 134 ToolHop tool errors, 40 missing-required-argument patterns; trajectory 100 missing `date_range` | Schema and argument mismatch recur for nested objects, enums, IDs, and similar argument names | High | Add required-field preflight, enum validation, nested-object checks, and repair-before-execution |
| Verifier output becomes a substitute for evidence instead of a constraint on next action | Action | Cross-Module Interface | `VerifierContractTool` in `action_module/provider.py` | 319 verifier calls; trajectory 100 verifier says missing evidence plus `no_blocker`; trajectories 34 and 1218 finalize impossibility | Unenforced verifier text can amplify uncertainty in any noisy retrieval or tool-use task | High | Parse verifier fields into hard constraints and prevent finalization on unresolved `missing_or_risk` |
| Search and multi-hop evidence chains stop on plausible but unverified snippets | Planning | Action | `planning_module/provider.py`; Planning -> Action evidence contract | SearchQA exact correctness 130/325; trajectories 12, 24, and 1201 select nearby but wrong relations | Distractor snippets and relation drift occur across open-domain QA and database lookup | High | Make plans produce relation-specific evidence targets and require verification before final |
| Final-answer canonicalization is not enforced | Action | Memory | `action_module/provider.py`; terminal `final_answer` behavior | 32 SearchQA `subem=1` but `answer_correct=0`; 5 ToolHop partial cases; trajectories 9 and 1220 | Exact raw-value output is a general terminal contract requirement | High | Add a raw-answer extraction gate that copies minimal supported values from observations |
| Low-value exploration after empty or failed observations | Action | Planning | `action_module/provider.py`; observation handling loop | ToolHop empty-list observations in 16 cases and 19 "cannot complete" finals; trajectories 55, 100, and 1236 | Empty observations are common across tools and need classified recovery, not parameter guessing | Medium | Classify observation failures and choose bounded recovery moves before giving up |

### PART 4: STRENGTHS TO PRESERVE

- The single-executor topology in Action is efficient for simple ToolHop chains; trajectory 1 solves a four-step author, education, count, and raw-final chain cleanly, so generation should not replace it with heavy collaboration for all tasks.
- The Planning module's initial plans usually expose target, required evidence, verification questions, remaining work, and final criteria; these fields help straightforward trajectories stay ordered and should be preserved while making them more structured.
- The Memory module is low-noise and procedural; it avoids storing task facts, IDs, or answers, which reduces overfitting risk and should remain true in the next harness.
- The guard wrapper in Action already provides useful soft repairs for extra keys, aliases, scalar-to-array coercion, and repeated-failure advisories; generation should strengthen this behavior rather than discard it.
- The builder preserves local harness-factory compatibility by injecting `PlanningClass`, setting `project_root`, and binding selected tools back to the agent; these wiring behaviors should not regress.
- The action loop successfully calls `final_answer` in most QA tasks: SearchQA had valid answers for all 325 tasks and ToolHop had valid answers for all 258 tasks, so the repair should target correctness and rawness rather than basic terminal-tool availability.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Stateful Side-Effect Ledger and Completion Gate]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** EnvScaler tasks are marked complete after partial or failed state mutations.
- **Mechanism:** Track required side effects, bound entity IDs, mutation success, recent failures, and unresolved postconditions. Block `complete_task` unless the ledger has no unresolved required mutation and no recent failed mutation that affects the goal.
- **Why This Module Owns It:** The action module owns concrete tool execution, observation handling, and terminal tool calls.
- **Generalization Rationale:** Any stateful API environment needs the same confirmed-mutation discipline regardless of domain.
- **Complexity:** Medium
- **Expected Impact:** Higher EnvScaler full-completion rate and fewer false `Task Completed` endings.
- **Risk:** If the gate is too strict, the agent may fail to complete tasks that are actually done but not explicitly recognized.

**[Priority 2: Schema Preflight Before Real Tool Execution]**
- **Target Module:** Action
- **Owner Path:** `_harness_guards.py` and `action_module/provider.py`
- **Problem:** Missing required arguments and invalid argument values still reach real tools.
- **Mechanism:** Validate required top-level keys, nested required keys, enum values, nullable object shapes, and tool existence before execution. Return a structured repair observation without calling the wrapped environment tool when preflight fails.
- **Why This Module Owns It:** The action module exposes and executes tools; schema compliance is an execution contract, not a planning preference.
- **Generalization Rationale:** Tool schema complexity appears across QA tools, database tools, and stateful APIs.
- **Complexity:** Medium
- **Expected Impact:** Fewer TypeError traces, fewer wasted repair loops, and less environment state pollution.
- **Risk:** Over-aggressive validation could reject permissive tool calls that the underlying tool would have accepted.

**[Priority 3: Enforced Verifier Contract]**
- **Target Module:** Action
- **Owner Path:** `VerifierContractTool` in `action_module/provider.py`
- **Problem:** Verifier output sometimes licenses finalization despite missing evidence.
- **Mechanism:** Parse verifier output into normalized fields. Treat non-empty `missing_or_risk` as a blocker unless the next action directly resolves it. Disallow `no_blocker` when the evidence field contains empty results, unknowns, or missing required information. Limit semantically repeated verifier calls.
- **Why This Module Owns It:** The verifier is implemented as an action-side tool and only action can enforce its output against the next tool call or final answer.
- **Generalization Rationale:** A verifier must constrain action in every domain where evidence can be incomplete or ambiguous.
- **Complexity:** Low
- **Expected Impact:** Fewer premature impossibility answers and fewer verifier loops.
- **Risk:** A brittle parser may misread free-form verifier output unless the verifier response format is made strict.

**[Priority 4: Structured Planning-to-Action Evidence Contract]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** Planning -> Action boundary between `planning_module/provider.py` and `action_module/provider.py`
- **Problem:** Plans are useful but remain free text, so action can ignore relation targets, final criteria, and unresolved evidence.
- **Mechanism:** Have planning emit compact structured fields such as target relation, required bindings, accepted evidence, unresolved blockers, and final raw-answer form. Have action update these fields after observations and consult them before finalization.
- **Why This Module Owns It:** Planning creates the evidence obligations, while action owns tool results and finalization.
- **Generalization Rationale:** Relation grounding and evidence state are needed for open-domain search, ToolHop chains, and stateful APIs.
- **Complexity:** Medium
- **Expected Impact:** Fewer distractor-snippet answers and fewer premature finals after partial evidence.
- **Risk:** Too much structure may add prompt burden and reduce flexibility on simple tasks.

**[Priority 5: Raw Final-Answer Canonicalization Gate]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** Correct evidence is sometimes submitted as a sentence, explanation, or over-specific variant.
- **Mechanism:** Before `final_answer`, extract the minimal answer span from observed evidence, strip explanatory prose, preserve exact casing and formatting when supported, and reject finals containing unsupported narrative text.
- **Why This Module Owns It:** The action module owns final tool calls and terminal answer formatting.
- **Generalization Rationale:** Exact raw-value output is required across short-answer QA, ToolHop, and many API terminal contracts.
- **Complexity:** Low
- **Expected Impact:** Recover many partial SearchQA and ToolHop cases where `subem` is already correct.
- **Risk:** Over-normalization may remove necessary disambiguators from answers with multiple valid aliases.

**[Priority 6: Failure-Class Memory Reminders]**
- **Target Module:** Memory
- **Owner Path:** `memory_module/provider.py`
- **Problem:** Memory warnings are relevant but too generic to redirect recurring schema, empty-result, and final-answer failures.
- **Mechanism:** Keep memory procedural, but route more specific reminders by failure class: missing required schema, empty result, repeated same failed call, verifier blocker, final rawness, and stateful postcondition.
- **Why This Module Owns It:** Memory owns reusable procedural guidance and phase-aware reminders.
- **Generalization Rationale:** Failure-class guidance transfers across domains without storing task-specific facts.
- **Complexity:** Low
- **Expected Impact:** Better compliance with schema repair and finalization rules when action sees repeated risk markers.
- **Risk:** Too many reminders could bloat prompts and distract the executor.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory 100, ToolHop: The agent omitted required `date_range` for `resolution_sponsor_finder`, then guessed broad date ranges that returned empty lists. The verifier said no sponsors were found and returned `next_safe_move: no_blocker`, after which the agent finalized an impossibility answer. Gold answer was `12`.
- Failed trajectory 9, SearchQA: One search retrieved evidence containing `Pittsburgh suburb`, but the final answer was a full sentence. The trajectory was path-correct but final-wrong because the terminal answer was not the raw value.
- Failed trajectory 12, SearchQA: The search result described Royal Mountain Records as based in Toronto, and the agent answered `Toronto`. The task asked for the city associated with the band that founded the label, whose gold answer was `Ottawa, Ontario`, showing a relation-chain break.
- Failed trajectory 1239, EnvScaler: The agent encountered patient lookup and bed reservation failures, repeated reservation attempts, and ended with `Task Failed` and score 0.0. This illustrates missing entity binding and stateful recovery.
- Failed trajectory 5, EnvScaler: The first therapy-session creation used a user name where the tool required an ID, then the agent repaired some calls and still called completion with only partial score 0.7778. This illustrates both schema weakness and terminal readiness weakness.
- Successful trajectory 1, ToolHop: The agent identified the author of `Hannibal and Scipio`, found the educational institution, counted the letter `r`, and called `final_answer` with raw `1`. This shows that the single-executor chain works when tool schemas are simple and each observation directly supports the next hop.
- Successful trajectory 28, SearchQA: The agent used one search and submitted raw `Herman's Hermits`, showing that concise retrieval plus raw final copying should be preserved.
- Bucket-level statistic: SearchQA had 32 cases with `subem=1.0` but `answer_correct=0.0`, making final-answer canonicalization a distinct failure from evidence retrieval.
- Bucket-level statistic: EnvScaler had only 26 full-score tasks out of 658, while 413 `complete_task` calls appeared in non-full-score trajectories, making premature or under-verified completion the dominant stateful-task failure.
- Bucket-level statistic: Tool errors were concentrated in EnvScaler and ToolHop, with 430 EnvScaler tool errors and 134 ToolHop tool errors, making schema and recovery behavior a major Action-module issue.
- Metric caveat: `report.txt` marks all 1241 executions as successful but leaves Correct and Incorrect at zero, so module diagnosis relies on `mixeddata.metrics.overall.json` and per-trajectory scoring fields.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Preserve compact initial plans, but make evidence obligations more structured and relation-specific.
- [Planning] Include final raw-answer form and unresolved blocker fields in the plan when the task is a short-answer or multi-hop evidence task.
- [Action] Add schema preflight before real tool execution, especially for required nested objects, enums, IDs, and unavailable tools.
- [Action] Add a stateful side-effect ledger and prevent `complete_task` when required mutations or postconditions are unresolved.
- [Action] Enforce verifier output as constraints; do not allow `no_blocker` when the verifier also reports missing required evidence.
- [Action] Add a raw final-answer canonicalization gate before `final_answer`.
- [Memory] Keep memory procedural and non-factual, but route reminders by failure class rather than using only generic finalization warnings.
- [Builder] Preserve `PlanningClass` injection, selected-tool binding, vector-memory wiring, and project-root setup.
- [Interface] Give action access to planning obligations in a format it can update after each observation.
- [Preserve] Keep the efficient single-executor path for simple chains; do not force expensive multi-agent coordination onto all tasks.
- [Avoid] Do not add benchmark-specific entity lists, hard-coded answer aliases, fixed date ranges, or special cases for the observed failed trajectories.
- [Avoid] Do not treat empty tool results as proof of impossibility without classified recovery and evidence-backed blocker resolution.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
