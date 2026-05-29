### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness under analysis is `harness_round01_8`, evaluated in `round02_02` with result model label `qwen3-8B-round01-harness8`. The builder is located at `harness_factory/rounds/round_02_02/base harness/builder.py`.

`builder.py` wires a single `ToolCallingAgent` through the local harness factory. `prepare_context` sets `planning_system` to `round01_status_packet_planning`, `action_system` and `prompts_type` to `round01_status_packet_react`, sets `project_root` to the harness directory, injects `PlanningClass` into `context.kwargs`, and defaults `max_tool_calls_per_step` to 2. `build_agent_from_context` then instantiates the `ActionProvider`, attaches harness metadata, binds selected tools back to the agent object, and connects vector-tool memory if available.

The harness metadata still reports `round: round_01`, and `Description.md` describes this as a round 01 harness even though the evaluated base harness is used under `round_02_02`. This metadata mismatch is not the dominant execution failure, but it can mislead later generation or analysis steps if round identity is used as evidence.

The builder appears compatible with the harness factory. The main wiring limitation is not a missing provider connection; it is that the builder passes planning, action, and memory together as a conventional single-agent loop without a typed state interface between modules.

#### 1.2 Planning Module Implementation

The planning module is implemented in `planning_module/provider.py` and uses `PLANNING_SYSTEM = "round01_status_packet_planning"`. It builds an initial compact status contract with fields for `target`, `planned_or_pending`, `observed_success`, `observed_failure`, `remaining`, and `final_criteria`. The prompt explicitly discourages executable-looking tool calls, invented tool names, placeholder variables, and plan-as-fact drift.

Initial planning renders the available tool schemas into a Jinja prompt, appends memory guidance to the planning input, and calls the model once. The plan is stored as a `PlanningStep` in agent memory. Adaptation occurs through `adaptation`, which asks the model to summarize observed success, observed failure, remaining work, repair guidance, next step, and final readiness based on memory messages.

The planning module does not produce a machine-enforced task ledger. Its status packet is text or JSON-like text, not a typed contract that the action loop must satisfy before `final_answer` or `complete_task`. It also does not own schema validation, argument repair, or final answer formatting. Planning influences action only indirectly through memory steps and prompt context.

Successful trajectories show that this lightweight planning is useful for simple one-hop QA and straightforward ToolHop chains. The weakness appears when the task requires persistent variable bindings, strict invariant tracking, or durable blocked-call state after errors.

#### 1.3 Action Module Implementation

The action module is implemented in `action_module/provider.py` with `ACTION_SYSTEM = "round01_status_packet_react"`. It uses a single primary ReAct executor, not a coordinator-worker, verifier-repairer, debate, or parallel-worker topology. `build_affordance` loads the primary task tools with reasoning enabled. `build_organization` wraps tools with `_harness_guards.guard_task_tools`, adds a non-environment `status_packet_check` tool, creates the agent, and sets `summary_interval` to 8 if unset.

The action prompt is a strict closed-set JSON tool-calling prompt. It tells the agent to copy exact tool names and argument keys from the current schemas, avoid invented tools, repair failed calls by changing arguments/tools/strategy, avoid identical repeated failures, and call `complete_task` for EnvScaler only after required mutations are observed successful.

The optional `StatusPacketCheckTool` reads recent trajectory messages and asks the model to return `verdict`, `evidence`, `missing_or_risk`, and `next_safe_move`. It is advisory only. There is no enforced consume protocol: if the checker says evidence is incomplete, the action loop can still repeat the same search, call the same failed tool, or finalize the same unsupported answer. In failed runs, this tool sometimes becomes a loop target rather than a useful verifier.

The action module owns tool selection, concrete argument construction, observation handling, retry behavior, and final or terminal submission. Current error handling is primarily prompt-level plus guard advisories. There is no structured blocked-call registry, schema preflight wrapper, typed observation parser, invariant ledger, or final-answer canonicalizer.

