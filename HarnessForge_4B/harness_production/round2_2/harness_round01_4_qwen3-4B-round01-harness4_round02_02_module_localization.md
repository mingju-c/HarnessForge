### PART 1: HARNESS IMPLEMENTATION ANALYSIS

#### 1.1 Builder / Wiring Implementation

The harness is assembled by `builder.py` as `HARNESS_NAME = "harness_round01_4"`. The builder wires `PlanningClass` from `planning_module/provider.py`, `ACTION_SYSTEM = "read_only_commit_guard"` from `action_module/provider.py`, and `MEMORY_SYSTEM = "evidence_digest_memory"` from `memory_module/provider.py`. `prepare_context` sets the planning and action system names, sets `prompts_type` to the action system, points `project_root` to the harness directory, injects the planning class through `context.kwargs["planning_class"]`, and defaults `max_tool_calls_per_step` to `2`.

The builder also binds several external tools back to the built agent when those tools expose an `agent` attribute. If the vector tool exists, its memory pointer is set to the agent memory. The wiring is otherwise a direct single-agent build through `ActionProvider.build`.

The main implementation-description match is accurate: the harness is a compact planner plus guarded single-executor ReAct agent plus provenance-aware memory. The important mismatch is metadata carryover. `harness_metadata["round"]` is `"round_01"` and `PAIRING_REASON` is `"round01_read_only_commit_guard"` even though this analysis is for round02_02. This is not the dominant behavioral failure, but it can confuse downstream generation or analysis that relies on metadata.

The more consequential wiring limitation is that planning packets are stored as text in memory rather than converted into an enforceable runtime state. Action-side guards inspect local tool calls and observations, but they do not consume a parsed list of required evidence slots, required mutations, dependency order, or terminal criteria.

#### 1.2 Planning Module Implementation

The planning provider implements `PLANNING_SYSTEM = "read_only_evidence_planning"`. On initialization, it renders a prompt asking the model to classify the task as `read_only_lookup`, `stateful_mutation`, `deterministic_transform`, or `unknown`, then produce a compact packet with `evidence_slots`, `required_mutations`, `answer_format`, `terminal_criteria`, and `next_tool_intent`. Memory guidance is appended before the task message.

The adaptation method runs every summary interval through the base agent loop and asks for fields such as observed evidence, derived facts, hypotheses to verify, failed or repeated calls, pending mutations, terminal readiness, and next safe move. The method stores the result as a `SummaryStep`; it does not parse or validate whether the returned summary actually follows the requested fields.

Planning influences action through memory context only. It does not create a structured ledger that action must update before finalization or `complete_task`. Trajectory evidence shows that this is a real boundary problem: some EnvScaler plans or summaries resemble a next tool call rather than a complete task decomposition, and some ToolHop plans list an evidence need but do not preserve the hop order needed to prevent unsupported fallback answers.

Planning also does not currently enforce answer-format canonicalization. It often says "raw requested answer", but it does not decide whether a date must be ISO, whether a list must be complete, or whether an alias is acceptable. That leaves final formatting to the model and the limited action-side canonicalizer.

#### 1.3 Action Module Implementation

The action module is a single-executor guarded ReAct topology. `ActionProvider.build_affordance` loads primary task tools and includes the reasoning tool. `GuardedRound01Agent` subclasses `ToolCallingAgent` and adds local checks around each tool call and final answer.

The implemented guard behavior includes unknown-tool detection, argument-object parsing, extra-key detection, missing-key detection, repeated failed-call blocking, low-value repeat blocking, a shallow evidence-before-final gate, empty-action handling, successful-mutation counting, partial commit after blockers, and conservative final-answer canonicalization. The active policy is:

- `evidence_gate = True`
- `complete_gate = False`
- `drop_extra_keys = False`
- `repeat_limit = 2`
- `partial_commit_on_blocker = True`
- `min_successful_mutations_before_partial_complete = 1`

