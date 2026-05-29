### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness in the round03_01 base directory is wired as `harness_round02_01_1`. `builder.py` sets `HARNESS_NAME = "harness_round02_01_1"`, `PAIRING_REASON = "round02_balanced_ledger_commit"`, and metadata round `"round_02_01"`, even though the analyzed snapshot is the base harness for `round_03_01`. This is a metadata mismatch, but the observed failures are mostly behavioral rather than caused by the name mismatch.

`prepare_context` injects `PlanningClass` into `context.kwargs`, sets `planning_system = "ledger_commit_planning"`, `action_system = "ledger_commit_react"`, `prompts_type = ACTION_SYSTEM`, `project_root` to the harness directory, and defaults `max_tool_calls_per_step` to 2. `build_agent_from_context` delegates construction to the action provider and then binds process/refine/executor/end-process tools back to the built agent when those tools exist.

The action provider is `ActionProvider` in `action_module/provider.py`, a thin configuration subclass over `Round02ActionProvider`. The planning provider is `PlanningProvider` in `planning_module/provider.py`. The memory metadata recommends `round02_signature_ledger_memory`, while the actual memory object is supplied through the external `ActionContext.memory_provider`.

#### 1.2 Planning Module Implementation

The planning module renders a compact checklist prompt from `planning_module/prompts/toolcalling_agent.yaml`, asks the backend model for a plan, and stores the raw output as a `PlanningStep`. It does not parse, validate, or repair the plan packet. If the model emits action-style JSON, that output is accepted as the plan.

This matters strongly for EnvScaler: 657 of 658 EnvScaler trajectories had action-like plan values with `think` and `tools` instead of the required fields such as `evidence_slots`, `required_mutations`, `terminal_policy`, and `verification_questions`. For SearchQA and ToolHop the plan usually includes the expected fields, but `next_tool_intent` often says `final_answer` before evidence is collected.

Adaptation summaries are also raw model outputs. The summary prompt asks for ledger fields, but the implementation does not enforce that shape. In trajectories, summary steps sometimes become action proposals instead of state summaries. Planning influences action mainly by being appended to memory; the action module only scans the latest plan text for route hints such as `deterministic_transform` or `stateful_mutation`. It does not consume structured evidence slots or mutation slots.

#### 1.3 Action Module Implementation

The action module is a guarded single-executor ReAct loop implemented by `Round02GuardedAgent` in `action_module/round02_agent.py`. There is no coordinator-worker, verifier-repairer, debate, or parallel-agent topology. The only executor calls all environment tools.

Tools are loaded through `get_primary_task_tools(context, include_reasoning=True)`. The optional `LedgerReviewTool` exists but is disabled by `enable_ledger_review_tool = False`. The action loop performs schema preflight, unknown-tool checks, repeated-call blocking, SearchQA first-query repair, final-answer support gating, answer canonicalization, and partial completion after observed stateful progress.

The guard behavior is useful but shallow. `_preflight_arguments` blocks unknown tools and missing required keys, and may drop extra keys. `_guard_observation` returns a textual recovery hint. However, the recovery hint is not a controller: it does not force a different tool family, fill missing required fields from prior observations, or update a structured pending-slot ledger. Repeated guard observations can be counted as recent records by the executor context, which lets loops persist.

Final answers are accepted when `_answer_support_status` finds the candidate string or overlapping tokens in recent evidence, with a stricter SearchQA surface check. This verifies textual presence, not whether the candidate fills the correct relation slot. Stateful completion is allowed once `_terminal_ready` sees any successful real call or mutation, and `_partial_commit_ready` allows completion after only one successful mutation when a blocker appears.

#### 1.4 Memory Module Implementation

The memory module is `Round02MemoryProvider` in `memory_module/round02_memory.py`. At BEGIN, it injects compact procedural guidance and up to two task-signature memories unless the task is SearchQA. At IN phase, every third step it injects a short recovery reminder. It stores successes and reusable failure lessons using token-overlap signatures, with SearchQA trajectories skipped to avoid answer/query leakage.

