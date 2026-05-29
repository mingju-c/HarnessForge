### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness under analysis is `harness_round02_01_7`, evaluated as model/run `qwen3-8B-round_02_01-harness7` in `round03_02`. The inspected snapshot is `harness_factory/rounds/round_03_02/base harness`, and trajectory evidence comes from `output/exp_4_three_rounds/round03_02/harness_seed_run`.

`builder.py` assembles a single `ToolCallingAgent` through `action_module/provider.py`. It injects `PlanningClass` into `context.kwargs["planning_class"]`, sets `planning_system` to `round02_01_recovery_status_planning`, sets `action_system` to `round02_01_recovery_status_react`, assigns the base harness directory as `project_root`, and defaults `max_tool_calls_per_step` to 2. It also sets a `harness_status_contract` of `RECOVERY_STATUS`.

The builder binds selected tools back to the created agent when they expose an `agent` attribute, including process, end-process, delete-memory, executor, and refine tools. If a vector tool exists, it assigns `prepared_context.vector_tool.memory = agent.memory`. For OWL-style planning systems, it also initializes `web_memory` and `reasoning_memory`, though this harness does not use OWL.

The main metadata mismatch is bookkeeping rather than behavior: the evaluated base harness lives under `round_03_02`, but `HARNESS_NAME`, module constants, `PAIRING_REASON`, and harness metadata identify it as a `round_02_01` recovery-status harness. This is expected for a reused base candidate, but generation and reporting should not mistake it for a newly implemented round03_02 harness.

#### 1.2 Planning Module Implementation

`planning_module/provider.py` implements `PlanningProvider`, described in code as a compact planner for recovery routes and terminal contract discipline. During `topology_initialize`, it renders the configured initial-planning prompt with the available tools, task, and planning system name, appends memory guidance, calls the model once, stores the resulting free-form plan as a `PlanningStep`, and appends that step to agent memory.

Adaptation is periodic summarization. The planner reads prior memory messages, renders summary pre/post prompts, calls the model, stores the result as a `SummaryStep`, and appends it to memory. The action provider sets the agent summary interval to 7 unless already configured, so planning state is refreshed periodically rather than after every important observation or failed call.

Planning influences action only through natural-language memory messages. It does not emit a machine-readable task ledger, does not bind required state mutations to observed success flags, does not enforce relation-slot dependencies for ToolHop, and does not block finalization when the action loop has unresolved plan rows. The observed plans and summaries often mention recovery routes and final readiness, but action can repeat a failed call or finalize despite those summaries.

#### 1.3 Action Module Implementation

`action_module/provider.py` uses a single-executor topology. There is no coordinator-worker split, no independent verifier, no debate, no parallel evidence collection, and no separate repairer. The only additional action-side component is `RecoveryContractTool`, exposed as `recovery_contract_check`.

The provider wraps all primary task tools with `guard_task_tools(..., policy_label="round02_recovery_status")`. The guard is soft. It can repair some extra argument keys, map a limited set of aliases, coerce scalars into arrays for array schemas, and add repeated-failure advisories after identical failed calls. It does not fully preflight unknown tool names, required fields, nested schemas, enum constraints, or semantic preconditions before execution. It also does not block a repeated failed real call; it only appends an advisory to the observation.

The recovery checker is non-environmental. It reads recent trajectory history, asks the same model to inspect a draft, and returns concise free text with fields such as `verdict`, `exhausted_routes`, `terminal_readiness`, and `next_safe_move`. The output is not parsed into hard constraints. In observed trajectories, the action loop sometimes uses checker output to justify an impossibility answer even when the benchmark expects continued state mutation or raw final answer.

Final answers are submitted either through `final_answer` for QA/ToolHop tasks or `complete_task` for EnvScaler state-change tasks. There is no dedicated final-answer canonicalizer, no structured state-diff readiness check before `complete_task`, no stop rule for repeated failed calls, and no evidence arbitration protocol when observations contradict the task prompt or each other.

#### 1.4 Memory Module Implementation

`memory_module/provider.py` implements lightweight procedural memory. At BEGIN, it injects one reminder that every non-final step should use a real schema-listed tool and should change query, arguments, tool, or strategy when stuck.

