### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness is assembled in `builder.py` as a single `ToolCallingAgent` with local planning, action, and memory providers. `prepare_context` sets `planning_system=round02_01_repair_ledger_planning`, `action_system=round02_01_repair_ledger_react`, `prompts_type` to the action system, `project_root` to the harness directory, `planning_class=PlanningClass`, `max_tool_calls_per_step=2`, and `harness_status_contract=REPAIR_LEDGER`. `build_agent_from_context` then constructs the agent through `ActionProvider`, annotates the agent with `harness_name=harness_round02_01_2`, binds tool back-references, and ensures OWL memory fields if needed.

The harness directory is the round 03.01 base harness, but the implementation and metadata still identify the harness as `harness_round02_01_2`, with metadata round `"round_02_01"` and model outputs labeled `qwen3-8B-round_02_01-harness2`. This is a metadata mismatch relative to the current factory round, but the observed failures are behavioral rather than caused by wrong provider wiring. The description accurately states the intended design: preserve a single ReAct executor while adding a repair ledger, bounded failure triage, and phase-aware memory reminders.

#### 1.2 Planning Module Implementation

`planning_module/provider.py` implements `PlanningProvider`, a compact planner that asks the model to produce a repair-ledger status contract. The initial planning prompt requests fields such as `target`, `answer_or_state_type`, `planned_or_pending`, `repair_ledger`, `remaining`, and `final_criteria`. The adaptation prompt asks for periodic ledger summaries containing observed successes, observed failures, remaining work, retry guidance, and final readiness.

The planning module does not validate the plan schema, normalize it into structured state, or enforce that the action module follows it. In several EnvScaler trajectories, the actual plan degenerates into an immediate tool-call-shaped JSON object instead of the requested status contract. For example, item 460 starts with a plan to call only `update_patient_info`, and item 212 starts with only the first patient contact update. This leaves multi-row state-change tasks without a durable checklist that can block premature completion.

Memory guidance is appended to planning inputs, but planning stores it only as `memory_guidance` on the `PlanningStep`; there is no code-level routing from memory to a structured ledger. Planning therefore influences action mostly through text in the agent memory, not through a machine-checkable interface.

#### 1.3 Action Module Implementation

`action_module/provider.py` implements a single-agent ReAct topology. It loads the task tools, wraps them with `_harness_guards.guard_task_tools`, adds one extra non-environment tool called `repair_triage_check`, and creates one primary `ToolCallingAgent`. There is no coordinator-worker, verifier-repairer, debate, or parallel worker topology.

`RepairTriageTool` reads recent trajectory messages and asks the model to classify the latest failure as schema mismatch, bad ID, missing entity, precondition, permission, empty result, contradiction, or execution error. It returns advisory text only. It does not mutate environment state, does not update a structured ledger, and does not prevent the main agent from repeating a failed call or calling a terminal tool while required work remains open.

The action prompt requires strict JSON, exact schema names, a mental `REPAIR_LEDGER`, and a warning not to repeat identical failed calls unless a precondition changed. It also says stateful rows remain open until successful observations close them. However, these are prompt-level instructions. The action loop has no explicit terminal preflight, no row-completion checker, no aggregation protocol, and no arbitration layer for contradictory observations. This explains why the agent often calls `complete_task` after only partial EnvScaler completion and why repeated failure loops continue despite guard advisories.

#### 1.4 Memory Module Implementation

`memory_module/provider.py` implements lightweight procedural memory. At `BEGIN`, it injects one reminder: after a failed tool call, classify the error and change the next attempt. During `IN`, it uses string heuristics over recent context to decide whether to inject reminders about repeated failure, bad IDs, raw value copying, or terminal readiness refresh. `take_in_memory` explicitly stores no task facts, IDs, answers, or trajectory-specific lessons.

The memory is compact and generally aligned with the repair-ledger concept, but it is not a state tracker. It cannot remember which EnvScaler rows are complete, which required rows are still blocked, or which intermediate ToolHop slot has been verified. In trajectories, memory reminders often appear even when the immediate problem is not a repeated failure, and the reminders remain advisory. Memory is a secondary contributor to distraction and weak recovery, not the primary owner of the dominant failures.

