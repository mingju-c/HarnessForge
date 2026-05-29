### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness under analysis is `harness_round02_01_7`, evaluated in `round03_02` with model name `qwen3-4B-round_02_01-harness7`. `builder.py` wires a single `ToolCallingAgent` through `ActionProvider.build`, injects `PlanningClass` into `context.kwargs`, sets `planning_system = "evidence_search_planning"`, `action_system = "evidence_search_react"`, points `project_root` at the base harness directory, and defaults `max_tool_calls_per_step` to 2.

The builder also binds process, end-process, delete-memory, executor, and refine tools back to the agent when those tools expose an `agent` attribute. If a vector tool exists, its memory pointer is set to the agent memory. The metadata records the source harness round as `round_02_01`, which is consistent with the harness origin but not with the current evaluation folder `round03_02`; this is not a dominant behavioral failure.

The main wiring limitation is that planning is passed as a class and planning packets are stored as text in memory, but there is no parsed state contract between planning and action. Required evidence slots, dependency edges, required mutations, answer-format requirements, and terminal criteria are advisory text. The action guard creates its own heuristic ledger from tool observations, not from a structured planning state.

#### 1.2 Planning Module Implementation

The planning provider implements `PLANNING_SYSTEM = "evidence_search_planning"`. At initialization it renders a prompt asking for a compact packet with `task_type`, `route`, `evidence_slots`, `dependency_edges`, `required_mutations`, `answer_format`, `terminal_policy`, `verification_questions`, and `next_tool_intent`. It appends memory guidance before the task message and stores the model response as a `PlanningStep`.

The adaptation method renders a progress-summary prompt every summary interval and asks for completed evidence slots, blocked slots, derived facts, failed calls, mutation progress, terminal readiness, recovery route, and next safe move. This summary is also stored as text. The provider does not parse, validate, or repair malformed plan packets.

Trajectory evidence shows a sharp planning failure on EnvScaler: all 658 EnvScaler runs produced a plan shaped like an immediate tool-call JSON object rather than the required planning packet. Example item 460 begins with a plan value containing `think` and `tools`, not a mutation checklist. Since the action module does not receive a structured checklist, stateful tasks lose the intended decomposition before execution begins.

For ToolHop and SearchQA, planning is usually closer to the requested packet shape, but it still tends to make `next_tool_intent` too terminal-oriented and does not enforce dependency edges. In item 1171, planning correctly names the missing paternal-grandfather slot, but later summaries and actions can still jump to unrelated old-memory entities because no module-level invariant binds final transformations to completed slots.

#### 1.3 Action Module Implementation

The action module is a single-executor guarded ReAct topology. There are no worker, verifier, repairer, debate, or parallel-arbitration agents. `ActionProvider.build_affordance` loads the primary task tools and the reasoning tool. `Round02GuardedAgent` subclasses `ToolCallingAgent` and adds local runtime checks around tool execution and final answers.

The active variant config sets `support_record_gate = True`, `support_mode = "strict"`, `complete_gate = True`, `completion_policy = "progress"`, `drop_extra_keys = False`, `repeat_limit = 2`, `partial_commit_on_blocker = True`, `min_successful_mutations_before_partial_complete = 1`, and `enable_ledger_review_tool = False`. Thus the harness has hard schema preflight and support-record machinery, but the optional ledger-review tool is disabled.

Tool execution uses `_preflight_arguments` to block unknown tool names, non-dict arguments for multi-input tools, extra keys, and missing required keys. Repeated failed signatures and low-value repeats are blocked by `ROUND02_GUARD_BLOCK` observations. SearchQA has a raw-query repair guard before the first search. Observations are classified by string markers such as `error`, `not found`, `invalid`, `permission denied`, and `guard blocked`.

Final-answer handling is stronger than earlier shallow evidence gates but still incomplete. For SearchQA, `_searchqa_answer_support_status` accepts an answer when the answer surface appears in one evidence record or all answer tokens appear in one evidence record. This blocks some unsupported answers, but it does not prove the candidate is the minimal requested span or that it answers the specific relation in the question. `_canonicalize_answer` strips labels and does limited date/binary normalization, but it does not extract a raw span from a full sentence.