During IN phases, memory scans the current context for markers such as `error`, `unknown tool`, `invalid`, `success: false`, `not found`, `does not exist`, `complete_task`, `final_answer`, `cannot determine`, `placeholder`, `slot`, `pending`, and raw-value markers. It then injects short reminders about avoiding premature cannot-determine answers, recording missing preconditions, choosing a different valid route, submitting raw observed values, or refreshing recovery status.

Memory stores no task facts, entity IDs, answers, or trajectory-specific lessons. `take_in_memory` explicitly reports that it stores procedural reminders only. The memory is compact and relevant, but it is too generic and advisory-only to prevent the dominant failures. In many failures, memory warns against repeated failed routes or prose uncertainty, yet the action loop repeats identical tool calls, calls unknown tools, or finalizes with unresolved state changes.

### PART 2: FAILURE MODE ANALYSIS

#### Failure Mode 1: Stateful task checklist drift and premature completion

- **Name:** EnvScaler tasks are completed or abandoned while required state changes remain unresolved.
- **Frequency / importance:** Dominant for EnvScaler. EnvScaler has 658 tasks with average score 0.4351. Only 30/658 reach full score, 395 are partial completions, and 233 are zero-score. `Task Completed` appears in 584 EnvScaler outputs, but 554 of those are still not full-score.
- **Symptom:** The agent performs some writes, receives failed observations for other required writes, and still calls `complete_task` or returns a non-terminal prose failure.
- **Mechanism:** The harness has no durable side-effect ledger connecting the task's requested mutations to observed successful tool calls. Planning may describe required changes in text, and summaries may mention remaining work, but action does not maintain a confirmed/unconfirmed row for each mutation before terminalization.
- **Generalized capability gap:** Missing transactional progress tracking and terminal readiness gating for stateful tool environments.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Action
- **Evidence:** EnvScaler had `success: false` observations in 474/658 trajectories and repeated-failure advisories in 258/658. Trajectory 6 creates folders and tags, hits invalid tag IDs, continues after unresolved failures, and still ends with `Task Completed` and score 0.0. Trajectory 460 updates a patient contact field, fails to add or edit medical records because of permissions, calls an invented `switch_user_to_provider`, and finalizes with an escalation message instead of completing the state task.
- **Generalization rationale:** Any stateful API task requires confirmed object identity, successful mutation, and terminal completion only after all required postconditions are satisfied. This weakness transfers across carts, billing, health records, folders, scheduling, and other domains.
- **Confidence:** High

#### Failure Mode 2: Recovery loops repeat failed routes instead of changing state, tool, or hypothesis

- **Name:** Failed calls trigger textual recovery status but not a different executable route.
- **Frequency / importance:** High. Repeated-failure advisories appear in 258/658 EnvScaler trajectories and 46/258 ToolHop trajectories. EnvScaler has periodic summaries in 647/658 runs, yet repeated failures remain common.
- **Symptom:** The agent receives a failed observation and an advisory not to repeat the same call, then repeats the same tool with the same or equivalent arguments. In other cases, it switches briefly to a read/check tool and then returns to the failed mutation.
- **Mechanism:** `GuardedTool` and memory provide advisory text only. The action loop has no hard failed-call registry, no route-difference requirement, and no rule that the next call must resolve the stated precondition before retrying.
- **Generalized capability gap:** Missing executable recovery protocol that classifies a failure and requires a materially changed repair move.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Trajectory 13 repeatedly tries dispute status updates after observing status validation failures, including repeated `update_dispute_resolution_status` calls for `under_review` and `pending`, then ends without a terminal tool. Trajectory 381 repeats the same `movie_director_lookup` for `Mercy` with year 2000 more than twenty times despite repeated-failure advisories. Trajectory 214 repeats failed `geo_location_linker` and `historical_query_tool` routes before guessing a count.
- **Generalization rationale:** Repeated failed-call loops are a general tool-use failure in any environment with noisy lookup, missing entities, permissions, or constrained schemas.
- **Confidence:** High

#### Failure Mode 3: Tool schema and tool-existence control remains too soft