### PART 2: FAILURE MODE ANALYSIS

**Name:** Premature terminal completion on partially completed state-change tasks

- **Frequency / importance:** Dominant EnvScaler failure. EnvScaler has 658 items, only 21 full-score completions, 429 partial completions with `complete_task`, and 208 zero-score runs without completion. Overall EnvScaler average score is 0.4598 despite `envscaler_done=0.6839`.
- **Symptom:** The harness calls `complete_task` with `"Task Completed"` while required state changes are failed, missing, or only partially attempted.
- **Mechanism:** The action module treats terminal completion as a normal tool call and has no enforced check that every required row has an observed successful mutation. Planning often fails to provide a complete structured row ledger, and action keeps the ledger only in natural-language "think" text.
- **Generalized capability gap:** Missing terminal-readiness gate for multi-operation, stateful tasks.
- **Primary module owner:** Action
- **Secondary contributor:** Cross-Module Interface, specifically Planning -> Action
- **Evidence:** Item 460 completes after successful patient/provider contact updates but failed `add_medical_record` and failed `edit_medical_record_details`. Item 212 completes after repeated permission failures and only provider updates. Item 1222 completes with score 0.64 after omitting the `Research` folder and placing the PubMed bookmark under the wrong subfolder.
- **Generalization rationale:** Any unseen stateful workflow with multiple required mutations can be marked complete prematurely unless terminal calls are gated by observed row completion.
- **Confidence:** High

**Name:** Low-value repair loops after tool failures, schema mismatches, or unavailable actions

- **Frequency / importance:** 549 failed cases contain tool failure/error evidence; 159 involve schema, invalid argument, or unknown-tool patterns. Six QA tasks fail to call `final_answer`, typically after long loops.
- **Symptom:** The agent repeats invalid or unproductive calls, calls unavailable tools, or keeps retrying the same broad strategy after the environment has already returned a decisive failure.
- **Mechanism:** `repair_triage_check` is advisory and can recommend unavailable or vague moves. Guard advisories warn about repeated failures but do not block execution or force a different valid schema path. The main executor has no bounded failure-state machine.
- **Generalized capability gap:** Missing failure arbitration protocol that converts failure classes into enforceable next-action constraints.
- **Primary module owner:** Action
- **Secondary contributor:** Memory
- **Evidence:** Item 212 repeatedly attempts unavailable `authenticate_as_admin` and repeats authentication checks despite repeated-failure advisories. Item 486 makes 296 tool calls around `monarch_reign_analyzer` and `relationship_query_tool` before ending without a valid answer. Item 203 alternates unsupported `name_variants` arguments and unknown father lookups, then answers from unsupported prior knowledge.
- **Generalization rationale:** Tool-rich tasks commonly expose schema friction, missing data, and precondition errors; without bounded recovery, the agent wastes budget and may terminate incorrectly.
- **Confidence:** High

**Name:** Multi-hop evidence-chain break and unverified intermediate slots

- **Frequency / importance:** ToolHop has 131 incorrect items out of 258; 122 incorrect ToolHop cases show chain/transform-style error signals. Average ToolHop answer correctness is 0.4922.
- **Symptom:** The agent accepts an intermediate answer that does not satisfy the requested relation or transformation, then confidently computes the final value from the wrong slot.
- **Mechanism:** Planning decomposes tasks into plausible steps but does not require each intermediate slot to be verified against the target relation before downstream tools consume it. Action copies whatever the latest tool returns into the next slot, even when the observation is for a parent instead of a paternal grandfather, or for the original subject rather than the requested ancestor.
- **Generalized capability gap:** Missing intermediate-slot verifier for relation depth, entity identity, and transformation preconditions.
- **Primary module owner:** Planning
- **Secondary contributor:** Action
- **Evidence:** Item 1116 asks for the count of `ō` in the first name of the paternal grandfather of Hōjō Akitoki. The agent accepts `Kanezawa Sanetoki` as the paternal grandfather after a `parentage` lookup, extracts `Kanezawa`, and answers `0`; the gold answer is `2`. Item 1171 fails to find Kerry Earnhardt's paternal grandfather and falls back to Kerry Earnhardt's own last name before converting `t` to binary.
- **Generalization rationale:** Multi-hop tasks across genealogy, dates, publications, geography, and arithmetic all require verified slot binding before transformation; the weakness is not tied to one domain.
- **Confidence:** High