Stateful completion is also too permissive. `_terminal_ready` allows completion on stateful routes after at least one successful mutation or successful real call under the `progress` policy. `_partial_commit_ready` can auto-submit `complete_task` after one successful mutation and a blocker. This explains why EnvScaler often finishes with partial credit rather than waiting for all requested state changes.

#### 1.4 Memory Module Implementation

The memory module implements `round02_search_evidence_memory` through `Round02MemoryProvider`. At BEGIN it always provides phase guidance that distinguishes observed facts, derived facts, hypotheses, old memories, and commit rules. During execution it provides an in-task reminder every third step. It stores both failures and successes, and retrieves up to three records by lexical task-signature overlap.

The SearchQA path is intentionally safer than previous harnesses: SearchQA receives only phase guidance and does not retrieve old memories, and SearchQA trajectories are skipped during memory ingestion to avoid answer or query leakage. This should be preserved.

For ToolHop and EnvScaler, however, retrieved memories often include concrete old entity names, IDs, tool arguments, and trace snippets. This creates prompt bulk and sometimes contaminates current execution. In item 1171, the BEGIN memory includes an old successful procedure mentioning `Donnchad Midi`; after the current Kerry Earnhardt lookup fails, the action loop calls `extract_last_name` on `Donnchad Midi` and finalizes the resulting binary code. In item 1053, old dispute UUIDs from memory appear before the task-specific `D1` and `D2` identifiers are resolved. The guidance says old memories are only workflow hints, but the memory content is not abstracted enough to prevent the action module from treating old trace values as candidate evidence.

### PART 2: FAILURE MODE ANALYSIS

**Name:** Stateful plan contract collapses into first-action JSON and completion lacks a required-mutation ledger

**Frequency / importance:** Very high for EnvScaler. EnvScaler has 658 tasks, average score 0.4582, only 13 full-score runs, 563 partial-score runs, and 82 zero-score runs. `complete_task` was called in 584 runs, and 563 runs were done but not full score.

**Symptom:** The agent completes a subset of requested state changes, hits blockers or repeated-call guards, and still calls or auto-submits `complete_task`. The initial plan does not enumerate all requested mutations as a durable checklist.

**Mechanism:** Planning outputs immediate tool-call JSON for all EnvScaler items instead of the requested packet with `required_mutations`. Action then relies on heuristic counts of successful calls, not a complete task checklist. Under `completion_policy = "progress"`, one successful mutation or real call can make a stateful route terminal-ready, and partial commit can fire after a blocker.

**Generalized capability gap:** Missing structured mutation ledger shared from Planning to Action, with per-requirement status, verification evidence, and completion blocking.

**Primary module owner:** Cross-Module Interface

**Secondary contributor:** Planning and Action

**Evidence:** `plan_as_tool_json = 658/658` for EnvScaler. EnvScaler has `ROUND02_PARTIAL_COMMIT` in 282 runs, guard blocks in 567 runs, and complete-task calls in 584 runs. Item 460 completed with score 0.2222 after only some EHR updates, repeated an unknown `get_current_authenticated_role` tool, and then submitted `complete_task`. Item 1053 completed with score 0.9091 after resolving most but not all billing/dispute requirements.

**Generalization rationale:** Any stateful tool environment with multi-step updates needs an explicit checklist and verification ledger. A terminal policy based only on "some progress happened" will recur across calendars, medical records, billing, bookmarks, bookings, and other state-changing APIs.

**Confidence:** High

**Name:** Guard blocks detect tool errors but do not route recovery

**Frequency / importance:** High across ToolHop and EnvScaler. Guard blocks appear in 567 EnvScaler runs, 203 ToolHop runs, and 50 SearchQA runs. EnvScaler has 362 schema-preflight blocks, 339 repeated-failed-call blocks, 217 low-value-repeat blocks, and 291 unknown-tool blocks. ToolHop has 94 schema-preflight blocks, 117 repeated-failed-call blocks, 57 low-value-repeat blocks, and 101 tool-execution-error blocks.