This means final answers are blocked until at least one non-final evidence observation exists, but terminal completion for stateful tasks is not hard-gated by a complete mutation checklist. It also means schema preflight is strict: extra keys are not dropped, and every non-nullable schema key is treated as required.

There is a `RepairCheckpointTool` implementation, but it is disabled by `if False` inside `build_organization`. The prompts and guard observations still tell the model to recover with a valid schema-matching tool or checkpoint-like reasoning, but no actual checkpoint tool is available. As a result, many trajectories detect the failure correctly and then repeat, guess, or terminate.

Final-answer handling is too shallow for the observed failures. `_has_prior_evidence()` only checks that some evidence-like tool observation exists. It does not verify that the answer candidate is tied to the correct entity, relation, document span, field, or deterministic transformation. This explains many path-correct but final-wrong SearchQA and ToolHop failures.

#### 1.4 Memory Module Implementation

The memory provider implements `MEMORY_SYSTEM = "evidence_digest_memory"`. At BEGIN, and every configured IN interval, it provides compact procedural guidance: separate observed facts from hypotheses, treat memory as route hints rather than evidence, repair schema after errors, and finalize only from observations or deterministic derivations.

At BEGIN, it also retrieves up to two successful reusable procedures by lexical token overlap between the current query and stored memory content. It stores only successful trajectories. Stored content includes a task-pattern prefix, a generic reusable procedure, and a truncated observed sequence sketch.

The guidance is conceptually aligned with the harness's goals, but retrieval is too broad for this mixed benchmark. The task wrappers share many tokens, so lexical overlap often retrieves unrelated successes. For example, SearchQA item 460, a queen bed measurement question, received prior memories about unrelated SearchQA answers such as Glee and The Angry Birds Movie. SearchQA item 20 received a ToolHop genealogy memory. These memories are not the primary failure cause, but they add prompt bulk and do not provide the missing recovery or evidence-arbitration procedure.

The memory module also stores only successful procedures, so repeated failure patterns such as relation-enum repair, "not found" recovery, ID-vs-name resolution, and premature completion do not become reusable failure lessons.

### PART 2: FAILURE MODE ANALYSIS

**Name:** Evidence-present but answer unsupported or selected from the wrong span

**Frequency / importance:** High. SearchQA has 325 items with exact answer accuracy 116/325 = 35.69 percent. Among 209 incorrect SearchQA items, 168 still produced a valid final answer, and 137 incorrect items finalized after exactly one tool call.

**Symptom:** The agent retrieves plausible evidence, then commits an answer from a distractor snippet, adjacent entity, incomplete list, or insufficiently checked source.

**Mechanism:** The action-side final gate only requires that some prior evidence observation exists. It does not require a support record connecting the final answer to the specific requested slot. In item 460, the search results included both a bed-size document and a pillow document. The agent answered `20x30 inches`, copied from the queen pillow snippet, while the requested queen bed measurement was `60 in x 80 in`.

**Generalized capability gap:** Missing evidence-to-answer attribution and relevance arbitration before `final_answer`.

**Primary module owner:** Action

**Secondary contributor:** Planning and Memory

**Evidence:** SearchQA average score is 0.3831. Item 460 is a clear wrong-span selection. Item 744 answers `River Horse` for the state animal of Washington DC, showing surface retrieval without entity grounding. Item 467 returns only a partly correct Lynyrd Skynyrd member list, showing no completeness check before finalization.

**Generalization rationale:** Any retrieval setting with distractor passages, near-duplicate entities, list answers, or adjacent facts will fail if the action loop treats "some evidence exists" as sufficient support.

**Confidence:** High

**Name:** Multi-hop evidence-chain break after a failed intermediate lookup

**Frequency / importance:** High. ToolHop has 259 items with exact answer accuracy 99/259 = 38.22 percent. Among 160 incorrect ToolHop items, 122 still produced a valid final answer, 88 contain guard blocks, 63 contain repeated failed-call blocks, and 37 contain tool execution errors.

