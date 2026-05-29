### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness is assembled by `builder.py` as `harness_round01_2`. It wires `PlanningClass` from `planning_module/provider.py`, `ACTION_SYSTEM = "schema_cooldown_react"` from `action_module/provider.py`, and `MEMORY_SYSTEM = "schema_hint_memory"` from `memory_module/provider.py`. `prepare_context` sets `planning_system`, `action_system`, `prompts_type`, the project root, and `max_tool_calls_per_step = 2` by default.

The builder also binds process/end/delete/executor/refine tools back to the agent when those tools expose an `agent` attribute. Metadata records `round: "round_01"` even though this analysis is for the round02_01 seed run; this is a metadata carryover rather than the dominant behavioral cause. The harness description accurately states the major design: compact planning, single-executor guarded ReAct action, and provenance-aware procedural memory.

The important wiring limitation is that the builder gives the action module a planning class but no stronger shared state contract. Planning packets are appended to memory, yet action-side guards only inspect local tool calls and observations. There is no required evidence-slot ledger that action must update before finalization or terminal completion.

#### 1.2 Planning Module Implementation

The planning provider implements a compact initial plan using `planning_module/prompts/toolcalling_agent.yaml`. The intended output is a structured packet with `task_type`, `evidence_slots`, `required_mutations`, `answer_format`, `terminal_criteria`, and `next_tool_intent`. The adaptation method summarizes recent memory every few steps using fields such as observed evidence, hypotheses, failed calls, pending mutations, terminal readiness, and next safe move.

Planning uses memory through `append_memory_guidance` before calling the model. It does not parse its own packet into enforceable state. The plan is stored as text in `AgentMemory`, and the action loop is expected to follow it through prompt conditioning rather than through a programmatic contract.

Observed trajectories show that planning sometimes misclassifies ToolHop short-answer tasks as `stateful_mutation` and sometimes emits a first tool-call shaped JSON object instead of the expected packet on EnvScaler tasks. It often names high-level evidence needs, but it does not reliably decompose multi-hop chains into ordered source, transform, and verification slots. As a result, action can move from failed relationship lookup to unrelated extraction or finalization without violating any hard planning invariant.

#### 1.3 Action Module Implementation

The action module is a single-executor guarded ReAct topology. `ActionProvider.build_affordance` loads the primary task tools and includes reasoning. `GuardedRound01Agent` wraps `ToolCallingAgent` and adds local guards for schema preflight, repeated calls, low-value repeats, terminal readiness, evidence-before-final, empty actions, answer canonicalization, and partial commit after blockers.

Tool preflight checks unknown tool names, extra keys, and missing required keys. Extra keys are dropped when configured. Repeated exact failed calls are blocked through `ROUND01_GUARD_BLOCK` observations. The action module also tracks successful real calls and successful state-changing calls using heuristic tool-name and observation-string matching.

The topology has no worker/verifier split, no parallel arbitration protocol, and no explicit recovery planner. The checkpoint tool exists in code but is disabled by `if False`, while guard messages still tell the model to use a checkpoint-like recovery path. `complete_gate` is set to `False`, so terminal completion is mainly controlled by prompt discipline and partial-commit heuristics rather than a hard checklist of requested state changes.

Final-answer gating is shallow: if any prior non-final evidence tool was observed, `final_answer` can proceed. The guard does not verify that the answer is supported by the relevant document, field, relation hop, or requested transformation. This is why path-correct but final-wrong cases survive the guard.

#### 1.4 Memory Module Implementation

The memory provider supplies phase guidance at BEGIN and every third IN step. It reminds the agent to separate observed facts from hypotheses, use exact schema keys, and finalize only from observations or deterministic derivations. At BEGIN, it retrieves up to two stored successful reusable procedures by lexical overlap. It stores only successful trajectories.