#### 1.4 Memory Module Implementation

The memory module is implemented in `memory_module/provider.py` with `MEMORY_SYSTEM = "round01_status_packet_memory"`. It is a lightweight phase-aware procedural memory. At `BEGIN`, it reminds the agent to use a status packet and not treat pending work as observed facts. At `IN`, every configured interval or when error markers appear, it reminds the agent that planned or pending items must not become observed success.

`take_in_memory` explicitly does not persist trajectory facts. The memory system does not retrieve task-specific lessons, store recurring failure repairs, route guidance by benchmark type, or provide separate procedures for EnvScaler, SearchQA, and ToolHop. Its guidance is compact and mostly relevant to the original plan-as-fact failure class, but it is too generic to prevent repeated schema errors, invented identifiers, low-value search loops, or final-answer formatting mistakes.

Memory should be preserved as a low-noise source of procedural reminders, but the observed dominant failures are not caused primarily by memory distraction. They are caused by action-side execution control and the missing planning-to-action state interface.

### PART 2: FAILURE MODE ANALYSIS

- **Name:** Stateful completion without invariant-level verification
- **Frequency / importance:** High. EnvScaler has 658 tasks, average score 0.4825, only 30 perfect scores, 427 partial scores, and 201 zero scores. `complete_task` was called in 458 tasks, but only 30 of those reached score 1.0; 427 completed tasks were partial. The 200 tasks without `complete_task` all scored 0.
- **Symptom:** The agent often reports `Task Completed` after some successful tool observations while hidden or explicit state requirements remain unsatisfied. In ID 1000, the agent completed with EnvScaler score 0.6667 after performing core billing updates but without satisfying the full dispute-resolution detail requirement. In ID 500, the agent completed with score 0.9 despite a largely successful meeting-update workflow, indicating at least one unchecked state expectation remained.
- **Mechanism:** The action loop treats a sequence of local `success: true` observations as enough for terminal readiness. The planner writes high-level final criteria, but the action module does not convert those criteria into an enforced checklist of required state mutations and verification observations.
- **Generalized capability gap:** Missing invariant ledger for stateful workflows. The harness needs a reusable way to track requested mutations, required final state predicates, and terminal readiness across many domains.
- **Primary module owner:** Action
- **Secondary contributor:** Cross-Module Interface, specifically Planning -> Action
- **Evidence:** EnvScaler score distribution: 201 zero, 427 partial, 30 perfect. `complete_task` called in 458 tasks with average score 0.6932 and only 30 perfect. ID 1000 and ID 500 both show terminal completion with partial scores.
- **Generalization rationale:** Any environment with multi-step state changes, hidden constraints, or required verification will fail if terminal submission is governed by prose confidence rather than an explicit observation-backed ledger.
- **Confidence:** High

- **Name:** Failed-call repair collapses into repeated low-value loops
- **Frequency / importance:** High. EnvScaler has repeated-failure advisories in 264 tasks, averaging 5.66 repeated advisories when present. EnvScaler also has 460 tasks with failed observations and 114 tasks with unknown-tool errors. SearchQA has 11 long-loop tasks over 8 tool calls, all incorrect. ToolHop has 27 long-loop tasks over 8 tool calls, 23 incorrect.
- **Symptom:** The agent repeats failed or low-yield actions despite explicit error observations and repeated-failure advisories. ID 2 repeatedly queried the cancelled order and retried `create_order` after a prescription validation mismatch. ID 9 called `status_packet_check` many times after failed user lookup and ended without making environment progress. ID 46 repeatedly probed authentication and patient info after permission denial. ID 49 repeatedly attempted the same waitlist insertion after "procedure does not exist".
- **Mechanism:** The prompt says not to repeat failed calls, but the action module has no durable blocked-call state or error-class repair policy. Guard advisories remain textual observations, so the model can acknowledge them and still repeat the same operation.
- **Generalized capability gap:** Missing execution-level repair controller that classifies failures, blocks repeated exact calls, and forces a different schema-listed repair path.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Repeated advisories in 264 EnvScaler tasks; ID 2, ID 9, ID 46, and ID 49 show repeated failed calls or repeated checker calls. The memory reminder appears during several failed loops but does not change behavior.
- **Generalization rationale:** Repeated-call collapse is not domain-specific. It appears in order workflows, healthcare authentication, waitlist updates, SearchQA query loops, and ToolHop lookup chains.
- **Confidence:** High