**Symptom:** The agent obtains one intermediate fact or hits a failed lookup, then repeats the failed call, changes to a weakly related tool, or fabricates a fallback answer from an unverified entity.

**Mechanism:** Planning names the needed evidence but does not produce an executable hop ledger. Action handles each observation locally and has no invariant requiring the chain source, relation, target, transform, and final value to remain connected. In item 1171, the agent fails to resolve the publisher/founder chain for Big Picture Magazine, keeps retrying equivalent publication/founder calls, then answers `1` without the required founder evidence. In item 1222, after failing to find Robert Petre's paternal grandmother, it extracts and reverses `Petre` from the original subject, yielding `erteP` instead of the required grandmother surname reversal.

**Generalized capability gap:** Missing ordered provenance ledger for multi-hop tasks.

**Primary module owner:** Cross-Module Interface

**Secondary contributor:** Planning and Action

**Evidence:** ToolHop incorrect runs average more tool calls than correct runs, 6.03 vs 4.83, suggesting repeated exploration after chain breaks. Items 1171, 543, and 1222 show the agent detecting failed evidence acquisition but lacking a recovery route that preserves the original dependency chain.

**Generalization rationale:** Multi-hop workflows in biographies, publications, dates, arithmetic transforms, API chains, and database lookups all require stateful provenance across hops. Local tool-call correctness is not enough.

**Confidence:** High

**Name:** Guard detects schema and repeat errors but does not route recovery

**Frequency / importance:** High. Guard blocks occur in 512 EnvScaler runs, 123 ToolHop runs, and 31 SearchQA runs. Within incorrect ToolHop runs, 31 include schema preflight failures, 63 repeated failed-call blocks, 27 low-value repeat blocks, and 21 unknown-tool blocks. EnvScaler has 339 schema preflight blocks, 259 repeated failed-call blocks, 137 low-value repeat blocks, 132 unknown-tool blocks, and 237 missing-required-key blocks.

**Symptom:** The harness correctly identifies unknown tools, missing keys, invalid repeated calls, or low-value repeats, but the agent often retries the same class of call or terminates from the blocker.

**Mechanism:** The guard is a detector, not a repair policy. It emits `ROUND01_GUARD_BLOCK` text and asks the model to repair, but the checkpoint tool is disabled and there is no programmatic fallback that maps failure type to recovery actions. In EnvScaler item 1053, the agent first invents `get_appointments_by_patient`, then uses a wrong patient ID, then repeats `get_patient_info` with missing or invalid arguments. In item 1059, it observes `Work` has folder id `F2` but repeatedly uses the name `Work` as `parent_folder_id`, causing repeated "Parent folder does not exist" failures before eventually looking up the id.

**Generalized capability gap:** Missing post-error recovery router for schema repair, ID resolution, enum repair, and alternative-tool selection.

**Primary module owner:** Action

**Secondary contributor:** Planning and Memory

**Evidence:** EnvScaler item 1053 shows unknown-tool and missing-key guard blocks without productive recovery. ToolHop item 543 attempts unavailable `complete_task` in a short-answer toolset after repeated lookup failures. The code contains `RepairCheckpointTool`, but `build_organization` never enables it.

**Generalization rationale:** Any tool-rich environment will produce invalid enum, not-found, missing-key, extra-key, authorization, or ID-vs-name failures. Detecting them is useful only when paired with a reusable repair protocol.

**Confidence:** High

**Name:** Premature or incomplete stateful completion without a required-mutation ledger

**Frequency / importance:** Very high for EnvScaler. EnvScaler has 658 items, average score 0.3854, `done` rate 516/658 = 78.42 percent, but only 11 full-score runs. There are 505 done-but-not-full runs and 148 zero-score runs.

**Symptom:** The agent completes some state changes, then calls `complete_task` before all requested changes are verified, or loops on blockers until no meaningful progress remains.

