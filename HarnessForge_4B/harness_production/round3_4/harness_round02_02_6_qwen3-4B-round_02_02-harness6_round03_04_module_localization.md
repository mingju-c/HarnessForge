### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness under analysis is `harness_round02_02_6`, evaluated in `round03_04` with model `qwen3-4B-round_02_02-harness6`. `builder.py` wires `PlanningClass` from `planning_module/provider.py`, `ActionProvider` from `action_module/provider.py`, and the recommended memory system `format_contract_memory`. It sets `planning_system = "format_contract_planning"`, `action_system = "format_contract_react"`, `prompts_type = ACTION_SYSTEM`, points `project_root` to the local base harness directory, and injects `max_tool_calls_per_step = 2` by default.

The builder binds task tools back to the root `ToolCallingAgent` when they expose an `agent` attribute, and it attaches metadata containing planning/action system names, default bench type, memory system, pairing reason, round, candidate index, and action policy. If a vector tool exists, its memory pointer is set to the agent memory.

The main implementation mismatch is round identity. The evaluated directory is `round_03_04/base harness`, but the harness name, class names, prompt strings, metadata round, and description all identify the implementation as `round02_02`. This is not a direct cause of most trajectory failures, but it can confuse downstream harness selection and reporting. A more consequential wiring limitation is that planning is passed as a class and stored as raw text or raw model output in agent memory; the action module reconstructs ledger state through brittle string parsing rather than receiving a validated planning object.

#### 1.2 Planning Module Implementation

`planning_module/provider.py` implements `PLANNING_SYSTEM = "format_contract_planning"` and a compact planner focused on answer format, date/list/numeric/unit requirements, evidence support, and terminal policy. At initialization, it prompts the model to emit a packet containing `task_type`, `route`, `evidence_slots`, `dependency_edges`, `required_mutations`, `verification_targets`, `answer_format`, `terminal_policy`, and `next_tool_intent`. Memory guidance is appended before the task prompt. If the model returns no content, the provider falls back to an empty unknown-route packet.

The adaptation method periodically asks for a progress packet with observed evidence, derived facts, pending evidence, mutation status, blockers, terminal readiness, and next safe move. These summaries are also stored as raw text. The provider does not parse, validate, repair, or normalize either the initial plan or the progress summary.

Trajectory evidence shows that the planning contract is unreliable on EnvScaler. Of 658 EnvScaler tasks, 598 initial plans were dictionary-shaped tool proposals, 30 were JSON-string tool proposals, and 30 were other dictionaries, leaving no EnvScaler plan in the intended `task_type/route/evidence_slots/required_mutations` ledger format. SearchQA and ToolHop usually emitted ledger strings, but every SearchQA and ToolHop plan mentioned `final_answer`, and many plans seeded terminal intent before the evidence chain was complete. Planning therefore provides useful intent when it follows the template, but it does not currently guarantee an action-visible, route-correct checklist.

#### 1.3 Action Module Implementation

The action module is a guarded single-executor ReAct topology. There are no coordinator-worker, verifier-repairer, debate, or parallel arbitration agents. `action_module/provider.py` configures `format_contract_react` with `support_record_gate=True`, `support_mode="route"`, `complete_gate=True`, `completion_policy="progress"`, `drop_extra_keys=True`, `repeat_limit=2`, `partial_commit_on_blocker=True`, `min_successful_mutations_before_partial_complete=1`, `planned_mutation_cap=1`, `date_iso_canonicalization=True`, `narrow_alias_trim=True`, and `enable_ledger_review_tool=False`.

`action_module/round02_02_agent.py` contains the main behavior. It preflights tool names and argument schemas, drops extra keys when configured, detects repeated failed signatures, blocks low-value repeats, records successful and failed signatures, estimates route from plan text and tool descriptions, and keeps a lightweight evidence/mutation ledger. It canonicalizes some dates, label prefixes, binary strings, and narrow city aliases. It also creates a support record before accepting `final_answer`.