**Symptom:** The harness correctly detects unknown tools, missing keys, invalid relationship values, not-found results, permission errors, and repeated failed calls. After receiving the guard observation, the agent often retries the same class of action, invents another unavailable tool, or finalizes from a blocker.

**Mechanism:** The guard observation is diagnostic text, not an executable recovery router. The enabled tools do not include `ledger_review`, and there is no programmatic mapping from failure class to the next valid recovery action. The model must infer the repair path from a long prompt and accumulated trace.

**Generalized capability gap:** Missing action-side repair protocol for schema repair, ID resolution, enum discovery, authorization checks, and alternative-tool selection after guard blocks.

**Primary module owner:** Action

**Secondary contributor:** Memory and Planning

**Evidence:** Item 1171 repeats invalid or unavailable family relationship tools, then follows a summary suggestion to use unavailable `historical_genealogy_lookup`, then repeats blocked calls. Item 1053 first uses stale dispute IDs, then repeatedly lists disputes even after the correct `D1` is visible. Item 460 loops on unknown `get_current_authenticated_role` despite the guard listing valid alternatives.

**Generalization rationale:** Tool-rich tasks in any domain produce missing-key, unknown-tool, not-found, invalid-enum, and authorization errors. Blocking the bad call is useful only if recovery is guided by a reusable, schema-aware repair policy.

**Confidence:** High

**Name:** SearchQA final answers are evidence-present but not relevance- or span-canonicalized

**Frequency / importance:** High for SearchQA. SearchQA has 325 tasks, exact accuracy 141/325 = 43.38 percent, sub-EM 50.77 percent, and 184 zero-score failures. All 325 SearchQA runs called `final_answer`. Of the 184 wrong SearchQA answers, 24 contained the gold string as a substring but failed exact scoring due to extra words, extra entities, or over-broad lists.

**Symptom:** The agent retrieves evidence and calls `final_answer`, but the final value is a distractor span, adjacent fact, full sentence, or overlong list instead of the raw requested answer.

**Mechanism:** The SearchQA support gate accepts answer candidates when the surface string or all answer tokens appear in one evidence record. That is not the same as proving question-slot relevance. The canonicalizer does not extract the minimal answer span from a supported sentence, and it does not enforce answer-type constraints such as city-only, date-only, object-only, or complete list-only.

**Generalized capability gap:** Missing evidence-to-question-slot arbitration and minimal raw-span canonicalization for short-answer retrieval.

**Primary module owner:** Action

**Secondary contributor:** Planning

**Evidence:** Item 12 answered `Toronto` for a question whose gold city was `Ottawa, Ontario`, because `Toronto` appeared in retrieved evidence but did not satisfy the relation chain. Item 9 answered `a Pittsburgh suburb in the early 1990s` when the gold answer was `Pittsburgh suburb`. Item 275 repeatedly attempted the full sentence `You must be 18 years or older to get a tattoo, though some states or studios may allow minors with parental consent` when the gold span was only `18 years or older`.

**Generalization rationale:** Retrieval tasks with distractor snippets, adjacent entities, dates, aliases, list answers, or explanatory evidence will fail if "present in evidence" is treated as sufficient for "is the requested raw answer."

**Confidence:** High

**Name:** Multi-hop ToolHop provenance breaks after failed intermediate lookups

**Frequency / importance:** High for ToolHop. ToolHop has 258 tasks, average score 0.5233, 133 full-score runs, 4 partial-score runs, and 121 zero-score runs. Valid answers were produced for all 258 tasks, but 121 were wrong. ToolHop failures frequently contain not-found observations, tool-execution errors, repeated-failed-call guards, or final answers supported only by a local transform result.

**Symptom:** The agent obtains a partial fact or fails to obtain an intermediate relation, then transforms the wrong entity, a stale-memory entity, or the original subject and finalizes a plausible raw value.