**Mechanism:** The harness encourages partial commit after blockers and sets `complete_gate = False`. Action counts successful mutations heuristically from observation strings and state-changing tool-name patterns, but it does not know the full task checklist. Planning lists required mutations only as text, and action does not update a per-requirement status table. In item 1197, the agent verifies class availability, repeatedly checks enrollments, then tries to enroll both users in a class that the tool says is not scheduled for the future. It repeats failed enrollment calls and eventually returns `Task Completed` with score 0. In item 1108, it cannot locate a patient, loops over demographics and authorization calls, and leaves the requested allergy updates undone.

**Generalized capability gap:** Missing stateful execution ledger with requested mutation, resolved identifiers, mutation result, verification result, and terminal readiness.

**Primary module owner:** Cross-Module Interface

**Secondary contributor:** Action and Planning

**Evidence:** 559 EnvScaler traces include `complete_task`; 505 completed but did not get full score. Full success is rare even though many runs make partial progress. Successful item 249 shows the missing discipline: it lists enrollment records, verifies status, performs mutations one at a time, checks trial status, and only then calls `complete_task` for score 1.0.

**Generalization rationale:** Stateful tasks across scheduling, healthcare, folders, bookmarks, subscriptions, payments, and user management all require complete checklist tracking before terminal completion.

**Confidence:** High

**Name:** Final-answer canonicalization and answer-format failures

**Frequency / importance:** Medium. SearchQA has 17 incorrect examples with `subem = 1`, and ToolHop has 5 such near-miss examples. These are smaller than evidence-chain failures but directly actionable.

**Symptom:** The trace contains the needed value or a semantically close answer, but final output uses the wrong date format, adds extra context, returns an incomplete list, or preserves an alias inconsistent with the benchmark.

**Mechanism:** Planning usually says "raw requested answer" without deriving a concrete format contract. The action canonicalizer strips labels and some leading zeros, but it does not normalize dates, list ordering, aliases, or "first/last letter" casing beyond what the model chooses. In ToolHop item 99, the date calculator returns `1968-06-23`, but the final answer is `23 June 1968`; the gold answer is ISO `1968-06-23`. In SearchQA item 669, the expected location is `Rome`, while the final answer is `Rome, Italy`.

**Generalized capability gap:** Missing answer-format contract and final canonicalization layer tied to the task type and observed tool value.

**Primary module owner:** Action

**Secondary contributor:** Planning

**Evidence:** Item 99 has a correct path and tool observation but wrong final format. SearchQA near misses include extra dates, expanded names, and overlong lists. The current `_canonicalize_answer` does not address these classes.

**Generalization rationale:** Exact-answer tasks across QA, date arithmetic, string transforms, and list extraction require format control after evidence is collected.

**Confidence:** Medium

**Name:** Empty or zero-token execution artifact

**Frequency / importance:** Medium, but it should be isolated from harness reasoning failures. There are 146 runs with `api_calls = 0` and `total_tokens = 0`: 73 EnvScaler, 40 SearchQA, and 33 ToolHop.

**Symptom:** The trajectory contains empty action records, no plan, no tool calls, no observations, and no final answer. The run status is still marked success by the evaluator.

**Mechanism:** The recorded metrics indicate that the model was not invoked. Items 889, 848, and 872 each contain three empty action records and zero API calls. This is most likely an external runner, backend, timeout, or evaluation artifact rather than a module-level reasoning failure. A small number of non-zero-token empty-action cases remain harness-action issues, but the dominant zero-token bucket should be separated.

**Generalized capability gap:** Run-level instrumentation and retry for model-call aborts or uninitialized agent cycles, rather than task-specific reasoning.

**Primary module owner:** External / Evaluation Artifact

**Secondary contributor:** Builder / Wiring and Action

**Evidence:** Item 889 has `api_calls: 0`, `total_tokens: 0`, `tool_call_count: 0`, and no answer. Item 848 shows the same pattern for ToolHop. These cases should not be counted as evidence that planning chose the wrong tool.

**Generalization rationale:** Infrastructure no-op episodes can occur in any benchmark and should not drive harness generation toward benchmark-specific patches.