The action loop handles errors through guard observations such as `schema_preflight`, `tool_execution_error`, `repeated_failed_call`, `low_value_repeat`, `terminal_not_ready`, `unsupported_final_answer`, and `answer_support_missing`. These observations include textual recovery advice, but the guard does not force a concrete recovery action. The optional `ledger_review` tool exists in code but is disabled by the variant config.

Final answers are accepted when the candidate appears in recent evidence, when a canonicalized form appears, when answer tokens overlap evidence tokens, when a numeric result appears deterministically derivable, or when the route is stateful. This is useful for blocking unsupported first-step answers, but it is not relation-grounded: it checks evidence presence, not whether the candidate fills the requested slot after all dependencies are satisfied. Terminal completion for stateful tasks is also permissive. `_terminal_ready` uses successful mutation or successful real-call progress, while `_partial_commit_ready` can submit completion after one successful mutation and a blocker. Because EnvScaler plans rarely provide a valid mutation ledger, this often converts partial progress into premature completion.

#### 1.4 Memory Module Implementation

`memory_module/provider.py` implements `format_contract_memory`, a lightweight task-signature memory. At `BEGIN`, it always provides procedural guidance distinguishing observed facts, derived facts, hypotheses, old memories, and commit rules. During execution, every third step it injects a reminder to route recovery by failure class and commit only from current observations or deterministic derivations. If stored records exist, it retrieves up to two records by token overlap with the current query.

The memory module stores success procedures and classified failure lessons. Failure lessons are only stored when the trace matches coarse classes such as schema, repeat, not_found, authorization, empty, unsupported_final, or terminal. The stored lessons include task signatures and truncated trace sketches. This design is directionally helpful, and the guidance correctly says old memories are workflow hints, not current evidence. However, retrieved memories remain lexical and trace-heavy, so they do not provide a structured repair agenda and may add stale IDs or schemas to the prompt. In the observed failures, memory is rarely the primary cause; the dominant weaknesses remain the planning/action contract, terminal readiness, and final-answer support.

### PART 2: FAILURE MODE ANALYSIS

#### Failure Mode 1: Stateful mutation ledger collapse on EnvScaler

- **Name:** Stateful mutation ledger collapse on EnvScaler
- **Frequency / importance:** Dominant. EnvScaler has 658 tasks, average score 0.4341, only 13 exact full-score tasks, 85 zero-score tasks, 100 nonzero tasks below 0.25, 164 tasks from 0.25 to below 0.5, and 236 tasks from 0.5 to below 0.8. `envscaler_done` is high at 0.8815, so many tasks are marked done despite partial or incorrect state.
- **Symptom:** The agent performs some state-changing actions, misses or repeats other required operations, and often completes with low partial credit.
- **Mechanism:** Planning almost never emits a valid EnvScaler ledger. Instead, the initial plan is usually a tool-call-shaped object. Action then parses no reliable `required_mutations` or `verification_targets`, so terminal readiness falls back to local progress signals rather than all requested operations.
- **Generalized capability gap:** The harness lacks a schema-validated stateful Planning -> Action mutation ledger with per-operation status and verification evidence.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Planning and Action
- **Evidence:** 658/658 EnvScaler plans were not intended ledger strings. Captured EnvScaler guard ledgers reported `planned_mutations=0` in 2595 observations and `planned_mutations=1` in only 307 observations. Example 3 performed several pregnancy/health updates, then repeatedly called nonexistent `append_note_to_log` until max steps with score 0.0. Example 5 created duplicate therapy sessions and completed after missing the required duration update, scoring 0.1111. Example 33 resolved no disputes successfully despite several lookups and ended with score 0.0.
- **Generalization rationale:** Any multi-step stateful tool environment needs durable requested-operation tracking. Without it, local progress is easily mistaken for full task completion across scheduling, EHR, billing, group management, therapy, inventory, and account workflows.
- **Confidence:** High

