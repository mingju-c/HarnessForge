### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness under analysis is `harness_round02_02_1`, evaluated in `round03_03` with model `qwen3-4B-round_02_02-harness1`. The builder wires `slot_ledger_planning` as the planning system, `slot_ledger_react` as the action system, and recommends `slot_signature_memory` as the memory system. `builder.py` injects `PlanningClass` through `context.kwargs["planning_class"]`, sets `max_tool_calls_per_step` to 2 by default, binds task tools back to the root agent, and attaches metadata such as planning/action system names, pairing reason, round, and policy.

The main implementation mismatch is round identity and behavior mismatch. The directory is `round_03_03/base harness`, but the harness metadata, prompt names, class names, and description all identify the implementation as `round02_02`. More importantly, the description claims a compact evidence and mutation ledger, but many EnvScaler trajectories show the planner emitting a tool-call-shaped plan instead of a parseable ledger packet. In 579 of 658 EnvScaler tasks, the plan trajectory was JSON-tool-like rather than a compact `route/evidence_slots/required_mutations` packet. This causes the action module's ledger parser to see `planned_mutations=0` in most stateful guard observations.

#### 1.2 Planning Module Implementation

`planning_module/provider.py` implements `PlanningProvider.topology_initialize`, which prompts the model to produce a compact execution ledger containing route, evidence slots, dependency edges, required mutations, verification targets, answer format, terminal policy, and next tool intent. It appends memory guidance before asking for the initial plan. If the model returns no text, it falls back to a minimal empty ledger. The adaptation method periodically summarizes observed evidence, derived facts, pending evidence, mutation status, blockers, terminal readiness, and next safe move.

Planning does not validate the returned plan against the requested ledger schema. It stores whatever the model emits as raw plan text. The action module later parses the plan using line-prefix string matching, so any JSON-like plan, prose, duplicated fields, or malformed list text silently degrades the ledger. Planning also does not enforce route-specific semantics: in many SearchQA and ToolHop plans, read-only tool calls are listed under `required_mutations`, which pollutes downstream ledger counts. Planning influences action only indirectly through raw memory text; there is no structured plan object or schema-validated interface.

#### 1.3 Action Module Implementation

The action module is a single-executor guarded ReAct agent. `action_module/provider.py` configures `slot_ledger_react` with `support_record_gate=True`, `support_mode="route"`, `complete_gate=True`, `completion_policy="ledger_or_progress"`, `repeat_limit=2`, `partial_commit_on_blocker=True`, `min_successful_mutations_before_partial_complete=1`, `planned_mutation_cap=2`, and `enable_ledger_review_tool=False`.

`action_module/round02_02_agent.py` contains the real behavior. It preflights tool names and argument keys, drops extra keys when configured, blocks repeated failed calls, records failed signatures, canonicalizes dates and some binary strings, and gates final answers through a support record. It treats an answer as supported if the candidate string appears in recent observations, if its tokens overlap with evidence tokens, if the route is stateful, or if numeric answers may be deterministic. For terminal completion tools, `_terminal_ready` allows completion if either successful mutations reach the ledger requirement or successful real calls reach a small threshold. `_partial_commit_ready` can auto-call the completion tool after a blocker once at least one successful mutation is detected.

The topology has no separate verifier, repairer, or evidence arbitrator. Recovery advice is textual and local to observations. The agent can continue retrying blocked calls or repeated search queries because the guard has no structured recovery state that forces a new identifier source, query decomposition, or alternative tool family. The final-answer support gate is shallow: it checks span or token presence, not whether the answer satisfies the requested relation or all evidence slots.

#### 1.4 Memory Module Implementation

`memory_module/provider.py` implements lightweight task-signature memory. At `BEGIN`, it always provides procedural guidance that distinguishes observed facts, derived facts, hypotheses, retrieval rules, and commit rules. It optionally retrieves the top two records by token overlap between the current task and stored success/failure records. At `IN` phase, every third step it injects a compact reminder to route recovery by failure class and commit only from current observations or deterministic derivations.

