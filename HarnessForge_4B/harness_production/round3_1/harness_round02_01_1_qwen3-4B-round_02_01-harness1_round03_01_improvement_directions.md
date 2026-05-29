### PART 1: LOCALIZATION SUMMARY

The current winner under analysis is `harness_round02_01_1`, a balanced single-executor ReAct harness with compact ledger-oriented planning, hard schema preflight, repeated-call cooldown, support-record finalization, progress-based partial completion, and task-signature memory. The Stage 1 report attributes the dominant failures to module-level gaps rather than benchmark artifacts. The highest-impact failures are: surface-level support records accepting wrong final answers, multi-hop dependency collapse, premature EnvScaler completion after partial mutation progress, schema/repeat recovery that remains advisory instead of strategic, unvalidated plan packets that do not become a reliable execution contract, and noisy memory retrieval that supplies long loosely related traces.

Module ownership is clear. Planning must own validated plan packets and stable task-state contracts. Action must own relation-aware answer arbitration, schema-aware recovery, repeated-call strategy changes, and stateful terminal discipline. Memory must own topology-aware, phase-aware retrieval with compact procedural lessons. The Cross-Module Interface must pass structured evidence and mutation state from Planning to Action and let Action update progress after observations. Builder/Wiring should preserve the local harness factory contract while correcting stale metadata. The most valuable behaviors to preserve are the single mutating executor, hard schema preflight, repeated-call awareness, SearchQA raw-query and no-leakage memory policy, support-record discipline as a concept, and compact procedural memory.

The highest-leverage Stage 3 repair is not a whole-architecture replacement. It should turn the current ledger idea into an enforceable contract: validated plan packets, action-visible evidence and mutation slots, relation-aware final-answer support, all-required-mutation completion gating, bounded failure-class recovery, and memory routing by task topology and active failure class.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round01_4`

- **Observed Structure:** Single executor with read-only evidence gates, explicit answer commitment rules, and procedural memory that treats current observations as authoritative.
- **Relevant Strength:** It is the best complete round01 harness by overall score, with `mixed_primary_score = 0.4659`, `toolhop_correct = 0.5659`, `toolhop_path = 0.5891`, and reliable SearchQA search use.
- **Relevant Weakness / Risk:** It is not the cheapest complete candidate and its SearchQA subEM is solid but not leading. It does not by itself solve the Stage 1 need for action-visible mutation coverage.
- **Related Winner Failure:** Evidence-surface support gate accepts wrong final answers; multi-hop evidence-chain break.
- **Transferable Module Pattern:** Borrow the idea that read-only and multi-hop final answers require current observed or deterministically derived support before commitment.
- **Generalization Rationale:** Evidence-gated commitment transfers to any task where distractor observations can contain plausible but wrong entities.
- **Do Not Borrow:** Do not copy the whole round01 harness or regress the winner's schema preflight, cooldown, and task-signature memory improvements.
- **Transfer Confidence:** High

#### Example: `harness_round02_01_7`

- **Observed Structure:** Retrieval-focused direct harness with targeted search pressure, strict support records, route-aware completion gates, repeated-call recovery, and task-signature memory.
- **Relevant Strength:** It is the best full-run round02_01 candidate with `mixed_primary_score = 0.4541`, best round02_01 EnvScaler score, strong SearchQA subEM, and reliable search use.
- **Relevant Weakness / Risk:** It is still below the round01 parent overall, has higher token cost, and ToolHop trails the current winner's ToolHop signal.
- **Related Winner Failure:** Evidence-surface support gate accepts wrong final answers; SearchQA finalization with broad or distractor spans.
- **Transferable Module Pattern:** Borrow targeted search pressure and cautious arbitration among plausible answer spans, but implement it as a small action-side finalization check rather than a broader search-heavy policy.
- **Generalization Rationale:** Many QA tasks require distinguishing a correct answer-bearing span from nearby broad entities in the same evidence.
- **Do Not Borrow:** Do not increase search/ledger context indiscriminately or replace the current single-executor loop.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_3`