#### Failure Mode 2: Partial progress and blockers are converted into completion

- **Name:** Blocker-after-progress premature completion
- **Frequency / importance:** High for EnvScaler. `complete_task` was called 603 times across EnvScaler trajectories, and `ROUND02_02_PARTIAL_COMMIT` appeared in 297 EnvScaler tasks. Most partial commits occurred in failures.
- **Symptom:** The agent submits `complete_task` after one or more successful state changes even when later required actions failed, repeated, or were never attempted.
- **Mechanism:** `_partial_commit_ready` allows completion after a blocker once at least one successful mutation is observed. `_terminal_ready` under `completion_policy="progress"` accepts mutation progress rather than full checklist satisfaction. Because the planning ledger is missing, the action module cannot distinguish "some progress" from "all requirements completed."
- **Generalized capability gap:** The action module lacks an all-slots terminal gate for stateful tasks and lacks a structured distinction between recoverable blocker, irrecoverable blocker, and complete final state.
- **Primary module owner:** Action
- **Secondary contributor:** Cross-Module Interface
- **Evidence:** Example 5 completed with score 0.1111 after creating multiple duplicate sessions, adding exercises, and appending progress notes, while its own summary claimed the session duration was updated even no `update_session_details` call occurred. Example 33 attempted dispute resolutions with statuses that the environment rejected, retried failed calls, then still reached completion logic with score 0.0. Example 212 repeatedly called `complete_task` and received guard blocks with no successful mutation progress.
- **Generalization rationale:** State-changing APIs often reward exact final state, not partial effort. A progress-based completion rule will misfire in any domain where required operations are conjunctive.
- **Confidence:** High

#### Failure Mode 3: Final-answer support is evidence-present but not relation-grounded

- **Name:** Distractor-supported wrong final answers
- **Frequency / importance:** Dominant for SearchQA and substantial for ToolHop. SearchQA accuracy is 114/325 = 0.3508, and ToolHop accuracy is 108/258 = 0.4186. Among wrong SearchQA tasks, 207/211 still produced a `support_ok: True` support record. Among wrong ToolHop tasks, 134/150 had `support_ok: True`.
- **Symptom:** The harness submits an answer that appears in recent observations but does not answer the requested relation, hop, comparison, or exact answer type.
- **Mechanism:** `_answer_support_status` checks string presence, canonical string presence, token overlap, or route-level acceptance. It does not bind the answer candidate to the planned evidence slot, dependency edge, question relation, or transform input provenance.
- **Generalized capability gap:** The action module lacks slot-bound evidence arbitration before finalization.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** Example 9 answered `Pittsburgh, Pennsylvania` because the string appeared in the search results, but the gold answer was `Pittsburgh suburb`. Example 104 answered `United States Ship` for the Star Trek acronym because token overlap with `ship` and `united` passed support, while the gold answer was `United Space Ship`. Example 198 eventually answered `plants` after relevant evidence stated both entities were shrubs; support passed because `plants` appeared in evidence, but the gold answer was `shrubs`.
- **Generalization rationale:** Retrieval tools routinely return adjacent facts, aliases, distractors, and broader categories. Presence in evidence is not the same as satisfying the requested slot, so this weakness transfers to unseen QA and tool-hop tasks.
- **Confidence:** High

#### Failure Mode 4: Multi-hop dependency chains break after intermediate failures