- **Name:** Tool/schema hallucination and placeholder identifier use
- **Frequency / importance:** High for EnvScaler and moderate elsewhere. EnvScaler has 114 tasks with unknown-tool errors. Many zero-score stateful tasks begin with invented IDs or natural-language workflow tools that are not in the schema.
- **Symptom:** The agent invents unavailable tools or placeholder arguments. ID 46 called unknown `authenticate_patient` after permission errors. ID 16 called unknown `update_invoice_total_amount`. ID 9 used placeholder user identifiers and guessed email. ID 35 used placeholder `ADDR-12345` before retrieving the actual added address. ID 49 fabricated procedure and department IDs and then failed to reconcile them with environment state.
- **Mechanism:** The action prompt is closed-set, but the model still projects a plausible administrative workflow onto the environment. Planning sometimes lists operations such as "authenticate" when no valid authentication tool exists, and the action loop lacks a schema preflight/argument-source check before execution.
- **Generalized capability gap:** Missing schema-grounded argument provenance discipline. The harness needs to distinguish user-provided IDs, observed IDs, and invented placeholders before mutable calls.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** 114 EnvScaler unknown-tool tasks. ID 46 unknown `authenticate_patient`; ID 16 unknown `update_invoice_total_amount`; ID 35 `ADDR-12345`; ID 9 guessed account identifiers.
- **Generalization rationale:** Dynamic tool environments frequently expose domain-specific IDs and partial CRUD APIs. Without argument provenance checks, the same failure transfers to billing, orders, healthcare, waitlists, support systems, and any future stateful API task.
- **Confidence:** High

- **Name:** SearchQA evidence arbitration and answer extraction weakness
- **Frequency / importance:** High. SearchQA has 325 tasks, 128 correct, 197 incorrect, 143 with no substring match, and 54 partial cases where the gold answer is present but the final answer is not canonical.
- **Symptom:** The agent finalizes an answer that is only loosely related to search results, overlong, or not the requested entity. ID 13 answered a broad July 2018 Stevenbomb period instead of the requested airing dates. ID 14 answered Leighton Baines even after the checker indicated the observation supported only "most assists as a defender", not overall Premier League assists. ID 95 answered Scott McNeil even though later observations mentioned Samuel Vincent in the relevant context. ID 53 repeated nearly identical searches for Madison Grey and ended with a non-answer.
- **Mechanism:** The action loop lacks an evidence arbitration protocol. It does not reliably compare candidate entities across snippets, detect qualifier mismatches, or require that the answer field be bound to a decisive observation. The optional checker can identify weak evidence but does not prevent unsupported finalization.
- **Generalized capability gap:** Missing answer-candidate arbitration and decisive-evidence binding for retrieval QA.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** SearchQA average score 0.4769; 197 incorrect; all 11 long SearchQA loops were incorrect. ID 14 ignored a checker warning; ID 53 looped on repeated search results; ID 95 contradicted its own later evidence.
- **Generalization rationale:** The same failure appears whenever retrieved evidence contains distractors, qualifiers, aliases, dates, or multiple plausible entities.
- **Confidence:** High