- **Observed Structure:** Single executor with ordered hop-chain planning and provenance records for source entity, relation result, intermediate value, transform, and final value.
- **Relevant Strength:** It has the best full-run round02_02 ToolHop correctness and path score, showing a direct fit for multi-hop provenance failures.
- **Relevant Weakness / Risk:** It is costly, with high elapsed time, tokens, API calls, and max-step rate, and it is weak on EnvScaler done rate.
- **Related Winner Failure:** Multi-hop evidence-chain break in transform tasks.
- **Transferable Module Pattern:** Borrow ordered hop-chain provenance as a compact evidence-slot status record: source, relation, derived value, transform, final candidate.
- **Generalization Rationale:** Ordered provenance is domain-agnostic because every multi-hop task has dependencies that should be satisfied before downstream transforms.
- **Do Not Borrow:** Do not apply the full hop-chain policy to stateful tasks or add expensive extra audit passes.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_4`

- **Observed Structure:** Single executor with mutation-progress and verification-signal tracking before terminal completion, optional ledger review, and compact mutation-readiness planning.
- **Relevant Strength:** It demonstrates a stateful mutation-readiness pattern in a full-run candidate with good EnvScaler done rate.
- **Relevant Weakness / Risk:** Its overall score trails stronger round02_02 candidates, and optional ledger review can add cost without resolving read-only QA weaknesses.
- **Related Winner Failure:** Premature stateful completion after partial mutation progress.
- **Transferable Module Pattern:** Borrow route-specific mutation readiness: each required mutation should have a verification signal and completion should depend on coverage, not one successful mutation.
- **Generalization Rationale:** Stateful tasks in any domain require all requested updates to be tracked against observed success criteria.
- **Do Not Borrow:** Do not add heavy verifier calls for every mutation; keep readiness as an internal checklist where possible.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_5`

- **Observed Structure:** Fail-soft recovery harness with explicit routing for schema, ID, enum, not-found, repeat, authorization, and empty-action failures.
- **Relevant Strength:** It is the best partial round02_02 candidate by score and its failure-class taxonomy maps directly to Stage 1's schema and repeated-call recovery gaps.
- **Relevant Weakness / Risk:** It is partial-eval only and its token cost is not the lowest; ToolHop and SearchQA are not standout.
- **Related Winner Failure:** Schema and repeated-call recovery does not change strategy reliably.
- **Transferable Module Pattern:** Borrow failure-class recovery routing as an action-side controller: diagnose failure class, select a bounded repair move, and avoid repeating failed signatures.
- **Generalization Rationale:** Tool-use failures such as unknown tool, missing key, not found, authorization, and repeat are domain-general.
- **Do Not Borrow:** Do not keep fail-soft partial completion as a default for stateful tasks; Stage 1 shows partial completion is harmful without full mutation coverage.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_7`

- **Observed Structure:** Memory-routed harness that improves retrieval by task signature, tool family, and reusable failure lessons while keeping action lightweight.
- **Relevant Strength:** It has a useful memory-routing pattern and strong partial SearchQA subEM with reliable search use.
- **Relevant Weakness / Risk:** It is only partial-eval, does not clearly improve overall score, and has weak ToolHop performance.
- **Related Winner Failure:** Noisy memory retrieval distracts without enforcing reusable lessons.
- **Transferable Module Pattern:** Borrow tool-family and task-topology routing, but only as a small filter and formatter on the current memory provider.
- **Generalization Rationale:** Memories are useful when the current task shares a workflow shape and active failure class, not just lexical overlap.
- **Do Not Borrow:** Do not relax repeat limits or let memory-guided retries extend loops.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_8`