- **Name:** Multi-hop provenance break after failed intermediate lookup
- **Frequency / importance:** High for ToolHop. ToolHop has average tool-call count 9.47, no-final-answer failures in 28 wrong tasks, `repeated_failed_call` in 77 wrong tasks, `low_value_repeat` in 53 wrong tasks, and `not_found` in 91 wrong tasks.
- **Symptom:** The agent finds a partial fact, fails to retrieve the next dependency, then transforms the wrong date, entity, or fallback value and submits a supported but incorrect final answer.
- **Mechanism:** Planning can name dependency edges, but Action does not maintain a completed-hop ledger. A later transform result can be treated as supported even if the transform input came from an adjacent field or incomplete chain.
- **Generalized capability gap:** The harness lacks dependency-checked provenance from source entity to intermediate relation to transform input to final answer.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Planning and Action
- **Evidence:** Example 4 found the publisher of `National Contest Journal`, then used the publication date `2023` as a proxy for the publisher's founding year and returned `2015`; the gold answer was `1906`. Example 490 repeatedly failed to retrieve the death date for the father of Charles Somers-Cocks, then ended with `unable_to_determine` instead of month `10`. Example 53 cycled through genealogy lookups and invalid fallback tools, then ended with `unknown` instead of `Elizabeth`.
- **Generalization rationale:** Multi-hop tasks across publications, genealogy, dates, organizations, and transformations all require preserving dependency provenance. A correct local transform is insufficient when the input is not proven to be the requested intermediate.
- **Confidence:** High

#### Failure Mode 5: Guard feedback is diagnostic text, not a stateful recovery protocol

- **Name:** Guarded low-value exploration loop
- **Frequency / importance:** High. Across all tasks, `repeated_failed_call` appeared in 402 trajectories, `low_value_repeat` in 281, `schema_preflight` in 308, `tool_execution_error` in 91, `unknown_tool` in 221, and `missing_required` in 136. In failures alone, `repeated_failed_call` appeared 369 times and `low_value_repeat` 262 times.
- **Symptom:** The guard correctly identifies unknown tools, missing keys, repeated failed calls, execution errors, and not-found results, but the agent continues retrying the same signature, inventing unavailable tools, or making near-identical queries.
- **Mechanism:** `_recovery_advice` writes a textual instruction into the observation. It does not update a structured repair state that forces a new identifier source, selects a schema-listed alternative, broadens a query, advances to another pending slot, or stops after irrecoverable evidence.
- **Generalized capability gap:** The action module lacks a repair-state machine for schema errors, ID resolution, relation failures, enum mistakes, and repeated exploration.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Example 3 repeated the unknown tool `append_note_to_log` many times despite the guard listing valid tools. Example 5 invented `add_exercises_to_session` and `create_exercise`, then recovered only after additional loops; it still completed with missing required work. Example 53 received repeated and low-value-repeat guards on genealogy calls, tried unknown `genealogy_search`, and still did not reach the valid answer.
- **Generalization rationale:** Tool-rich environments always contain schema mismatches and unavailable identifiers. Text feedback helps only if action selection has a stateful rule that changes behavior after the first failure class.
- **Confidence:** High

#### Failure Mode 6: Route and mutation semantics drift in planning/action parsing

- **Name:** Read-only work is counted as mutation work or unknown route
- **Frequency / importance:** Medium. SearchQA and ToolHop plans were ledger-shaped, but action-side ledgers often showed nonzero planned mutations for non-stateful tasks. Captured SearchQA ledgers reported `planned_mutations=1` in 968 observations, and ToolHop ledgers reported nonzero planned mutations in most captured observations. ToolHop route was `unknown` in 932 captured ledgers.
- **Symptom:** Read-only QA and transform tasks appear in action ledgers as having mutation counts or unknown route, while the plan often says `required_mutations: []`.
- **Mechanism:** `_planned_mutation_count` falls back to scanning plan text for the substring `mutation`; because every plan contains the field name `required_mutations`, the fallback can report planned mutation progress even when the list is empty or unparsable. Route detection also relies on coarse string and tool-description heuristics.
- **Generalized capability gap:** The planning/action interface lacks typed route semantics and typed slot lists.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Action and Planning
- **Evidence:** Example 1 is a successful read-only ToolHop task, but its support ledger still reports `planned_mutations=1`. Example 4 is a read-only multi-hop task with `planned_mutations=1` and route `unknown` in support records. SearchQA guard ledgers usually reported one planned mutation despite read-only routes.
- **Generalization rationale:** Route-specific guards must know whether a task is lookup, transform, or mutation. String-based route inference will remain brittle across new tools and task families.
- **Confidence:** Medium