- **Name:** ToolHop chain repair and intermediate variable binding failure
- **Frequency / importance:** High. ToolHop has 259 tasks, 145 correct and 114 incorrect. 108 incorrect tasks have no substring match. 36 ToolHop tasks have repeated-failure advisories. Long ToolHop loops are mostly wrong: 23 of 27 tasks over 8 tool calls are incorrect.
- **Symptom:** The agent loses the chain when an intermediate lookup fails, uses an ungrounded fallback value, or finalizes "cannot determine" despite the benchmark having a deterministic tool path. ID 3 failed to find a genealogy relation, retried with an invalid argument, then stopped. ID 31 found the husband but could not retrieve the birth date and finalized unavailability. ID 57 failed to identify the correct author, hallucinated a fallback birth date, calculated from it, and finalized the wrong date.
- **Mechanism:** The initial plan lists the hop sequence, but the action module does not maintain a typed binding table for intermediate variables, source confidence, unresolved variables, and alternate tool candidates. When a hop fails, the model either repeats the same tool or invents a plausible value.
- **Generalized capability gap:** Missing multi-hop state management and repair when an intermediate variable is unresolved or contradictory.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Action
- **Evidence:** ToolHop average score 0.5714; 114 incorrect; ID 3, ID 31, and ID 57 show unresolved intermediate variables leading to wrong or non-answers. The successful ID 22 shows the desired behavior: each intermediate value is obtained from a tool and passed to the next tool.
- **Generalization rationale:** Multi-hop tasks in any domain require durable variable binding, not just a prose plan. This transfers to genealogy, dates, film metadata, publications, arithmetic, and future tool chains.
- **Confidence:** High

- **Name:** Final-answer canonicalization failure
- **Frequency / importance:** Medium. SearchQA has 54 incorrect partial cases where the gold answer appears in the prediction. ToolHop has 6 such cases. These are preventable losses after useful evidence exists.
- **Symptom:** The agent finds the needed value but returns it in the wrong format or with extra prose. ID 119 obtained tool result `1983-02-14` but answered `February 14, 1983`. ID 134 obtained sorted letters as a list but answered `"['a', 'c', 'e', 'i', 'r', 'r']"` instead of `aceirr`. SearchQA partial cases include yes/no answers embedded in sentences and entity answers with extra explanation.
- **Mechanism:** The final prompt says to copy decisive fields exactly, but there is no final-answer postprocessor or answer-type-specific canonicalization step. The model rephrases values naturally even when exact raw output is required.
- **Generalized capability gap:** Missing final answer canonicalizer and raw-value copy discipline.
- **Primary module owner:** Action
- **Secondary contributor:** Cross-Module Interface
- **Evidence:** SearchQA 54 subEM-only failures; ToolHop 6 subEM-only failures; ID 119 and ID 134 have correct observations but incorrect answer strings.
- **Generalization rationale:** Exact answer formats matter across dates, numbers, binary strings, sorted strings, yes/no questions, names, and IDs. The failure is not tied to one benchmark entity type.
- **Confidence:** High