- **Observed Structure:** Low-overhead light ledger with softer gates, compact evidence/recovery state, and sparse memory exposure.
- **Relevant Strength:** It has the best partial round02_02 EnvScaler score and done rate, with the lowest partial round02_02 runtime, token cost, and max-step marker rate.
- **Relevant Weakness / Risk:** It is weak on ToolHop and SearchQA, and its softer gates are unsafe for the winner's final-answer arbitration failure.
- **Related Winner Failure:** Prompt growth and recovery overhead; EnvScaler completion cost and loops.
- **Transferable Module Pattern:** Borrow compact ledger formatting and low-overhead status records, not its soft final-answer gates.
- **Generalization Rationale:** A compact ledger reduces context growth while preserving enough state for any task family.
- **Do Not Borrow:** Do not soften support gates or repeat limits for read-only QA.
- **Transfer Confidence:** Medium

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style multi-agent harness with broader coordination and Cerebra fusion memory.
- **Relevant Strength:** It demonstrates that extra roles can improve coverage in some cases and has moderate EnvScaler score.
- **Relevant Weakness / Risk:** It has the highest token cost and max-step rate among active seed candidates, and the pool notes that orchestration is too heavy for Qwen3-4B.
- **Related Winner Failure:** None that requires heavy multi-agent execution. Stage 1 attributes failures to contracts, gates, and recovery, not lack of acting agents.
- **Transferable Module Pattern:** Negative control: use only the principle that any verifier must be non-acting and bounded.
- **Generalization Rationale:** For stateful tasks, multiple acting agents can corrupt state or duplicate work; a single executor remains safer.
- **Do Not Borrow:** Do not copy heavy multi-agent orchestration, broad fusion memory exposure, or multiple acting roles.
- **Transfer Confidence:** Low

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Planning | Unvalidated plan packet creates weak execution contracts | No enforceable evidence/mutation/terminal state contract | None; repair within winner pattern | Validate plan packets and reject action-style `think/tools` output | Every task family benefits from a stable plan contract before action begins | Avoid heavy orchestration plans from `harness5` | High | Medium |
| Cross-Module Interface | Multi-hop evidence-chain break | Planning evidence slots are not action-visible or updated | `harness_round02_02_3` | Compact ordered hop provenance with source, relation, intermediate, transform, final slots | Ordered dependencies transfer across lookup, transform, and database tasks | Avoid full costly hop-chain policy on stateful routes | High | Medium |
| Action | Wrong answers pass support records | Surface support is not relation-slot correctness | `harness_round01_4`, `harness_round02_01_7`, `harness_round02_02_2` | Requested-slot support record and cautious answer-span arbitration | Correct finalization requires matching candidate to the requested relation and answer type | Avoid soft support gates from `harness_round02_02_8` | High | Medium |
| Action | Premature EnvScaler completion after partial progress | Completion gate lacks full mutation coverage | `harness_round02_02_4`, `harness_round02_02_8` | Required-mutation readiness with compact verification signals | Stateful tasks require every requested change to be accounted for before completion | Avoid fail-soft partial completion from `harness_round02_02_5` as default | High | Medium |
| Action | Schema/repeat recovery remains advisory | No bounded controller for failure-class-specific repair | `harness_round02_02_5`, `harness_round01_2` | Failure-class recovery router plus failed-call cooldown | Unknown tools, missing keys, not-found, authorization, and repeats recur in any tool-rich domain | Avoid unbounded recovery loops from costly candidates | High | Medium |
| Memory | Noisy retrieved memories distract | Retrieval lacks topology, tool-family, and phase routing | `harness_round02_02_7`, dynamic cheatsheet and workflow memory examples | Task-topology and failure-class memory routing with distilled one-line recipes | Reusable lessons transfer through workflow shape, not entity overlap | Avoid long trace sketches and API-style SkillWeaver tools | Medium | Low |
| Builder/Wiring | Stale round metadata | Harness identity and metadata do not match round context | None; repair within winner pattern | Update harness name, round metadata, policy labels, and recommended memory system consistently | Accurate metadata helps evaluation, reporting, and later generation lineage | Avoid changing factory contracts or provider entry points | Medium | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve hard schema preflight; owner module Action; it prevents malformed tool calls from crashing execution and already converts errors into recoverable observations.
- Preserve repeated-call awareness; owner module Action; it is a useful guard against low-value loops, but Stage 3 must make the follow-up strategy active.
- Preserve the single mutating executor; owner module Action; it keeps stateful environments safe from duplicate or conflicting mutations.
- Preserve support-record finalization as a concept; owner module Action; correct trajectories show it helps when paired with proper evidence, but it must become relation-aware.
- Preserve SearchQA memory leakage prevention and raw-query-first guidance; owner module Memory; it keeps old answers from masquerading as current evidence.
- Preserve compact procedural memory; owner module Memory; it is preferable to long retrieved traces if routing and formatting are tightened.
- Preserve builder factory compatibility; owner module Builder/Wiring; Stage 3 should keep `build_agent_from_context`, provider injection, project root, and tool-agent binding compatible.