**Name:** SearchQA distractor selection and final-answer extraction failure

- **Frequency / importance:** SearchQA has 195 incorrect answers out of 325; 194 of these use `search`, so the dominant issue is not missing search use. Average SearchQA answer correctness is 0.4000.
- **Symptom:** The agent retrieves useful or partially useful passages but extracts the wrong entity, often a distractor mentioned near the relevant evidence.
- **Mechanism:** The action module has no evidence arbitration step that checks candidate answers against the predicate, answer type, and question subject. Planning's search query is often a single broad query, and action finalizes after one search without verifying whether the chosen span answers the requested relation.
- **Generalized capability gap:** Missing observation-to-answer verifier for short-answer QA.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** Item 752 asks for the full name of the leader of the band Tommy Duncan was part of. Search evidence mentions Bob Wills and The Texas Playboys, but the agent answers Tommy Duncan's own full name, `Thomas Elmer Duncan`; the gold answer is `James Robert Wills`.
- **Generalization rationale:** Search snippets commonly contain subjects, related entities, and distractors. A transferable harness must verify that the final entity fills the requested role, not merely appears in the passage.
- **Confidence:** High

**Name:** Final-answer canonicalization and raw-answer contract violations

- **Frequency / importance:** Across QA benchmarks, 320 items call `final_answer` but are wrong; 31 incorrect QA cases have `subem=1.0`, indicating the harness often finds a related value but emits the wrong canonical form or extra text. This includes 22 SearchQA and 9 ToolHop cases.
- **Symptom:** The final answer includes extra prose, a leading zero, an impossibility statement, or a related but non-canonical variant.
- **Mechanism:** The final-answer prompt says to return only the raw answer, but the action module does not run a final canonicalization preflight. It also lacks answer-type-specific normalization rules, such as binary strings without leading padding when the expected raw answer omits padding.
- **Generalized capability gap:** Missing final-answer format validator and evidence-to-answer canonicalizer.
- **Primary module owner:** Action
- **Secondary contributor:** Planning
- **Evidence:** Item 1171 returns `01110100` while the gold answer is `1110100`; the path partially finds the character but fails the canonical output. Item 203 returns a full explanatory sentence instead of only the raw answer `6`.
- **Generalization rationale:** Raw-answer compliance matters across short-answer, arithmetic, transformed-value, date, and ID tasks. The weakness is independent of the specific entity.
- **Confidence:** Medium

**Name:** Planning-output contract drift and weak Planning -> Action handoff