The guidance is generally aligned with the harness goal, but the retrieval is too coarse for mixed benchmark prompts. Because many tasks share the same benchmark wrapper text, memory often injects long, truncated examples from unrelated tasks. For example, a SearchQA bed-size question received prior examples about The Bangles and The Angry Birds Movie, while ToolHop failures received unrelated publication, movie-cast, or genealogy sketches. Memory is therefore useful as a broad reminder but not a reliable task-specific routing signal.

The memory module also does not store reusable failure lessons. Recurrent patterns such as relationship-enum errors, repeated "not found" loops, and premature partial completion are seen again without a targeted procedural memory that tells the action loop how to recover.

### PART 2: FAILURE MODE ANALYSIS

**Name:** Evidence-present but answer extracted from the wrong evidence span

**Frequency / importance:** High for SearchQA. SearchQA has 325 items, 112 exact successes, 185 zero-score failures, and 28 partial-credit cases. Among 213 incorrect SearchQA examples, 180 still called `final_answer`, so the dominant issue is not only missing terminal calls.

**Symptom:** The agent performs a plausible search, sees relevant and irrelevant snippets, then finalizes an answer copied from the wrong snippet or wrong entity.

**Mechanism:** The action guard only checks that some evidence exists before finalization. It does not require the final answer span to be tied to the specific question slot. In item 460, the search results included a bed-size document and a pillow document. The agent answered `20x30 inches`, which came from a queen pillow snippet, while the gold answer was `60 in x 80 in` for a queen bed.

**Generalized capability gap:** Missing evidence attribution and answer-span arbitration after retrieval.

**Primary module owner:** Action

**Secondary contributor:** Planning and Memory

**Evidence:** SearchQA answer accuracy is 0.3446. Item 460 shows observed evidence but wrong span selection. Item 467 earns partial credit because the final answer contains some but not all requested entities. Memory in item 460 injected unrelated successful QA procedures, increasing prompt noise without helping relevance selection.

**Generalization rationale:** Any retrieval task with distractor snippets, near-duplicate entity names, or adjacent facts can fail if the action loop treats "some evidence exists" as enough.

**Confidence:** High


**Name:** SearchQA over-harnessing regression during round02-style regeneration

**Frequency / importance:** High for regeneration. In the first-200 round02_01 pilot, the seed scored 0.4565 on the 46 SearchQA items, while all eight generated round02_01 variants scored lower before the lightweight patch.

**Symptom:** The regenerated harness keeps the general ledger/verifier behavior but loses simple SearchQA accuracy. It rewrites the first search query away from the raw question, picks an answer from a distractor snippet, returns semantically equivalent but surface-wrong dates, or retrieves stale SearchQA memories from unrelated tasks.

**Mechanism:** The round02 ledger and support gate are beneficial for ToolHop and stateful tasks, but SearchQA often needs a short direct path: raw question search, evidence-span copying, and exact surface-form preservation. Generic token-overlap support is too weak because distractor snippets contain plausible names, dates, and years. Generic date canonicalization is also harmful when the evaluator expects the observed natural-language date.

**Generalized capability gap:** Missing benchmark-family fast path for short-answer retrieval tasks. SearchQA should use lightweight retrieval and exact span preservation while still retaining schema guards and final support checks.

**Primary module owner:** Action

**Secondary contributor:** Planning and Memory

**Evidence:** Pilot examples include `April 1, 1996` being changed to `1996-04-01`, raw query rewrites changing answers from `Millard Fillmore` to `Franklin Pierce`, and a stale/off-topic first query such as `The Bangles formed in which city` appearing on an unrelated Glee episode task.

**Generalization rationale:** This repair does not hard-code any answer; it routes an entire short-answer retrieval family toward raw-query search, same-record support, and evidence surface-form preservation.

**Confidence:** High

**Name:** Multi-hop evidence chain break after a failed intermediate lookup