The BEGIN guidance is broadly useful: it distinguishes observed facts, derived facts, hypotheses, and commit rules. The weakness is retrieval precision. The signature scorer is a shallow token overlap over query and stored trace text, so unrelated long examples can enter the prompt. In several ToolHop and EnvScaler failures, retrieved memories were only loosely related and added lengthy trace sketches without supplying a concrete current-task recovery procedure.

### PART 2: FAILURE MODE ANALYSIS

**Name:** Evidence-surface support gate accepts wrong final answers

**Frequency / importance:** High. SearchQA accuracy is 137/325, and 176 of 188 wrong SearchQA trajectories still have a support record. ToolHop has 130 wrong trajectories, and 109 of those also have a support record.

**Symptom:** The agent reaches `final_answer` with an answer that appears somewhere in evidence but is not the requested answer. Example 480 answers `Parliament` although the evidence states that most bills are introduced by a Government minister and any parliamentarian may introduce a bill.

**Mechanism:** `_answer_support_status` and `_searchqa_answer_support_status` check answer-surface presence or token inclusion in observations. They do not bind the candidate to the planned evidence slot, relation, answer type, or contrast set. A broader entity can pass if it appears in the same snippet.

**Generalized capability gap:** The action module lacks relation-aware evidence arbitration for finalization. It can prove that a string was observed, but not that the string is the correct value for the asked slot.

**Primary module owner:** Action

**Secondary contributor:** Planning

**Evidence:** Overall SearchQA answer correctness is 0.4215. Wrong SearchQA final-answer calls appear in 188/188 wrong SearchQA items, and support records appear in 176/188. ToolHop wrong support records appear in 109/130 wrong ToolHop items.

**Generalization rationale:** Any short-answer task with distractor entities, aliases, broader categories, dates, or multi-hop relations can satisfy surface support while still answering the wrong slot.

**Confidence:** High

**Name:** Multi-hop evidence-chain break in transform tasks

**Frequency / importance:** High. ToolHop accuracy is 128/258, with lower accuracy as expected tool count rises: 0.594 for 4-tool tasks, 0.448 for 5-tool tasks, and 0.321 for 6-tool tasks.

**Symptom:** The agent completes a plausible chain but skips or misinterprets a dependency. Example 1116 asks for the count of the o-macron character in the first name of the paternal grandfather of Hojo Akitoki. The agent calls a parentage tool once, treats the returned parent as the paternal grandfather, extracts the first name, counts 0, and finalizes. The gold answer is 2.

**Mechanism:** Planning often lists evidence slots, but no runtime structure checks whether each dependency edge was satisfied. The action module sees only raw memory text and route hints; it does not maintain slot statuses or require a verification question before transform/finalization.

**Generalized capability gap:** The harness lacks a Planning -> Action interface for dependency-aware evidence state. It cannot distinguish "some related entity was found" from "the required relation hop was completed."

**Primary module owner:** Cross-Module Interface

**Secondary contributor:** Planning and Action

**Evidence:** ToolHop has 94 wrong trajectories with guard blocks, 56 wrong trajectories with low-value repeats, and 109 wrong trajectories that still pass support-record finalization. Successful example 826 works when each hop is explicitly followed: publisher -> founding date -> digit extraction -> final answer.

**Generalization rationale:** Multi-hop QA, transformation, database lookup, and stateful workflows all require ordered dependency satisfaction before downstream actions.

**Confidence:** High

**Name:** Premature stateful completion after partial mutation progress

**Frequency / importance:** High. EnvScaler has average score 0.4158, only 8/658 perfect scores, and `envscaler_done = 1` in 568 cases. The agent frequently terminates even when the state is only partially correct.

**Symptom:** The agent calls `complete_task` after making some successful changes and encountering blockers on others. Example 460 updates patient contact and provider contact, but fails to add a medical record because of permission denial, does not edit the existing medical record, then completes with EnvScaler score 0.2222.