**Mechanism:** Planning names evidence slots, but Action does not maintain an ordered provenance ledger for source entity, relation result, derived field, transform input, transform output, and final answer. For transform or unknown routes, support can be reported as "support not required for this route" even when the transform input was never tied to the requested entity chain.

**Generalized capability gap:** Missing multi-hop provenance ledger with dependency-checked finalization.

**Primary module owner:** Cross-Module Interface

**Secondary contributor:** Planning and Action

**Evidence:** Item 1171 failed to find Kerry Earnhardt's paternal grandfather, then extracted `Donnchad Midi` from old memory and finalized binary `1101001` instead of `1110100`. Item 44 failed to find Alexandre Berthier's paternal grandfather, extracted the first name from the original subject, and returned `erdnaxela` instead of `erdnaxela-siuol`. Item 2 retrieved Bellingham Review's publication date `2023`, reversed it, and returned `3202`, while the question required the founding year of the publisher.

**Generalization rationale:** Multi-hop lookup and transform tasks in biographies, publications, business records, and API workflows require preserving which observation belongs to which dependency. Local transform correctness does not guarantee chain correctness.

**Confidence:** High

**Name:** Retrieved memory contains concrete old trace values that leak into current action

**Frequency / importance:** Medium to high. Relevant memory appears in 251/258 ToolHop runs and 625/658 EnvScaler runs. SearchQA avoids this retrieval path, which likely helps prevent old answer leakage there.

**Symptom:** Old successful or failed trajectory snippets introduce entity names, IDs, dates, UUIDs, and tool arguments from unrelated tasks. The action loop sometimes uses those old values as if they were current evidence or plausible identifiers.

**Mechanism:** Memory stores and retrieves truncated observed sequence sketches with concrete arguments and observations. The phase guidance says old memories are workflow hints, but the retrieved content is not masked or structurally separated from current observations. Action has no quarantine rule that prevents old-memory strings from becoming tool arguments unless they appeared in current observations.

**Generalized capability gap:** Missing memory abstraction and memory-to-action evidence quarantine.

**Primary module owner:** Memory

**Secondary contributor:** Memory -> Action interface

**Evidence:** Item 1171 retrieved old genealogy memories containing `Donnchad Midi`; later the current action called `extract_last_name` on `Donnchad Midi` despite no current tool observation supporting that entity. Item 1053 memory contained old dispute UUIDs such as `ee69bb4c...`, causing early not-found calls before the current `D1` and `D2` identifiers were resolved. The terms `Donnchad Midi` appeared across 7 result files and old genealogy names appeared across more than a dozen files, indicating repeated memory reuse, not a one-off.

**Generalization rationale:** Any memory system that includes concrete old trace values can pollute unseen tasks when current tasks share superficial tokens with old ones. This weakness transfers beyond the observed benchmark entities.

**Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Stateful plan contract collapses into first-action JSON and completion lacks a required-mutation ledger | Cross-Module Interface | Planning and Action | `planning_module/provider.py -> action_module/round02_agent.py` | EnvScaler plan-as-tool JSON in 658/658 runs; only 13 full-score runs; 563 done-but-partial runs; 282 partial commits | Stateful tasks in any API domain need a shared checklist of requested mutations and proof of completion | High | Parse or generate a structured mutation ledger and require Action to update every requirement before completion |
| Guard blocks detect tool errors but do not route recovery | Action | Memory and Planning | `action_module/round02_agent.py` | 567 EnvScaler guard-block runs; 203 ToolHop guard-block runs; item 1171 and item 460 repeat after guard advice | Tool-rich environments always need schema, enum, ID, and authorization repair after failed calls | High | Add a schema-aware recovery router and make repeated guard classes produce concrete alternative actions or stop conditions |
| SearchQA final answers are evidence-present but not relevance- or span-canonicalized | Action | Planning | `action_module/round02_agent.py` final-answer support and canonicalization | SearchQA exact 141/325; 184 zero-score failures; 24 wrong answers contained gold as substring; items 9, 12, 275 | Short-answer retrieval often has distractor snippets and overlong evidence sentences | High | Add question-slot answer typing, same-record relevance checks, and minimal-span extraction before `final_answer` |
| Multi-hop ToolHop provenance breaks after failed intermediate lookups | Cross-Module Interface | Planning and Action | `planning_module/provider.py -> action_module/round02_agent.py` | ToolHop 121 zero-score runs; 117 repeated-failed-call blocks; 101 tool-execution-error blocks; items 2, 44, 1171 | Multi-hop transforms require dependency-checked provenance across source, relation, transform, and final value | High | Maintain a hop ledger and require final transforms to cite completed dependency slots |
| Retrieved memory contains concrete old trace values that leak into current action | Memory | Cross-Module Interface | `memory_module/round02_memory.py -> action_module/round02_agent.py` | Relevant memories in 251/258 ToolHop and 625/658 EnvScaler runs; item 1171 uses `Donnchad Midi` from old memory | Memory retrieval with unmasked old values can pollute any superficially similar unseen task | Medium | Abstract stored memories, mask concrete entities/IDs, and prevent memory-only strings from being used as current evidence |