**Frequency / importance:** High for ToolHop. ToolHop has 259 items, 105 exact successes, 151 zero-score failures, and 3 partial-credit cases. Among 154 incorrect ToolHop items, 84 contain error/not-found observations and 80 contain guard blocks.

**Symptom:** The agent obtains one useful intermediate fact or hits an invalid relation, then jumps to a wrong entity, an unsupported transform, or a fabricated fallback answer.

**Mechanism:** Planning names evidence slots but does not create an enforceable hop ledger. Action handles each observation locally. When a relationship or metadata tool fails, the agent repeats the call, changes to another weakly related tool, or uses the original subject as if it were the missing target. In item 1116, the paternal-grandmother relation failed; the agent then extracted the last name of Hieronim Augustyn Lubomirski himself and counted vowels, returning `4` instead of `3`.

**Generalized capability gap:** Missing ordered provenance ledger for source entity, relation result, transformed field, and final computation.

**Primary module owner:** Cross-Module Interface

**Secondary contributor:** Planning and Action

**Evidence:** ToolHop failures average 6.15 tool calls. Repeated failed calls appear in 59 ToolHop failures, low-value repeats in 44, and schema preflight blocks in 21. Items 1116, 1171, 153, and 167 all show a broken chain followed by unsupported continuation.

**Generalization rationale:** Multi-hop tasks in any domain require preserving which entity each observation refers to. Without that interface, local tool correctness does not guarantee chain correctness.

**Confidence:** High

**Name:** Guard observations stop repeats but do not route recovery

**Frequency / importance:** High across ToolHop and EnvScaler. Guard blocks appear in 80 ToolHop failures and 435 EnvScaler failures.

**Symptom:** The harness detects repeated or malformed calls, emits `ROUND01_GUARD_BLOCK`, and the agent still loops, retries equivalent calls, or finalizes from a blocker.

**Mechanism:** The guard is a blocker, not a recovery policy. It says to repair arguments, choose another valid tool, use a checkpoint, or finalize when supported, but the checkpoint tool is disabled. The model must invent the recovery path from text alone. In item 1171, publication and founder lookups fail, repeated calls are blocked, and the agent finally answers `0` without the required founder/deanna-drake evidence.

**Generalized capability gap:** Missing post-error recovery router that maps failure types to alternative evidence acquisition, argument repair, or controlled termination.

**Primary module owner:** Action

**Secondary contributor:** Memory

**Evidence:** ToolHop has 59 repeated-failed-call blocks and 44 low-value-repeat blocks among failures. EnvScaler has 224 repeated-failed-call blocks and 231 low-value-repeat blocks among failures. Item 480 repeatedly queries `MEET-01` after "Meeting does not exist" and then searches by topic `Samira Patel`, which returns no meetings.

**Generalization rationale:** Any tool-rich task can produce not-found, invalid enum, authorization, or missing-key errors. Detecting the error is helpful only if paired with a reusable repair protocol.

**Confidence:** High

**Name:** Stateful task progress is not tracked as a complete checklist

**Frequency / importance:** Very high for EnvScaler. EnvScaler has 658 items, only 12 full-score runs, 506 partial-score runs, and 140 zero-score runs. Average EnvScaler score is 0.3876.

**Symptom:** The agent completes some mutations, then either calls `complete_task` early for partial credit or stalls with empty actions before all requested state changes are complete.

**Mechanism:** Action tracks successful mutations using heuristic observation strings and tool-name patterns, but it does not maintain the task's required mutation checklist. `complete_gate` is disabled, and partial commit is encouraged after blockers. This preserves partial credit but often prevents full completion. In item 480, the agent correctly finds Samira profiles and creates the follow-up meeting, but it guesses invalid meeting IDs, loops on blocked lookups, and cannot complete all transfer/enrollment requirements. In item 772, it performs the early Alice meal-record updates, then produces empty action steps and never reaches the remaining additions or terminal completion.

**Generalized capability gap:** Missing stateful execution ledger with per-requirement status, required identifiers, verification result, and terminal readiness.