#### Failure Mode 7: Memory guidance is generally correct but too coarse to prevent recurring failures

- **Name:** Coarse memory lessons without actionable routing
- **Frequency / importance:** Low to medium. Memory reminders appear frequently, but the dominant failures occur despite guidance that correctly warns against unsupported final answers and repeated failed calls.
- **Symptom:** The agent receives reminders to change identifier source, avoid repeats, and commit from current observations, yet still repeats failed calls or completes from partial state.
- **Mechanism:** Memory retrieves lexical, trace-sketch records and phase reminders. It does not provide route-specific repair plans tied to the current tool schemas and does not quarantine old trace values as unusable tool arguments.
- **Generalized capability gap:** The memory module lacks compact, route-aware, failure-class-specific procedural memories that can be consumed by planning and action as operational constraints.
- **Primary module owner:** Memory
- **Secondary contributor:** Memory -> Action
- **Evidence:** In examples 3 and 5, memory guidance explicitly says to route recovery after schema/not-found/repeat errors, but the agent still repeats invalid tools and completes prematurely. In ToolHop loops such as examples 53 and 490, memory does not turn repeated lookup failures into a concrete alternate search or stop policy.
- **Generalization rationale:** General reminders are useful but insufficient for unseen tasks with new schemas; memory must become a compact operational hint rather than a broad admonition.
- **Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Stateful mutation ledger collapse on EnvScaler | Cross-Module Interface | Planning and Action | `planning_module/provider.py` -> `action_module/round02_02_agent.py` | 658/658 EnvScaler plans were not intended ledger strings; EnvScaler average score 0.4341; only 13 exact full-score tasks | Multi-operation stateful tasks need an authoritative shared checklist before terminal completion can be trusted | High | Validate a structured planning packet and expose required mutations to Action as typed state |
| Blocker-after-progress premature completion | Action | Cross-Module Interface | `action_module/round02_02_agent.py::_terminal_ready`, `_partial_commit_ready`, `_run_partial_commit` | 603 EnvScaler completion calls; 297 partial commits; examples 5, 33, and 212 complete or attempt completion despite missing work | Exact final-state domains require all requested operations, not merely local progress | High | Replace progress-based completion with all-required-slots readiness and explicit blocker states |
| Distractor-supported wrong final answers | Action | Planning | `action_module/round02_02_agent.py::_answer_support_status` | 207/211 wrong SearchQA and 134/150 wrong ToolHop tasks had `support_ok: True`; examples 9, 104, 198 | Retrieval results contain distractors and adjacent facts; support must bind answers to requested relations | High | Require slot-bound support records with relation and answer-type validation |
| Multi-hop provenance break after failed intermediate lookup | Cross-Module Interface | Planning and Action | `planning_module/provider.py` -> `action_module/round02_02_agent.py` | ToolHop accuracy 108/258; wrong ToolHop has 77 repeated failures, 91 not-found traces, and 28 no-final cases; examples 4, 490, 53 | Multi-hop tasks need dependency-checked provenance across every hop and transform | High | Maintain a hop ledger and block final transforms until all prerequisite slots are complete |
| Guarded low-value exploration loop | Action | Memory | `action_module/round02_02_agent.py::execute_tool_call`, `_recovery_advice`, `step` | 402 repeated failed-call trajectories, 281 low-value repeats, 308 schema preflight blocks, 221 unknown-tool traces | Tool schemas and identifiers fail in every domain; recovery must change state, not just print advice | High | Add a structured repair router for schema, not-found, repeat, enum, and authorization failures |
| Read-only work is counted as mutation work or unknown route | Cross-Module Interface | Action and Planning | `planning_module/provider.py` -> `action_module/round02_02_agent.py::_planned_mutation_count`, `_task_route` | SearchQA ledgers reported `planned_mutations=1` in 968 observations; ToolHop route was `unknown` in 932 observations | Route-specific policies cannot transfer if route and slot types are inferred from raw text | Medium | Use typed plan fields and remove substring-based mutation fallback |
| Coarse memory lessons without actionable routing | Memory | Memory -> Action | `memory_module/provider.py::provide_memory`, `_make_failure_record` | Memory reminders are present in examples 3, 5, 53, and 490 but do not prevent repeat loops or premature completion | Unseen schemas need concise operational recovery rules, not broad reminders or old traces | Medium | Store compact route/failure-class procedures and prevent memory-only values from acting as evidence |