The memory module stores both success procedures and classified failure lessons. Failure lessons are generated only for coarse classes such as schema, repeat, not_found, authorization, empty, unsupported_final, and terminal. The retrieved memories can be long trace snippets with stale identifiers, prior task entities, and partial failed calls. The memory guidance is usually directionally correct, but it is not phase-specific enough to prevent the dominant failures. It is a secondary contributor in some stateful tasks because irrelevant prior traces add prompt mass and may bias the initial plan toward copied schemas or entity patterns.

### PART 2: FAILURE MODE ANALYSIS

#### Failure Mode 1: Stateful plans are not converted into a reliable mutation ledger

- **Name:** Planning-to-action mutation ledger collapse on EnvScaler tasks
- **Frequency / importance:** Dominant for EnvScaler. Only 10 of 658 EnvScaler tasks reached full score. 579 of 658 EnvScaler plans were tool-call-like instead of ledger-like. In extracted guard statuses, `planned_mutations=0` appeared in 2331 of 2635 EnvScaler ledger observations.
- **Symptom:** Multi-step state-change tasks often ended with `Task Completed` while required mutations were missing, failed, or only partially attempted.
- **Mechanism:** Planning emits raw unvalidated text, often a JSON tool-use proposal. Action parses plan fields by simple line prefixes. When the expected `required_mutations` field is absent or malformed, the action ledger treats the task as having no planned mutations and therefore cannot enforce per-operation readiness.
- **Generalized capability gap:** The harness lacks a schema-validated Planning -> Action contract for required state changes, evidence dependencies, and terminal criteria.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Planning and Action
- **Evidence:** EnvScaler score buckets: 79 zero-score tasks, 276 tasks in 0.01-0.49, 200 in 0.50-0.74, 93 in 0.75-0.99, and only 10 full-score tasks. Example 460 planned only an `update_patient_info` tool-like action for a four-mutation EHR task; the guard later reported `planned_mutations=0` and completed after failed medical-record operations. Example 959 planned only user lookup for a multi-operation mood-entry cleanup and completed after a repeated restore failure.
- **Generalization rationale:** Any stateful task family with multiple required operations will fail if the terminal gate cannot see an authoritative list of required mutations.
- **Confidence:** High

#### Failure Mode 2: Partial commit turns blockers into premature completion

- **Name:** Blocker-after-progress premature completion
- **Frequency / importance:** High. `ROUND02_02_PARTIAL_COMMIT` occurred in 297 tasks, all concentrated in EnvScaler failures. Among EnvScaler tasks below full score, 297 of 648 contained partial commit.
- **Symptom:** The agent calls `complete_task` after one or more blockers, producing `Task Completed` even when earlier required state changes failed.
- **Mechanism:** `_partial_commit_ready` permits completion after a blocker once a small successful-mutation threshold is met. `_terminal_ready` uses `ledger_or_progress`, which can accept either mutation progress or successful real calls. Because the plan ledger often has zero planned mutations, the threshold collapses to one local success rather than all required changes.
- **Generalized capability gap:** The action module lacks an all-slots-complete terminal gate for stateful workflows and lacks a distinction between recoverable blockers, irrecoverable blockers, and finished state.
- **Primary module owner:** Action
- **Secondary contributor:** Cross-Module Interface
- **Evidence:** Example 460 completed after permission-denied and unauthorized medical-record operations. Example 37 completed after repeated user-account creation failures and only a profile update success. Example 959 completed after `restore_deleted_mood_entry` failed and repeated. EnvScaler done count was 587 of 658, but average EnvScaler score was only 0.441, showing frequent terminal completion without correct final state.
- **Generalization rationale:** Stateful benchmarks commonly reward exact final state, not merely some progress. A blocker-to-completion rule will recur across EHR, scheduling, account, loan, and inventory domains.
- **Confidence:** High

#### Failure Mode 3: Final-answer support is span-based rather than relation-grounded