**Mechanism:** `_terminal_ready` permits a completion tool after at least one successful real call or mutation, and `_partial_commit_ready` permits partial completion after one successful mutation plus a blocker. Because EnvScaler plans are action-like in 657/658 cases, there is no required-mutation checklist for the action module to compare against.

**Generalized capability gap:** The action module lacks all-required-mutations completion gating, and the Planning -> Action boundary does not pass an auditable mutation ledger.

**Primary module owner:** Action

**Secondary contributor:** Planning

**Evidence:** Partial commits occur in 339 EnvScaler trajectories, with average score 0.3686 and no perfect scores. EnvScaler trajectories without repeat markers average 0.6481, while trajectories with repeat markers average 0.3249.

**Generalization rationale:** Any stateful task with multiple requested updates can be harmed by completion criteria based on partial progress rather than complete requirement coverage.

**Confidence:** High

**Name:** Schema and repeated-call recovery does not change strategy reliably

**Frequency / importance:** High. `schema_preflight` appears in 284 trajectories, unknown tools in 223, repeated-failed-call in 360, and low-value-repeat in 441.

**Symptom:** The agent receives useful guard observations but repeats the same failed call, invents near-miss tool names, or cycles through invalid argument variants. Example 765 fails to find the publisher, repeats failed publisher/founding-year calls, invents `publication_list_search`, and never calls `final_answer`.

**Mechanism:** Guard observations are advisory strings. They do not trigger a structured recovery policy such as "enumerate valid tools," "extract required missing key from last successful observation," "switch from exact lookup to list/search," or "stop and answer with a supported blocker." Missing required arguments are blocked but not repaired even when prior observations contain the needed field.

**Generalized capability gap:** The action module lacks a schema-aware recovery controller and a progress-sensitive exploration budget.

**Primary module owner:** Action

**Secondary contributor:** Memory

**Evidence:** ToolHop wrong trajectories include 49 schema-preflight cases and 56 low-value-repeat cases. EnvScaler has 207 schema-preflight cases and 307 low-value-repeat cases.

**Generalization rationale:** Tool-rich environments commonly produce lookup misses, missing fields, and name mismatches. Textual guard hints alone do not reliably redirect execution.

**Confidence:** High

**Name:** Unvalidated plan packet creates weak execution contracts

**Frequency / importance:** High for stateful tasks and medium for answer tasks. EnvScaler plans are action-like in 657/658 cases. ToolHop plans include `next_tool_intent: final_answer` in most cases despite missing evidence.

**Symptom:** The initial plan often becomes a tool-call proposal, a premature finalization hint, or a loose checklist that action cannot execute against. In EnvScaler, the required mutation list is usually absent, so the action loop cannot know which requested changes remain.

**Mechanism:** `PlanningProvider.topology_initialize` stores model output verbatim. There is no parser, required-field validator, fallback re-ask, or deterministic extraction of mutation/evidence slots from the task.

**Generalized capability gap:** The planning module lacks contract enforcement for structured task state.

**Primary module owner:** Planning

**Secondary contributor:** Builder/Wiring

**Evidence:** Plan-format statistics show 657/658 EnvScaler plans with `think/tools` action format. SearchQA and ToolHop plans contain expected fields more often, but many still set `next_tool_intent` to `final_answer` before any observation.

**Generalization rationale:** If the initial plan cannot be trusted as structured state, every downstream module has to infer task progress from raw conversation text.

**Confidence:** High

**Name:** Noisy memory retrieval distracts without enforcing reusable lessons

**Frequency / importance:** Medium. Memory is not the dominant source of wrong answers, but it amplifies loops and wrong repair choices in ToolHop and EnvScaler.

**Symptom:** Retrieved memories often contain long sketches from only loosely related tasks. Example 1116 retrieves memories about game developers and unrelated relationship repeats; example 460 retrieves old medical-record failures but still repeats provider-authentication and schema mistakes.

**Mechanism:** The memory scorer uses token overlap on task text and stored trace text. It does not strongly route by benchmark family, tool topology, dependency shape, or failure phase. The retrieved examples are procedure hints, not executable constraints, so action may ignore them.