- **Name:** Unknown tools and malformed argument repairs consume budget and derail trajectories.
- **Frequency / importance:** High for EnvScaler and medium for ToolHop. Unknown tools appear in 115/658 EnvScaler trajectories and 4/258 ToolHop trajectories. Tool-call error lines appear in 139/658 EnvScaler trajectories and 59/258 ToolHop trajectories.
- **Symptom:** The agent invents tools or supplies unsupported arguments, then spends later steps repairing the self-created error. Unknown EnvScaler tools include `get_patient_treatment_history`, `get_patient_treatments`, `add_guest`, `authenticate_as_admin`, `create_patient`, and many others.
- **Mechanism:** Tool selection is left to the executor model. The guard can repair argument keys for existing wrapped tools, but it cannot intercept an invented tool before the agent emits it. It also does not enforce required fields and enum constraints strongly enough to prevent TypeError-style or semantic tool failures.
- **Generalized capability gap:** Missing schema preflight and allowed-tool selection discipline before real execution.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Trajectory 460 calls invented `switch_user_to_provider` twice after permission failures. Trajectory 203 calls `historical_genealogy_lookup` with unsupported parameters such as `genealogy_depth`, `name_variants`, and `historical_context`, receives execution errors, and eventually submits a cannot-determine answer. The aggregate run shows EnvScaler unknown-tool failures in 17.5% of trajectories.
- **Generalization rationale:** Tool-name and schema mismatch recur whenever a harness operates over unfamiliar APIs with similar but non-identical affordances.
- **Confidence:** High

#### Failure Mode 4: Evidence-chain slot binding breaks under failed or ambiguous lookups

- **Name:** The agent transforms the wrong entity or finalizes from an unresolved intermediate slot.
- **Frequency / importance:** High for ToolHop. ToolHop exact answer correctness is 131/258 with average score 0.5252. Wrong ToolHop cases average 10.88 tool calls, showing that many failures are not from refusing to use tools but from using them on the wrong chain state.
- **Symptom:** After an intermediate lookup fails, the agent applies extraction, arithmetic, or conversion tools to the source entity, an unresolved placeholder, or a nearby relation instead of the required observed intermediate value.
- **Mechanism:** The planning prompt and regression guidance mention slot discipline, but the action loop does not enforce that transformation inputs must come from an observed slot in the intended chain. Summaries can say an intermediate is missing while action still performs downstream operations or finalizes.
- **Generalized capability gap:** Missing observation-grounded slot ledger for multi-hop chains.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** Trajectory 1171 asks for the binary code of the last letter of the last name of Kerry Earnhardt's paternal grandfather. Father/grandparent lookups fail, but the agent extracts the last name from `Kerry Earnhardt` itself and answers `01110100` instead of gold `1110100`. Trajectory 203 cannot retrieve the paternal grandfather, tries unsupported genealogy arguments, and finalizes with cannot-determine. Trajectory 214 identifies Stanley Park, cannot retrieve its designer, loops on failed lookups, and guesses `5` instead of gold `4`.
- **Generalization rationale:** Multi-hop tasks across genealogy, publications, geography, films, and arithmetic require exact propagation of observed intermediate bindings. The failure is not tied to any one tool family.
- **Confidence:** High

#### Failure Mode 5: SearchQA evidence sufficiency is shallow and relation verification is weak

- **Name:** The agent finalizes from the first plausible snippet even when the snippet answers a nearby relation.
- **Frequency / importance:** High for SearchQA. SearchQA exact answer correctness is 129/325, average score is 0.4308, and zero-score cases account for 174/325 tasks. Wrong SearchQA cases still average 2.36 tool calls, so the issue is not tool absence.
- **Symptom:** A search result contains related entities or a plausible answer type, and the agent returns a nearby answer without checking whether it satisfies the exact relation in the question.
- **Mechanism:** Planning does not consistently create relation-specific verification questions, and action has no arbitration step that compares the candidate answer against the requested relation before `final_answer`.
- **Generalized capability gap:** Missing relation-grounded evidence target and verification-before-final protocol.
- **Primary module owner:** Planning
- **Secondary contributor:** Action
- **Evidence:** Trajectory 480 asks who proposes a new law in the Bahamas for the government. After one search, the agent answers `The Prime Minister of the Bahamas`, while the gold answers are `any parliamentarian` or `a Government minister`. Trajectory 752 answers `Robert Lee Wills` instead of `James Robert Wills`. Trajectory 889 answers `National Theatre Connections` instead of `London Academy of Music and Dramatic Art`.
- **Generalization rationale:** Nearby-relation distractors appear in open-domain QA, database retrieval, and entity-linking tasks. The reusable weakness is relation verification, not a missing fact about the Bahamas or any other entity.
- **Confidence:** High