- **Name:** Optional checker is not action-binding and sometimes becomes a distraction
- **Frequency / importance:** Medium. Checker usage is concentrated in failed tasks. In SearchQA, checker use appears in 25 tasks with only 4 correct and 21 incorrect. In ToolHop, checker use appears in 31 tasks with only 3 correct and 28 incorrect. In EnvScaler, checker use appears in 17 tasks with average score 0.2905 and no perfect scores.
- **Symptom:** The checker either warns about incomplete evidence and the agent ignores it, or the checker itself becomes a repeated low-value action. ID 14 used the checker, received a warning that evidence did not support the overall assists answer, then finalized Leighton Baines anyway. ID 9 repeatedly called `status_packet_check` after account lookup failures instead of selecting a productive environment action.
- **Mechanism:** `status_packet_check` is advisory free text. The action loop has no rule that maps checker output to an enforced next action, a blocked final answer, or a throttle on repeated checker calls.
- **Generalized capability gap:** Missing verifier-to-executor contract.
- **Primary module owner:** Action
- **Secondary contributor:** Cross-Module Interface
- **Evidence:** Checker-used tasks are mostly incorrect or partial; ID 14 ignored checker evidence; ID 9 entered a checker loop.
- **Generalization rationale:** Any non-environment verifier needs an actionable integration contract. Otherwise it adds tokens and can amplify uncertainty without changing execution.
- **Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Stateful completion without invariant-level verification | Action | Cross-Module Interface | `action_module/provider.py`; Planning -> Action boundary | EnvScaler: 30 perfect, 427 partial, 201 zero; 458 `complete_task` calls but only 30 perfect; ID 1000 and ID 500 completed with partial scores | Multi-step state tasks require explicit mutation and verification ledgers across domains | High | Add an observation-backed invariant ledger that gates `complete_task` |
| Failed-call repair collapses into repeated low-value loops | Action | Memory | `action_module/provider.py`; guard observation handling | 264 EnvScaler tasks with repeated-failure advisories; ID 2, ID 9, ID 46, ID 49 repeat failed or low-value calls | Tool/API errors recur in any dynamic environment; prompt-only repair does not transfer reliably | High | Add blocked-call registry, error classification, and mandatory strategy switch after repeated failures |
| Tool/schema hallucination and placeholder identifier use | Action | Planning | `action_module/prompts/toolcalling_agent.yaml`; `planning_module/provider.py` | 114 EnvScaler unknown-tool tasks; ID 46 unknown `authenticate_patient`; ID 16 unknown `update_invoice_total_amount`; ID 35 placeholder address ID | Any tool environment with dynamic IDs requires schema and provenance discipline | High | Add schema preflight and argument-source validation before execution |
| SearchQA evidence arbitration and answer extraction weakness | Action | Planning | `action_module/provider.py`; SearchQA action loop | SearchQA: 197 incorrect of 325; ID 13, ID 14, ID 53, ID 95 show distractor acceptance or query loops | Retrieval tasks often contain distractors and qualifier mismatches | High | Add candidate-evidence table, qualifier checks, and decisive-observation binding before final answer |
| ToolHop chain repair and intermediate variable binding failure | Cross-Module Interface | Action | Planning -> Action boundary; `action_module/provider.py` | ToolHop: 114 incorrect of 259; ID 3, ID 31, ID 57 lose or hallucinate intermediate values | Multi-hop tasks require durable variable state across domains and tools | High | Pass a typed hop ledger from planning to action and update it from observations |
| Final-answer canonicalization failure | Action | Cross-Module Interface | `action_module/prompts/toolcalling_agent.yaml`; final-answer path | SearchQA 54 subEM-only failures; ToolHop 6 subEM-only failures; ID 119 and ID 134 have correct observations but wrong final format | Exact answer formats matter for dates, numbers, strings, yes/no, and entity values | High | Add answer-type detection and exact raw-value canonicalization |
| Optional checker is not action-binding and sometimes distracts | Action | Cross-Module Interface | `StatusPacketCheckTool` in `action_module/provider.py` | Checker-used tasks are mostly failed: SearchQA 21 incorrect vs 4 correct; ToolHop 28 incorrect vs 3 correct; ID 14 ignored warning; ID 9 looped checker | Verifiers must change executor state or they become token-heavy advice | Medium | Make checker outputs enforce a next-action contract or throttle checker use |

### PART 4: STRENGTHS TO PRESERVE