### PART 4: STRENGTHS TO PRESERVE

- The schema preflight guard in Action catches unknown tools, missing keys, extra keys, and repeated failed signatures; item 59 eventually repairs a missing `account_id` and achieves full EnvScaler score, so generation should not remove hard validation.
- The SearchQA raw-query and support-record discipline in Action enables many short direct successes; items 28, 31, and 38 solve with raw question search plus exact supported final span, so generation should preserve the lightweight retrieval path.
- The Memory module's SearchQA leakage prevention is valuable; SearchQA receives no retrieved old trajectory records, which avoids the stale-answer problem seen in ToolHop and EnvScaler.
- The single-executor topology keeps tool ownership simple and avoids coordination overhead; average successful SearchQA cases often finish in two calls, so generation should improve the executor rather than replacing it with broad multi-agent orchestration.
- The phase guidance distinction between observed facts, derived facts, and hypotheses is directionally correct; the next harness should make that distinction enforceable rather than deleting it.
- The ability to make partial state progress in EnvScaler is useful; the problem is premature completion after partial progress, not the mutation tooling itself.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Structured Stateful Mutation Ledger]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py -> action_module/round02_agent.py`
- **Problem:** EnvScaler plans collapse into first tool calls and Action completes after partial progress.
- **Mechanism:** Convert stateful planning into a compact list of required mutations with stable IDs, expected verification evidence, and status fields. Action should update this ledger after each observation and block `complete_task` until every required mutation is verified or explicitly impossible.
- **Why This Module Owns It:** Planning must express the task checklist, while Action owns execution and terminal completion. Neither module alone can guarantee full state completion without a shared state contract.
- **Generalization Rationale:** Multi-step stateful tasks in any domain need all requested changes tracked independently of tool-call count.
- **Complexity:** High
- **Expected Impact:** Should reduce done-but-partial EnvScaler runs and prevent partial commit from ending tasks after one successful mutation.
- **Risk:** If the ledger parser is too brittle, it may overblock valid completions or fail on long natural-language tasks.

**[Priority 2: Schema-Aware Recovery Router After Guard Blocks]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_agent.py`
- **Problem:** Guard observations detect failures but leave the model to invent recovery.
- **Mechanism:** Map guard classes to concrete repair behavior: missing keys should reuse observed fields from the latest successful lookup; unknown tools should forbid the invalid name and choose from valid tools; invalid enum/not-found should call list/search/get tools when available; repeated failed calls should advance to a different unresolved ledger slot.
- **Why This Module Owns It:** The Action module owns tool schemas, tool-call execution, failed signatures, and observation handling.
- **Generalization Rationale:** Schema repair and ID/enum recovery are domain-general tool-use capabilities.
- **Complexity:** Medium
- **Expected Impact:** Should reduce low-value repeat loops in ToolHop and EnvScaler and improve recovery from malformed calls without weakening validation.
- **Risk:** A too-aggressive router could choose semantically wrong tools or hide useful model reasoning.

