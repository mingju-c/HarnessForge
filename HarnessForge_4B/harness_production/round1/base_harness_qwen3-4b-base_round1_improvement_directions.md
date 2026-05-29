### PART 1: LOCALIZATION SUMMARY

The current winner is `base_harness`, with the architecture `generic_planning + single_react + lightweight_memory`. Its useful foundation is a simple single-executor ReAct path that remains compatible with the harness factory and can solve simple SearchQA/ToolHop tasks with one or two tool calls. Stage 1 shows, however, that it lacks executable evidence boundaries, schema-repair state, long-task completion ledgers, and memory provenance. The dominant failures are: many SearchQA/ToolHop cases call `final_answer` without any non-terminal evidence-tool observation; EnvScaler cases repeat failed calls, use unknown tools or wrong arguments, omit terminal actions or call `complete_task` too early; and short-answer canonicalization is weak. In module attribution, the highest priority is the Cross-Module Interface: a Planning -> Action evidence contract and an EnvScaler checklist/ledger. Next are Action-side schema preflight, repetition guards, output-contract recovery, and final canonicalization. Memory needs lightweight provenance-aware guidance. Stage 3 should preserve single-executor efficiency and existing builder compatibility, borrow targeted guards, a non-acting critic, a read-only evidence gate, and compact procedural memory from peer harnesses, and avoid copying heavy multi-agent structures.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness1`

- **Observed Structure:** `flash_searcher` planning, `single_react` action, `expel` memory, direct single-executor topology.
- **Relevant Strength:** In the pool, fair_first100 mixed score is 0.5049, EnvScaler score is 0.5066, and SearchQA used_search is 0.9286. This shows that a direct single executor plus compact search-oriented planning remains a high-quality reference for the current 4B model.
- **Relevant Weakness / Risk:** Average tokens are 198970.6 and average elapsed time is 109.87s; failures can accumulate long context. Do not move full ExpeL successful trajectories or long reflection wholesale into the winner.
- **Related Winner Failure:** The winner's `single_react` should preserve direct execution strengths while fixing zero-evidence finalization and repeated failure accumulation.
- **Transferable Module Pattern:** Borrow the `flash_searcher` style of short search targets plus single-chain execution, and the ExpeL idea of soft procedural hints; do not add acting roles.
- **Generalization Rationale:** Short targets, single-chain execution, and soft memory hints are domain-agnostic execution discipline for retrieval, multi-hop, and tool tasks.
- **Do Not Borrow:** Do not borrow high-token exposure of full successful trajectories or unbounded long-context accumulation.
- **Transfer Confidence:** High

#### Example: `harness2`

- **Observed Structure:** concise reflection planning/action, single executor, periodic compact reflection, final verifier, `agent_kb` memory.
- **Relevant Strength:** SearchQA used_search is 1.0 and small-sample subEM is 0.625, suggesting that fixed-interval short reflection can help retrieval routing.
- **Relevant Weakness / Risk:** Mixed score is 0.3251, ToolHop correctness is 0.1111, and EnvScaler maxstep_rate is 0.26. Reflection by itself does not solve repeated failures or exact-answer problems.
- **Related Winner Failure:** The compact reflection format is useful for action-side readiness checks, but ordinary natural-language reflection should not be trusted to solve schema or ledger failures.
- **Transferable Module Pattern:** Borrow the format of a short checkpoint that only answers progress, latest error, and next step, and use it for Action repair summaries.
- **Generalization Rationale:** Fixed short checkpoints help small models regain direction on long tasks without introducing multi-agent cost.
- **Do Not Borrow:** Do not borrow the weak ToolHop verifier or the full `agent_kb` design that may amplify bad memory.
- **Transfer Confidence:** Medium

#### Example: `harness3`

- **Observed Structure:** guarded JoyAgent-style augmented ReAct, guarded worker tools, low-token execution, MEMP memory.
- **Relevant Strength:** Average tokens are 20236.0, maxstep_rate is 0.02, and ToolHop correctness is 0.5455. Guarded execution is effective for cost and repetition control.
- **Relevant Weakness / Risk:** SearchQA used_search is 0.0, EnvScaler done is high but score is low, and early-stop guards may cause shallow completion or premature terminal actions.
- **Related Winner Failure:** The winner needs schema whitelisting, repeated-call blocking, and budget guards, but should not copy this harness's early-stop tendency.
- **Transferable Module Pattern:** Borrow Action-side `guard_task_tools` behavior: schema-key checking, failed-call signature tracking, and real-tool budget control.
- **Generalization Rationale:** Tool-name and argument validation plus repeated-failure blocking apply to all schema-rich tool environments.
- **Do Not Borrow:** Do not borrow the small ensemble workers or routing/early-commit behavior that causes SearchQA to avoid search.
- **Transfer Confidence:** High for guards, Low for topology

#### Example: `harness4`

- **Observed Structure:** `reflection_critic` planning/action, single executor plus non-environment critic, `agent_workflow_memory`.
- **Relevant Strength:** The pool marks it as the best balanced seed; SearchQA used_search is 1.0, all_available mixed score is 0.39, and average elapsed time is 47.93s. Its critic does not operate the environment; it only checks tool existence, argument plausibility, repeated failures, and stop readiness.
- **Relevant Weakness / Risk:** EnvScaler score still trails `harness1`, and some max-step failures remain. The critic is advisory; without hard gates it may still be ignored.
- **Related Winner Failure:** It directly addresses schema repair, repetition guards, terminal readiness, and no-op recovery.
- **Transferable Module Pattern:** Borrow the lightweight topology of "single executor + non-acting critic + guarded tools"; the critic only reads recent trajectory and allowed tools.
- **Generalization Rationale:** A non-acting critic is suitable for stateful tasks because it does not mutate the environment in parallel and can still provide tool and termination checks.
- **Do Not Borrow:** Do not borrow long critic transcripts, and do not turn the critic into a second acting agent.
- **Transfer Confidence:** High

#### Example: `harness5`

- **Observed Structure:** AgentOrchestra-style heavy orchestration, multi-role execution/checking, Cerebra fusion memory.
- **Relevant Strength:** SearchQA used_search is 1.0 and EnvScaler score is 0.4284, showing that broader coverage can sometimes improve partial state-task performance.
- **Relevant Weakness / Risk:** Average tokens are 292135.6, API calls are 26.26, and maxstep_rate is 0.35, making it one of the highest-cost and highest-max-step risks in the current pool. It is too heavy for `qwen3-4b-base`.
- **Related Winner Failure:** The winner does need verifier/repairer behavior, but Stage 1 does not justify heavy multi-agent parallelism.
- **Transferable Module Pattern:** Use it only as a negative example: a verifier is useful, but it should be compressed into a `harness4`-style non-acting critic.
- **Generalization Rationale:** For small models and stateful environments, reducing acting handoffs is more robust than adding roles.
- **Do Not Borrow:** Do not borrow multi-actor orchestration, high-frequency Cerebra fusion memory exposure, or high-cost handoffs.
- **Transfer Confidence:** Low as positive example, High as negative control

#### Example: `harness6`

- **Observed Structure:** guarded small committee, strict budget discipline, SkillWeaver memory.
- **Relevant Strength:** Average tokens are 13369.6 and maxstep_rate is 0.0, making it a low-cost guard baseline.
- **Relevant Weakness / Risk:** Mixed score is 0.1684, EnvScaler score is 0.0682, and SearchQA used_search is 0.0. The budget discipline is too strong and can under-act.
- **Related Winner Failure:** It can help the winner reduce repetition and wasted steps, but must not sacrifice evidence acquisition or EnvScaler state completion.
- **Transferable Module Pattern:** Borrow the "small but hard" idea of budget limits and max-step discipline; do not borrow the committee.
- **Generalization Rationale:** All tool tasks need protection against endless exploration, but budget control must work together with evidence gates and checklist readiness.
- **Do Not Borrow:** Do not borrow the low-quality main architecture or early-stop strategy that prevents search and state completion.
- **Transfer Confidence:** Medium for budget guard, Low for architecture

#### Example: `harness7`

- **Observed Structure:** router/debate for read-only tasks; stateful tasks fallback to single executor plus critic; dynamic cheatsheet memory.
- **Relevant Strength:** SearchQA used_search is 1.0 and ToolHop correctness is 0.5. Its implementation includes a read-only evidence gate requiring a solver to complete at least one evidence-tool observation before finalization, and it reports an evidence digest/reconciled report.
- **Relevant Weakness / Risk:** EnvScaler max-step rate is 0.26 and all_available ToolHop drops. Debate has cost and conflict risks on stateful tasks.
- **Related Winner Failure:** It directly addresses zero-evidence finalization and also indicates that stateful tasks should avoid parallel acting.
- **Transferable Module Pattern:** Borrow the read-only evidence gate and evidence digest/reconciliation; enable them only for read-only tool schemas, while keeping stateful routes single-executor.
- **Generalization Rationale:** "If non-terminal evidence tools exist, observe before finalizing" is a general constraint across QA, retrieval, and read-only database tasks.
- **Do Not Borrow:** Do not borrow the full debate/judge topology, and do not enable parallel solvers on EnvScaler/API mutation tasks.
- **Transfer Confidence:** High for evidence gate, Medium for routing

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Cross-Module Interface | Plan/memory guesses treated as evidence | Planning-to-Action evidence provenance and final-answer gate | `harness7` | Read-only evidence gate requiring at least one evidence-tool observation before finalization | Any evidence-dependent task needs source-aware commitment | Full debate topology on stateful tasks | High | Medium |
| Planning | EnvScaler and long tasks lack subgoal tracking | Structured checklist and terminal criteria | None; repair within winner pattern | Add compact checklist fields: required facts, required state mutations, terminal criteria | Checklist decomposition is task-general and keeps single-executor continuity | Heavy AgentOrchestra decomposition from `harness5` | High | Medium |
| Action | Wrong tool names/args and repeated failures | Schema preflight, failed-call signature guard, bounded repair loop | `harness3`, `harness4` | Guarded tool wrapper plus non-acting critic audit of allowed tools and arguments | Tool schema contracts recur across EnvScaler, ToolHop, and API tasks | Early-stop behavior that prevents SearchQA retrieval in `harness3/6` | High | Medium |
| Action | EnvScaler calls `complete_task` too early or not at all | Mutation ledger and terminal readiness check | `harness4` | Non-environment critic for stop readiness, adapted into hard checklist gate | State mutation tasks require verified completion before terminal action | Advisory-only critic with no hard gate | High | Medium |
| Action | Correct evidence but wrong final string | Commit-time canonicalization | None; repair within winner pattern | Final answer transform: requested span, units, leading zeros, alias length, no explanation | Exact-match answers across domains need final normalization | Over-normalizing values that preserve meaningful formatting | Medium | Low |
| Action | Empty/no-op action steps are not repaired | Output contract recovery for strict JSON agent loops | `harness4` guard discipline, winner prompt contract | Retry once with compact JSON schema reminder; if still empty, force one valid evidence/action step or safe terminal refusal | Small local models often need output-format repair independent of domain | Multi-agent retry storms from `harness5` | High | Low |
| Memory | Memory stores unverified guesses as facts | Provenance-aware, phase-aware compact procedural memory | ExpeL provider, AgentWorkflowMemory, DynamicCheatsheet provider | Store/retrieve compact procedural hints with metadata; label observed facts vs hypotheses | Memory should guide procedure without overriding live observations | Rich fusion memory from `harness5`, stale hard constraints | Medium | Medium |
| Builder/Wiring | Must remain harness factory compatible | Metadata and provider wiring should expose policy without breaking factory | `harness4` | Set lightweight `harness_policy` metadata for guards, critic, evidence gate | Helps evaluation/debugging while preserving local factory contract | Replacing benchmark loop or external services | High | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve direct single-executor ReAct for most real tool calls; owner module Action; it keeps simple QA and ToolHop efficient and avoids state conflicts.
- Preserve short initial planning; owner module Planning; it helps qwen3-4b-base avoid bloated reasoning and worked in successful examples such as one-search SearchQA and simple ToolHop chains.
- Preserve one-tool-by-default discipline; owner module Action; it reduces accidental state mutation coupling and keeps observations interpretable.
- Preserve EnvScaler terminal contract `complete_task({"answer": "Task Completed"})`; owner module Action/Builder; evaluator compatibility depends on it.
- Preserve lightweight memory footprint; owner module Memory; the current model is sensitive to prompt bloat and Stage 1 did not justify heavy memory exposure.
- Preserve harness factory file layout and provider names; owner module Builder/Wiring; Stage 3 must remain loadable without changing the evaluation loop.

#### Borrow

- Borrow from `harness7`; target module Cross-Module Interface; exact pattern read-only evidence gate before `final_answer`; expected benefit fewer zero-evidence SearchQA/ToolHop finals; it generalizes whenever non-final evidence tools exist.
- Borrow from `harness4`; target module Action; exact pattern non-acting critic that audits valid tools, arguments, repeated failures, and stop readiness; expected benefit safer repair without parallel state mutation; it generalizes to schema-rich and stateful tasks.
- Borrow from `harness3`; target module Action; exact pattern guarded tool wrapper with schema-key blocking and failed-call signature memory; expected benefit fewer repeated invalid calls; it generalizes across all tool schemas.
- Borrow from `harness1`; target module Planning/Action; exact pattern direct search-oriented single-chain execution; expected benefit maintain quality without heavy orchestration; it generalizes to multi-hop tasks that need continuity.
- Borrow from ExpeL/AgentWorkflowMemory examples; target module Memory; exact pattern compact procedural insights with metadata and retrieval scoring; expected benefit memory remains useful without storing unverified facts; it generalizes as procedure rather than answer memory.
- Borrow from DynamicCheatsheet; target module Memory/Interface; exact pattern under-200-word phase-aware cheatsheet; expected benefit concise routing and caution reminders; it generalizes if kept domain-agnostic.

#### Avoid

- Avoid copying `harness5` full AgentOrchestra; risk high token cost and handoff loops; it should not enter Stage 3 because Stage 1 calls for targeted evidence/schema/ledger repair, not heavy orchestration; risk type complexity/regression.
- Avoid copying `harness3` or `harness6` early-stop behavior wholesale; risk SearchQA no-search and shallow EnvScaler completion; it should not enter Stage 3 without evidence gates and checklist readiness; risk type regression.
- Avoid exposing full successful trajectories from ExpeL-style memory; risk prompt bloat and stale procedure over current observation; it should not enter Stage 3 because winner needs compact provenance, not more context; risk type complexity.
- Avoid debate or parallel acting on EnvScaler/stateful schemas; risk conflicting mutations and duplicated writes; it should not enter Stage 3 because stateful routes need one executor; risk type regression.
- Avoid benchmark-specific patches for `INC100x`, binary leading-zero cases, specific people, or task IDs; risk overfitting; it should not enter Stage 3 because directions must transfer; risk type weak transfer evidence.
- Avoid making critic purely advisory when it guards terminal actions; risk model ignores critic; Stage 3 should turn evidence and checklist constraints into hard gates where feasible; risk type weak transfer evidence.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Evidence-Gated Read-Only Finalization]**

- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Unobserved plan/memory content treated as sufficient evidence
- **Current Weakness:** Plan, memory, and model prior are free text, so action can submit them as if they were observations.
- **Desired Behavior:** For read-only QA/ToolHop/search-like schemas, `final_answer` is blocked until at least one relevant non-final evidence tool has returned an observation, unless the task is explicitly self-contained.
- **Borrowed Pattern:** `harness7` read-only evidence gate and evidence digest, adapted without full debate.
- **Preserved Behavior:** Keep winner's direct single-executor path after the evidence requirement is satisfied.
- **Implementation Shape:** Add a simple evidence provenance flag visible to action: `no_evidence_yet`, `observed_evidence_available`, `computed_from_observation`; finalization prompt and action wrapper must reject `plan_guess` and `memory_hint` as sufficient evidence.
- **Generalization Rationale:** External facts, database facts, and multi-hop retrieval all need observation-grounded commitment.
- **Complexity:** Medium
- **Expected Impact:** Directly targets 132 wrong zero-evidence SearchQA finals and 31 wrong zero-evidence ToolHop finals.
- **Regression Risk:** May cause over-search on simple deterministic transformations; include a narrow self-contained exception when no non-final evidence tools are available or task is pure string/math over given input.

**[Direction 2: Guarded Tool Schema Preflight and Repair]**

- **Target Module:** Action
- **Stage 1 Failure Addressed:** Tool schema and tool-name repair is prompt-only
- **Current Weakness:** The action loop relies on prompt instructions to choose valid tools and arguments.
- **Desired Behavior:** Tool calls are validated before execution; unknown tools, extra keys, and repeated known-failed signatures produce a repair observation instead of wasting real tool calls.
- **Borrowed Pattern:** `harness3` guarded tools and `harness4` critic audit of allowed tools/argument plausibility.
- **Preserved Behavior:** Keep one tool call by default and do not add acting subagents.
- **Implementation Shape:** Wrap task tools with a guard that checks tool name and schema keys, records failed call signatures, exposes allowed keys in the observation, and asks the same executor to choose a repaired valid call.
- **Generalization Rationale:** Tool schemas differ by benchmark, but the validity contract is universal.
- **Complexity:** Medium
- **Expected Impact:** Should reduce EnvScaler `Unknown tool`/`unexpected keyword` failures and ToolHop missing-required loops.
- **Regression Risk:** Guard can block useful idempotent retries; allow retry only when new observation changes preconditions.

**[Direction 3: Stateful Checklist and Mutation Ledger]**

- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** EnvScaler long-horizon tasks lack explicit completion ledger
- **Current Weakness:** Planning produces free-text intent, while Action does not know which state changes remain incomplete.
- **Desired Behavior:** Planning emits a compact checklist of required mutations and terminal conditions; Action updates a ledger after every observation and can call `complete_task` only when all required items are verified.
- **Borrowed Pattern:** `harness4` non-acting critic for stop readiness, plus winner's direct executor; no full peer harness copy.
- **Preserved Behavior:** Keep EnvScaler as single executor and preserve `complete_task` terminal contract.
- **Implementation Shape:** Add checklist fields such as `required_mutations`, `verification_queries`, `terminal_ready=false`; action summaries must mark items `pending/succeeded/failed/blocked` with observation snippets.
- **Generalization Rationale:** Any state-changing environment needs durable progress tracking independent of domain names.
- **Complexity:** Medium
- **Expected Impact:** Should improve EnvScaler full-score rate, reduce 198 no-terminal cases, and reduce terminal-score-zero cases.
- **Regression Risk:** A bad checklist can omit implicit constraints; prompts should say checklist is minimum required state, not a license to ignore fresh observations.

**[Direction 4: Non-Acting Repair Critic With Hard Stop Signals]**

- **Target Module:** Action
- **Stage 1 Failure Addressed:** Low-value repeated exploration after failed or sufficient observations
- **Current Weakness:** Summaries are natural-language suggestions and do not prevent repeated invalid calls or endless verification.
- **Desired Behavior:** A non-environment critic or internal repair checkpoint audits recent trajectory for repeated failures, sufficient evidence, and terminal readiness, then returns a concise `next_safe_move`.
- **Borrowed Pattern:** `harness4` ReflectionCriticTool.
- **Preserved Behavior:** Only the main executor can operate task tools; critic never mutates state.
- **Implementation Shape:** Invoke critic after a failed call, after two similar calls, before terminal actions, and near budget limits; convert clear critic outcomes into guard observations or hard blocks.
- **Generalization Rationale:** Repetition and premature/late stopping are structural control problems across task families.
- **Complexity:** Medium
- **Expected Impact:** Targets 423 EnvScaler consecutive-repeat tasks and 68 ToolHop consecutive-repeat tasks.
- **Regression Risk:** Too frequent critic calls increase cost; use event-triggered critic rather than fixed every-step reflection.

**[Direction 5: Commit-Time Answer Canonicalization]**

- **Target Module:** Action
- **Stage 1 Failure Addressed:** Final-answer canonicalization is under-specified
- **Current Weakness:** The final answer path returns observed or computed strings without a final task-format check.
- **Desired Behavior:** Before `final_answer`, action performs a compact format pass: requested span only, no explanation, units/aliases as requested, leading zeros only if task requires fixed width.
- **Borrowed Pattern:** None
- **Preserved Behavior:** Keep final answer concise and task-specific.
- **Implementation Shape:** Add a final-answer checklist in the final prompt and optionally a small helper note derived from task wording: `answer_type`, `granularity`, `format_constraints`, `source_observation`.
- **Generalization Rationale:** Exact-match output constraints recur in QA, computation, database extraction, and API argument tasks.
- **Complexity:** Low
- **Expected Impact:** Should recover part of SearchQA 17 and ToolHop 3 wrong-but-subEM-positive cases.
- **Regression Risk:** Over-normalization could remove meaningful leading zeros, prefixes, or units; canonicalization must be task-conditioned.

**[Direction 6: Provenance-Aware Compact Memory]**

- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Memory guidance lacks provenance and phase-aware caution
- **Current Weakness:** Short-term memory can store model thoughts as key facts, and begin guidance can over-emphasize direct execution.
- **Desired Behavior:** Memory should provide compact procedural reminders and only label tool observations as facts; plan/model statements should be labeled hypotheses.
- **Borrowed Pattern:** ExpeL insight formatting, AgentWorkflowMemory workflow induction, DynamicCheatsheet under-200-word concise guidance.
- **Preserved Behavior:** Keep memory lightweight and sparse.
- **Implementation Shape:** Add provenance tags in memory item content or metadata: `observed_fact`, `derived_from_observation`, `hypothesis`, `procedure_hint`; for evidence-required tasks, begin guidance should say “act directly, but obtain supporting observation before final answer.”
- **Generalization Rationale:** Memory is useful when it transfers procedure, not when it transfers unsupported answers.
- **Complexity:** Medium
- **Expected Impact:** Should reduce hallucination reinforcement and improve recovery when plan/action guesses are wrong.
- **Regression Risk:** Excessive filtering may suppress useful derived facts; allow derived facts only when their source observation is named.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The next harness should be a direct but verification-aware single-executor harness: keep the base harness's compact ReAct style, but add lightweight hard guards around evidence, schemas, repetition, and terminal readiness. It should feel closer to `single_react + critic/guards` than to a multi-agent orchestra: one agent acts, optional critic/checkpoints only read, memory gives compact procedural cautions, and interfaces carry just enough structured state to prevent premature finalization or incomplete state changes.

#### 6.2 Module-Level Blueprint

Planning Blueprint

- Implement compact structured planning output with fields for `task_type`, `required_evidence`, `required_mutations`, `answer_format`, and `terminal_criteria`.
- Preserve the current short planning style and avoid verbose multi-role decomposition.
- Avoid putting candidate final answers into the plan unless they are explicitly marked as `hypothesis`.
- Motivating evidence is the zero-evidence finalization in `460.json`/`1116.json` and EnvScaler incomplete tasks.
- The design is task-general because evidence, mutations, and answer format are abstract execution categories.

Action Blueprint

- Implement guarded tool execution with schema-key preflight, failed-call signature memory, and budget-aware repetition blocking.
- Add event-triggered non-acting critic checks after invalid calls, repeated calls, near-budget conditions, and before terminal actions.
- Add read-only evidence gate for schemas with non-terminal evidence tools: no evidence observation means no `final_answer`.
- Add EnvScaler/stateful terminal readiness gate that checks planning checklist and action ledger before `complete_task`.
- Add final canonicalization checklist at commit time.
- Preserve one-tool-by-default direct execution and do not create acting worker pools.
- Avoid debate/parallel acting for stateful tools and avoid critic calls on every step.
- Motivating evidence includes 172 EnvScaler unknown-tool files, 423 EnvScaler consecutive-repeat tasks, 198 no-terminal EnvScaler cases, and wrong-but-subEM-positive short answers.
- The design is task-general because it validates contracts and commitment criteria, not benchmark entities.

Memory Blueprint

- Implement provenance-aware formatting for short-term memory: observed facts, derived facts, hypotheses, and procedure hints should be visibly separated.
- Provide phase-aware BEGIN guidance that is concise and does not encourage unsupported finalization.
- Borrow only compact procedural insight patterns from ExpeL/AgentWorkflowMemory/DynamicCheatsheet.
- Preserve lightweight storage and sparse retrieval.
- Avoid full trajectory dumps, rich fusion memory, or hard constraints that override current observations.
- Motivating evidence is `460.json`, where unsupported false content became memory “Key Information & Constraints”.
- The design is task-general because source provenance protects any domain.

Builder / Wiring Blueprint

- Keep factory-compatible files and provider exports.
- Add metadata such as `harness_policy` describing evidence gate, schema guard, critic, checklist ledger, and memory provenance.
- Preserve `HARNESS_NAME`, action/planning/memory constants semantics for registry compatibility, though new names may describe the improved modules.
- Avoid changing benchmark loop, dataset, evaluator, or external services.
- Motivating evidence is that Stage 1 found no builder mismatch, only missing behavior behind compatible wiring.
- The design is task-general because metadata and wiring do not assume any task domain.

Interface Blueprint

- Pass planning checklist and evidence requirements to action as short structured text or agent attributes, not only prose.
- Let action observations update a ledger visible to summaries and terminal checks.
- Let memory provide provenance labels that planning/action can respect.
- Preserve loose coupling: the executor still reasons with text, but gates read compact structured markers.
- Avoid complex shared state machines that require evaluator changes.
- Motivating evidence is that failures arise at Planning -> Action and Memory -> Action boundaries.
- The design is task-general because the interface categories apply to read-only, multi-hop, and stateful tasks.

#### 6.3 Minimal Required Changes

- Add a read-only evidence gate that blocks `final_answer` before at least one non-terminal evidence observation when evidence tools exist.
- Add action-side schema-key preflight and repeated-failed-call blocking around task tools.
- Add a compact planning checklist for stateful tasks and an action mutation ledger updated from observations.
- Add a terminal readiness check before `complete_task`.
- Add commit-time answer canonicalization instructions tied to task wording.
- Add provenance labels to memory guidance so unsupported thoughts are not presented as facts.
- Preserve single-executor state mutation and builder compatibility.

#### 6.4 Optional Enhancements

- Add event-triggered non-acting critic only after invalid/repeated calls and before terminal actions.
- Add a compact evidence digest for read-only tasks to help final answer grounding.
- Add a low-cost budget guard that warns near max steps without forcing premature completion.
- Add workflow-memory induction for successful trajectories if it remains under a short word limit.
- Add route detection for read-only vs stateful schemas, but keep stateful execution single-agent.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Generate compact structured plans with evidence requirements, mutation checklist, answer format, and terminal criteria.
- [Planning] Mark any candidate answer from prior knowledge, memory, or plan as hypothesis until supported by observation.
- [Planning] Keep planning short and avoid multi-role orchestration unless the task is read-only and the action module explicitly routes it.
- [Action] Use one primary executor for all state-changing tools.
- [Action] Validate tool names and argument keys before real execution; invalid calls must return repair guidance instead of touching the environment.
- [Action] Block repeated identical failed calls unless new observation changes the precondition.
- [Action] For read-only evidence tasks, block `final_answer` until a non-final evidence tool has produced an observation.
- [Action] Before `complete_task`, verify the stateful checklist ledger shows every required mutation as succeeded or explicitly impossible with evidence.
- [Action] Add final-answer canonicalization based on task wording and observed value, not benchmark-specific examples.
- [Action] Use non-acting critic/checkpoint only for invalid calls, repeated calls, near-budget review, and terminal readiness.
- [Memory] Separate observed facts, derived facts, hypotheses, and procedure hints in memory output.
- [Memory] Keep guidance compact and phase-aware; do not expose full successful trajectories.
- [Builder] Preserve harness factory layout, provider exports, and benchmark-loop compatibility.
- [Interface] Pass evidence/checklist/provenance information in a compact structured form that action can inspect.
- [Preserve] Preserve direct ReAct efficiency for simple one-search or short ToolHop tasks.
- [Preserve] Preserve `complete_task` and `final_answer` terminal tool contracts.
- [Avoid] Do not copy AgentOrchestra-style heavy multi-agent execution from `harness5`.
- [Avoid] Do not enable debate or parallel acting on EnvScaler/stateful tasks.
- [Avoid] Do not hard-code task IDs, entity names, incident IDs, binary examples, or golden answers.
- [Avoid] Do not make budget guards so aggressive that SearchQA stops before using search or EnvScaler stops before required mutations.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