- **Frequency / importance:** Qualitatively important across EnvScaler and ToolHop failures; it is not directly counted by metrics but appears in representative trajectories.
- **Symptom:** The initial plan sometimes ignores the required repair-ledger schema and emits an immediate tool-call object or an incomplete first-step plan. Action then proceeds without a full list of required rows or terminal criteria.
- **Mechanism:** The planning provider stores model text without schema validation. The action provider does not parse the plan into required rows, so it cannot tell whether `complete_task` or `final_answer` is allowed.
- **Generalized capability gap:** Missing machine-readable contract between planning and execution.
- **Primary module owner:** Cross-Module Interface
- **Secondary contributor:** Planning
- **Evidence:** Item 460's plan is just a first `update_patient_info` call even though the task has four required mutations. Item 212's plan starts with only one patient update in a multi-patient, multi-record administrative task.
- **Generalization rationale:** Any complex task with multiple rows, dependencies, or final criteria needs planning state that survives into action. Natural-language intent is too weak for reliable terminal control.
- **Confidence:** High

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Premature terminal completion on partially completed state-change tasks | Action | Cross-Module Interface | `action_module/provider.py`; Planning -> Action terminal boundary | EnvScaler: 429 partial `complete_task` calls; items 460, 212, 1222 | Multi-operation state tasks need observed row completion before terminal calls, regardless of domain | High | Add a terminal-readiness gate that blocks `complete_task` while any required row is pending, failed, or unverified |
| Low-value repair loops after tool failures, schema mismatches, or unavailable actions | Action | Memory | `action_module/provider.py`; `repair_triage_check`; guarded tool loop | 549 failed cases with tool errors; 159 schema/invalid cases; items 212, 486, 203 | Tool-rich tasks often include schema and precondition failures; recovery must be bounded and enforce valid next moves | High | Convert failure classification into enforceable retry constraints and escalation rules |
| Multi-hop evidence-chain break and unverified intermediate slots | Planning | Action | `planning_module/provider.py`; action observation-to-slot binding | ToolHop: 131 incorrect; 122 chain/transform failures; items 1116, 1171 | Multi-hop transformations require verified relation depth and entity identity before downstream computation | High | Add intermediate-slot verification for relation, entity, and transformation preconditions |
| SearchQA distractor selection and final-answer extraction failure | Action | Planning | `action_module/provider.py`; final answer selection loop | SearchQA: 195 incorrect, 194 with search; item 752 | Search snippets contain distractors; final candidates must match predicate and answer type | High | Add candidate-answer arbitration before `final_answer` for short-answer QA |
| Final-answer canonicalization and raw-answer contract violations | Action | Planning | `action_module/prompts/toolcalling_agent.yaml`; final-answer phase | 31 incorrect QA cases with `subem=1.0`; items 1171 and 203 | Raw-answer formatting is benchmark-independent for short answers, dates, numbers, IDs, and transformed values | Medium | Add a final canonicalization checklist or validator before terminal short-answer submission |
| Planning-output contract drift and weak Planning -> Action handoff | Cross-Module Interface | Planning | `planning_module/provider.py`; `builder.py` context contract | Items 460 and 212 show first-action plans instead of full ledgers | Complex tasks require durable planning state visible to execution and terminal gating | High | Parse or normalize planning output into a structured row ledger consumed by action |

### PART 4: STRENGTHS TO PRESERVE

- The single-executor ReAct topology in Action should be preserved for simple linear tasks; SearchQA item 480 succeeds with one search after a repair-triage query and then copies `Government minister`, showing that a lightweight executor can solve direct evidence tasks without expensive collaboration.
- The direct tool-chain execution pattern in Action should be preserved when intermediate slots are obvious and observations are decisive; ToolHop item 826 correctly retrieves the publisher, obtains founding year `1914`, extracts digits `9` and `1`, concatenates them, and answers `91`.
- The repair-aware prompting in Planning and Memory should be preserved because it sometimes recovers from initial bad IDs or failed calls; EnvScaler item 1123 eventually recovers from a wrong patient ID and a broken `reserve_bed` path by finding the correct patient and alternative reservation route.
- The closed-set schema emphasis in Action should be preserved because it keeps many successful QA tasks concise and terminal-compliant; SearchQA has 130 correct answers and ToolHop has 127 correct answers under this simple tool-use contract.
- The builder's local provider wiring should be preserved because the intended planning, action, and memory modules are actually connected; the failures come from missing enforcement inside the connected modules rather than from an absent provider.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Add Terminal Readiness Gate for Stateful Tasks]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`; terminal tool handling around `complete_task`
- **Problem:** EnvScaler calls `complete_task` after partial completion, failed mutations, or omitted required rows.
- **Mechanism:** Before `complete_task`, require a compact row ledger with one row per requested mutation and block terminal calls unless every row has a successful observation or a supported impossibility route that the benchmark allows.
- **Why This Module Owns It:** The action loop chooses terminal tools and observes mutation results.
- **Generalization Rationale:** Any stateful workflow benefits from row-level terminal gating, whether the domain is health records, bookmarks, reservations, disputes, or enrollment.
- **Complexity:** Medium
- **Expected Impact:** Should directly reduce the 429 partial EnvScaler completions.
- **Risk:** If implemented too rigidly, it may block valid terminal calls when the environment uses implicit state changes or when the task genuinely permits evidence-backed impossibility.