**Confidence:** Medium

**Name:** Memory retrieval is broad, verbose, and not failure-aware

**Frequency / importance:** Low-to-medium as a secondary contributor. It appears in representative failures but is not the main mechanism behind most wrong answers.

**Symptom:** BEGIN memory often contains long truncated successes from unrelated tasks, selected mostly by shared benchmark wrapper tokens.

**Mechanism:** The memory scorer uses lexical overlap on the full query, and stored records include the repeated terminal-rule boilerplate. It stores successful trajectories only, so recurrent failure lessons are absent. The result is prompt bloat rather than targeted procedural help.

**Generalized capability gap:** Missing task-signature routing and compact failure-memory ingestion.

**Primary module owner:** Memory

**Secondary contributor:** Cross-Module Interface

**Evidence:** Item 460 receives unrelated SearchQA memories about other entities. Item 20 receives a ToolHop genealogy memory during a SearchQA cocktail comparison. These memories repeat generic "ground in observations" advice but do not add relevance checks, relation repair, or ID resolution procedures.

**Generalization rationale:** Mixed-task systems with shared wrappers need memory keyed by task structure and failure mode, not only lexical overlap.

**Confidence:** Medium

### PART 3: MODULE ATTRIBUTION MATRIX

| Failure Mode | Primary Module | Secondary Module | Owner Path | Evidence | Generalization Rationale | Confidence | Repair Implication |
|---|---|---|---|---|---|---|---|
| Evidence-present but unsupported or wrong-span final answer | Action | Planning, Memory | `action_module/provider.py` final-answer gate and observation handling | SearchQA 168 incorrect valid answers; item 460 selects queen pillow size instead of queen bed size | Retrieval tasks often include distractors, adjacent facts, and incomplete snippets | High | Add evidence-to-answer support records and relevance arbitration before `final_answer` |
| Multi-hop evidence-chain break after failed lookup | Cross-Module Interface | Planning, Action | `planning_module/provider.py` text packets -> `action_module/provider.py` local execution | ToolHop 122 incorrect valid answers; items 1171 and 1222 finalize from broken chains | Multi-hop tasks require preserving source, relation, target, transform, and final provenance | High | Convert plan slots into an executable ledger updated by action observations |
| Guard blocks without recovery routing | Action | Planning, Memory | `action_module/provider.py` guard logic and disabled `RepairCheckpointTool` | EnvScaler 512 guard traces; ToolHop 88 incorrect guard traces; item 1053 loops through unknown tool and missing-key errors | Tool-rich tasks need generic recovery after schema, ID, enum, and not-found failures | High | Enable a repair router/checkpoint that maps failure type to next safe alternatives |
| Premature or incomplete stateful completion | Cross-Module Interface | Action, Planning | Planning required mutations -> Action `complete_task` readiness boundary | EnvScaler 505 done-but-not-full runs; only 11/658 full-score runs; item 1197 returns `Task Completed` with score 0 | Stateful workflows need per-requirement mutation and verification status before terminal completion | High | Add a mutation ledger and make terminal readiness depend on all required changes |
| Final-answer canonicalization and answer-format failure | Action | Planning | `action_module/provider.py` `_canonicalize_answer`; planning `answer_format` field | ToolHop item 99 observes `1968-06-23` but submits `23 June 1968`; SearchQA has 17 incorrect `subem = 1` near misses | Exact-answer tasks require output format control after evidence collection | Medium | Add format-specific canonicalizers and require concrete answer-format constraints from planning |
| Empty or zero-token execution artifact | External/Evaluation | Builder/Wiring, Action | Model-call/evaluation loop boundary; empty action trajectories | 146 zero-token, zero-API runs across all benchmarks; items 889 and 848 have no model call | No-op infrastructure episodes can affect any task and should not be treated as reasoning failures | Medium | Instrument zero-token aborts separately and add run-level retry or exclusion before harness diagnosis |
| Broad, verbose, non-failure-aware memory retrieval | Memory | Cross-Module Interface | `memory_module/provider.py` lexical scoring and successful-only storage | Item 460 and item 20 receive unrelated retrieved procedures | Mixed benchmarks share wrapper text, so lexical memory can inject irrelevant examples | Medium | Route memory by task signature and store compact reusable failure lessons |