### PART 4: STRENGTHS TO PRESERVE

- The single-executor Action topology keeps tool ownership simple and can solve direct chains efficiently; successful ToolHop example 1 uses three tools and a final answer without coordination overhead, so generation should improve the executor rather than replacing it with broad multi-agent orchestration.
- The schema preflight guard in Action is valuable because it catches unknown tools, missing keys, and repeated failed calls before they silently mutate state; examples 3 and 5 show clear guard observations that identify invalid tool names.
- The support-record mechanism in Action prevents unsupported first-step final answers; example 77's initial `final_answer` before evidence was blocked, which is behavior worth preserving even though later support arbitration was too shallow.
- The planner's compact ledger target is the right abstraction when it is followed; successful ToolHop example 1 uses an ordered dependency chain that matches the solved trajectory.
- The Memory rule that old memories are workflow hints and current observations are evidence is correct and should remain, because it reduces answer leakage risk.
- The Action module's ability to repair some failed identifiers from observations should be preserved; successful EnvScaler example 362 first failed to create a journal entry, then activated membership, retried successfully, completed all required operations, and scored 1.0.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Structured Planning-to-Action Ledger Validation]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py` -> `action_module/round02_02_agent.py`
- **Problem:** EnvScaler plans collapse into tool-call proposals, and Action cannot see the required mutation checklist.
- **Mechanism:** Convert the initial planning response into a typed packet with route, evidence slots, dependency edges, required mutations, verification targets, answer format, and terminal policy. If validation fails, run a short repair prompt or deterministic extractor before any action step.
- **Why This Module Owns It:** Planning expresses task decomposition, but Action owns execution and terminal checks. The failure occurs at their boundary.
- **Generalization Rationale:** Typed state transfers across read-only QA, multi-hop transforms, and stateful API tasks because it preserves what must be proven before termination.
- **Complexity:** Medium
- **Expected Impact:** Highest likely EnvScaler gain and better finalization checks across all benchmarks.
- **Risk:** Overly rigid validation may block useful concise plans; validation should allow empty lists while rejecting tool-call-shaped plans for planning.

**[Priority 2: All-Required-Mutations Terminal Gate]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_02_agent.py::_terminal_ready`, `_partial_commit_ready`, `_run_partial_commit`
- **Problem:** `complete_task` fires after partial progress and blockers.
- **Mechanism:** Track every required mutation as pending, succeeded, verified, failed-recoverable, or failed-irrecoverable. Permit `complete_task` only when all required mutations are succeeded or verified, or when an explicit benchmark-permitted irrecoverable-blocker report is available.
- **Why This Module Owns It:** The action module implements terminal tools, partial commit, and blocker handling.
- **Generalization Rationale:** Exact final-state tasks in any API domain require complete operation coverage.
- **Complexity:** Medium
- **Expected Impact:** Reduces low-score EnvScaler completions and prevents "Task Completed" after missing operations.
- **Risk:** If success detection is too strict, the agent may fail to terminate after correct work; observation success parsing must be robust.

**[Priority 3: Slot-Bound Final-Answer Support]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_02_agent.py::_answer_support_status`, `_support_record`
- **Problem:** Wrong answers pass support because they appear in evidence or share tokens with evidence.
- **Mechanism:** Build support records by evidence slot: source observation, extracted candidate, relation label, transform source, and final derivation. Require the final answer to fill the requested slot, not merely appear in an observation. Add answer-type checks for city, date, number, list, acronym expansion, and category-level specificity.
- **Why This Module Owns It:** Action accepts or blocks `final_answer` and has access to observations and tool outputs.
- **Generalization Rationale:** Slot-level support protects against distractors across retrieval and tool-hop tasks.
- **Complexity:** Medium
- **Expected Impact:** Improves SearchQA and ToolHop exact accuracy, especially for distractor-heavy queries.
- **Risk:** A conservative support check can overblock correct short answers if extraction is brittle.