- **Name:** Distractor-supported wrong final answers
- **Frequency / importance:** Dominant for SearchQA and substantial for ToolHop. SearchQA accuracy was 120/325. Among 205 incorrect SearchQA tasks, 202 had `support_ok: True`. ToolHop accuracy was 125/258; among 133 incorrect ToolHop tasks, 104 had `support_ok: True`.
- **Symptom:** The final answer is wrong even though the harness records a support record as successful.
- **Mechanism:** `_answer_support_status` accepts answers when the string appears in recent evidence or answer tokens overlap evidence. This verifies presence, not whether the candidate satisfies the requested relation, comparison, boolean condition, or multi-hop dependency.
- **Generalized capability gap:** The action module lacks evidence arbitration that maps final candidates back to planned slots, relation constraints, and contradictory evidence.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** Example 424 answered `Cold War` because that string appeared in a search result, but the gold answer was `World War II`. Example 198 answered a refusal-like sentence; support passed due token overlap with `Cydista`, `Pachystegia`, `found`, and `evidence`, while the gold answer was `shrubs`. Example 467 answered `Tu Hi Re` because it appeared in results, but the requested film was `Ek Tara`.
- **Generalization rationale:** Retrieval environments routinely return distractors containing plausible spans. Span presence alone is not transferable evidence of correctness.
- **Confidence:** High

#### Failure Mode 4: Recovery after schema, not-found, and repeat failures is textual but not stateful

- **Name:** Guarded low-value exploration loop
- **Frequency / importance:** High. Overall, `ROUND02_02_GUARD_BLOCK` appeared in 884 tasks, `repeated_failed_call` in 393, `low_value_repeat` in 265, `schema_preflight` in 277, and `tool_execution_error` in 98. In incorrect ToolHop tasks, 71 of 133 had repeated failed calls and 46 of 133 had low-value repeats.
- **Symptom:** The agent receives useful guard feedback but continues retrying the same failed lookup, repeats near-identical search queries, or oscillates between invalid schema variants.
- **Mechanism:** The guard records failed signatures and emits recovery text, but it does not maintain a structured repair agenda, force query diversification, inspect enum alternatives deeply enough, or choose a deterministic fallback when the needed transform is already computable from observations.
- **Generalized capability gap:** The action module lacks a repair-state machine for failed tool calls and repeated exploration.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Example 42 found `Philip Mountbatten` but repeatedly failed the calculator schema and then looped on unsupported `final_answer("15")`; it could have directly computed the combined length. Example 1014 repeatedly queried unavailable genealogy relations after `Information not found` and invalid relationship errors. Example 549 repeatedly searched the same periodical queries and repeatedly tried the same unsupported `Yes` answer.
- **Generalization rationale:** Tool-rich tasks often require switching identifier source, changing relation path, or performing a local transform after tool failure. Textual advice alone does not reliably change the action policy.
- **Confidence:** High

#### Failure Mode 5: Read-only work is mislabeled as mutation work in the plan

- **Name:** Route and slot semantics drift in planning packets
- **Frequency / importance:** Medium. SearchQA and ToolHop plans often contained `required_mutations` even for read-only lookup or deterministic transform tasks. In guard statuses, planned mutations were nonzero for most SearchQA and ToolHop final-answer tasks.
- **Symptom:** The ledger reports mutation counts for read-only QA, and the plan sometimes seeds premature final answers before evidence is collected.
- **Mechanism:** The planning prompt asks for `required_mutations`, but the model fills that field with lookup or transform steps. The action parser treats those list items as mutation counts even though the route is read-only. Some plans set `next_tool_intent` to a final answer candidate before evidence exists.
- **Generalized capability gap:** Planning lacks route-specific field validation and a separation between evidence slots, deterministic transforms, and state mutations.
- **Primary module owner:** Planning
- **Secondary contributor:** Cross-Module Interface
- **Evidence:** Example 424's plan included `next_tool_intent: call final_answer with answer "Napoleonic Wars"` before any search. Example 50, a read-only date question, listed `get_date_of_death_of_wife` and `calculate_one_year_after_date` as required mutations. SearchQA guard statuses showed `planned_mutations=1` in 449 of 498 captured statuses despite read-only routes.
- **Generalization rationale:** If plan fields do not preserve semantic types, downstream modules cannot apply route-specific terminal and verification rules across unseen task families.
- **Confidence:** Medium

#### Failure Mode 6: Memory retrieval is not harmful enough to be primary, but it is noisy and stale