### PART 4: STRENGTHS TO PRESERVE

- Hard schema preflight, owned by Action, prevents unknown tools and malformed arguments from silently executing; guard evidence in EnvScaler and ToolHop shows many invalid calls are caught, so generation should keep strict schema validation while improving repair.
- Single-executor ReAct execution, owned by Action, remains efficient for simple tasks; SearchQA item 20 and many one-search successes show the base loop can solve direct evidence tasks without expensive orchestration.
- Stepwise tool use with observation reading, owned by Action, supports successful multi-hop recovery; ToolHop item 1116 fails two initial genealogy routes, then finds the father, finds the father's mother, counts vowels, and finalizes correctly.
- Compact planning packets, owned by Planning, give useful initial fields for task type, evidence slots, terminal criteria, and next intent; successful item 249 benefits from sequential evidence and mutation reasoning, so the next harness should strengthen this packet into state rather than discard it.
- Provenance-aware memory reminders, owned by Memory, correctly distinguish observations from hypotheses; this rule directly matches the dominant failure modes and should be preserved with better retrieval selectivity.
- Partial progress preservation, owned by Action, helps EnvScaler average score remain nonzero despite many incomplete tasks; generation should keep partial-credit awareness but prevent it from replacing full checklist completion.

### PART 5: MODULE-LEVEL REPAIR PRIORITIES

**[Priority 1: Evidence Attribution and Sufficiency Gate]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** Final answers can pass after any evidence observation, even if the answer is from a distractor span or an incomplete chain.
- **Mechanism:** Require a compact support record before `final_answer`: answer candidate, source tool, observation excerpt or field, requested slot, entity match, and derivation type. For list/comparison questions, require all declared slots to be filled.
- **Why This Module Owns It:** The action loop owns observation processing and the final-answer decision.
- **Generalization Rationale:** Retrieval QA, database lookup, API chaining, and deterministic transforms all need answer-to-evidence linkage.
- **Complexity:** Medium
- **Expected Impact:** Should reduce the largest SearchQA failure bucket and many ToolHop unsupported finalizations.
- **Risk:** If too strict, it may increase no-final failures on simple questions where a single observation is sufficient.

**[Priority 2: Runtime Evidence and Mutation Ledger]**
- **Target Module:** Cross-Module Interface
- **Owner Path:** `planning_module/provider.py` -> `action_module/provider.py`
- **Problem:** Planning text lists evidence and mutations, but action does not update or enforce them.
- **Mechanism:** Parse or generate a small ledger with evidence slots, dependency links, required mutations, resolved identifiers, status, source observation, and verification result. Action updates it after each tool observation and consults it for final answer and terminal completion.
- **Why This Module Owns It:** The failure is at the boundary between planning's intended structure and action's execution state.
- **Generalization Rationale:** The same ledger supports ToolHop provenance and EnvScaler stateful checklist completion.
- **Complexity:** High
- **Expected Impact:** Should reduce multi-hop chain breaks and premature EnvScaler completion.
- **Risk:** A heavy ledger can slow simple SearchQA tasks or cause over-constrained behavior if the planner emits bad slots.