**[Priority 3: Evidence-Linked Raw Answer Canonicalizer]**
- **Target Module:** Action
- **Owner Path:** `action_module/round02_agent.py`
- **Problem:** SearchQA often finalizes evidence-present but wrong, overlong, or over-broad answers.
- **Mechanism:** Add a final-answer candidate checker that records the evidence sentence, predicted answer type, minimal supported span, and relation match. If the model proposes a full sentence containing a shorter span, extract the raw span before finalization. For list answers, require all requested entities and avoid extra unrelated items when evidence permits.
- **Why This Module Owns It:** Final-answer submission, support checks, and canonicalization all happen in Action.
- **Generalization Rationale:** Short-answer QA across domains requires raw span extraction and relevance arbitration, not benchmark-specific facts.
- **Complexity:** Medium
- **Expected Impact:** Should improve SearchQA exact match while preserving raw-query search successes.
- **Risk:** Overzealous span trimming could remove required units, aliases, list delimiters, or date context.

**[Priority 4: Dependency-Checked Multi-Hop Provenance Ledger]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py -> action_module/round02_agent.py`
- **Problem:** ToolHop transforms can be applied to the wrong entity after failed intermediate lookups.
- **Mechanism:** Track source entity, relation call, observed target, derived field, transform input, transform output, and final answer as linked slots. Finalization should require that each transform input came from a completed current-observation slot, not from task text, memory text, or a failed lookup.
- **Why This Module Owns It:** Planning defines the dependency chain and Action observes or derives each hop.
- **Generalization Rationale:** The same provenance discipline applies to genealogy, publication metadata, sports facts, calendars, IDs, and database joins.
- **Complexity:** Medium
- **Expected Impact:** Should reduce ToolHop failures like items 2, 44, 52, and 1171 where local transforms are correct but the input entity is wrong.
- **Risk:** If implemented as verbose prompt text only, it may increase token cost without enforcing behavior.

**[Priority 5: Abstract and Quarantine Retrieved Memories]**
- **Target Module:** Memory
- **Owner Path:** `memory_module/round02_memory.py`
- **Problem:** Retrieved memories include concrete old values that leak into current tool arguments.
- **Mechanism:** Store procedural memories with entity names, IDs, dates, and answers masked or summarized. Separate `procedure_hint` from `current_evidence` in the message format. Add an Action-side check that a concrete value from memory cannot be used as a tool argument unless it also appears in the current task or a current observation.
- **Why This Module Owns It:** Memory controls what old content is retrieved and how it is presented; the Memory -> Action interface controls evidence quarantine.
- **Generalization Rationale:** Abstract memories transfer across tasks, while concrete old traces overfit and contaminate new tasks.
- **Complexity:** Low to Medium
- **Expected Impact:** Should reduce stale-entity and stale-ID errors in ToolHop and EnvScaler without losing reusable failure lessons.
- **Risk:** Over-masking could remove useful schema examples or recovery patterns if not carefully summarized.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory, EnvScaler item 460: The task required four EHR updates. The plan was an immediate tool-call JSON rather than a mutation checklist. The agent added or updated some records, hit permission and authorization blockers, then repeatedly called unknown `get_current_authenticated_role` and finished with `complete_task`. Score was 0.2222. This supports the stateful-ledger and recovery-router diagnoses.
- Failed trajectory, EnvScaler item 1053: The task required resolving billing and dispute issues for two patients. Retrieved memory introduced stale dispute UUIDs; the agent later resolved current `D1` and `D2` after repeated listing and ID recovery, but still ended at score 0.9091. This shows memory bloat/stale IDs and incomplete checklist verification even when most actions succeed.
- Failed trajectory, ToolHop item 1171: The task asked for the binary code of the last letter of the last name of Kerry Earnhardt's paternal grandfather. After failed family lookups, the action loop used `Donnchad Midi` from old memory, transformed that value, and finalized `1101001` instead of `1110100`. This shows memory leakage plus missing multi-hop provenance.
- Failed trajectory, ToolHop item 44: The task asked for the reversed first name of Alexandre Berthier's paternal grandfather. After failed genealogy lookups, the agent extracted `Alexandre` from the original subject and returned `erdnaxela` instead of `erdnaxela-siuol`. This shows transform-on-wrong-entity failure.
- Failed trajectory, SearchQA item 12: The task asked for the city of the band that founded Royal Mountain Records. The agent answered `Toronto`, a supported surface in evidence, but the gold answer was `Ottawa, Ontario`. This shows that evidence presence is not enough without relation-specific answer arbitration.
- Failed trajectory, SearchQA item 275: The gold answer was `18 years or older`; the model repeatedly proposed a full explanatory sentence. The support gate blocked many attempts, but the run still ended wrong. This shows the need for minimal raw-span extraction rather than repeated final-answer attempts.
- Successful trajectory, ToolHop item 1: The agent found the author of `Hannibal and Scipio`, found the education place `Exeter College`, counted `r`, and finalized `1` with a support record. This shows that the single-executor path works when every hop is observed and the final transform input is current evidence.
- Successful trajectory, SearchQA item 28: A raw-question search followed by a supported exact span produced `Herman's Hermits`. This is the short retrieval behavior to preserve.
- Successful trajectory, EnvScaler item 59: The agent recovered from missing `account_id` schema blocks, used the observed account ID, made the requested clinical-trial updates, and completed with score 1.0. This shows schema preflight can help when paired with actual repair.
- Bucket-level statistic: EnvScaler has 584 done runs but only 13 full-score runs, meaning terminal completion is usually not aligned with full state satisfaction.
- Bucket-level statistic: SearchQA has 325/325 final-answer calls but only 141 exact successes, so the dominant SearchQA issue is not failure to terminate; it is answer arbitration and raw-answer formatting.
- Bucket-level statistic: ToolHop has 258/258 valid answers but 121 zero-score runs, showing that the harness often finalizes plausible values even when the evidence chain is broken.