#### Borrow

- Borrow from `harness_round01_4`; target module Action; exact pattern: read-only answer commitment only from current observed or deterministically derived facts; expected benefit is fewer unsupported or distractor final answers; it generalizes because every evidence task separates current evidence from hypotheses.
- Borrow from `harness_round02_01_7`; target module Action; exact pattern: targeted search pressure and arbitration among plausible answer spans; expected benefit is improved SearchQA final-answer selection; it generalizes because retrieval tasks often contain multiple plausible spans in one observation.
- Borrow from `harness_round02_02_3`; target module Cross-Module Interface; exact pattern: ordered hop provenance records; expected benefit is fewer multi-hop transform collapses; it generalizes because dependency order is independent of domain content.
- Borrow from `harness_round02_02_4`; target module Action; exact pattern: mutation readiness with per-requirement verification signals; expected benefit is fewer low-score EnvScaler completions; it generalizes to any multi-update stateful workflow.
- Borrow from `harness_round02_02_5`; target module Action; exact pattern: failure-class recovery router; expected benefit is fewer schema, not-found, authorization, repeat, and empty-action loops; it generalizes because these are common tool-use failure classes.
- Borrow from `harness_round02_02_7`; target module Memory; exact pattern: task signature plus tool-family retrieval; expected benefit is less distracting memory context; it generalizes because memory should match workflow topology rather than entity names.
- Borrow from dynamic cheatsheet and workflow memory providers; target module Memory; exact pattern: distilled short procedural notes instead of long trace sketches; expected benefit is lower prompt noise; it generalizes because compact lessons are easier to apply across tasks.

#### Avoid

- Avoid heavy multi-agent orchestration from `harness5`; risk is complexity and high token/max-step cost; it should not enter Stage 3 because Stage 1 failures are not caused by missing parallel actors.
- Avoid full hop-chain policy from `harness_round02_02_3` on stateful routes; risk is cost and EnvScaler regression; borrow only compact provenance for read-only and transform tasks.
- Avoid soft support gates from `harness_round02_02_8`; risk is final-answer regression; Stage 1 already shows surface support is too permissive.
- Avoid fail-soft partial completion from `harness_round02_02_5` as a default; risk is stateful regression; the current winner already completes too early after partial progress.
- Avoid long memory trace sketches from the current winner and broad memory exposure from `harness5`; risk is prompt bloat and weak transfer; memory should be compact and routed.
- Avoid benchmark-specific patches for the observed examples; risk is irrelevance and overfit; improvements must operate over slots, dependencies, schemas, failure classes, and terminal contracts.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Validated Planning Contract]**
- **Target Module:** Planning
- **Stage 1 Failure Addressed:** Unvalidated plan packet creates weak execution contracts
- **Current Weakness:** The planner stores raw model output and accepts action-style `think/tools` JSON as a plan, especially on EnvScaler.
- **Desired Behavior:** The planner should always produce a validated compact contract with route, evidence slots, dependency edges, required mutations, answer format, terminal policy, and verification questions.
- **Borrowed Pattern:** None; repair within winner pattern
- **Preserved Behavior:** Keep compact planning and avoid long essays or heavy decomposition.
- **Implementation Shape:** Add a plan-shape validator and fallback repair prompt or deterministic default. If the model emits action JSON, transform it into a planning contract or re-ask for the required fields. Store a normalized plan packet for action to read.
- **Generalization Rationale:** A valid task-state contract helps unseen QA, transform, and stateful tasks because it defines what must be proven before committing.
- **Complexity:** Medium
- **Expected Impact:** Large reduction in EnvScaler premature completion and ToolHop dependency skips.
- **Regression Risk:** Overly strict validation could block execution if the model gives a useful but nonconforming plan; include a compact fallback.