**[Priority 3: Schema/Error Recovery Router]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py`
- **Problem:** Guard blocks are detected but not converted into productive recovery actions.
- **Mechanism:** Add an internal repair policy keyed by guard reason and tool observation: unknown tool -> choose closest valid tool only if schema-compatible; missing ID -> search/list by name then substitute observed id; invalid enum -> inspect allowed values from the error; repeated failure -> forbid equivalent calls and select a new evidence route; unavailable terminal tool -> return to active final-answer contract.
- **Why This Module Owns It:** Tool-call execution, guard observation, and retry behavior all live in action.
- **Generalization Rationale:** Schema, ID, enum, not-found, and authorization errors are common across tool environments.
- **Complexity:** Medium
- **Expected Impact:** Should reduce EnvScaler schema loops and ToolHop repeated-call failures.
- **Risk:** Over-automatic repairs could choose semantically wrong alternatives if not tied to observed tool schemas.

**[Priority 4: Hard Terminal Readiness for Stateful Tasks]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py` terminal handling plus `Planning -> Action` mutation ledger
- **Problem:** `complete_gate` is disabled, and `complete_task` is often called before all requested changes are verified.
- **Mechanism:** Re-enable a stateful terminal gate backed by the mutation ledger. Permit partial completion only when a required mutation has succeeded and the ledger marks remaining items as blocked with explicit evidence.
- **Why This Module Owns It:** Action executes terminal tools and currently owns partial commit behavior.
- **Generalization Rationale:** Stateful tasks in any domain require verified completion rather than prompt-only terminal discipline.
- **Complexity:** Medium
- **Expected Impact:** Should raise EnvScaler full-score rate while preserving partial credit when truly blocked.
- **Risk:** If the gate cannot recognize valid completion, it may reduce `done` rate and lose partial score.

**[Priority 5: Concrete Answer-Format Canonicalizer]**
- **Target Module:** Action
- **Owner Path:** `action_module/provider.py` `_canonicalize_answer`; planning `answer_format`
- **Problem:** Correct or near-correct evidence is sometimes submitted in the wrong exact format.
- **Mechanism:** Extend canonicalization for dates, simple numeric strings, first/last-letter casing, list separators, and location/entity alias trimming. Planning should emit concrete format constraints such as `ISO date`, `integer`, `single lowercase letter`, or `complete comma-separated entity list`.
- **Why This Module Owns It:** Action sees the final candidate and can compare it against observed tool outputs before submission.
- **Generalization Rationale:** Exact-answer scoring appears in both SearchQA and ToolHop and will transfer to other short-answer tasks.
- **Complexity:** Low
- **Expected Impact:** Should recover near misses like ToolHop item 99 without changing search strategy.
- **Risk:** Aggressive normalization could strip required qualifiers, units, leading zeros, or aliases.

**[Priority 6: Task-Signature Memory Routing and Failure Lessons]**
- **Target Module:** Memory
- **Owner Path:** `memory_module/provider.py`
- **Problem:** Memory retrieval is dominated by shared wrapper text and stores only successful procedures.
- **Mechanism:** Score memory against extracted task signatures such as benchmark family, operation type, relation chain, stateful domain, and failure class. Store compact successful procedures and compact failure lessons, not long truncated trajectory sketches.
- **Why This Module Owns It:** Memory selection, compression, and ingestion policy live in the memory provider.
- **Generalization Rationale:** Better memory routing helps unseen tasks by providing procedures for recurring error classes rather than copied examples.
- **Complexity:** Medium
- **Expected Impact:** Should reduce prompt noise and improve recovery after repeated schema, relation, and ID-resolution failures.
- **Risk:** Poor signature extraction could suppress useful generic memories.

### PART 6: REPRESENTATIVE EVIDENCE