### PART 7: GENERATION CONSTRAINTS

- [Planning] For stateful tasks, produce a real `required_mutations` checklist with one stable row per requested state change; do not allow a first tool-call JSON object to stand in for a plan.
- [Planning] For multi-hop tasks, include dependency edges that separate source entity, relation result, derived field, transform input, and final value.
- [Action] Keep hard schema preflight, repeated-call blocking, and support-record logging, but add a recovery router that turns each guard class into concrete next-action constraints.
- [Action] Do not call or auto-submit `complete_task` merely because one mutation or one real call succeeded; require the shared mutation ledger to be satisfied.
- [Action] For SearchQA and other short-answer retrieval tasks, finalize only a minimal raw span or complete requested list tied to the relevant question slot.
- [Action] For transform answers, require the transform input to be a completed current-observation slot; memory text and task text alone are not valid transform inputs.
- [Memory] Keep the SearchQA no-retrieved-memory policy unless a later design can prove old memories are fully abstract and leakage-safe.
- [Memory] Store failure lessons as abstract procedures with masked concrete IDs, names, dates, and answers; avoid injecting old trace values as free text.
- [Interface] Make Planning -> Action state machine readable by the guard code, not only by the language model context.
- [Interface] Make Memory -> Action explicitly non-evidential; old-memory strings cannot become tool arguments unless repeated in current task text or current observations.
- [Preserve] Preserve the compact single-executor ReAct loop for low-hop retrieval tasks where it solves quickly with raw search plus final support.
- [Preserve] Preserve successful schema repair behavior, such as using an observed missing key after a guard block.
- [Avoid] Do not add benchmark-specific checks for particular entities, IDs, gold answers, or observed item numbers; repairs must operate on evidence slots, mutation ledgers, schema classes, and memory provenance.
- [Avoid] Do not weaken schema preflight or final-answer support gates to increase termination rate; the problem is unsupported or incomplete success, not insufficient willingness to finish.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