**[Direction 2: Action-Visible Evidence And Mutation Ledger]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Multi-hop evidence-chain break in transform tasks; premature stateful completion after partial mutation progress
- **Current Weakness:** Planning lists slots, but Action only sees raw text and route hints. No structured slot status is updated after tool observations.
- **Desired Behavior:** Action should maintain a lightweight runtime ledger with evidence slot status, dependency satisfaction, mutation status, and terminal readiness.
- **Borrowed Pattern:** `harness_round02_02_3` ordered hop provenance; `harness_round02_02_4` mutation readiness
- **Preserved Behavior:** Keep one executor and current schema preflight.
- **Implementation Shape:** Let Planning expose normalized slots to Action. After each observation, Action records whether a slot or mutation was satisfied, blocked, or needs repair. Terminal calls check the ledger rather than only recent observations or one successful mutation.
- **Generalization Rationale:** Slot progress and mutation coverage are task-general abstractions for ordered work.
- **Complexity:** Medium
- **Expected Impact:** Higher ToolHop path correctness and fewer low-score EnvScaler `complete_task` calls.
- **Regression Risk:** If slot matching is too literal, valid progress may not be recognized; use conservative heuristics and allow evidence notes.

**[Direction 3: Relation-Aware Final Answer Arbitration]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Evidence-surface support gate accepts wrong final answers
- **Current Weakness:** The support gate checks whether the candidate string appears in evidence, not whether it answers the requested slot.
- **Desired Behavior:** Finalization should require a support record that binds the candidate to target slot, relation phrase, answer type, source observation, and derivation path.
- **Borrowed Pattern:** `harness_round01_4` read-only evidence gate; `harness_round02_01_7` cautious answer-span arbitration; `harness_round02_02_2` requested-slot support audit
- **Preserved Behavior:** Keep raw final answer output and support-record logging.
- **Implementation Shape:** Before accepting `final_answer`, Action asks a compact internal check: what slot is being answered, which observation sentence supports it, whether competing candidates exist, and whether the answer type matches. For transforms, require the final value to derive from the last satisfied transform slot.
- **Generalization Rationale:** Relation-aware support transfers to all evidence tasks with distractors, aliases, dates, counts, or multi-hop dependencies.
- **Complexity:** Medium
- **Expected Impact:** Lower SearchQA and ToolHop path-correct/final-wrong rate.
- **Regression Risk:** Too strict an arbitration rule may reject valid paraphrases; allow deterministic derivations and accepted aliases when observed.

**[Direction 4: Bounded Failure-Class Recovery Router]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Schema and repeated-call recovery does not change strategy reliably
- **Current Weakness:** Guard observations are textual hints; they do not force a different action after schema, unknown-tool, not-found, repeat, authorization, or empty-action failures.
- **Desired Behavior:** Each failure class should trigger a bounded recovery route that changes tool family, repairs arguments from observations, enumerates valid tools, or stops with an evidence-backed blocker when no route exists.
- **Borrowed Pattern:** `harness_round02_02_5` recovery router; `harness_round01_2` failed-call cooldown
- **Preserved Behavior:** Keep hard schema preflight, failed-signature tracking, and one tool call by default.
- **Implementation Shape:** Replace plain recovery advice with a compact policy table. For missing keys, search prior observations for required values. For unknown tools, select from valid tools by schema description. For not-found, switch exact lookup to list/search if available. For repeat, block the signature and require a different identifier source.
- **Generalization Rationale:** Tool-call failures recur across domains and can be handled by failure class rather than benchmark-specific patches.
- **Complexity:** Medium
- **Expected Impact:** Fewer low-value repeats, schema loops, no-final ToolHop failures, and wasted EnvScaler steps.
- **Regression Risk:** Over-automated repair could choose the wrong generic tool; keep changes advisory but enforce no exact repeat after failure.