- The closed-set JSON tool-calling prompt is owned by Action; successful ID 1 copied the `search` schema and finalized `Peregrine White` after one observation; generation should not regress strict schema copying.
- The single primary executor is owned by Action; successful ID 22 completed a ToolHop chain through director lookup, relationship lookup, first-name extraction, consonant counting, and exact final answer; generation should preserve low-overhead direct execution for simple deterministic chains.
- The compact status packet is owned by Planning; successful and partial EnvScaler tasks use it to keep a visible target and remaining-work list; generation should strengthen it into typed state rather than replacing it with verbose planning.
- The lightweight phase-aware memory is owned by Memory; it avoids contaminating observations with planned actions and adds little prompt noise; generation should preserve this low-noise procedural style while adding more targeted procedural lessons.
- Guard advisories are owned by Action/tool wrapping; they expose repeated failures without crashing the run; generation should preserve the advisory signal but make the executor actually consume it.
- Simple repair after ID collisions is owned by Action; ID 500 and ID 1000 recover from an existing participant/payment ID by finding or selecting a new ID; generation should preserve this local repair behavior while preventing endless retries.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Add a Stateful Invariant Ledger]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`; Planning -> Action boundary
- **Problem:** EnvScaler tasks frequently call `complete_task` with only partial state satisfaction, or fail to call it after getting stuck.
- **Mechanism:** Convert the task and planning status into a compact checklist of required mutations, required verification predicates, observed success, observed failure, and terminal blockers. Gate `complete_task` until each required predicate is supported by an observation or explicitly impossible.
- **Why This Module Owns It:** The action loop chooses terminal actions and observes tool results; therefore it must own readiness gating.
- **Generalization Rationale:** A ledger applies to any stateful CRUD or workflow task, regardless of domain.
- **Complexity:** Medium
- **Expected Impact:** Higher EnvScaler score by reducing partial terminal completions and zero-score non-terminal runs.
- **Risk:** If too rigid, the ledger may over-verify and waste steps on tasks where direct completion is already supported.

**[Priority 2: Add Error-Class Repair and Blocked-Call State]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`; guard-tool observation handling
- **Problem:** The agent repeats failed calls and checker calls despite repeated-failure advisories.
- **Mechanism:** Maintain a per-task blocked-call registry keyed by tool name and normalized arguments. Classify observations into unknown tool, invalid schema, not found, already exists, permission/authentication, validation/precondition, and low-yield retrieval. After a repeated failure, require a different schema-listed tool, different observed ID, or terminal impossible state.
- **Why This Module Owns It:** Malformed calls, retries, and tool selection are action-side responsibilities.
- **Generalization Rationale:** Error classes recur across APIs, search tools, and multi-hop lookup tools.
- **Complexity:** Medium
- **Expected Impact:** Fewer long loops, lower token cost, and more productive repair attempts.
- **Risk:** Over-aggressive blocking could prevent a valid retry after an intervening state-changing observation.

**[Priority 3: Enforce Argument Provenance Before Mutable Calls]**
- **Target Module:** Action
- **Owner Path:** `action_module/prompts/toolcalling_agent.yaml`; `action_module/provider.py`
- **Problem:** The agent invents IDs, authentication tools, and update helpers that do not exist or are not supported by observations.
- **Mechanism:** Add a preflight rule for mutable calls: every ID-like argument must be user-provided, observed from a prior tool result, or explicitly generated only when the schema asks the agent to create a new ID. Unknown tool names should be repaired before execution, not after repeated attempts.
- **Why This Module Owns It:** The action module forms tool calls and has access to the current schema block and recent observations.
- **Generalization Rationale:** Argument provenance is needed in all dynamic tool tasks with entity IDs, records, orders, patients, invoices, meetings, and support tickets.
- **Complexity:** Medium
- **Expected Impact:** Fewer zero-score EnvScaler trajectories caused by placeholder IDs and unavailable helper tools.
- **Risk:** The agent may become too conservative when a valid new ID must be generated; the schema must distinguish create-ID cases.

**[Priority 4: Add Multi-Hop Binding and Evidence Arbitration]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** Planning -> Action boundary; `planning_module/provider.py`; `action_module/provider.py`
- **Problem:** SearchQA and ToolHop failures lose intermediate variables, accept distractors, or finalize unsupported candidates.
- **Mechanism:** Represent key variables as bindings with fields for name, value, source tool, observation snippet, confidence, and unresolved blockers. For retrieval QA, maintain candidate answers and reject candidates whose qualifiers do not match the question. For ToolHop, do not finalize while required intermediate bindings are missing.
- **Why This Module Owns It:** Planning can define the variables, but Action must fill and validate them from observations.
- **Generalization Rationale:** Variable binding and evidence arbitration are reusable across search, genealogy, dates, film metadata, publications, arithmetic, and future multi-hop tasks.
- **Complexity:** Medium
- **Expected Impact:** Better SearchQA and ToolHop correctness, especially on distractor-heavy or failed-hop tasks.
- **Risk:** Excessively detailed binding state can increase prompt length and slow simple one-hop tasks.