**[Priority 2: Normalize the Planning Ledger into Executable State]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** Planning -> Action boundary; `planning_module/provider.py` output consumed by the agent memory/action loop
- **Problem:** Plans often become first-action suggestions rather than complete final criteria, leaving action without durable required rows.
- **Mechanism:** Normalize planning output into structured fields: task type, required rows, dependencies, observed success, observed failure, pending rows, and terminal criteria. If the model emits malformed planning text, repair it before action begins.
- **Why This Module Owns It:** Planning is asked to produce the ledger, but action must consume it; the weakness is the interface between them.
- **Generalization Rationale:** Structured state supports multi-hop QA, stateful tasks, and transformed-value tasks without benchmark-specific rules.
- **Complexity:** Medium
- **Expected Impact:** Should improve terminal control and reduce missed subtasks in EnvScaler and ToolHop.
- **Risk:** Overly verbose ledgers could increase prompt bloat and slow simple one-hop tasks.

**[Priority 3: Enforce Bounded Failure Arbitration]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`; `RepairTriageTool`; guarded action loop
- **Problem:** The harness repeats failed calls, invents unavailable tools, and follows vague repair advice.
- **Mechanism:** Track recent failed tool-name/argument pairs and require the next move to satisfy one of a small set of enforceable changes: valid schema repair, different available tool, observed precondition change, or explicit non-terminal impossibility note. Do not let `repair_triage_check` recommend unavailable tools as actionable.
- **Why This Module Owns It:** The action module owns tool selection, error handling, and retry behavior.
- **Generalization Rationale:** Bounded failure handling transfers to any environment with schemas, permissions, missing data, or transient tool errors.
- **Complexity:** Medium
- **Expected Impact:** Should reduce long loops like item 486 and unknown-tool loops like item 212.
- **Risk:** Too aggressive stopping may abandon recoverable tasks if the allowed repair categories are too narrow.

**[Priority 4: Add Intermediate-Slot Verification for Multi-Hop Tasks]**
- **Target Module:** Planning
- **Owner Path:** `planning_module/provider.py`; planning prompt and adaptation summaries
- **Problem:** ToolHop failures often compute from an entity that has not been verified as the requested relation or slot.
- **Mechanism:** Require each planned intermediate slot to include an expected relation, accepted evidence form, and a "slot closed only if" condition. Before downstream transformation, action should restate which observation closed the slot.
- **Why This Module Owns It:** Planning owns decomposition, relation depth, and final criteria; action is a secondary enforcer.
- **Generalization Rationale:** Relation-depth and slot-verification discipline applies to genealogy, publications, geography, dates, arithmetic, and entity-property chains.
- **Complexity:** Medium
- **Expected Impact:** Should reduce wrong-chain ToolHop answers such as items 1116 and 1171.
- **Risk:** More verification may add tool calls and hurt very simple tasks if not kept compact.

**[Priority 5: Add Final-Answer Canonicalization Preflight]**
- **Target Module:** Action
- **Owner Path:** `action_module/prompts/toolcalling_agent.yaml`; final-answer generation path
- **Problem:** The harness sometimes emits extra prose, padded binary strings, or related values instead of the requested raw answer.
- **Mechanism:** Before `final_answer`, classify answer type and apply a compact checklist: raw value only, no prose, no unsupported normalization, no distractor entity, and exact copying unless transformation is requested.
- **Why This Module Owns It:** Action owns the terminal answer call and observation-to-answer extraction.
- **Generalization Rationale:** Canonicalization is needed for all short-answer tasks, not just the observed examples.
- **Complexity:** Low
- **Expected Impact:** Should recover some of the 31 QA cases where `subem=1.0` but exact correctness fails.
- **Risk:** If the canonicalizer over-normalizes, it may remove meaningful leading zeros or formatting when the task actually asks for them.

### PART 6: REPRESENTATIVE EVIDENCE

- **Failed trajectory 460, EnvScaler, score 0.2222:** The agent updates patient contact info successfully, then `add_medical_record` fails with permission denied and `edit_medical_record_details` fails as unauthorized. It still updates provider contact info and calls `complete_task`, producing only partial state completion.
- **Failed trajectory 212, EnvScaler, score 0.2:** The agent receives permission errors, invents unavailable `authenticate_as_admin`, repeats failed authentication-related calls despite advisories, performs only provider updates, then calls `complete_task` while patient and record updates remain unresolved.
- **Failed trajectory 1222, EnvScaler, score 0.64:** The agent creates some folders and bookmarks but omits the required `Research` subfolder, places the PubMed bookmark under `Herbal Medicine` while thinking it is under `Research`, and calls `complete_task`. This shows premature completion even without explicit tool failure.
- **Failed trajectory 1116, ToolHop, score 0.0:** The task asks for the count of `ō` in the first name of the paternal grandfather of Hōjō Akitoki. The agent accepts a `parentage` result as the paternal-grandfather slot, extracts the wrong first name, and answers `0` instead of `2`.
- **Failed trajectory 752, SearchQA, score 0.0:** Search returns evidence about Tommy Duncan, Bob Wills, and The Texas Playboys. The agent answers Tommy Duncan's own full name, `Thomas Elmer Duncan`, instead of the band leader's full name, `James Robert Wills`.
- **Successful trajectory 480, SearchQA, score 1.0:** The agent uses repair triage to refine the query, searches for the Bahamas legislative proposal process, reads evidence that most bills are introduced by a Government minister, and submits the raw answer `Government minister`.
- **Successful trajectory 826, ToolHop, score 1.0:** The agent retrieves the publisher of National Contest Journal, gets the publisher founding year `1914`, extracts the second and third digits, concatenates them, and submits `91`.
- **Bucket-level statistics:** Overall score is 0.4634 over 1241 items. EnvScaler has 21 full successes, 429 partial completions, and 208 zero-score non-completions. SearchQA correctness is 130/325. ToolHop correctness is 127/258. QA has 31 incorrect cases with `subem=1.0`, indicating canonicalization or answer-format failures after partial semantic success.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Generate a compact but complete row ledger for multi-step tasks, with one row per required evidence item, mutation, or transformation.
- [Planning] Include explicit slot-closure criteria for multi-hop tasks before downstream transformations are allowed.
- [Action] Block `complete_task` unless every state-change row has a successful observation or a benchmark-valid impossibility route.
- [Action] Convert repeated tool failures into bounded, enforceable next-action constraints rather than advisory prose.
- [Action] Before `final_answer`, verify that the candidate fills the requested predicate and answer type, not merely that it appears in an observation.
- [Action] Add a raw-answer canonicalization preflight for short answers, numbers, dates, binary strings, IDs, and transformed values.
- [Memory] Keep procedural reminders compact and phase-aware; do not inject broad repeated-failure reminders as a substitute for state tracking.
- [Builder] Preserve the current local provider wiring and tool-reference binding, but update metadata only if needed for round consistency.
- [Interface] Make Planning -> Action state machine-readable enough for terminal gating and slot verification.
- [Preserve] Keep the single-executor topology for simple tasks where the evidence chain is linear and tool observations are decisive.
- [Avoid] Do not add benchmark-specific patches for Alice Chan, Hōjō Akitoki, Kerry Earnhardt, Traditional Chinese Medicine folders, or any observed entity; repair the general ledger, retry, slot-verification, and finalization capabilities instead.
- [Avoid] Do not treat `repair_triage_check` output as environment evidence or as permission to call unavailable tools.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