- **Name:** Long stale failure snippets as weak workflow hints
- **Frequency / importance:** Low to medium. Memory guidance appeared frequently at task start and periodically during execution, but the dominant failures still occurred when memory guidance gave the correct general warning.
- **Symptom:** The prompt includes old task traces with unrelated IDs, names, partial failures, and truncated arguments.
- **Mechanism:** Memory scoring is token-overlap based and stores trace sketches up to 900-1000 characters. Retrieved memories are marked as procedure hints, but the agent still sees concrete stale identifiers and schemas in the prompt.
- **Generalized capability gap:** The memory module lacks compact abstraction of reusable lessons and phase-aware filtering by route and failure class.
- **Primary module owner:** Memory
- **Secondary contributor:** Planning
- **Evidence:** Example 460 began with retrieved failure lessons containing unrelated patient IDs, old account values, and truncated EHR traces. The memory correctly warned that current observations are required, but it did not prevent the planner from emitting a tool-call-like plan or the action module from completing after blockers.
- **Generalization rationale:** Long stale memories can distract any tool-use task where exact IDs and schemas are environment-local.
- **Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Stateful plans are not converted into a reliable mutation ledger | Cross-Module Interface | Planning, Action | `planning_module/provider.py` -> `action_module/round02_02_agent.py` | 579/658 EnvScaler plans were tool-call-like; `planned_mutations=0` in 2331/2635 captured EnvScaler ledger statuses; only 10/658 EnvScaler full-score tasks | Multi-operation stateful tasks need an authoritative operation ledger before terminal completion can be trusted | High | Add schema-validated plan packets and action-side fallback extraction for required mutations |
| Partial commit turns blockers into premature completion | Action | Cross-Module Interface | `action_module/round02_02_agent.py::_partial_commit_ready`, `_terminal_ready`, `_run_partial_commit` | 297 EnvScaler partial commits; examples 460, 959, 37 completed after failed required operations | Any stateful environment can have partial progress plus recoverable blockers; completion must mean all required state changes are satisfied | High | Replace blocker-after-progress completion with all-required-slots completion or explicit irrecoverable-blocker reporting |
| Final-answer support is span-based rather than relation-grounded | Action | Planning | `action_module/round02_02_agent.py::_answer_support_status` | 202/205 incorrect SearchQA and 104/133 incorrect ToolHop tasks had `support_ok: True`; examples 424, 198, 467 | Retrieval results often contain distractor spans; final support must bind candidates to relations and slots | High | Require slot-level support records and contradiction checks before accepting final answers |
| Recovery after schema, not-found, and repeat failures is textual but not stateful | Action | Memory | `action_module/round02_02_agent.py::execute_tool_call`, `_recovery_advice`, `step` | 884 guard blocks overall; 393 repeated failed calls; 265 low-value repeats; examples 42, 1014, 549 | Tool-use tasks routinely require structured repair, not repeated textual reminders | High | Add repair-state routing that forces alternate identifier sources, query diversification, schema repair, or deterministic local transform |
| Read-only work is mislabeled as mutation work in the plan | Planning | Cross-Module Interface | `planning_module/provider.py`, `planning_module/prompts/toolcalling_agent.yaml` | SearchQA guard statuses often had nonzero planned mutations; example 424 seeded a final answer; example 50 listed read-only lookup as mutation | Route semantics must transfer across QA, tool reasoning, and stateful tasks | Medium | Enforce route-specific plan schema and prohibit read-only operations in `required_mutations` |
| Memory retrieval is noisy and stale | Memory | Planning | `memory_module/provider.py::_make_failure_record`, `provide_memory` | Example 460 retrieved long unrelated EHR failure snippets; memory did not prevent plan/action failures | Environment-local IDs and traces can distract future tasks if stored as long snippets | Medium | Store abstract failure procedures with short route/failure-class keys instead of long trace sketches |

### PART 4: STRENGTHS TO PRESERVE