#### Failure Mode 6: Final-answer canonicalization is underdeveloped

- **Name:** Correct or nearly correct evidence is submitted in an evaluator-incompatible form.
- **Frequency / importance:** Medium. SearchQA has 22 wrong-answer cases with `subem=1.0`, and ToolHop has 9 wrong-answer cases with `subem=1.0`. Additional numeric/date canonicalization failures have `subem=0` but are semantically close.
- **Symptom:** The agent submits a surface form that is equivalent, over-specific, padded, or differently typed from the expected raw answer.
- **Mechanism:** The action loop relies on the executor model to decide the final answer string. Memory reminds the agent to submit raw observed values, but there is no terminal normalizer that applies answer-type-specific formatting rules or copies the expected raw span from observations.
- **Generalized capability gap:** Missing raw-answer extraction and answer-type canonicalization at the terminal boundary.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Trajectory 848 observes that the first Soviet bomb was detonated on `August 29, 1949` and answers that string, while the gold answer is `29 August 1949`. Trajectory 680 computes `12167` for a cube result while the gold answer is `12167.0`. Trajectory 1171 returns the 8-bit ASCII string `01110100` while the gold answer omits the leading zero as `1110100`.
- **Generalization rationale:** Exact terminal formats matter in short-answer QA, numeric transformations, date tasks, and API contracts. This is a harness-level terminal behavior.
- **Confidence:** High

#### Failure Mode 7: Contradictory tool-contract observations are not arbitrated

- **Name:** The harness keeps acting on inconsistent tool feedback without deciding which contract controls.
- **Frequency / importance:** Medium for EnvScaler. Common EnvScaler errors include status values being rejected even after tools report those values as allowed, for example `accepted` and `under_review` dispute statuses.
- **Symptom:** The agent observes an allowed-value list, calls a mutation tool with one of those values, receives a rejection, then alternates between the same rejected values and the same tools.
- **Mechanism:** The action module has no contradiction handler for cases where a read-only schema/metadata tool and a mutation tool disagree. It also lacks a policy for switching from repeated mutation attempts to a different compatible mutation path, partial completion, or evidence-grounded impossibility.
- **Generalized capability gap:** Missing evidence arbitration for conflicting tool observations and API contract ambiguity.
- **Primary module owner:** Action
- **Secondary contributor:** External/Evaluation
- **Evidence:** Trajectory 13 retrieves allowed resolution statuses including `accepted`, `rejected`, `pending`, `under_review`, and `escalated`, then repeatedly receives status rejection errors and loops. Trajectory 33 observes that `accepted` is listed as allowed, but repeated attempts to set `accepted` fail and the agent ends with a task-failed message. Aggregate EnvScaler errors include 52 observations where `accepted` is rejected while the allowed-values payload itself includes `accepted`.
- **Generalization rationale:** Real tool ecosystems often contain stale metadata, state-dependent constraints, or inconsistent validation. A harness must arbitrate contradictions without overfitting to a specific status enum.
- **Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Stateful task checklist drift and premature completion | Cross-Module Interface | Action | Planning -> Action boundary; `action_module/provider.py` terminal behavior | EnvScaler average score 0.4351; only 30/658 full score; 554 non-full-score `Task Completed` outputs; trajectories 6 and 460 | Stateful tasks in any domain require confirmed mutations before terminalization | High | Add a structured side-effect ledger shared from planning to action and gate `complete_task` on observed success |
| Recovery loops repeat failed routes instead of changing state, tool, or hypothesis | Action | Memory | `action_module/provider.py`; `_harness_guards.py`; `memory_module/provider.py` | Repeated-failure advisories in 258/658 EnvScaler and 46/258 ToolHop; trajectories 13, 381, and 214 | Failed observations are universal in tool environments and require materially changed repairs | High | Convert repeated-failure advisory into a hard route-change requirement or retry budget |
| Tool schema and tool-existence control remains too soft | Action | Memory | `action_module/provider.py`; `_harness_guards.py` | Unknown tools in 115/658 EnvScaler; tool-call error lines in 139/658 EnvScaler and 59/258 ToolHop; trajectories 460 and 203 | Schema mismatch transfers across unfamiliar APIs, constrained enums, IDs, and nested arguments | High | Add preflight for allowed tools, required fields, enum values, and nested schema shapes before execution |
| Evidence-chain slot binding breaks under failed or ambiguous lookups | Action | Planning | `action_module/provider.py`; Planning -> Action evidence contract | ToolHop exact correctness 131/258; wrong ToolHop cases average 10.88 tool calls; trajectories 1171, 203, and 214 | Multi-hop chains require observed intermediate bindings before transformation in any domain | High | Maintain a slot ledger and block transformations on source entities or unresolved placeholders |
| SearchQA evidence sufficiency is shallow and relation verification is weak | Planning | Action | `planning_module/provider.py`; `action_module/provider.py` finalization | SearchQA exact correctness 129/325; 174/325 zero-score cases; trajectories 480, 752, and 889 | Relation distractors are common in search, database retrieval, and entity linking | High | Make plans include relation-specific verification questions and require action to verify candidate-answer relation |
| Final-answer canonicalization is underdeveloped | Action | Memory | `action_module/provider.py` terminal `final_answer` behavior | 22 SearchQA and 9 ToolHop wrong cases with `subem=1.0`; trajectories 848, 680, and 1171 | Exact raw-value formatting is a general terminal contract requirement | High | Add an answer-type canonicalization gate before `final_answer` |
| Contradictory tool-contract observations are not arbitrated | Action | External/Evaluation | `action_module/provider.py` observation handling | EnvScaler status-validation contradictions; trajectories 13 and 33; 52 `accepted` rejection observations with allowed-values payload including `accepted` | APIs can expose stale or state-dependent constraints, so action needs contradiction arbitration | Medium | Add a contradiction handler that records conflicting observations and chooses a different executable path or evidence-grounded stop |