**[Direction 5: Topology-Routed Compact Memory]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Noisy memory retrieval distracts without enforcing reusable lessons
- **Current Weakness:** Memory retrieval uses shallow token overlap and can inject long loosely related traces.
- **Desired Behavior:** Memory should retrieve compact lessons by benchmark family, route, dependency depth, tool family, active failure class, and phase, while keeping old memories as hints only.
- **Borrowed Pattern:** `harness_round02_02_7` tool-family memory routing; dynamic cheatsheet and workflow memory distilled notes
- **Preserved Behavior:** Keep SearchQA trajectory skip policy and observed-fact/hypothesis distinction.
- **Implementation Shape:** Store route metadata and failure class with each memory. At BEGIN, return at most two short topology-matched procedure notes. At IN, return one current-failure repair recipe only when the step number and failure class match.
- **Generalization Rationale:** Workflow-shape retrieval transfers better than entity-word overlap and reduces prompt noise across unseen domains.
- **Complexity:** Low
- **Expected Impact:** Lower distraction in ToolHop and EnvScaler, better recovery after repeated failures, and reduced prompt growth.
- **Regression Risk:** Over-filtering can hide useful memories for rare tasks; keep a default phase reminder.

**[Direction 6: Metadata And Cost Hygiene]**
- **Target Module:** Builder/Wiring
- **Stage 1 Failure Addressed:** Builder / Wiring metadata mismatch and prompt growth pressure
- **Current Weakness:** The harness still names itself and its metadata as round02_01 while used as round03_01 base; ledger and memory context can grow.
- **Desired Behavior:** Builder metadata should match the generated candidate identity, and module policies should be labeled consistently. Ledger and memory exposure should remain compact.
- **Borrowed Pattern:** `harness_round02_02_8` light ledger cost-control pattern
- **Preserved Behavior:** Keep factory-compatible provider entry points and tool-agent binding.
- **Implementation Shape:** Update harness name, round metadata, pairing reason, and policy labels. Preserve `prepare_context` wiring but expose compact policy flags for plan validation, slot ledger, relation support, recovery router, and memory routing.
- **Generalization Rationale:** Accurate metadata supports later selection and debugging; compact context improves reliability across long tasks.
- **Complexity:** Low
- **Expected Impact:** Cleaner evaluation lineage and lower prompt bloat risk.
- **Regression Risk:** Changing wiring names incorrectly could break harness factory loading; keep public class/function names stable.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The Stage 3 candidate should be a planning-guided, verification-aware single-executor harness. It should feel like the current winner with its useful guardrails tightened: one mutating executor, compact validated planning, action-visible slot and mutation ledger, relation-aware final-answer arbitration, bounded recovery after tool failures, and compact topology-routed memory. It should avoid heavy multi-agent orchestration and instead make the existing direct loop more disciplined.

#### 6.2 Module-Level Blueprint

**Planning Blueprint**

Implement a validated compact plan contract. The planner should output route, evidence slots, dependency edges, required mutations, answer format, terminal policy, verification questions, and next non-terminal tool intent. Preserve compactness and the current observed-fact versus hypothesis discipline. Avoid accepting action JSON as a plan, avoid long task essays, and avoid benchmark-specific slot names beyond what the task itself requires. The evidence is Stage 1's 657/658 EnvScaler action-like plans and many premature `final_answer` next intents. The design is task-general because every task needs a small state contract before execution.

**Action Blueprint**

Keep a single executor as the only component that calls task tools. Implement three action-side controls. First, a runtime slot ledger updates evidence, dependency, transform, and mutation status after each observation. Second, final-answer arbitration checks requested slot, relation phrase, answer type, candidate, source observation, and derivation path before accepting `final_answer`. Third, a failure-class recovery router handles schema, unknown-tool, missing-key, not-found, authorization, repeat, and empty-action failures with bounded strategy changes. Preserve hard schema preflight, cooldown, raw final answers, and one tool call by default. Avoid multiple acting agents, unbounded verifier calls, and soft final-answer gates. The evidence is the high rate of wrong support records, repeated-call markers, and partial EnvScaler completion. The design is task-general because it operates on tools, observations, slots, and failure classes.