**Primary module owner:** Cross-Module Interface

**Secondary contributor:** Action and Planning

**Evidence:** Among EnvScaler failures, 514 call `complete_task`, 131 have empty actions/no terminal, 460 include error observations, and 450 include multi-tool steps. Full success is rare, but partial progress is common.

**Generalization rationale:** Stateful workflows in meetings, nutrition, scheduling, healthcare, file systems, and commerce all require checking off multiple independent mutations before termination.

**Confidence:** High

**Name:** Terminal and format contract confusion across benchmark families

**Frequency / importance:** Medium. ToolHop failures include 14 `complete_task` calls even though ToolHop short-answer tasks should use `final_answer`. SearchQA failures include 44 no-terminal cases.

**Symptom:** The harness sometimes treats short-answer ToolHop tasks like stateful tasks, attempts unavailable `complete_task`, or returns a date/name format that is semantically close but not canonical.

**Mechanism:** Planning mislabels some ToolHop tasks as `stateful_mutation`, while action guard text includes a stateful partial-credit instruction even when the active toolset has no `complete_task`. The final-answer canonicalizer removes some labels and leading zeros but does not normalize dates to the benchmark-required ISO format or arbitrate aliases. In item 153, the agent ends with `11 June 1516` while the gold answer is `1516-06-11`; the trace also shows an attempted `complete_task` that is not a valid ToolHop tool.

**Generalized capability gap:** Missing benchmark-family terminal policy and output canonicalization contract shared by planning and action.

**Primary module owner:** Cross-Module Interface

**Secondary contributor:** Planning and Action

**Evidence:** Item 153 shows ToolHop complete_task misuse plus date-format mismatch. SearchQA has 44 incorrect runs with no terminal answer. ToolHop has 35 incorrect runs with no terminal answer.

**Generalization rationale:** Mixed-task harnesses must keep terminal tools and answer formats separated by active tool contract, not by generic prompt text.

**Confidence:** Medium

**Name:** Empty or zero-token execution episodes

**Frequency / importance:** Medium but likely partially external. Among failures, 39 SearchQA, 29 ToolHop, and 80 EnvScaler runs have zero API calls and zero tokens. Empty action steps appear in 44 SearchQA failures, 35 ToolHop failures, and 131 EnvScaler failures.

**Symptom:** The trajectory contains repeated user messages or empty action records with no plan, no tool call, no observation, and no final answer.

**Mechanism:** The local evidence indicates the model was not invoked in zero-token cases, so this bucket should not be over-attributed to reasoning quality. However, the harness also lacks a robust fallback path when an action step has no executable tool call; it writes a guard observation only when the agent loop reaches `step`, and some zero-token trajectories never get that far.

**Generalized capability gap:** Missing run-level instrumentation and recovery for model-call aborts, empty parsed outputs, and uninitialized planning/action cycles.

**Primary module owner:** External/Evaluation

**Secondary contributor:** Builder/Wiring and Action

**Evidence:** Items 889 and 848 have three empty action records, `api_calls: 0`, `total_tokens: 0`, `tool_call_count: 0`, and no final answer.

**Generalization rationale:** Infrastructure or parser-level no-op episodes can affect any benchmark and should be separated from harness reasoning failures before generation overfits to them.

**Confidence:** Medium

**Name:** Memory retrieval is broad, long, and not failure-aware

**Frequency / importance:** Medium as a secondary contributor. Memory appears in the most important failure samples and often includes long truncated unrelated procedures.

**Symptom:** Retrieved memory examples share benchmark wrapper text but not the actual problem structure. They consume prompt budget and sometimes reinforce generic "use exact schema" behavior while failing to provide the missing recovery procedure.

**Mechanism:** Memory retrieval scores lexical overlap over the full query, which is dominated by shared terminal-rule boilerplate. The memory store keeps successful procedures only, so repeated failures do not become compact reusable lessons.