### PART 4: STRENGTHS TO PRESERVE

- The single-executor Action topology is efficient on simple, linear ToolHop chains; trajectory 826 retrieves a publisher, founding date, digit span, and final raw answer `91` in three tool calls, so generation should not add heavy collaboration to every task.
- The Builder/Wiring module correctly injects the local `PlanningClass`, sets `project_root`, binds tool references back to the agent, and preserves factory compatibility; these integration behaviors should remain stable.
- The Planning module produces useful free-form status objects with targets, pending steps, recovery routes, and final criteria in successful trajectories; generation should preserve this compact planning behavior while making critical fields enforceable.
- The Action guard already provides useful soft protections such as alias repair, scalar-to-array coercion, and repeated-failure advisories; generation should strengthen these protections rather than discarding them.
- The Memory module is compact and procedural, with no persisted task facts, IDs, or answers; this lowers overfitting risk and should be preserved.
- The harness reliably reaches terminal tools in many read-only tasks: all SearchQA and ToolHop trajectories have nonzero tool-call counts and valid final outputs, so repairs should improve evidence quality and answer rawness rather than basic terminal availability.
- The harness can complete stateful tasks when entity binding and mutation sequencing are straightforward; trajectory 208 clears and rebuilds a cart, updates the timestamp, calls `complete_task`, and receives EnvScaler score 1.0.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Shared Stateful Progress Ledger]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** Planning -> Action boundary between `planning_module/provider.py` and `action_module/provider.py`
- **Problem:** EnvScaler tasks are marked complete despite unresolved required writes.
- **Mechanism:** Planning should emit compact required-mutation rows, and action should update each row with bound IDs, attempted tool, observed success/failure, and unresolved blocker. `complete_task` should be blocked unless all required rows are satisfied or explicitly impossible with evidence.
- **Why This Module Owns It:** Planning defines obligations, while action observes tool results and controls terminalization.
- **Generalization Rationale:** Confirmed side-effect tracking is necessary for any stateful API task, independent of domain.
- **Complexity:** Medium
- **Expected Impact:** Higher EnvScaler full-score rate and fewer false `Task Completed` endings.
- **Risk:** If the ledger is too rigid, simple tasks may spend extra steps verifying already completed work.