**Memory Blueprint**

Keep memory procedural and compact. At BEGIN, provide phase guidance plus at most two topology-matched memories. At IN, provide one short repair recipe only when the active failure class and phase justify it. Add metadata for route, tool family, dependency depth, stateful versus read-only, and failure class. Preserve SearchQA trajectory skip and old-memory-as-hint discipline. Avoid long trace sketches, old answers, broad fusion memory, and API/tool memory injection. The evidence is Stage 1's unrelated retrieved memories in ToolHop and EnvScaler. The design is task-general because it matches reusable workflow shape rather than entity names.

**Builder / Wiring Blueprint**

Keep harness factory compatibility: `builder.py`, provider classes, `prepare_context`, `build_agent_from_context`, project-root assignment, and agent-tool binding. Update harness metadata to the new round03_01 candidate identity and expose policy flags for validated planning, slot ledger, relation-aware support, recovery routing, and topology-routed memory. Avoid changing external benchmark/evaluator behavior. The evidence is the Stage 1 metadata mismatch and the need for clean lineage. The design is task-general because it improves traceability without changing the task loop.

**Interface Blueprint**

Add a simple Planning -> Action state handoff. The normalized plan packet should be accessible to Action as structured state or a compact parseable text block. Action should update runtime slot/mutation status after observations and consult that status for final answer and completion decisions. Memory should influence Planning and Action only as short procedural hints, not as evidence. Avoid complex shared state stores or extra agent roles. The evidence is that raw plan text currently does not enforce evidence or mutation coverage. The design is task-general because checklists and status summaries are enough for many task families.

#### 6.3 Minimal Required Changes

- Implement plan-shape validation that rejects or repairs action-style `think/tools` planning output.
- Create an action-visible runtime ledger for evidence slots, dependency edges, transforms, required mutations, and terminal readiness.
- Replace final-answer support checks based only on surface presence with requested-slot and relation-aware support records.
- Replace one-success or blocker-based stateful completion with all-required-mutation coverage checks.
- Add a bounded failure-class recovery router for schema, unknown-tool, missing-key, not-found, authorization, repeat, and empty-action errors.
- Add topology and failure-class filters to memory retrieval, and shorten retrieved lessons to compact procedural notes.
- Update builder metadata to a round03_01 candidate identity while preserving factory entry points.

#### 6.4 Optional Enhancements