**[Priority 4: Dependency-Checked Multi-Hop Provenance Ledger]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py` -> `action_module/round02_02_agent.py`
- **Problem:** The agent transforms wrong intermediate values after lookup failures.
- **Mechanism:** Represent each dependency edge as a state item with source, relation, observed output, transform input, transform output, and completion flag. Finalization must cite completed dependency slots in order.
- **Why This Module Owns It:** Planning provides dependency edges, while Action must update them from observations and block unsupported transforms.
- **Generalization Rationale:** Multi-hop provenance is domain-independent and applies to biographies, publications, dates, organizations, and numerical transforms.
- **Complexity:** Medium
- **Expected Impact:** Reduces ToolHop wrong-transform and unable-to-determine failures.
- **Risk:** Adds bookkeeping overhead and may require careful prompt compaction to avoid bloating action context.

**[Priority 5: Stateful Recovery Router After Guard Blocks]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_02_agent.py::execute_tool_call`, `_recovery_advice`, `step`
- **Problem:** Guard observations do not force behavior change after schema, not-found, repeat, or unknown-tool failures.
- **Mechanism:** Maintain repair state by failed slot and failed signature. Unknown tools should be banned for the rest of the run and mapped to close valid alternatives when safe. Repeats should force a broader list/search/get call or a different pending slot. Not-found should require identifier resolution before retry. Schema errors should prefill only schema-listed keys from current observations.
- **Why This Module Owns It:** Tool selection, schema preflight, execution, and recovery are action-side responsibilities.
- **Generalization Rationale:** Every tool-use benchmark contains invalid schemas, IDs, enums, and unavailable relations.
- **Complexity:** Medium
- **Expected Impact:** Reduces repeated failed-call loops and max-step dead ends.
- **Risk:** Forced diversification can wander if the tool set is very small; repair state should reset when new evidence arrives.