**Generalized capability gap:** The memory module lacks topology-aware, phase-aware retrieval and compact current-failure recipes.

**Primary module owner:** Memory

**Secondary contributor:** Planning

**Evidence:** SearchQA memory leakage prevention appears useful, but ToolHop and EnvScaler prompt context often includes unrelated prior traces. In-task reminders are generic and do not stop repeated-call or schema loops.

**Generalization rationale:** Memory systems need to select lessons by reusable workflow shape, not just shared words, across unseen task families.

**Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Evidence-surface support gate accepts wrong final answers | Action | Planning | `action_module/round02_agent.py::_answer_support_status`, `_searchqa_answer_support_status` | 176/188 wrong SearchQA trajectories and 109/130 wrong ToolHop trajectories have support records; item 480 passes support with `Parliament` | Surface presence is weaker than relation-slot correctness in any evidence-based QA task | High | Add relation-aware final-answer support records that bind candidate, slot, source sentence, and answer type |
| Multi-hop evidence-chain break in transform tasks | Cross-Module Interface | Planning, Action | `Planning -> Action`, `planning_module/provider.py`, `action_module/round02_agent.py` | Item 1116 uses one parentage hop as paternal-grandfather evidence; ToolHop accuracy falls on higher tool-count buckets | Ordered dependencies recur in multi-hop lookup, transform, and stateful workflows | High | Pass structured evidence slots to action and update slot status after every observation |
| Premature stateful completion after partial mutation progress | Action | Planning | `action_module/round02_agent.py::_terminal_ready`, `_partial_commit_ready`, `_run_partial_commit` | EnvScaler average score 0.4158; 568 done cases but only 8 perfect; partial commits average 0.3686 and never reach perfect | Multi-update tasks require all requested mutations, not any progress plus blocker | High | Replace one-mutation completion gates with all-required-mutation coverage checks |
| Schema and repeated-call recovery does not change strategy reliably | Action | Memory | `action_module/round02_agent.py::_preflight_arguments`, `_guard_observation`, `execute_tool_call` | 284 schema-preflight, 223 unknown-tool, 360 repeated-failed-call, and 441 low-value-repeat trajectories | Tool-rich unseen domains will keep producing lookup misses and schema mismatches | High | Add a structured recovery controller that enumerates valid tools, changes lookup strategy, and repairs missing fields from evidence |
| Unvalidated plan packet creates weak execution contracts | Planning | Builder/Wiring | `planning_module/provider.py::topology_initialize`, planning prompt templates | 657/658 EnvScaler plans are action-like instead of structured mutation ledgers | Downstream modules cannot consume a plan that is not guaranteed to contain required state | High | Parse and validate plan packets; re-ask or deterministically fill missing fields before action |
| Noisy memory retrieval distracts without enforcing reusable lessons | Memory | Planning | `memory_module/round02_memory.py::_score`, `provide_memory`, `take_in_memory` | ToolHop and EnvScaler failures retrieve loosely related long traces; SearchQA skip policy is stronger | Reusable memories need topology and phase matching, not shallow lexical overlap | Medium | Route memories by benchmark family, task topology, and active failure class; shorten trace sketches |

### PART 4: STRENGTHS TO PRESERVE