**Generalized capability gap:** Missing task-signature routing and reusable failure-memory ingestion.

**Primary module owner:** Memory

**Secondary contributor:** Cross-Module Interface

**Evidence:** Item 460 receives SearchQA memories about The Bangles and The Angry Birds Movie. Item 1116 receives truncated genealogy/repeated-letter memories that include invalid relationship attempts but no actionable rule for relation-enum recovery.

**Generalization rationale:** In mixed benchmarks, superficial prompt overlap is not enough for useful memory. The same issue transfers to any task family with shared wrappers and diverse internal workflows.

**Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Evidence-present but wrong answer span | Action | Planning, Memory | `action_module/provider.py` final-answer gate and observation handling | SearchQA accuracy 0.3446; item 460 answers pillow size instead of bed size | Retrieval tasks often contain distractor snippets and adjacent facts | High | Add evidence-to-answer attribution and relevance arbitration before `final_answer` |
| SearchQA over-harnessing regression | Action | Planning, Memory | `action_module/round02_agent.py`, action/planning prompts, `memory_module/round02_memory.py` | First-200 pilot: all eight round02_01 variants below seed on SearchQA before lightweight patch; examples show query drift, ISO date surface loss, weak support, stale memory | Short-answer retrieval needs raw-query first search and evidence surface copying, not heavy multi-hop-style arbitration | High | Add SearchQA fast path, raw first-query guard, same-record support, date-surface preservation, and SearchQA memory suppression |
| Multi-hop chain break after failed lookup | Cross-Module Interface | Planning, Action | `planning_module/provider.py` -> `action_module/provider.py` memory/plan boundary | ToolHop 84 failure traces with errors; item 1116 uses target surname after relation failure | Multi-hop tasks require ordered provenance across source, relation, transform, and final value | High | Make evidence slots executable ledger entries that action must update |
| Guard blocks without recovery routing | Action | Memory | `action_module/provider.py` guard observation and disabled checkpoint | 80 ToolHop and 435 EnvScaler failures with guard blocks; item 1171 loops then guesses | Tool-rich tasks need generic repair paths after invalid, not-found, and repeated calls | High | Add failure-type recovery router and enable or remove checkpoint affordance |
| Incomplete stateful checklist before completion | Cross-Module Interface | Action, Planning | Planning required mutations -> Action terminal completion | EnvScaler only 12/658 full-score; 514 failed EnvScaler runs call `complete_task` | Stateful workflows require per-requirement completion and verification | High | Add mutation ledger and hard terminal readiness based on all required state changes |
| Terminal and format policy confusion | Cross-Module Interface | Planning, Action | `planning_module` task type, `action_module` terminal/canonicalization | ToolHop failures include 14 `complete_task` calls; item 153 has date format mismatch | Mixed benchmarks need active-tool terminal policy and canonical output rules | Medium | Separate terminal policies by active toolset and add format-specific canonicalizers |
| Empty or zero-token execution episodes | External/Evaluation | Builder/Wiring, Action | Evaluation loop / model-call boundary; empty `agent_trajectory` actions | 39 SearchQA, 29 ToolHop, 80 EnvScaler zero-token failures; items 889 and 848 | No-op model-call episodes can strike any task and should not be treated as reasoning failures | Medium | Instrument and classify zero-token aborts; add safe retry around empty parsed steps |
| Broad, non-failure-aware memory retrieval | Memory | Cross-Module Interface | `memory_module/provider.py` scoring and storage policy | Unrelated memories in items 460 and 1116; successful-only storage | Shared wrapper text causes false memory matches across domains | Medium | Route memory by task signature and store compact reusable failure lessons |

### PART 4: STRENGTHS TO PRESERVE