**[Priority 6: Compact Route-Aware Memory Lessons]**
- **Target Module:** Memory
- **Owner Path:** `memory_module/provider.py`
- **Problem:** Memory reminders are too broad and retrieved trace sketches do not become operational recovery policies.
- **Mechanism:** Store short abstract memories keyed by route and failure class, such as `stateful + unknown_tool`, `multi_hop + not_found`, or `read_only + distractor_span`. Avoid injecting raw old IDs unless explicitly marked same-environment and currently observed.
- **Why This Module Owns It:** The memory provider owns retrieval, scoring, storage, and formatting.
- **Generalization Rationale:** Abstract recovery rules transfer better than stale trace snippets across unseen schemas.
- **Complexity:** Low
- **Expected Impact:** Improves planning stability and reduces prompt distraction.
- **Risk:** Over-compression may remove concrete examples that sometimes help schema repair.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory 3, EnvScaler health/pregnancy update: the agent completed several useful mutations, then repeatedly called nonexistent `append_note_to_log` despite guard messages listing valid tools. It reached max steps with score 0.0, showing that schema feedback did not become a recovery route or completion decision.
- Failed trajectory 5, EnvScaler therapy session task: the agent initially used the user name as an ID, repeated lookups, created duplicate therapy sessions, invented `add_exercises_to_session` and `create_exercise`, eventually added exercises and notes, then completed while missing the claimed duration update. Score was 0.1111.
- Failed trajectory 4, ToolHop publication/publisher founding-year task: the agent repaired a nested metadata schema, found the publisher, but used the publication date `2023` as a proxy for the publisher's founding year and returned `2015`; the gold answer was `1906`.
- Failed trajectory 9, SearchQA location task: the search result contained both `Pittsburgh suburb` and `Pittsburgh, Pennsylvania`; the agent chose the broader city/state answer, and support passed because the string appeared in evidence. Gold was `Pittsburgh suburb`.
- Failed trajectory 104, SearchQA acronym task: the agent answered `United States Ship` for Star Trek `USS`; support passed on token overlap with `ship` and `united`, while the gold answer was `United Space Ship`.
- Failed trajectory 53, ToolHop genealogy task: the agent repeatedly tried failed genealogy calls, attempted unknown `genealogy_search`, and ended with `unknown` instead of `Elizabeth`, demonstrating that repeated-call guards did not impose a new retrieval strategy.
- Successful trajectory 1, ToolHop letter-count task: the plan named the dependency chain, Action called `author_lookup`, `educational_background_finder`, `letter_counter`, then `final_answer`. The answer `1` was supported by the last observation and scored 1.0.
- Successful trajectory 362, EnvScaler group/journal task: after an initial failed journal creation, the agent activated membership, retried creation, deleted and created discussion threads, updated visibility, and called `complete_task` with score 1.0. This shows the single-executor repair loop can work when operations are simple and state progress remains aligned with the task.
- Bucket-level statistic: overall average score was 0.4103 across 1241 tasks. EnvScaler average was 0.4341, SearchQA exact accuracy was 0.3508, and ToolHop exact accuracy was 0.4186.
- Answer-type statistic: SearchQA long-phrase answers were especially weak at 0.257 accuracy, numeric SearchQA was 0.294, and short entity/span SearchQA was 0.371. ToolHop numeric tasks were 0.404, date/day tasks were 0.510, and short entity/span tasks were 0.372. The issue is therefore not limited to one answer format; it reflects support and provenance weaknesses.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Emit a parseable ledger packet for every route; do not let a tool-call object substitute for the planning packet.
- [Planning] Keep lookup and transform steps out of `required_mutations`; only state-changing operations belong there.
- [Planning] Do not place concrete final-answer candidates in `next_tool_intent` before current observations support them.
- [Action] Treat `complete_task` as all-required-mutations-ready, not as progress-plus-blocker-ready.
- [Action] Remove or sharply constrain automatic partial commit unless every required mutation is complete or the task explicitly permits partial completion.
- [Action] Replace string-presence support with slot-bound support that verifies the requested relation, answer type, and transform provenance.
- [Action] After unknown-tool, schema, not-found, or repeat errors, update repair state so the exact failed strategy cannot be selected again without new evidence.
- [Action] For multi-hop ToolHop tasks, block final transforms until every prerequisite hop has a completed evidence record.
- [Memory] Provide compact route/failure-class lessons and avoid injecting long stale trace sketches as guidance.
- [Builder] Update harness metadata so `round03_04` outputs do not still identify themselves as `round_02_02`.
- [Interface] Validate and normalize Planning -> Action fields before execution; expose validation failures as repairable plan defects.
- [Preserve] Keep the single-executor topology, hard schema preflight, and support-record concept because they help successful direct trajectories.
- [Preserve] Keep the distinction that memory and planning are hypotheses while tool observations are current evidence.
- [Avoid] Do not add benchmark-specific patches for `append_note_to_log`, Alice Chan, National Contest Journal, genealogy names, Star Trek acronyms, or Pittsburgh answers.
- [Avoid] Do not fix SearchQA by simply requiring more searches; require better binding between the answer candidate and the requested slot.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