- Hard schema preflight in Action converts unknown tools and missing keys into recoverable guard observations; evidence is the 284 schema-preflight cases that did not crash the run; generation should preserve this robustness while making recovery more active.
- Support-record finalization in Action helps keep answers tied to observations; correct SearchQA trajectories have support records in 134/137 cases and correct ToolHop trajectories in 123/128 cases; generation should strengthen the check rather than remove it.
- SearchQA leakage avoidance in Memory skips storing old SearchQA trajectories and adds a raw-query reminder; all 325 SearchQA items produced a valid answer and average tool calls stayed low at 2.49; generation should keep the no-old-answer rule.
- Single-executor simplicity in Action keeps tool ownership clear and avoids coordination overhead; successful item 826 completes a publisher-to-date-to-digit chain with three evidence/transform calls and one final answer; generation should not add multi-agent orchestration unless it directly improves arbitration.
- Guarded repeat blocking in Action can redirect lookup strategy when the model follows the hint; successful item 269 recovers from a failed membership check by listing group members, then completes a complex stateful task with score 1.0; generation should preserve repeat awareness but pair it with stronger strategy selection.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Validate And Materialize Plan Packets]**
- **Target Module:** Planning
- **Owner Path:** `planning_module/provider.py`, `planning_module/prompts/toolcalling_agent.yaml`
- **Problem:** EnvScaler plans are action-like in 657/658 cases, and many answer-task plans contain premature final-answer intent.
- **Mechanism:** Parse the plan into required fields, reject `think/tools` action JSON as a plan, and re-ask or deterministically fill missing `evidence_slots`, `required_mutations`, `dependency_edges`, `answer_format`, and `terminal_policy`.
- **Why This Module Owns It:** The planning provider currently accepts raw model output as authoritative planning state.
- **Generalization Rationale:** Every task family benefits when downstream action receives a stable task-state contract.
- **Complexity:** Medium
- **Expected Impact:** Better stateful coverage, fewer skipped multi-hop dependencies, and clearer terminal criteria.
- **Risk:** Overly rigid parsing could discard useful free-form plan details if no compact fallback is provided.

**[Priority 2: Add Relation-Aware Final Answer Arbitration]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_agent.py::_answer_support_status`, `_support_record`, `step`
- **Problem:** Wrong answers pass support because the candidate appears in evidence.
- **Mechanism:** Require a support record with candidate, target slot, source observation, relation phrase, and answer-type compatibility. For SearchQA, prefer exact answer-bearing clauses over document titles or broad entities. For ToolHop, require the final candidate to derive from the last satisfied dependency slot.
- **Why This Module Owns It:** Final-answer acceptance is implemented in the action loop.
- **Generalization Rationale:** Evidence-based QA across domains needs slot-specific support, not just token overlap.
- **Complexity:** Medium
- **Expected Impact:** Reduces path-correct but final-wrong failures and wrong candidates after partial evidence.
- **Risk:** Too strict a gate could block valid paraphrases or deterministic derivations unless derivation records are explicitly supported.

**[Priority 3: Replace Partial Completion With Required-Mutation Coverage]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `Planning -> Action`, `planning_module/provider.py`, `action_module/round02_agent.py::_terminal_ready`
- **Problem:** EnvScaler completes after partial progress and blockers.
- **Mechanism:** Convert planned `required_mutations` into action-visible checklist items, update each item from successful mutation observations, and allow `complete_task` only when all required mutations are satisfied or explicitly proven impossible under a supported blocker policy.
- **Why This Module Owns It:** Planning must expose the mutation list, and Action must enforce it before terminal calls.
- **Generalization Rationale:** Multi-update environments require completion decisions over full requirement coverage.
- **Complexity:** Medium
- **Expected Impact:** Fewer low-score completed EnvScaler tasks and better resistance to hallucinated "all done" states.
- **Risk:** If mutation extraction is incomplete, the action module may block completion even after the real task is solved.

**[Priority 4: Implement A Schema-Aware Recovery Controller]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_agent.py::_preflight_arguments`, `_guard_observation`, `execute_tool_call`
- **Problem:** Guard hints do not reliably change tool strategy after schema, not-found, permission, or repeat errors.
- **Mechanism:** After each failure class, choose from a small recovery policy: enumerate valid tools, repair missing required fields from last observations, switch exact lookup to list/search, avoid failed signatures, and cap repeated recovery attempts per slot.
- **Why This Module Owns It:** Tool selection, schema preflight, failure signatures, and observations are action-side responsibilities.
- **Generalization Rationale:** All tool-use domains encounter schema and identifier mismatches.
- **Complexity:** Medium
- **Expected Impact:** Fewer loops, fewer no-final ToolHop cases, and higher EnvScaler scores after lookup failures.
- **Risk:** A controller that overrules the model too aggressively could choose generic list/search calls when a direct call is correct.