**[Priority 2: Hard Retry and Route-Change Protocol]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py` and `_harness_guards.py`
- **Problem:** The agent repeats failed tool calls even after repeated-failure advisories.
- **Mechanism:** Track failed `(tool, arguments)` keys and prevent identical retries unless a later observation changes the failed precondition. Require the next attempt to name a changed argument, changed tool, or changed hypothesis.
- **Why This Module Owns It:** Action owns concrete tool execution and observation handling.
- **Generalization Rationale:** Bounded, materially different repair is useful across search, database lookup, and stateful mutation tools.
- **Complexity:** Low
- **Expected Impact:** Fewer long loops like trajectories 381, 214, 13, and 33; more budget for real alternate routes.
- **Risk:** A strict blocker could prevent legitimate retries after transient failures unless precondition-change detection is implemented.

**[Priority 3: Tool Schema Preflight and Unknown-Tool Gate]**
- **Target Module:** Action
- **Owner Path:** `_harness_guards.py`; `action_module/provider.py`
- **Problem:** Unknown tools and malformed arguments consume budget and create self-inflicted failures.
- **Mechanism:** Before executing, validate tool existence, required keys, nested required structures, enum-like fields when exposed, array/scalar shape, and known alias repairs. Return a structured repair observation without calling the environment if preflight fails.
- **Why This Module Owns It:** Tool selection, argument preparation, and execution are action-side responsibilities.
- **Generalization Rationale:** Tool schemas vary across all benchmark families and unseen tasks.
- **Complexity:** Medium
- **Expected Impact:** Fewer unknown-tool errors, fewer TypeError traces, and less wasted recovery.
- **Risk:** Over-aggressive validation may reject calls that the underlying tools would tolerate.

**[Priority 4: Observation-Grounded Slot Ledger for Multi-Hop Tasks]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`; Planning -> Action evidence contract
- **Problem:** ToolHop transformations are sometimes applied to source entities or unresolved slots.
- **Mechanism:** Track named intermediate slots from the plan, mark each as observed or unresolved, and block extraction, arithmetic, date, or encoding tools when their input is not an observed value for the intended slot.
- **Why This Module Owns It:** Action sees the observations and chooses transformation tools.
- **Generalization Rationale:** Multi-hop reasoning in any domain depends on exact propagation of intermediate values.
- **Complexity:** Medium
- **Expected Impact:** Fewer chain breaks like trajectories 1171 and 214, and fewer premature cannot-determine answers after recoverable lookup failures.
- **Risk:** Slot tracking can become brittle if plan field names are inconsistent or too verbose.

**[Priority 5: Relation-Specific Search Verification]**
- **Target Module:** Planning
- **Owner Path:** `planning_module/provider.py`
- **Problem:** SearchQA answers often come from nearby but wrong relations.
- **Mechanism:** Add a compact verification target to the plan: requested relation, expected answer type, disallowed nearby relation, and final check question. Action should see this before finalizing a search result.
- **Why This Module Owns It:** Planning owns decomposition, evidence targets, and verification questions before final answer.
- **Generalization Rationale:** Relation drift is common in open-domain search, knowledge-base lookup, and document QA.
- **Complexity:** Low
- **Expected Impact:** Better SearchQA exact answer rate with limited extra tool cost.
- **Risk:** Too much verification may cause over-searching when the first result is already decisive.