- Schema preflight and repeated-call blocking, owned by Action, prevented many invalid calls from silently mutating state; successful recovery in item 612 shows that guard feedback can help when the agent can choose a valid alternative, so generation should not remove the hard schema checks.
- Direct single-executor ReAct execution, owned by Action, solves a meaningful subset without orchestration overhead: 112 SearchQA and 105 ToolHop exact successes, plus 506 partial EnvScaler scores, show that the simple loop is useful and should remain the base path.
- Compact initial planning packets, owned by Planning, keep simple lookup tasks short and usually identify evidence or terminal criteria; item 20 succeeds after the plan asks for both cocktail ingredient counts, so generation should strengthen rather than discard compact planning.
- Provenance reminders, owned by Memory, correctly state that observations are evidence and plans are hypotheses; this principle is aligned with the observed failures and should be preserved while making retrieval more selective.
- Local answer canonicalization, owned by Action, strips some answer labels and unsupported prose; it should be expanded carefully rather than removed, because exact-answer benchmarks benefit from raw-answer enforcement.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Evidence Attribution Gate]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** SearchQA and ToolHop final answers pass after any evidence observation, even when the chosen answer span belongs to the wrong entity or snippet.
- **Mechanism:** Before `final_answer`, require a compact support record: answer candidate, source observation id/tool, relevant entity or slot, and whether the value is copied or deterministically derived.
- **Why This Module Owns It:** The final-answer decision and observation handling live in the action loop.
- **Generalization Rationale:** Retrieval, API lookup, and multi-hop tasks all need answer-to-evidence linkage.
- **Complexity:** Medium
- **Expected Impact:** Reduces path-correct but final-wrong failures like item 460 and unsupported ToolHop finalizations.
- **Risk:** If the gate is too strict, it may block obvious direct answers or increase no-final failures.


**[Priority 1A: SearchQA Lightweight Fast Path]**
- **Target Module:** Planning, Action, Memory
- **Owner Path:** `action_module/round02_agent.py`, action/planning prompt YAMLs, and `memory_module/round02_memory.py`
- **Problem:** General round02 evidence ledgers can over-control SearchQA and regress direct retrieval accuracy.
- **Mechanism:** Detect SearchQA tasks, preserve raw question wording for the first search, allow decomposition only after missing/ambiguous evidence, keep final date/name/title surface forms from evidence, require same-record support rather than loose token overlap, and suppress retrieval/storage of old SearchQA answer/query memories.
- **Why This Module Owns It:** The first search call, final-answer canonicalization, support gate, and memory injection are controlled by these modules.
- **Generalization Rationale:** The rule applies to a benchmark family and workflow type, not to observed entities or answers.
- **Complexity:** Low to Medium
- **Expected Impact:** Prevents the regeneration process from trading away SearchQA accuracy while preserving ToolHop/EnvScaler improvements.
- **Risk:** If applied after useful evidence exists, it may prevent decomposed verification; scope the raw-query repair to the no-evidence first search only.