**[Priority 5: Route Memory By Topology And Failure Phase]**
- **Target Module:** Memory
- **Owner Path:** `memory_module/round02_memory.py::_score`, `provide_memory`, `take_in_memory`
- **Problem:** Retrieved memories are sometimes long, loosely related, and not actionable for the current failure.
- **Mechanism:** Add routing keys for benchmark family, route, number of dependency hops, stateful-vs-read-only, active failure class, and phase. Compress stored traces into one-line procedure recipes plus one relevant tool-pattern example.
- **Why This Module Owns It:** Memory selection and formatting are implemented entirely in the memory provider.
- **Generalization Rationale:** The same lesson is useful only when the current task shares the same workflow topology or failure phase.
- **Complexity:** Low
- **Expected Impact:** Less prompt noise and more useful recovery guidance.
- **Risk:** Over-filtering could remove helpful analogies for rare tool families.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory 480, SearchQA: the search snippet contains the correct narrow answers, "Government minister" and "any parliamentarian", but the agent finalizes `Parliament`. The support record accepts it because the word appears in evidence. This is a final-answer arbitration failure, not a search failure.
- Failed trajectory 1116, ToolHop: the task requires the first name of the paternal grandfather of Hojo Akitoki. The agent performs one parentage lookup, extracts the first name from that result, counts the target character, and finalizes `0` with support. The gold answer is `2`. This shows dependency-chain collapse.
- Failed trajectory 460, EnvScaler: the task asks for four EHR state changes. The agent updates patient contact, fails to add a medical record due to permission denial, invents an unavailable provider-authentication tool, updates provider contact after schema repair, and calls `complete_task` with score 0.2222. This shows partial progress being treated as terminal readiness.
- Failed trajectory 765, ToolHop: the agent repeats failed publisher and founding-year lookups, invents `publication_list_search`, hits repeated-call and schema guards, and never calls `final_answer`. This shows that guard observations are not enough to force strategic recovery.
- Successful trajectory 826, ToolHop: the agent retrieves the publisher of National Contest Journal, retrieves the founding date of American Radio Relay League, extracts digits 2 and 3 from 1914, and finalizes `91`. This is the behavior to preserve: ordered evidence collection, deterministic transform, and raw supported final answer.
- Successful trajectory 269, EnvScaler: after an initial failed membership check, the agent lists group members, extracts the membership id, updates membership, changes journal visibility, deletes the correct discussion thread, updates group info, creates the announcement thread, and reaches score 1.0. This shows that list-based identifier repair and full mutation coverage can work.
- Bucket-level statistics: overall score is 0.4360 across 1241 items. EnvScaler averages 0.4158 with only 8 perfect cases. SearchQA accuracy is 0.4215. ToolHop accuracy is 0.4961. Guard markers are widespread: 284 schema-preflight cases, 223 unknown-tool cases, 360 repeated-failed-call cases, 441 low-value-repeat cases, and 339 EnvScaler partial commits.

### PART 7: GENERATION CONSTRAINTS