- Add an internal non-acting finalization checklist for read-only tasks when multiple plausible answer candidates appear in one observation.
- Add a compact observation summarizer that extracts candidate slot fills and mutation successes into the runtime ledger.
- Add a low-cost ledger status line to guard observations so recovery can see pending slots without bloating the prompt.
- Add narrow commit-time canonicalization for dates, aliases, lists, and fixed-width formats only when the plan's answer format requires it.
- Add route-specific budgets that trigger recovery or controlled stop before max-step loops, while never completing stateful tasks without mutation coverage.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] The generated harness must validate the initial plan packet and must not accept action-style `think/tools` JSON as a valid plan.
- [Planning] The plan must contain route, evidence slots, dependency edges, required mutations, answer format, terminal policy, verification questions, and next non-terminal intent.
- [Planning] The planner must keep output compact and must not solve the task in planning.
- [Action] The harness must keep a single mutating executor; no peer worker may call state-changing tools.
- [Action] The final-answer gate must bind candidate answers to requested slots, relation/derivation evidence, answer type, and source observation.
- [Action] The stateful completion gate must require all planned required mutations to be satisfied or explicitly and evidence-backed blocked; one successful mutation is not enough.
- [Action] The schema preflight and repeated-call cooldown must be preserved.
- [Action] Guard blocks must trigger bounded recovery routes instead of only textual advice.
- [Action] The recovery router must avoid repeating exact failed signatures and must change identifier source, tool family, or argument source after failures.
- [Memory] SearchQA memories must not reuse old answers or old rewritten queries.
- [Memory] Retrieved memories must be compact procedural hints, not long trace sketches or current evidence.
- [Memory] Memory retrieval must use route, tool family, task topology, phase, and failure class when available.
- [Builder] Preserve harness factory compatibility, provider class exports, project-root wiring, and tool-agent binding.
- [Builder] Update harness identity and metadata to the new round03_01 candidate.
- [Interface] Action must be able to consume Planning's normalized slots and update their runtime status after observations.
- [Interface] Memory must not override live observations or tool schemas.
- [Preserve] Preserve the winner's direct ReAct loop, hard schema preflight, support-record concept, repeated-call awareness, and SearchQA raw-query discipline.
- [Avoid] Do not copy heavy multi-agent orchestration, broad fusion memory, or multiple acting roles from peer harnesses.
- [Avoid] Do not add benchmark-specific rules, task IDs, answer strings, entity names, or golden trace patches.
- [Avoid] Do not soften final-answer support gates or rely on partial stateful completion as a default recovery path.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```

### POST-RUN TOOLHOP / ENVSCALER PATCH NOTES

This section is mandatory guidance for regenerated round03_01 harnesses. It converts the first-200 common-task trajectory analysis into concrete generation constraints for the two weakest benchmark families, ToolHop and EnvScaler.

#### ToolHop Generation Requirements

- Add or preserve a ToolHop runtime argument-coercion layer before Python tool execution. If a schema supplies `input` but the implementation expects a single differently named parameter, rename it. If a schema supplies a list under `input` and the implementation expects multiple required parameters, map list elements positionally. Drop unknown keys only when the implementation does not accept `**kwargs`.
- Prompt and action policy must explicitly decompose relation chains before lookup. Paternal means father-side and maternal means mother-side; do not use a one-hop result as a grandparent, spouse, sibling, or child unless that exact relation has been observed.
- Bind every transform input to the most recent satisfied requested slot. Counts, string lengths, reversals, ASCII sums, date extraction, and timezone conversions should run on the entity/date/string requested by the full relation chain, not on the original source entity or an intermediate relative.
- Accept deterministic transform finals when they are derived from observed tool results, even if the exact final scalar does not appear verbatim in a raw lookup observation. Conversely, reject surface-supported numeric answers when the dependency chain is incomplete.
- Canonicalize dates and times consistently: `YYYY-MM-DD` for dates, `YYYY-MM-DD HH:MM` for datetimes, `AoE` as UTC-12, and day-of-birth/death as day-of-month unless the prompt explicitly asks for weekday.
- After a schema mismatch on a transform tool, retry once with the closest schema-listed key or derive manually from already observed values. Never loop the same invalid transform signature.

#### EnvScaler Generation Requirements

- Planning must materialize an operation-level mutation checklist from the user request. Split numbered, bulleted, and conjoined instructions into separate required mutations and expose them to action.
- For every mutation requiring an ID, action must first retrieve the exact ID from a list/search/detail tool or reuse an exact ID from a prior observation. Names, phone numbers, addresses, locations, labels, and invented placeholders must not be used as IDs.
- For fields that should remain unchanged, action must call a detail/read tool once and reuse the returned current IDs/values rather than guessing them.
- For enum/status/category fields, action must use exact allowed tokens. Natural-language labels such as "in review" must be mapped to the actual allowed enum value returned or implied by the tools, for example `under_review` when that is the accepted token.
- After invalid-id, not-found, permission, capacity, overlap, or repeated-call feedback, the next call must change identifier source or switch to a broader list/search/detail strategy. Repeating the same failed signature should be blocked.
- `complete_task` may be called only when every checklist item is satisfied or every remaining item has an observed blocker. A single successful mutation plus a blocker is not enough for terminal completion.

#### Expected Effect

These constraints target the observed low-score causes directly: ToolHop lookup-not-found, transform schema mismatch, relation-chain collapse, and support-blocked deterministic answers; EnvScaler mutation-coverage gaps, invalid IDs, enum mismatch, repeat loops, and premature completion. Future generated harnesses should implement these as runtime/prompt behavior, not as benchmark-specific memorized examples.

