### PART 1: LOCALIZATION SUMMARY

The current winner is `harness_round01_4` with model identity `qwen3-4B-round01-harness4`. It is a compact planning plus guarded single-executor ReAct harness: `read_only_evidence_planning` emits short evidence and terminal packets, `read_only_commit_guard` performs one-agent tool execution with schema preflight, repeat blocking, shallow evidence-before-final gating, partial commit heuristics, and limited final canonicalization, and `evidence_digest_memory` provides provenance reminders plus retrieved successful workflows. Stage 1 found that this foundation should be preserved, but the dominant failures come from missing enforceable state between modules. SearchQA often retrieves evidence but commits the wrong span; ToolHop breaks ordered evidence chains after failed intermediate lookups; EnvScaler frequently calls `complete_task` before all requested mutations are verified; guard blocks detect schema/repeat errors but do not route recovery; final answers miss exact formatting; memory retrieves broad, wrapper-matched successful examples and lacks compact failure lessons; and zero-token runs should be treated as runner/evaluation artifacts rather than harness reasoning defects. Module attribution is therefore Action for evidence support, tool repair, and answer formatting; Cross-Module Interface for evidence/mutation ledgers and terminal readiness; Memory for routing and failure lessons; Builder/Wiring only for metadata and instrumentation hygiene. Highest-leverage Stage 3 repair targets are a planning-to-action evidence and mutation ledger, a slot-specific final-answer support gate, an action-side failure-type recovery router with a non-acting critic/checkpoint, a hard stateful terminal readiness contract, task-conditioned answer canonicalization, and compact task-signature memory. The next harness must preserve hard schema preflight, direct single-executor acting, short plans, one-tool-by-default stateful execution, provenance language, and standard `final_answer` / `complete_task` contracts.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness1`

- **Observed Structure:** Direct single-executor ReAct with `flash_searcher` planning and ExpeL memory. The 8B pool marks it as a strong seed and quality reference.
- **Relevant Strength:** It has the strongest all-available mixed score among non-trivial 8B seeds, with fair_first100 mixed primary score 0.5049 and strong EnvScaler score 0.5066. It demonstrates that direct serial execution can be high quality when continuity is preserved.
- **Relevant Weakness / Risk:** It is expensive: average tokens are about 198,970.6 on fair_first100 and it can accumulate long context before stopping.
- **Related Winner Failure:** Premature or incomplete stateful completion; memory lacks failure lessons.
- **Transferable Module Pattern:** Borrow direct execution discipline and ExpeL-style compact success/failure insight storage, but not the full long-context trajectory exposure.
- **Generalization Rationale:** A single executor preserves state continuity across multi-step tool workflows, while failure insights can transfer by procedure rather than by entity.
- **Do Not Borrow:** Do not borrow high token usage, long reflections, or unbounded context accumulation.
- **Transfer Confidence:** Medium

#### Example: `harness2`

- **Observed Structure:** Concise reflection harness with short plans, one executor, periodic compact reflection, final verifier, and Agent-KB memory.
- **Relevant Strength:** It demonstrates a simple reflection/verifier layer that inspects progress without adding acting workers. SearchQA uses search reliably in the small 8B sample.
- **Relevant Weakness / Risk:** It has weak ToolHop correctness, high max-step rate, and repeated failed tool calls, so its verifier should not be copied as the main repair.
- **Related Winner Failure:** Guard detects schema and repeat errors but does not route recovery; final-answer canonicalization and readiness are weak.
- **Transferable Module Pattern:** Borrow only the compact verifier shape: a short non-acting readiness check after repeated failures or before final submission.
- **Generalization Rationale:** A bounded verifier can improve stop/readiness decisions across tasks without changing the acting topology.
- **Do Not Borrow:** Do not borrow Agent-KB facts or periodic reflection frequency if it increases loops and max-step failures.
- **Transfer Confidence:** Low

#### Example: `harness3`

- **Observed Structure:** Guarded low-token JoyAgent-style harness with terse planning, tool whitelist checks, repeated-call detection, early-stop guards, and MEMP memory.
- **Relevant Strength:** It is token-efficient and has low max-step rate. It is useful as a cost-control and guard-style reference.
- **Relevant Weakness / Risk:** SearchQA used_search is zero in the 8B fair_first100 slice, and EnvScaler done does not translate into high score, indicating premature or shallow completion.
- **Related Winner Failure:** Guard detects errors but lacks recovery; EnvScaler completes without full score.
- **Transferable Module Pattern:** Borrow budget discipline, concise guard observations, and repeat-call caps as constraints around the winner's stronger evidence and schema system.
- **Generalization Rationale:** Low-cost guard discipline transfers to any strict JSON tool loop, as long as it is not allowed to replace evidence acquisition.
- **Do Not Borrow:** Do not borrow early commitment or no-search behavior.
- **Transfer Confidence:** Medium

#### Example: `harness4`

- **Observed Structure:** Balanced light reflection harness with short planner, single executor, non-acting critic, final answer path, and agent workflow memory.
- **Relevant Strength:** It is the best speed-quality balance in the 8B pool, with all_available mixed primary score 0.39, reliable SearchQA search use, and reasonable ToolHop path quality. Its critic checks tool existence, argument plausibility, repeated failures, and stop readiness while keeping the executor as the only actor.
- **Relevant Weakness / Risk:** EnvScaler score still trails `harness1`, and max-step failures remain on stateful tasks. A critic alone is not a mutation ledger.
- **Related Winner Failure:** Guard blocks do not route recovery; terminal readiness is weak; evidence exists but final commitment is unsupported.
- **Transferable Module Pattern:** Borrow the non-acting critic/checkpoint pattern as an event-triggered repair and readiness audit, not as a second executor.
- **Generalization Rationale:** Schema repair, repeated failure diagnosis, and terminal readiness checks are tool-contract-level behaviors that transfer across domains.
- **Do Not Borrow:** Do not let the critic call task tools or create a heavy reflection loop.
- **Transfer Confidence:** High

#### Example: `harness5`

- **Observed Structure:** AgentOrchestra-style multi-agent harness with heavier coordination and Cerebra fusion memory.
- **Relevant Strength:** It shows that additional coordination can improve coverage in some EnvScaler cases, with fair_first100 EnvScaler score 0.4284.
- **Relevant Weakness / Risk:** It has the highest token cost, high max-step rate, and high handoff overhead. The pool explicitly recommends shrinking orchestration to one executor plus a small verifier.
- **Related Winner Failure:** Agent collaboration is not the primary Stage 1 failure; the winner needs better contracts and repair routing, not more acting agents.
- **Transferable Module Pattern:** Use as a negative control: if extra coordination is needed, keep it non-acting and bounded.
- **Generalization Rationale:** Stateful environments are vulnerable to duplicated or conflicting mutations when multiple actors can execute tools.
- **Do Not Borrow:** Do not borrow heavy orchestration, broad Cerebra memory exposure, or multiple acting roles.
- **Transfer Confidence:** Low

#### Example: `harness6`

- **Observed Structure:** Guarded small-committee harness with strict budget discipline, whitelist and max-step guards, and SkillWeaver memory.
- **Relevant Strength:** It is the cheapest seed with zero max-step rate in current runs, making it useful as an efficiency reference.
- **Relevant Weakness / Risk:** Quality is too low: EnvScaler score 0.0682, weak ToolHop correctness, and SearchQA does not use search.
- **Related Winner Failure:** Empty/no-op and budget control, but not the core evidence or mutation failures.
- **Transferable Module Pattern:** Borrow only conservative budget caps and minimal memory exposure as optional constraints.
- **Generalization Rationale:** Strict cost controls are domain-independent, but they must not suppress required evidence tools.
- **Do Not Borrow:** Do not borrow under-acting behavior, committee framing, or search suppression.
- **Transfer Confidence:** Low

#### Example: `harness7`

- **Observed Structure:** Router/debate harness for read-only tasks, with stateful fallback to one executor plus critic and dynamic cheatsheet memory.
- **Relevant Strength:** It reliably uses SearchQA search and has strong early ToolHop correctness in the fair_first100 slice. Its design explicitly separates read-only debate from stateful single-executor behavior.
- **Relevant Weakness / Risk:** EnvScaler max-step rate is high and all-available ToolHop score drops after more samples. Debate can add cost and inconsistency if used broadly.
- **Related Winner Failure:** Terminal policy confusion across benchmark families; evidence-present but wrong or incomplete final answer; broad memory retrieval.
- **Transferable Module Pattern:** Borrow route-level policy separation: read-only tasks may use additional non-mutating verification, while stateful tasks must stay single-executor. Borrow dynamic cheatsheet as compact route/procedure memory.
- **Generalization Rationale:** The distinction between read-only evidence gathering and state-changing execution is domain-agnostic and protects stateful tasks from parallel mutation risks.
- **Do Not Borrow:** Do not borrow open-ended debate or parallel acting for EnvScaler-style tasks.
- **Transfer Confidence:** Medium

#### Example: `DynamicCheatsheetProvider`, `AgentWorkflowMemoryProviderLite`, and `ExpeLProvider`

- **Observed Structure:** Memory examples rather than full harnesses. DynamicCheatsheet distills successful trajectories into short reusable cheatsheets; AgentWorkflowMemoryLite stores induced workflows with top-k retrieval; ExpeL stores success trajectories and success/failure insights, formatting failure insights as BEGIN warnings.
- **Relevant Strength:** They provide concrete memory patterns for compact procedural notes, workflow induction, and failure lessons.
- **Relevant Weakness / Risk:** Full ExpeL success trajectories and semantic dependencies can be costly. Lexical retrieval alone can still over-match shared wrapper text if task signatures are not extracted first.
- **Related Winner Failure:** Memory retrieval is broad, verbose, and not failure-aware.
- **Transferable Module Pattern:** Borrow compact workflow/failure records with metadata and phase-aware formatting; route by task signature, active tool family, and failure class.
- **Generalization Rationale:** Procedure-level and failure-class lessons transfer better than entity-specific traces or copied prior answers.
- **Do Not Borrow:** Do not add external embedding dependencies, full trajectory dumps, or long memory blocks.
- **Transfer Confidence:** Medium

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Planning | Text plan lists evidence and mutations but does not become executable state | Ordered evidence-chain and mutation decomposition with terminal criteria | `harness1`, `harness7`; mostly repair within winner pattern | Keep direct task continuity; add route-aware read-only vs stateful plan fields | Multi-hop QA and stateful workflows both require ordered goals independent of domain | Long planning transcripts from `harness1`; broad debate routing from `harness7` | High | Medium |
| Action - final commitment | Any prior evidence can unlock final answer | Slot-specific support and relevance arbitration | `harness4`, `harness7` | Non-acting critic/checkpoint verifies candidate answer, source observation, slot match, and derivation type | Retrieval and API tasks often contain distractors and adjacent records | Heavy multi-agent checking from `harness5` | High | Medium |
| Action - tool-use repair | Guard blocks bad calls but does not route recovery | Failure-type repair after schema, ID, enum, not-found, repeated-call, and empty-output errors | `harness4`, `harness3` | Event-triggered non-acting critic plus concise guard/budget discipline | Tool-contract failures recur across task families and can be repaired generically | Under-acting and no-search behavior from `harness3` | High | Medium |
| Action - orchestration | Stage 1 does not justify multiple acting agents | One executor with optional non-acting verifier | `harness4`, negative control `harness5` | Keep the executor as the only task-tool actor; critic/checkpoint only reads and audits | Avoids duplicate state mutations while adding recovery and readiness checks | AgentOrchestra-style heavy multi-agent execution from `harness5` | High | Low |
| Cross-Module Interface | Planning, action, memory, and terminal policy are loosely coupled | Runtime evidence/mutation ledger shared by Planning and Action | None; repair within winner pattern, with route separation inspired by `harness7` | Ledger fields for evidence slots, dependencies, mutation status, verification, terminal policy, and format contract | A compact interface generalizes across QA, ToolHop, and EnvScaler | Benchmark-specific state machines | High | High |
| Memory | Retrieved memories are broad, wrapper-matched, and success-only | Task-signature routing and compact failure lessons | DynamicCheatsheetProvider, AgentWorkflowMemoryLite, ExpeLProvider | Distilled workflow notes plus failure insights, capped and phase-aware | Procedure and failure-class memory transfers across domains better than entity traces | Full trajectory dumps and external embedding dependency | Medium | Medium |
| Builder/Wiring | Metadata is stale and zero-token artifacts are not exposed as harness policy | Accurate policy metadata and run hygiene flags | None; repair within winner pattern | Set harness metadata for round, ledger, repair router, terminal gate, and memory policy | Accurate metadata helps downstream generation and diagnosis without touching evaluator | Replacing benchmark loop or evaluator | Medium | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve hard schema preflight; owner module Action; it catches unknown tools, missing keys, extra keys, and repeated failed calls before they silently damage state.
- Preserve direct single-executor acting; owner module Action; Stage 1 successes and 8B pool quality references show serial continuity is valuable for multi-step tasks.
- Preserve short planning packets; owner module Planning; the winner's compact plan style is compatible with simple tasks and should become structured rather than verbose.
- Preserve one-tool-by-default stateful execution; owner module Action; it keeps state changes interpretable and reduces duplicate mutations.
- Preserve provenance language that separates observed facts, derived facts, hypotheses, and memory hints; owner module Memory / Interface; it is the conceptual basis for evidence support.
- Preserve partial-credit awareness for truly blocked stateful tasks; owner module Action; it protects EnvScaler score but must be controlled by a ledger.

#### Borrow

- Borrow from `harness4`; target module Action; exact pattern is a non-acting critic/checkpoint for tool existence, argument plausibility, repeated failures, and stop readiness; expected benefit is converting guard blocks into repair choices; it should generalize because these are schema-level and terminal-policy checks.
- Borrow from `harness1`; target module Action / Memory; exact pattern is direct execution discipline plus ExpeL-style procedural insight storage; expected benefit is stronger stateful continuity and failure lesson reuse; it should generalize by workflow rather than entity.
- Borrow from `harness7`; target module Cross-Module Interface; exact pattern is route-level separation between read-only verification and stateful single-executor execution; expected benefit is cleaner terminal policy and safer stateful tasks; it should generalize because read-only vs mutating is a tool-contract distinction.
- Borrow from `harness3`; target module Action; exact pattern is concise budget and repeated-call guard discipline; expected benefit is fewer runaway loops after repair failure; it should generalize to strict JSON tool loops.
- Borrow from DynamicCheatsheetProvider; target module Memory; exact pattern is short distilled cheatsheet records; expected benefit is less prompt bloat; it should generalize as procedural memory.
- Borrow from AgentWorkflowMemoryLite; target module Memory; exact pattern is induced workflow records with top-k retrieval; expected benefit is reusable task process guidance; it should generalize across domains with similar operation shapes.
- Borrow from ExpeLProvider; target module Memory; exact pattern is success and failure insights with BEGIN-only failure warnings; expected benefit is failure-aware memory without distracting IN-step noise; it should generalize by error class.

#### Avoid

- Avoid AgentOrchestra-style heavy multi-agent execution from `harness5`; risk is high token cost, high max-step rate, and conflicting state changes; it should not enter Stage 3 because Stage 1 does not attribute failures to lack of acting agents; risk type complexity and regression.
- Avoid broad debate from `harness7` on stateful tasks; risk is duplicate or contradictory mutations; it should not enter Stage 3 because EnvScaler needs one executor plus verification; risk type regression.
- Avoid low-cost under-acting from `harness6`; risk is suppressing necessary search and mutations; it should not enter Stage 3 because quality is too low despite cost benefits; risk type weak transfer evidence.
- Avoid binary evidence gating from the current winner; risk is wrong-span finalization; it should not enter Stage 3 unless upgraded to slot-specific support; risk type regression.
- Avoid prompt-only checklists; risk is EnvScaler `complete_task` before all mutations are done; it should not enter Stage 3 because Stage 1 requires an action-visible ledger; risk type weak transfer evidence.
- Avoid long full-trajectory memory blocks from ExpeL-style success storage; risk is prompt bloat and entity overfitting; it should not enter Stage 3 because Stage 1 found memory distraction; risk type complexity.
- Avoid task-specific patches for queen bed sizes, Big Picture Magazine, Robert Petre, Samira Patel, or any observed item; risk is benchmark overfitting; it should not enter Stage 3 because the repair must operate on schemas, observations, ledgers, and format contracts; risk type irrelevance.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Planning-to-Action Evidence and Mutation Ledger]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Multi-hop evidence-chain break after a failed intermediate lookup; premature or incomplete stateful completion without a required-mutation ledger
- **Current Weakness:** Planning emits useful text fields, but action does not maintain or enforce slot and mutation status.
- **Desired Behavior:** The new harness should maintain a compact runtime ledger with required evidence slots, dependencies, observed/derived values, source observations, required mutations, verification status, blockers, terminal policy, and answer format.
- **Borrowed Pattern:** `harness7` route separation and `harness1` direct continuity; no whole-harness copy.
- **Preserved Behavior:** Keep short planning and single-executor acting.
- **Implementation Shape:** The planner should emit compact structured fields; the action loop should update ledger entries after observations and consult them before `final_answer` or `complete_task`.
- **Generalization Rationale:** Evidence chains and stateful checklists are domain-agnostic progress structures for QA, ToolHop, API, and EnvScaler tasks.
- **Complexity:** High
- **Expected Impact:** Should reduce ToolHop broken-chain valid-wrong answers and EnvScaler done-but-not-full completions.
- **Regression Risk:** A malformed or overlarge ledger could slow direct SearchQA tasks; allow a minimal one-slot ledger for simple lookups.

**[Direction 2: Slot-Specific Final Answer Support Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Evidence-present but answer unsupported or selected from the wrong span
- **Current Weakness:** `final_answer` is allowed once any evidence observation exists, even if the candidate is not tied to the requested slot.
- **Desired Behavior:** Before committing, the action module should require a support record containing answer candidate, requested slot, source tool, source observation or field, entity match, and derivation type.
- **Borrowed Pattern:** `harness4` non-acting critic/checkpoint and the winner's existing read-only evidence gate.
- **Preserved Behavior:** Preserve direct finalization once support is sufficient.
- **Implementation Shape:** Add a bounded finalization audit that runs before `final_answer`; if the candidate fails slot support, request one more targeted evidence action or mark the slot unresolved.
- **Generalization Rationale:** Distractor evidence and adjacent records occur in search, databases, and tool observations across domains.
- **Complexity:** Medium
- **Expected Impact:** Should reduce SearchQA wrong-span and incomplete-list failures and ToolHop unsupported transformations.
- **Regression Risk:** Too strict a gate may increase no-final cases; self-contained deterministic tasks should bypass evidence-tool support requirements.

**[Direction 3: Event-Triggered Recovery Router and Non-Acting Critic]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Guard detects schema and repeat errors but does not route recovery
- **Current Weakness:** Guard observations block bad calls but leave the model to invent a recovery strategy.
- **Desired Behavior:** The action module should classify failures into unknown tool, missing/extra key, invalid ID, invalid enum, not found, unauthorized, repeated failed call, low-value repeat, empty action, and risky terminal action, then provide a specific repair mode.
- **Borrowed Pattern:** `harness4` non-acting critic/checkpoint plus `harness3` concise repeat/budget discipline.
- **Preserved Behavior:** Preserve strict schema preflight and failed-signature tracking.
- **Implementation Shape:** Use a non-acting checkpoint only after failure triggers or before terminal commitment; it should read allowed tools, recent observations, ledger status, and produce a compact `next_safe_move` without calling task tools.
- **Generalization Rationale:** Tool-contract failures recur across unseen tool schemas and can be addressed through generic repair classes.
- **Complexity:** Medium
- **Expected Impact:** Should reduce EnvScaler schema loops, ToolHop repeated failed calls, and wrong terminal fallback attempts.
- **Regression Risk:** A critic that runs too often may add cost; keep it event-triggered and short.

**[Direction 4: Stateful Terminal Readiness Gate]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Premature or incomplete stateful completion without a required-mutation ledger
- **Current Weakness:** `complete_gate` is disabled, and partial commit can fire after one successful mutation even when many requirements remain.
- **Desired Behavior:** `complete_task` should be allowed only when the active toolset includes it and the ledger marks required mutations as `verified`, `succeeded_without_verification_available`, or explicitly `blocked` under a controlled partial policy.
- **Borrowed Pattern:** `harness7` stateful single-executor route and `harness4` stop-readiness critic.
- **Preserved Behavior:** Preserve EnvScaler-compatible `complete_task({"answer": "Task Completed"})` and partial-credit awareness for real blockers.
- **Implementation Shape:** Make terminal readiness a ledger field updated after every mutation or verification observation; short-answer tasks must never attempt `complete_task`.
- **Generalization Rationale:** All state-changing workflows need complete and verified terminal semantics independent of domain entities.
- **Complexity:** Medium
- **Expected Impact:** Should improve EnvScaler full-score rate and reduce score-zero `Task Completed` trajectories.
- **Regression Risk:** Over-verification can consume steps; verify only required or uncertain mutations.

**[Direction 5: Task-Conditioned Canonicalization at Commit Time]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Final-answer canonicalization and answer-format failures
- **Current Weakness:** The current canonicalizer strips some labels but does not encode date, list, unit, alias, casing, or granularity contracts.
- **Desired Behavior:** The harness should infer a compact format contract from the task and ledger, then normalize only the final supported candidate.
- **Borrowed Pattern:** None; repair within winner pattern.
- **Preserved Behavior:** Preserve raw-answer-only final output and avoid explanations.
- **Implementation Shape:** Add low-cost canonicalization for ISO dates when tool outputs provide ISO values, single-letter casing, numeric-only answers, list completeness checks, and alias trimming when the task asks for a narrower span.
- **Generalization Rationale:** Exact-match tasks across QA and ToolHop often fail at presentation after the evidence path is correct.
- **Complexity:** Low
- **Expected Impact:** Should recover near-miss cases such as correct date observations submitted in natural-language format.
- **Regression Risk:** Over-normalization could remove required units, aliases, leading zeros, or qualifiers.

**[Direction 6: Compact Task-Signature Memory with Failure Lessons]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Memory retrieval is broad, verbose, and not failure-aware
- **Current Weakness:** Memory retrieval is dominated by shared benchmark wrapper text and stores successful workflows only.
- **Desired Behavior:** Memory should retrieve a few short phase-aware notes by task signature, active tool family, operation type, and failure class, and should store compact success workflows plus failure lessons.
- **Borrowed Pattern:** DynamicCheatsheetProvider short cheatsheets, AgentWorkflowMemoryLite induced workflows, and ExpeLProvider failure insights.
- **Preserved Behavior:** Preserve provenance reminders that memory hints are not current evidence.
- **Implementation Shape:** Strip benchmark boilerplate before scoring, tag records as `procedure_hint`, `workflow`, or `failure_lesson`, cap retrieved text, and expose failure warnings mainly at BEGIN or after matching failures.
- **Generalization Rationale:** Procedure and failure-class memories transfer across unseen tasks without memorizing entities or answers.
- **Complexity:** Medium
- **Expected Impact:** Should reduce distracting memory and improve recovery for recurring schema, relation, ID-resolution, and terminal-readiness failures.
- **Regression Risk:** Over-filtering can remove useful generic guidance; keep one default compact provenance reminder.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The next harness should be a planning-guided, single-executor ReAct harness with a small evidence/mutation ledger and event-triggered non-acting audit. It should feel like the current winner's direct and compact tool user, but with stricter commitment discipline: final answers require slot-specific support, stateful completion requires ledger readiness, guard blocks produce bounded repair modes, and memory stays short, procedural, and failure-aware. It should not become a heavy multi-agent system.

#### 6.2 Module-Level Blueprint

Planning Blueprint

- Implement compact structured planning with fields for `task_type`, `route`, `required_evidence`, `evidence_dependencies`, `required_mutations`, `verification_targets`, `answer_format`, `terminal_policy`, and `next_tool_intent`.
- Preserve short plans, direct task framing, and no final-answer commitment during planning.
- Avoid verbose essays, hidden chain transcripts, and task-specific entity patches.
- Motivation comes from Stage 1 evidence that text plans were not action-visible enough for ToolHop chains or EnvScaler checklists.
- The design is task-general because evidence slots, mutation requirements, and verification targets exist across domains.

Action Blueprint, including concrete agent collaboration / orchestration if applicable

- Keep one mutating executor as the only actor that calls task tools.
- Add an event-triggered non-acting critic/checkpoint that reads allowed tools, recent failures, ledger status, and terminal readiness, then emits a compact repair or commit recommendation.
- Implement a support gate for `final_answer` that requires candidate, slot, source observation, entity match, and derivation type.
- Implement a failure recovery router for schema mismatch, unknown tool, missing or extra keys, invalid ID/name confusion, invalid enum, not found, unauthorized, repeated failed call, low-value repeat, empty action, and risky terminal action.
- Implement stateful terminal readiness using the ledger, while preserving partial completion only for explicitly blocked remaining requirements.
- Implement low-cost answer canonicalization after support is verified.
- Preserve schema preflight, repeat blocking, one-tool-by-default stateful execution, and direct final answers for simple supported cases.
- Avoid parallel stateful acting, always-on critic loops, and broad debate.
- Motivation comes from wrong-span SearchQA, repeated guard loops, premature EnvScaler completion, and format near misses.
- The design is task-general because it operates on tool schemas, observations, ledger status, and terminal contracts.

Memory Blueprint

- Keep the default provenance reminder compact: observations are evidence, derived facts must name sources, plans and memories are hypotheses.
- Strip repeated benchmark wrapper text before memory scoring.
- Retrieve by task signature, active tool names, operation type, and failure class rather than raw lexical overlap alone.
- Store short success workflows and short failure lessons; cap retrieved memory to a small number of actionable notes.
- Preserve lightweight memory behavior and avoid long trajectory dumps.
- Motivation comes from Stage 1 unrelated memory retrieval in SearchQA and ToolHop.
- The design is task-general because workflow and failure-class memory applies across domains without storing answers.

Builder / Wiring Blueprint

- Keep factory-compatible exports and file layout.
- Set metadata to the active round and expose harness policy fields for ledger, support gate, recovery router, terminal gate, canonicalizer, and memory routing.
- Preserve existing tool binding behavior.
- Avoid changing the dataset, evaluator, benchmark loop, or external services.
- Motivation comes from Stage 1 metadata carryover and zero-token artifact separation.
- The design is task-general because policy metadata improves diagnosis without affecting task content.

Interface Blueprint

- Define a simple Planning -> Action ledger contract and keep it compact enough to fit in memory.
- Allow Action observations to update ledger status after each step.
- Let Memory provide only procedural hints and failure lessons; memory must not fill evidence slots unless the same fact is observed in the current task.
- Share terminal policy across Planning and Action: read-only tasks use `final_answer`; stateful tasks use `complete_task` only if available and ledger-ready.
- Avoid large orchestration layers or benchmark-specific state machines.
- Motivation comes from Stage 1 cross-module attribution for ToolHop and EnvScaler failures.
- The design is task-general because it represents progress state rather than domain facts.

#### 6.3 Minimal Required Changes

- Add a compact evidence/mutation ledger shared from Planning to Action and updated after observations.
- Add slot-specific final-answer support checks that go beyond binary evidence existence.
- Add an event-triggered non-acting recovery critic/checkpoint for guard blocks and terminal readiness.
- Add a stateful terminal gate based on the mutation ledger and active toolset.
- Add task-conditioned final canonicalization for dates, numbers, single letters, lists, and aliases after support is verified.
- Add memory routing by task signature and compact failure lessons while preserving provenance reminders.
- Update builder metadata to reflect the active harness policy and round.

#### 6.4 Optional Enhancements

- Add a bounded read-only debate or second-source check only for read-only retrieval tasks with conflicting evidence, never for stateful mutation tasks.
- Add a no-op or zero-token run marker in harness metadata if the local factory exposes such signals.
- Add a small observation compressor for long search results that preserves document titles, candidate spans, and slot relevance.
- Add a limited "one more targeted evidence action" rule when final support fails but budget remains.
- Add a route-specific memory cap so stateful tasks receive mutation/verification lessons while QA tasks receive evidence-selection lessons.

### PART 7: STAGE 3 CONSTRAINTS

- `[Planning]` Generate compact structured fields for route, evidence slots, dependencies, mutation checklist, verification targets, terminal policy, and answer format.
- `[Planning]` Keep plans short and do not emit final answers as facts during planning.
- `[Action]` Keep one executor as the only component that calls task tools.
- `[Action]` Add a non-acting critic/checkpoint only as an event-triggered audit after guard blocks, repeated failures, empty actions, or before risky terminal commitment.
- `[Action]` Require slot-specific support before `final_answer`; any candidate must name its source observation and derivation type.
- `[Action]` Keep schema preflight and repeated-call blocking, but map each guard reason to a concrete repair mode.
- `[Action]` Use the mutation ledger for `complete_task` readiness; do not call completion simply because one mutation succeeded.
- `[Action]` Never use `complete_task` for short-answer tasks when the active toolset does not include it.
- `[Action]` Canonicalize final answers only after support is established, and preserve units, aliases, casing, or leading zeros when requested.
- `[Memory]` Strip benchmark wrapper text before retrieval scoring where practical.
- `[Memory]` Retrieve compact workflow and failure-lesson notes by task signature, active tool family, and failure class.
- `[Memory]` Preserve the rule that memory hints are hypotheses until current-task observations support them.
- `[Builder]` Preserve harness factory compatibility and update metadata for the active round and policy features.
- `[Interface]` Planning outputs must be action-visible as a compact ledger, not only prose in memory.
- `[Interface]` Action observations must update ledger status and terminal readiness.
- `[Interface]` Terminal policy must distinguish read-only `final_answer` tasks from stateful `complete_task` tasks.
- `[Preserve]` Preserve direct single-executor ReAct, hard schema checks, one-tool-by-default stateful execution, compact planning, and provenance language.
- `[Avoid]` Do not copy whole peer harnesses or add heavy AgentOrchestra-style multi-agent execution.
- `[Avoid]` Do not add benchmark item IDs, entity names, expected answers, or observed trajectory-specific patches.
- `[Avoid]` Do not treat zero-token, zero-API runs as proof of a planning or reasoning defect; keep them classified as run/evaluation artifacts.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