- Failed trajectory 460, SearchQA: The agent searches `measurement of a queen size bed`, observes a result page containing both bed-size and pillow-size snippets, then finalizes `20x30 inches` from a queen pillow snippet. Gold is `60 in x 80 in`. This is evidence-present but wrong-span finalization.
- Failed trajectory 1171, ToolHop: The agent needs the founder of the organization that published Big Picture Magazine and Deanna Drake's last name. It finds `drake`, fails publication and founder lookups, repeats blocked calls, then finalizes `1` without founder evidence. This is a multi-hop chain break plus unsupported fallback.
- Failed trajectory 1053, EnvScaler: The agent invents `get_appointments_by_patient`, then calls similar tools with wrong patient identifiers and missing required arguments. Guard blocks correctly report unknown tool and missing keys, but the agent keeps cycling through invalid patient/appointment discovery. This is schema and ID-resolution recovery failure.
- Failed trajectory 1197, EnvScaler: The agent checks class details and availability, repeatedly verifies enrollments, tries to enroll users in a class that the tool says is not scheduled for the future, repeats the failed enrollment calls, and still returns `Task Completed` with score 0. This is incomplete stateful completion.
- Failed trajectory 99, ToolHop: The agent correctly finds the spouse, gets the birth date, and the date calculator observes `1968-06-23`, but it submits `23 June 1968`. This isolates final-answer canonicalization from path search.
- Successful trajectory 249, EnvScaler: The agent lists enrollments, withdraws the correct participant, verifies a completed enrollment, deletes it, creates a user account, updates consent, enrolls a participant, checks trial status, and only then calls `complete_task`, receiving EnvScaler score 1.0. This shows stepwise state verification should be preserved.
- Successful trajectory 1116, ToolHop: The agent recovers from failed initial genealogy tools by finding the father first, then the father's mother, then counting vowels in the observed surname. This shows the single-agent loop can recover when it changes route while preserving provenance.
- Bucket statistic: Overall average score is 0.3861 across 1242 items. EnvScaler average score is 0.3854 with only 11 full-score runs; SearchQA exact accuracy is 35.69 percent; ToolHop exact accuracy is 38.22 percent.
- Bucket statistic: 146 trajectories have `api_calls = 0` and `total_tokens = 0`, split as 73 EnvScaler, 40 SearchQA, and 33 ToolHop. These should be treated as external/evaluation artifacts rather than harness reasoning failures.

### PART 7: GENERATION CONSTRAINTS

- `[Planning]` Emit concrete evidence slots with dependency order, expected source tool or field, and answer-format constraints rather than only a generic next-tool intent.
- `[Planning]` For stateful tasks, produce a complete required-mutation checklist with verification criteria and terminal readiness conditions.
- `[Action]` Do not let `final_answer` pass merely because any evidence exists; require the answer candidate to be tied to the relevant observation and requested slot.
- `[Action]` Add a guard recovery router for unknown tools, missing keys, invalid IDs, invalid enum values, repeated failed calls, and unavailable terminal tools.
- `[Action]` Keep schema preflight and repeat blocking, but pair each block with a productive next-step policy.
- `[Action]` Re-enable hard terminal readiness for EnvScaler-style tasks through a mutation ledger; partial commit should require explicit blocked remaining work.
- `[Action]` Extend answer canonicalization for dates, numbers, single letters, aliases, and list completeness while preserving units and leading zeros when requested.
- `[Memory]` Retrieve memories by task signature and failure mode, not by shared benchmark wrapper text.
- `[Memory]` Store compact reusable failure lessons for schema repair, ID resolution, relation recovery, and premature completion avoidance.
- `[Interface]` Convert planning packets into action-visible runtime state that is updated after observations and consulted before final or terminal calls.
- `[Interface]` Keep terminal policy bound to the active toolset: short-answer tasks should not attempt unavailable `complete_task`, and stateful tasks should not finish through unsupported final text.
- `[Builder]` Update harness metadata round fields to match the active round so downstream tooling does not read stale round identifiers.
- `[Preserve]` Preserve single-executor ReAct as the default path for simple tasks because it solves many direct SearchQA and ToolHop items efficiently.
- `[Preserve]` Preserve provenance guidance that distinguishes observations, derived facts, hypotheses, and memory hints.
- `[Avoid]` Do not add task-id, entity-name, benchmark-record, or observed-answer patches; all repairs should operate on schemas, observations, ledgers, and terminal contracts.
- `[Avoid]` Do not treat zero-token, zero-API trajectories as proof of a planning or reasoning defect; classify and retry them at the runner/evaluation boundary.

### PART 8: READY SIGNAL

```text
READY_FOR_IMPROVEMENT_DIRECTION
```