- The single-executor topology in Action keeps tool ownership simple and avoids multi-agent handoff failures; successful EnvScaler examples such as 774 show that a direct executor can complete long stateful workflows when it keeps repairing identifiers and continues until all operations succeed.
- The hard schema preflight in Action catches many malformed calls before execution; examples 59 and 792 show schema errors being surfaced clearly, which helps the model recover when it chooses to change strategy.
- The support-record finalization in Action prevents unsupported first-step final answers; example 424's premature `Napoleonic Wars` answer was blocked before any search evidence existed.
- The memory rule that old memories are workflow hints rather than current evidence should be preserved; it is correct and reduces risk of copying stale answers, even though retrieval needs to be shorter and more targeted.
- The planner's compact ledger intent should be preserved; when it emits fields such as evidence slots and dependency edges, those fields give the right abstraction for transferable repairs.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Enforce a Structured Planning-to-Action Ledger]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py` -> `action_module/round02_02_agent.py`
- **Problem:** Stateful tasks lose required mutation counts when the plan is JSON-like, prose, or malformed.
- **Mechanism:** Validate the initial plan into a structured object with route, evidence slots, required mutations, verification targets, answer format, and terminal policy. If validation fails, run a compact repair prompt or deterministic extraction before action starts.
- **Why This Module Owns It:** The failure occurs at the boundary: planning produces text and action assumes parseable ledger fields.
- **Generalization Rationale:** A typed ledger is useful across stateful tools, multi-hop QA, and deterministic transforms because it preserves what must be proven before termination.
- **Complexity:** Medium
- **Expected Impact:** Large improvement on EnvScaler and better terminal gating on all routes.
- **Risk:** Overly rigid validation could block useful concise plans; the repair prompt must be short and route-aware.

**[Priority 2: Replace Partial Commit With All-Slot Terminal Readiness]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_02_agent.py`
- **Problem:** The agent calls `complete_task` after partial progress and blockers.
- **Mechanism:** Track each required mutation as pending, succeeded, verified, failed-recoverable, or failed-irrecoverable. Allow `complete_task` only when every required mutation is succeeded or verified, or when the benchmark explicitly permits partial completion with an irrecoverable blocker report.
- **Why This Module Owns It:** Terminal calls, partial commit, and blocker handling are implemented in the action loop.
- **Generalization Rationale:** Exact final-state benchmarks require operation-level readiness independent of domain.
- **Complexity:** Medium
- **Expected Impact:** Reduces false `Task Completed` results and improves EnvScaler score distribution.
- **Risk:** If too strict, the agent may fail to terminate after correct completion; verification must recognize successful mutation observations reliably.

**[Priority 3: Upgrade Final Support From Span Match to Slot Binding]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_02_agent.py::_answer_support_status`
- **Problem:** Wrong SearchQA and ToolHop answers pass support because the answer string appears somewhere in recent evidence.
- **Mechanism:** Build a support record per evidence slot: source observation, extracted candidate, relation, transform, and final answer derivation. For boolean/comparison questions, require evidence for both sides and a comparison statement. For "not found" answers, require the answer format to permit absence.
- **Why This Module Owns It:** The action module accepts or blocks final answers.
- **Generalization Rationale:** Slot binding transfers to any retrieval or tool-hop task with distractors.
- **Complexity:** Medium
- **Expected Impact:** Improves final-answer precision and reduces distractor-span errors.
- **Risk:** More conservative support may lower recall if extraction is brittle.