**[Priority 5: Add Raw Final-Answer Canonicalization]**
- **Target Module:** Action
- **Owner Path:** `action_module/prompts/toolcalling_agent.yaml`; final-answer path
- **Problem:** The agent often has the right evidence but returns prose, re-formatted dates, lists instead of strings, or embedded yes/no answers.
- **Mechanism:** Before `final_answer`, infer the requested answer type and copy the decisive raw value exactly from fields such as `result`, `date`, `answer`, `value`, or the last tool output. Add compact transformations for known generic outputs: date ISO preservation, binary string leading-zero handling, sorted-letter list joining, yes/no raw answer, and numeric string preservation.
- **Why This Module Owns It:** Final answer construction is owned by the action-side finalization path.
- **Generalization Rationale:** Exact output formats are required across many short-answer tasks, not only the observed examples.
- **Complexity:** Low
- **Expected Impact:** Recover many subEM-only SearchQA and ToolHop losses with minimal architecture change.
- **Risk:** A narrow canonicalizer could overfit benchmark formats or strip needed context from genuinely explanatory answers.

**[Priority 6: Make `status_packet_check` Action-Binding or Throttled]**
- **Target Module:** Action
- **Owner Path:** `StatusPacketCheckTool` in `action_module/provider.py`
- **Problem:** The checker is sometimes ignored when useful and sometimes repeatedly called when unhelpful.
- **Mechanism:** Limit checker use to one call per uncertainty episode, require the next action to address `missing_or_risk`, and prevent finalization of the same unsupported answer unless new evidence has been observed. If no new evidence can be gathered, terminate with the best observation-backed raw answer rather than looping on the checker.
- **Why This Module Owns It:** The checker is an action-side tool and its output must alter executor behavior.
- **Generalization Rationale:** Verifier tools only help if their output changes the executor state across tasks.
- **Complexity:** Low
- **Expected Impact:** Reduced token cost and fewer ignored checker warnings.
- **Risk:** Over-throttling could remove a useful sanity check before difficult final answers.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed EnvScaler ID 2: The agent cancelled an order, added and retrieved an address, verified medications, then failed `create_order` due to a prescription precondition. It validated a prescription against the cancelled order, reserved inventory, repeatedly inspected the cancelled order, retried `create_order`, and ended with score 0.0. This shows missing error repair and missing new-order state tracking.
- Failed EnvScaler ID 9: The agent guessed Maria Sanchez identifiers, failed authentication and user lookup, then called `status_packet_check` repeatedly. It ended with "Maria Sanchez's account is not found" and score 0.0. This shows placeholder identifiers plus checker-loop distraction.
- Failed EnvScaler ID 46: The agent attempted `update_patient_info`, received permission denied, invented unknown `authenticate_patient`, then repeated authentication/status probes many times. It ended with "Authentication is required..." and score 0.0. This shows schema hallucination and no productive repair route after permission errors.
- Failed EnvScaler ID 49: The agent created or guessed procedure and department IDs, then repeatedly attempted waitlist insertion after "procedure does not exist". It ended with score 0.0. This shows weak provenance for generated IDs and repeated failed-call loops.
- Failed SearchQA ID 14: The search result supported Leighton Baines only as the defender assists record holder. The checker warned that this did not prove the overall Premier League assists record, but the agent finalized Leighton Baines instead of Ryan Giggs. This shows ignored evidence arbitration.
- Failed SearchQA ID 53: The agent searched for the Madison Grey actor, then repeated similar searches many times and finalized that the actor was not identified. Gold was Elisabeth Rohm. This shows a low-value retrieval loop and poor query repair.
- Failed SearchQA ID 95: Later search evidence mentioned Samuel Vincent in the relevant Gundam context, but the agent finalized Scott McNeil. This shows distractor acceptance and failure to bind the final answer to decisive evidence.
- Failed ToolHop ID 3: The agent failed a genealogy lookup, tried an invalid extra argument, retried the same failed lookup, and finalized that the answer could not be determined. Gold was 14. This shows missing alternate-hop repair.
- Failed ToolHop ID 57: The agent failed to identify the correct author, hallucinated a fallback birth date, calculated from it, and finalized 1895-05-31 instead of 1935-08-07. This shows ungrounded fallback values after failed intermediate bindings.
- Failed ToolHop ID 119: The tool chain produced `1983-02-14`, but the final answer was `February 14, 1983`, scored wrong against the required raw date. This shows canonicalization failure after a correct path.
- Failed ToolHop ID 134: The agent obtained sorted letters as a list and returned the list string instead of `aceirr`. This shows final-output type mismatch after correct evidence.
- Successful SearchQA ID 1: A single search produced evidence for Peregrine White, and the agent copied the raw entity into `final_answer`. This shows the closed-set single-ReAct path works on simple one-hop evidence.
- Successful ToolHop ID 22: The agent found the director, found the director's father, extracted the first name, counted consonants, and finalized `3`. This shows the harness can succeed when every intermediate tool call returns a clean value and the final answer is copied raw.
- Successful/mostly successful EnvScaler ID 500: The agent recovered from a failed participant ID and an existing participant ID by looking up records and choosing a new participant ID, then completed with score 0.9. This shows local repair can work, but also that terminal invariant checks need strengthening.
- Material statistics: EnvScaler average score is 0.4825 with only 30 perfect tasks. SearchQA answer correctness is 128/325, while 54 additional tasks have substring evidence but non-canonical final answers. ToolHop answer correctness is 145/259, with 108 incorrect tasks having no substring match and 6 additional subEM-only formatting losses.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Preserve compact status packets, but make required variables and final criteria usable by the action loop as a ledger rather than only prose.
- [Planning] Do not plan unavailable authentication, search, helper, or verification tools unless they appear in the rendered schema.
- [Action] Add durable blocked-call and error-class state so repeated failures force a different observed-ID, different schema-listed tool, or explicit impossible-state reasoning.
- [Action] Require ID-like arguments for mutable calls to be user-provided, observed, or schema-authorized as newly generated.
- [Action] Gate `complete_task` on observation-backed state predicates, not on a summary sentence saying the task is complete.
- [Action] Bind final answers to decisive observations and copy raw fields exactly for short-answer tasks.
- [Action] Add answer-type canonicalization for dates, numbers, binary strings, sorted-letter outputs, yes/no answers, and entity-only answers without adding benchmark-specific cases.
- [Memory] Keep phase-aware procedural reminders lightweight, but add targeted recurring lessons for ID provenance, repeated-call blocking, and raw final-answer copying.
- [Builder] Preserve local factory compatibility, `PlanningClass` injection, tool reference binding, and project-root setup.
- [Interface] Introduce a Planning -> Action state handoff for required mutations, unresolved variables, observed bindings, terminal blockers, and final-readiness evidence.
- [Preserve] Keep the single-executor path efficient for one-hop SearchQA and clean ToolHop chains; do not add heavy committees that increase token cost for easy tasks.
- [Preserve] Keep guard advisories, but require the action module to consume them as state-changing repair signals.
- [Avoid] Do not add special cases for Maria Sanchez, Madison Grey, Gundam, specific procedure IDs, specific invoice IDs, or any observed benchmark entity.
- [Avoid] Do not solve EnvScaler by calling more verification tools unconditionally; verification should be tied to required predicates and available schemas.
- [Avoid] Do not let `status_packet_check` become a repeated substitute for environment actions or evidence retrieval.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