**[Priority 6: Terminal Raw-Answer Canonicalizer]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** Correct evidence is sometimes submitted in a non-canonical raw form.
- **Mechanism:** Before `final_answer`, apply lightweight answer-type rules: preserve observed date surface form when it matches the evidence, normalize integer/float only when the task or tool output requires it, remove explanatory prose, and avoid padded binary or over-specific spans unless requested.
- **Why This Module Owns It:** Action owns final-answer tool calls and terminal formatting.
- **Generalization Rationale:** Exact raw outputs are required by short-answer QA, ToolHop transformations, and many evaluation contracts.
- **Complexity:** Low
- **Expected Impact:** Recover a meaningful subset of SearchQA and ToolHop partial cases where evidence was already present.
- **Risk:** Bad normalization could damage valid aliases or remove necessary disambiguation.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory 460, EnvScaler: The agent authenticates Alice Chan and successfully updates contact information, but `add_medical_record` and `edit_medical_record_details` fail due to permission constraints. It invents `switch_user_to_provider`, repeats failed routes, calls `recovery_contract_check`, and finalizes with an escalation message. Score is 0.0.
- Failed trajectory 6, EnvScaler: The agent creates several folders and tags, then attempts bookmarks with invalid tag IDs and unresolved missing tags. Despite failed observations and repeated repair attempts, it returns `Task Completed` with score 0.0.
- Failed trajectory 13, EnvScaler: The agent sees allowed dispute statuses, receives status rejection errors, repeatedly alternates between rejected statuses and tools, and ends without a useful terminal completion. This shows repeated low-value recovery and weak contradiction arbitration.
- Failed trajectory 1171, ToolHop: Required genealogy lookups fail, but the agent extracts the last name of `Kerry Earnhardt` instead of the paternal grandfather and converts `t` to binary. It answers `01110100`; gold is `1110100`.
- Failed trajectory 480, SearchQA: One search result leads the agent to answer `The Prime Minister of the Bahamas`, while gold accepts `any parliamentarian` or `a Government minister`. This is a relation-specific evidence failure after shallow search.
- Failed trajectory 848, SearchQA: The search observation supports the date of the first Soviet atomic bomb as `August 29, 1949`; the gold answer is `29 August 1949`. This illustrates terminal canonicalization sensitivity rather than a tool-use failure.
- Successful trajectory 826, ToolHop: The agent retrieves the publisher of `National Contest Journal`, retrieves the publisher founding date `1914`, extracts digits 2-3 as `91`, and calls `final_answer` with raw `91`. This shows that the single-executor chain works when each slot is observed and transformed in order.
- Successful trajectory 208, EnvScaler: The agent retrieves a user and cart, clears the cart, adds the requested products with correct quantities, updates the cart timestamp, calls `complete_task`, and receives score 1.0. This shows the harness can handle stateful tasks when entity binding and mutation order are simple.
- Bucket-level statistic: Overall average score is 0.4527 across 1241 tasks. EnvScaler averages 0.4351, SearchQA averages 0.4308, and ToolHop averages 0.5252.
- Bucket-level statistic: EnvScaler has `success: false` observations in 474/658 trajectories and repeated-failure advisories in 258/658, making recovery and completion gating the dominant stateful-task issue.
- Bucket-level statistic: SearchQA exact correctness is 129/325, and 22 wrong SearchQA cases have `subem=1.0`, separating retrieval/relation failures from final-format failures.
- Bucket-level statistic: ToolHop exact correctness is 131/258, and wrong ToolHop cases average 10.88 tool calls, indicating evidence-chain and recovery quality issues rather than simple tool underuse.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Emit compact relation-specific verification targets for SearchQA and ToolHop rather than only broad next-step prose.
- [Planning] Preserve the existing compact status-plan style, but make required evidence, unresolved slots, and final criteria easy for Action to consume.
- [Action] Maintain a stateful side-effect ledger for EnvScaler and gate `complete_task` on observed successful required mutations.
- [Action] Convert repeated-failure advisories into an executable retry policy that blocks identical failed calls until a precondition changes.
- [Action] Add allowed-tool and schema preflight before real environment execution, including required keys, nested argument shape, and enum-like constraints when exposed.
- [Action] Block transformation tools when their inputs come from the source entity, task wording, or unresolved placeholders instead of observed intermediate slots.
- [Action] Add a terminal raw-answer canonicalization gate before `final_answer`.
- [Memory] Keep memory procedural and low-noise, but route reminders by failure class: schema preflight, repeated failed call, unresolved slot, stateful postcondition, and raw final answer.
- [Builder] Preserve factory-compatible wiring, local `PlanningClass` injection, project root assignment, and tool-agent binding.
- [Interface] Share structured planning obligations with action and update them from observations; do not rely only on periodic natural-language summaries.
- [Interface] Treat checker output as advisory constraints on the next action, not as substitute environment evidence.
- [Preserve] Keep the efficient single-executor path for simple read-only and linear multi-hop tasks.
- [Preserve] Keep the guard wrapper's useful alias repair and scalar-to-array coercion behavior while adding stronger preflight.
- [Avoid] Do not add benchmark-specific patches for particular names, statuses, medical-record permissions, folder/tag IDs, films, or genealogy entities.
- [Avoid] Do not solve EnvScaler by always calling `complete_task` earlier; the failure is missing verified completion, not lack of terminal calls.
- [Avoid] Do not replace all failures with cannot-determine prose; the terminal contract usually requires a raw answer or a completed state task.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