**[Priority 2: Shared Evidence and Mutation Ledger]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py` -> `action_module/provider.py`
- **Problem:** Planning lists slots, but action does not maintain their status and can continue from broken chains.
- **Mechanism:** Convert the plan packet into a small runtime ledger with required evidence slots, dependency order, observed value, source tool, confidence, and pending mutations. Action updates the ledger after each observation and uses it for final/terminal readiness.
- **Why This Module Owns It:** The gap is between planning's intended state and action's local execution state.
- **Generalization Rationale:** Multi-hop QA and stateful tasks both require persistent progress state.
- **Complexity:** High
- **Expected Impact:** Reduces ToolHop chain breaks and EnvScaler premature completion.
- **Risk:** A heavy ledger may slow simple tasks unless it has a lightweight default path.

**[Priority 3: Failure-Type Recovery Router]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** Guard blocks identify repeated, invalid, or not-found calls but leave recovery entirely to the model.
- **Mechanism:** Add a recovery policy that maps schema_preflight, repeated_failed_call, low_value_repeat, not_found, unauthorized, and empty action to one of: repair keys, choose suggested close match, query list/get tools, change identifier source, ask for alternate relation, or terminate only under active benchmark policy.
- **Why This Module Owns It:** Guard creation and tool execution are action-side responsibilities.
- **Generalization Rationale:** Error classes recur across tool schemas and domains.
- **Complexity:** Medium
- **Expected Impact:** Converts guard observations from blockers into useful control flow, reducing loops in items 1171 and 480.
- **Risk:** Over-prescriptive recovery may choose bad generic fallbacks if it ignores task context.

**[Priority 4: Stateful Completion Contract]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** Planning required mutations plus Action `complete_task` handling
- **Problem:** EnvScaler often calls `complete_task` after partial progress or stalls before all requested mutations are complete.
- **Mechanism:** Require each stateful task to maintain a checklist of requested mutations and verification observations. `complete_task` should be allowed only when all required items are complete, except for an explicit partial-credit mode that is never used for short-answer tasks.
- **Why This Module Owns It:** Planning must expose the checklist, and action must enforce terminal readiness.
- **Generalization Rationale:** All state-change tasks require reliable "done" semantics independent of domain.
- **Complexity:** High
- **Expected Impact:** Improves EnvScaler full completion while preserving partial-progress behavior as a controlled fallback.
- **Risk:** If the checklist extraction is wrong, the agent may over-work or fail to terminate.

**[Priority 5: Task-Signature Memory Routing]**
- **Target Module:** Memory
- **Owner Path:** `memory_module/provider.py`
- **Problem:** Memory retrieval is dominated by shared benchmark boilerplate and successful-only sketches.
- **Mechanism:** Score memories using task signature fields such as benchmark, tool family, relation/lookup/transform type, and observed failure class. Store compact failure lessons when a trajectory repeatedly hits schema, relation, or not-found blockers.
- **Why This Module Owns It:** Memory selection and ingestion are memory-provider responsibilities.
- **Generalization Rationale:** Useful memories should transfer by workflow, not by wrapper text.
- **Complexity:** Medium
- **Expected Impact:** Reduces prompt noise and gives action more relevant recovery hints.
- **Risk:** Over-filtering could remove helpful general reminders on rare task types.

**[Priority 6: Empty-Step and Zero-Token Instrumentation]**
- **Target Module:** Builder/Wiring
- **Owner Path:** evaluation/model-call boundary plus `builder.py` initialization path
- **Problem:** Some runs have zero API calls, zero tokens, no plan, and repeated empty action records.
- **Mechanism:** Add explicit run-status classification for model-call abort, parser-empty output, and planning-not-started. Retry once for parser-empty output, but keep zero-token backend failures labeled external.
- **Why This Module Owns It:** The harness should expose enough metadata to distinguish internal empty actions from evaluation artifacts.
- **Generalization Rationale:** Infrastructure no-op failures are benchmark-independent and should not distort harness generation.
- **Complexity:** Low
- **Expected Impact:** Prevents overfitting improvements to non-reasoning failures and may recover simple empty-output cases.
- **Risk:** Retrying without bounds could inflate cost or duplicate stateful mutations.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory 460, SearchQA: The agent searched "measurement of a queen size bed" and observed a bed-size document plus a pillow-size document. It finalized `20x30 inches`, copied from the pillow snippet, while the gold answer was `60 in x 80 in`. This is an Action-owned evidence relevance failure, not a schema failure.
- Failed trajectory 1116, ToolHop: The genealogy tool rejected `paternal_grandmother`; the agent tried `mother` and `grandparents`, then extracted the last name of the original subject `Hieronim Augustyn Lubomirski` and counted its vowels. The final answer `4` used a valid transform on the wrong entity.
- Failed trajectory 1171, ToolHop: Publication and founder lookup for Big Picture failed, repeated calls were blocked by `ROUND01_GUARD_BLOCK`, and the agent finalized `0` without observing either required last name. This shows guard-as-blocker without recovery routing.
- Failed trajectory 480, EnvScaler: The agent found duplicate Samira Patel profiles and created the requested follow-up meeting, but guessed invalid meeting IDs, repeated blocked lookups, and did not complete the enrollment transfer and participant normalization. The score was partial, illustrating missing stateful checklist control.
- Failed trajectory 772, EnvScaler: The agent identified both Alice Chan accounts, updated MR006, and deleted MR007, then emitted empty action steps and never completed the remaining required meal additions or terminal `complete_task`. This is an empty-step continuation failure after partial progress.
- Failed trajectories 889 and 848: Both contain empty action records, no plan, no tool call, no final answer, and `api_calls: 0`, so these should be classified separately as likely evaluation/model-call artifacts.
- Successful trajectory 20, SearchQA: The agent searched both cocktails in one read-only step, compared observed ingredient counts, and finalized `Vesper`, which was judged correct. This shows that direct single-executor lookup and deterministic comparison should be preserved.
- Successful trajectory 612, EnvScaler: The agent canceled one session, edited participants, encountered an authorization error while rescheduling, checked authorization, switched to authorized user U1004, completed the remaining mutation, and called `complete_task` for a score of 1.0. This shows guard-compatible local recovery can work when the next valid action is clear.
- Bucket-level statistic: SearchQA has 112/325 exact successes, ToolHop has 105/259 exact successes, and EnvScaler has only 12/658 full-score runs but 506 partial-score runs. The diagnosis should therefore prioritize final-answer relevance for QA, chain provenance for ToolHop, and complete mutation ledgers for EnvScaler.
- Round02_01 first-200 SearchQA pilot: the seed scored 0.4565, while generated variants scored 0.2826 to 0.4348 before the lightweight patch. The observed causes were query drift, date surface conversion, weak token-overlap support, and stale memory/query leakage.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Preserve compact plans, but make each evidence slot and mutation slot explicit enough for action to update after observations.
- [Planning] Do not classify ToolHop short-answer transformations as stateful mutations unless the active toolset truly contains a state-changing terminal workflow.
- [Planning] For SearchQA, the first planned retrieval should preserve the raw current question; decomposition is a fallback after ambiguous or missing first evidence.
- [Action] Keep hard schema preflight and repeated-call blocking, but pair every guard class with a recovery route or a controlled stop condition.
- [Action] Require final answers to cite an internal support record tying the candidate value to the relevant observation and requested slot.
- [Action] For SearchQA, same-record support should be required; loose answer-token overlap across all recent evidence is not enough.
- [Action] For SearchQA, guard the first search against off-topic query drift and restore evidence date/title/name surface forms before finalization.
- [Action] Treat `complete_task` as valid only when it is present in the active toolset and the stateful checklist is complete, except under an explicit partial-credit policy.
- [Memory] Retrieve memories by task workflow and tool family, not by shared benchmark wrapper text.
- [Memory] For SearchQA, do not retrieve or store old answer/query trajectories; use only fixed procedural reminders to avoid stale-entity leakage.
- [Memory] Add compact reusable failure memories for repeated schema, relation, not-found, and empty-action patterns.
- [Builder] Surface run metadata that distinguishes model-call aborts, empty parsed outputs, and normal reasoning failures.
- [Interface] Add a shared evidence/mutation ledger between planning and action; prompt text alone is not enough.
- [Avoid] Do not add task-specific patches for queen beds, paternal-grandmother relations, Big Picture Magazine, Alice Chan, or any observed entity.
- [Avoid] Do not remove the single-executor path or schema guards; the failures come from missing arbitration and state tracking, not from the existence of those mechanisms.
- [Preserve] Preserve direct read-only multi-call support for independent evidence gathering, as in the successful cocktail comparison case.
- [Preserve] Preserve provenance language that separates observations, derived facts, and hypotheses, but make it operational through ledger updates.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