**[Priority 4: Add Stateful Repair Routing After Tool Failures]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_02_agent.py::execute_tool_call`, `_recovery_advice`, `step`
- **Problem:** Guard feedback does not reliably change behavior after schema, not-found, repeat, or execution errors.
- **Mechanism:** Maintain a repair state per failed slot or signature. After repeat/not-found, force a different identifier source, broader list/search tool, enum inspection, or next dependency. After transform-tool schema failure, permit deterministic local computation when all inputs are observed.
- **Why This Module Owns It:** Tool choice, recovery, and observation handling are action-side responsibilities.
- **Generalization Rationale:** All tool-use domains need robust recovery from invalid identifiers, unavailable relations, and schema mismatches.
- **Complexity:** Medium
- **Expected Impact:** Reduces ToolHop loops and stateful dead ends.
- **Risk:** Forced diversification can wander if the available tool set is small; repair state should expire when new evidence arrives.

**[Priority 5: Compact and Route Memory by Failure Class]**
- **Target Module:** Memory
- **Owner Path:** `memory_module/provider.py`
- **Problem:** Retrieved memories contain long stale traces with unrelated IDs and schemas.
- **Mechanism:** Store shorter abstract lessons keyed by route, failure class, and recovery action. Avoid injecting raw identifiers unless the memory is same-environment and explicitly marked reusable.
- **Why This Module Owns It:** Memory selection and content formatting are implemented in the memory provider.
- **Generalization Rationale:** Abstract failure procedures transfer better than old task traces.
- **Complexity:** Low
- **Expected Impact:** Reduces prompt distraction and improves initial planning stability.
- **Risk:** Over-compression may remove concrete schema reminders that sometimes help.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory 460, EnvScaler EHR update: the plan was a single tool-call-like `update_patient_info` proposal for a four-mutation task. The agent updated provider info, failed to add a record with permission denied, failed to edit a medical record with unauthorized errors, then auto-submitted `complete_task` after a repeated failed edit. Score was 0.1111.
- Failed trajectory 959, EnvScaler mood-entry cleanup: the plan only looked up Alice Chan. The agent found the user and mood entry, failed to restore the deleted entry, then partial-committed after a repeated restore failure. Score was 0.0.
- Failed trajectory 42, ToolHop monarch spouse length: the agent correctly found `Elizabeth II`, spouse `Philip Mountbatten`, and first/last names, but failed calculator schema repair and repeatedly attempted unsupported `final_answer("15")`. Gold was `17`.
- Failed trajectory 424, SearchQA: the agent initially tried an unsupported final answer before evidence, then searched until a distractor result contained `Cold War`. The support gate accepted the span because it appeared in evidence, but the gold answer was `World War II`.
- Failed trajectory 198, SearchQA: search observations contained enough botanical evidence that `Cydista` is a genus of shrubs, but the final answer was a refusal-style sentence. Token-overlap support accepted it, while gold was `shrubs`.
- Successful trajectory 774, EnvScaler class-session update: despite an initial failed user lookup, the agent repaired identifiers through `get_user_by_name`, completed the instructor, location, capacity, registration modification, and new registration operations, then called `complete_task` with EnvScaler score 1.0.
- Successful trajectory 480, SearchQA: one search produced the answer span `a Government minister`; the final support record correctly tied the final answer to the search observation, and the task scored 1.0.
- Bucket-level statistics: overall average score was 0.4321 across 1241 tasks. EnvScaler average score was 0.4411 with only 10/658 full-score tasks. SearchQA answer accuracy was 120/325. ToolHop answer accuracy was 125/258. Guard blocks appeared in 884 tasks, and partial commit appeared in 297 tasks.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Emit a schema-valid ledger object for every task; do not let a tool-call proposal replace the plan packet.
- [Planning] Keep read-only lookup steps out of `required_mutations`; use evidence slots and deterministic transform slots instead.
- [Planning] Do not put a concrete final answer in `next_tool_intent` before current observations support it.
- [Action] Treat `complete_task` as all-required-mutations-ready, not as progress-plus-blocker-ready.
- [Action] Replace span-only support with slot-bound support that verifies the requested relation, comparison, or transform.
- [Action] After a repeated failed call, force a different recovery route rather than returning only textual advice.
- [Action] Allow deterministic local transforms when tool evidence supplies all inputs and the transform tool fails for schema reasons.
- [Memory] Retrieve compact route/failure-class lessons, not long raw trace snippets with stale environment-local IDs.
- [Builder] Update metadata so the harness identity and round fields match the actual round under analysis.
- [Interface] Validate Planning -> Action fields before execution and expose validation failures as repairable plan defects.
- [Preserve] Keep the single-executor direct tool-use topology and hard schema preflight because they help successful repair trajectories.
- [Preserve] Keep the rule that memory is a hint and current observations are evidence.
- [Avoid] Do not add benchmark-specific branches for Alice Chan, genealogy names, EHR schemas, or SearchQA entities; repair the generic ledger, support, and recovery capabilities instead.
- [Avoid] Do not make support stricter by simply requiring more searches; require better binding between observed evidence and the requested answer slot.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