- [Planning] Validate the initial plan packet before execution; do not accept action-style `think/tools` JSON as a plan.
- [Planning] Produce explicit evidence slots, dependency edges, required mutations, answer format, and terminal policy for every task family.
- [Action] Do not accept a final answer solely because the candidate string or tokens appear in recent evidence.
- [Action] Add relation-aware support records that bind candidate answers to the target slot and source observation.
- [Action] Replace one-success completion readiness with all-required-mutation coverage for stateful tasks.
- [Action] Convert guard blocks into structured recovery actions, including valid-tool enumeration, missing-key repair, and lookup strategy changes.
- [Memory] Retrieve memories by benchmark family, task topology, route, phase, and failure class, not by shallow token overlap alone.
- [Builder] Preserve the local harness factory wiring contract, provider class injection, project-root setting, and tool-agent binding behavior.
- [Interface] Pass structured plan state from Planning to Action and update slot or mutation status after each observation.
- [Avoid] Do not add entity-specific, benchmark-answer-specific, or trajectory-id-specific patches for Bahamas laws, Hojo genealogy, EHR records, or magazine publishers.
- [Avoid] Do not solve support-gate failures by removing the support gate; strengthen it with slot-specific evidence binding.
- [Preserve] Keep SearchQA memory leakage prevention and raw-query first-search guidance.
- [Preserve] Keep hard schema preflight and repeated-call awareness, but pair them with active recovery.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```

### POST-RUN TOOLHOP / ENVSCALER PATCH NOTES

This section is mandatory guidance for any regenerated round03_01 harness from this analysis. It records the first-200 common-task trajectory findings after comparing the 8 generated harnesses against the seed run, and it should be treated as a generation constraint rather than an optional improvement.

#### New Trajectory Evidence To Localize

ToolHop harness failures are concentrated in relation-chain and transform execution rather than only generic answer arbitration. Across the 8 harness runs on the first 200 common tasks, there are 304 ToolHop harness-task instances, with 127 successes and 177 failures. The dominant failure markers are: 118 lookup-not-found cases, 105 repeat-loop cases, 68 schema/tool-contract cases, 62 answer-support-missing cases, 116 wrong finals where the eventual answer was surface-supported, and 90 wrong supported finals with relation-overlap equal to 0. Twelve of the 38 ToolHop tasks are failed by all 9 runs including seed.

EnvScaler failures are concentrated in incomplete mutation coverage and identifier/schema recovery. Across 936 EnvScaler harness-task instances, 430 have score 0 and 565 score below 0.5. Low-score markers include 495 mutation-coverage gaps, 489 repeat loops, 366 schema or invalid-id cases, 331 cases without an actual terminal `complete_task`, and 234 premature or partial completion cases.

#### Required Localization Updates

- **ToolHop runtime/tool bridge:** The runtime must be localized as an owner of schema-contract failures. JSON schemas sometimes expose argument names that differ from Python function signatures, especially transform tools that advertise `input` while implementations expect fields such as `strings`, `first_name`, or `last_name`. Future harnesses should include an argument-coercion layer before tool execution, not only prompt-level retry advice.
- **ToolHop action policy:** The action module must own decomposition of family and relation phrases before transform calls. Paternal and maternal chains must be decomposed into ordered hops such as father -> requested relative and mother -> requested relative. The action module should not pass a natural-language compound relation directly to a narrower lookup tool and then finalize from the source entity.
- **ToolHop deterministic support gate:** The action module must distinguish a deterministic transform derived from observed tool results from an unsupported literal number. Valid transform finals include counts, lengths, reversals, date conversions, day-of-month extraction, and timezone conversions derived from the latest satisfied dependency slot. Surface numeric overlap alone is not sufficient when a relation chain is still unsatisfied.
- **ToolHop date/time canonicalization:** Date answers should canonicalize to `YYYY-MM-DD`, date-time answers to `YYYY-MM-DD HH:MM`, and `AoE` should be treated as UTC-12 when converting times. A question asking for the day of birth or death without asking for weekday should be localized as day-of-month, not weekday name.
- **EnvScaler planning contract:** Planning must be localized as owner of mutation enumeration. Numbered or bulleted natural-language requests must become action-visible required mutations, with one checklist item per requested create/update/delete/transfer/status change.
- **EnvScaler action policy:** The action module must own exact identifier and enum recovery. For `*_id` schemas, retrieve and reuse exact IDs from list/detail/search tools; never use names, phone numbers, locations, or placeholder strings as IDs. For enums, call or infer the allowed-values source and use the exact allowed token.
- **EnvScaler terminal discipline:** `complete_task` should be localized as a guarded terminal action. It is valid only after the required mutation checklist is covered, or after every uncovered mutation has an explicit observed blocker. Natural-language completion text is not terminal.

#### Preserve While Patching

Preserve the single mutating executor, hard schema preflight, support-record concept, SearchQA no-leakage memory policy, and compact memory reminders. The post-run evidence argues for stronger contracts and recovery policies, not heavy multi-agent orchestration or broader prompt context.

