### PART 1: LOCALIZATION SUMMARY

The current winner under improvement is `harness_round02_02_6` with model `qwen3-4B-round_02_02-harness6`. It is a guarded single-executor ReAct harness with compact format-contract planning, action-side schema preflight, route-aware support records, commit-time canonicalization, progress-based completion, repeated-call guards, and lightweight task-signature memory. Stage 1 found that the architecture should remain single-executor and direct, but its planning/action contract is too weak for stateful tasks and its final-answer support is too shallow for read-only and multi-hop tasks.

The dominant failures are: stateful mutation ledger collapse on EnvScaler, blocker-after-progress premature completion, distractor-supported wrong final answers, multi-hop provenance breaks after intermediate lookup failures, low-value repair loops after guard blocks, route and mutation semantic drift, and coarse memory guidance. The strongest module attribution is Cross-Module Interface for the missing typed Planning -> Action ledger, Action for terminal readiness, final-answer support, and recovery routing, and Memory for compact route-aware procedural lessons. The highest-leverage repairs are a validated typed ledger, all-required-mutations terminal readiness, slot-bound support records, dependency-checked hop provenance, and stateful recovery routing. The generator must preserve the single executor, hard schema preflight, support-record concept, compact planner target, memory-as-hint discipline, and direct identifier repair behavior shown in successful trajectories.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round02_02_1`

- **Observed Structure:** Single-executor harness with compact evidence and mutation slot ledger, support-record finalization, recovery routing, and task-signature memory.
- **Relevant Strength:** Best full-run round02_02 overall score and fastest full-run round02_02 candidate; uses a compact slot ledger without heavy orchestration.
- **Relevant Weakness / Risk:** Still uses ledger-or-progress completion and remains below the round01 parent; its EnvScaler score does not fully solve partial completion.
- **Related Winner Failure:** Stateful mutation ledger collapse, route semantics drift, and need to preserve compact direct execution.
- **Transferable Module Pattern:** Borrow compact slot naming and evidence/mutation packet discipline, but strengthen validation and terminal gating beyond progress.
- **Generalization Rationale:** Slot ledgers are task-general: they represent what must be observed, changed, and verified without encoding benchmark entities or answers.
- **Do Not Borrow:** Do not borrow progress-based completion as sufficient terminal readiness.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_3`

- **Observed Structure:** Single executor with ordered multi-hop provenance records for source, relation, intermediate value, transform, and final value.
- **Relevant Strength:** Best full-run round02_02 ToolHop correctness and path score; directly targets multi-hop provenance.
- **Relevant Weakness / Risk:** Expensive in time, tokens, API calls, and max-step rate; weak EnvScaler done rate.
- **Related Winner Failure:** Multi-hop provenance break after failed intermediate lookup and distractor-supported final answers.
- **Transferable Module Pattern:** Borrow lightweight hop-chain records only for read-only and ToolHop-like routes, not the full costly policy.
- **Generalization Rationale:** Dependency provenance transfers across biographies, publications, dates, organizations, and transform tasks because it verifies the relation chain rather than the surface entity.
- **Do Not Borrow:** Do not apply the full hop-chain policy to stateful routes or add expensive repeated review steps.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_5`

- **Observed Structure:** Fail-soft recovery harness with failure-class routes for schema, ID, enum, not-found, repeat, authorization, and empty-action failures.
- **Relevant Strength:** Best partial round02_02 overall score and a broadly useful recovery-router design.
- **Relevant Weakness / Risk:** Partial 200-task evidence only; token cost is higher than the light-ledger partial candidate; ToolHop and SearchQA are not standout.
- **Related Winner Failure:** Guarded low-value exploration loop after schema, repeat, not-found, and unknown-tool errors.
- **Transferable Module Pattern:** Borrow the failure-class taxonomy and bounded repair routing, but implement it as action-side state rather than more prompt text.
- **Generalization Rationale:** Tool-call failures are domain-general. Mapping each failure class to a required strategy change should help unseen schemas and APIs.
- **Do Not Borrow:** Do not keep partial completion after observed progress as a recovery endpoint for stateful tasks.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_8`

- **Observed Structure:** Low-overhead light ledger with soft support gates, relaxed repeat limits, progress-based recovery, and sparse memory exposure.
- **Relevant Strength:** Best partial round02_02 EnvScaler score and done rate with the lowest partial runtime, token cost, and max-step marker rate.
- **Relevant Weakness / Risk:** Weakest partial round02_02 ToolHop score and low SearchQA subEM despite using search.
- **Related Winner Failure:** Need for cost control while adding ledger validation and terminal checks.
- **Transferable Module Pattern:** Borrow light ledger compaction and sparse memory exposure as implementation constraints, not its soft gates.
- **Generalization Rationale:** Compact status records reduce prompt growth across all task families and help the 4B model stay within useful context.
- **Do Not Borrow:** Do not borrow relaxed repeat limits or soft final support where Stage 1 demands stronger gating.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_01_7`

- **Observed Structure:** Retrieval-focused direct harness with targeted search pressure, support records, cautious arbitration, and task-signature memory.
- **Relevant Strength:** Best full-run round02_01 overall score, strong SearchQA subEM, reliable search use, and good EnvScaler score for that round.
- **Relevant Weakness / Risk:** Higher token cost than the round01 parent and weaker ToolHop than some alternatives.
- **Related Winner Failure:** Distractor-supported SearchQA answers and shallow answer arbitration.
- **Transferable Module Pattern:** Borrow targeted search and candidate-support slot pressure for read-only routes.
- **Generalization Rationale:** Targeted retrieval and candidate arbitration are domain-agnostic because they require evidence for the requested slot rather than more searches for a specific benchmark.
- **Do Not Borrow:** Do not expand search context without slot binding; more retrieval alone does not fix distractor support.
- **Transfer Confidence:** Medium

#### Example: `harness_round01_2`

- **Observed Structure:** Efficient single-executor schema-repair harness with failed-call cooldown and concise in-task repair reminders.
- **Relevant Strength:** Best cost-quality tradeoff among complete round01 runs, strong ToolHop score, and low cost compared with later variants.
- **Relevant Weakness / Risk:** SearchQA weaker than other complete round01 candidates and less advanced than current format-contract support.
- **Related Winner Failure:** Repeated failed-call loops and need to preserve efficiency.
- **Transferable Module Pattern:** Borrow failed-call cooldown discipline and concise repair reminders as a baseline for the new action repair state.
- **Generalization Rationale:** Cooldown after repeated failures applies to any tool schema or identifier failure without task-specific rules.
- **Do Not Borrow:** Do not regress to weaker SearchQA support or remove current format-contract canonicalization.
- **Transfer Confidence:** High

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style multi-agent planning, action, and Cerebra fusion memory.
- **Relevant Strength:** Shows that broader orchestration can improve coverage in some cases.
- **Relevant Weakness / Risk:** Highest token cost, highest max-step rate among active seeds, and handoff overhead appears too heavy for Qwen3-4B.
- **Related Winner Failure:** Negative control for agent collaboration and orchestration transfer.
- **Transferable Module Pattern:** Borrow only the idea of non-acting verification when needed; do not borrow heavy multi-agent execution.
- **Generalization Rationale:** Stage 1 attributes failures to ledger, support, terminal readiness, and repair state, not lack of parallel agents.
- **Do Not Borrow:** Do not add multiple acting agents, broad debate, or high-frequency fusion memory.
- **Transfer Confidence:** Low

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Cross-Module Interface | EnvScaler plans are tool-call shaped and Action sees no mutation checklist | Typed Planning -> Action ledger with route, evidence, mutation, verification, and terminal fields | `harness_round02_02_1`, `harness_round01_3` | Compact slot ledger and mutation-readiness framing | A typed checklist transfers to any stateful API because it represents required operations, not domain items | Progress-only terminal readiness from `harness_round02_02_1` | High | Medium |
| Action | `complete_task` fires after partial progress and blockers | All-required-mutations terminal gate | `harness_round02_02_4`, `harness_round02_02_8` | Mutation readiness plus light ledger compaction | Completion should require all required state updates across domains | Soft gates and relaxed repeats from `harness_round02_02_8` | High | Medium |
| Action | Wrong answers pass support when string appears in evidence | Slot-bound answer support and answer-type validation | `harness_round02_02_2`, `harness_round02_01_7` | Requested-slot support records and targeted candidate arbitration | Retrieval tasks need relation-aware support rather than surface presence | Extra audit calls when evidence is already sufficient | High | Medium |
| Cross-Module Interface | ToolHop transforms wrong intermediate values | Dependency-checked hop provenance | `harness_round02_02_3`, `harness_round02_01_4` | Source -> relation -> transform -> final provenance record | Multi-hop provenance is independent of entity domain and tool names | Full costly hop-chain policy on stateful routes | High | Medium |
| Action | Guard messages do not change behavior after failures | Failure-class repair state machine | `harness_round02_02_5`, `harness_round01_2` | Recovery router plus failed-call cooldown | Schema, ID, enum, repeat, and not-found failures recur across tool families | Partial completion as a fail-soft endpoint | High | Medium |
| Memory | Memory reminders are broad and trace-heavy | Compact route/failure-class procedural hints | `dynamic_cheatsheet_provider_lite`, `agent_workflow_memory_provider_lite`, `harness_round02_02_7` | Distilled notes, workflow induction, task/tool-family routing | Abstract procedural lessons transfer better than stale IDs and long trace sketches | SkillWeaver API/tool injection and heavy memory exposure | Medium | Low |
| Builder/Wiring | Metadata still reports old round identity | Correct harness identity and policy metadata | None; repair within winner pattern | Align harness name, round, candidate index, and policy fields | Accurate metadata improves downstream selection without changing behavior | Broad wiring changes unrelated to factory compatibility | High | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve the direct single-executor topology in Action because successful ToolHop and EnvScaler traces show continuity helps when state and evidence remain aligned.
- Preserve hard schema preflight in Action because it catches unknown tools, missing keys, extra keys, and repeated failed signatures before silent state corruption.
- Preserve the support-record concept in Action because it blocks unsupported first-step final answers even though the support test must become slot-bound.
- Preserve compact planning in Planning because concise route, evidence, mutation, and terminal fields are the right interface for a 4B model.
- Preserve memory-as-hint discipline in Memory because current observations must remain authoritative and old memories must not become evidence.
- Preserve commit-time format canonicalization in Action because exact raw answers, dates, aliases, and leading-zero behavior remain useful lightweight gains.

#### Borrow

- Borrow from `harness_round02_02_1` into Cross-Module Interface: compact slot ledger structure; expected benefit is a reliable Planning -> Action contract; it generalizes because slots describe task requirements rather than benchmark entities.
- Borrow from `harness_round02_02_3` into Cross-Module Interface: ordered hop provenance for read-only multi-hop routes; expected benefit is fewer wrong transforms; it generalizes because every multi-hop chain has source, relation, intermediate, and transform dependencies.
- Borrow from `harness_round02_02_5` into Action: failure-class recovery router; expected benefit is fewer repeated failed calls and unknown-tool loops; it generalizes across schemas, IDs, enums, authorization, and not-found failures.
- Borrow from `harness_round01_2` into Action: failed-call cooldown with concise repair reminders; expected benefit is lower max-step and token waste; it generalizes because repeated bad signatures are domain-independent.
- Borrow from `harness_round02_01_7` into Action and Planning: targeted search pressure tied to requested support slots; expected benefit is fewer distractor-supported SearchQA answers; it generalizes by requiring evidence for the answer slot.
- Borrow from `dynamic_cheatsheet_provider_lite` and `agent_workflow_memory_provider_lite` into Memory: distilled short procedural memories; expected benefit is less stale trace noise; it generalizes because lessons are abstracted into workflows and notes.

#### Avoid

- Avoid heavy AgentOrchestra-style multi-agent execution from `harness5`; the risk is high complexity and token cost, and Stage 1 does not attribute failures to missing parallel actors.
- Avoid full hop-chain policy from `harness_round02_02_3` on stateful routes; the risk is cost and max-step regression, and its transfer evidence is strongest only for read-only multi-hop tasks.
- Avoid progress-based partial completion from `harness_round02_02_1`, `harness_round02_02_5`, and the current winner; the risk is EnvScaler regression because partial progress is already the main failure.
- Avoid relaxed repeat limits from `harness_round02_02_8`; the risk is more low-value loops, and Stage 1 shows repeated failures are already too frequent.
- Avoid SkillWeaver-style API memory injection for this repair; the risk is irrelevant complexity because Stage 1 calls for compact procedural hints, not generated tools.
- Avoid solving SearchQA by simply adding more search calls; the risk is weak transfer because the observed issue is relation binding, not lack of retrieved text.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Typed Ledger Contract Before Execution]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Stateful mutation ledger collapse on EnvScaler; read-only work counted as mutation work or unknown route.
- **Current Weakness:** Planning stores raw model output, and Action reconstructs route and mutation counts from brittle text scanning.
- **Desired Behavior:** The harness should validate or repair the plan into a typed packet before the first action step: route, evidence slots, dependency edges, required mutations, verification targets, answer format, terminal policy, and next action intent.
- **Borrowed Pattern:** `harness_round02_02_1` compact slot ledger and `harness_round01_3` mutation-ledger idea.
- **Preserved Behavior:** Keep the winner's compact planner and direct executor.
- **Implementation Shape:** Code-free direction: add a lightweight plan-normalization boundary that rejects tool-call-shaped plans as plans, preserves empty lists, separates lookup/transform/mutation slots, and exposes a compact status packet to Action.
- **Generalization Rationale:** Typed requirements help unseen stateful, read-only, and transform tasks because they express what must be proven before completion without item-specific rules.
- **Complexity:** Medium
- **Expected Impact:** Largest EnvScaler improvement, fewer false planned mutations in QA, and more reliable terminal policies.
- **Regression Risk:** Too rigid validation could overblock concise correct plans; keep a short repair path and safe defaults.

**[Direction 2: All-Slot Stateful Terminal Readiness]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Blocker-after-progress premature completion.
- **Current Weakness:** Completion can be triggered by progress or partial commit after a blocker.
- **Desired Behavior:** `complete_task` should be allowed only when every required mutation is succeeded or verified, or when an explicit irrecoverable-blocker state is produced and the environment accepts that condition.
- **Borrowed Pattern:** `harness_round02_02_4` mutation readiness, with cost discipline from `harness_round02_02_8`.
- **Preserved Behavior:** Keep schema preflight, one executor, and observation-based success detection.
- **Implementation Shape:** Code-free direction: maintain mutation slot statuses, update them from successful observations, require verification targets when available, and disable automatic partial commit as a generic endpoint.
- **Generalization Rationale:** Any stateful tool family with conjunctive requirements needs all-operation completion rather than local progress.
- **Complexity:** Medium
- **Expected Impact:** Fewer low-score EnvScaler completions and fewer cases where summaries claim unperformed mutations.
- **Regression Risk:** If the gate is too strict, correct stateful tasks may hit max steps; success and verification patterns must be broad and compact.

**[Direction 3: Slot-Bound Read-Only Answer Commitment]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Distractor-supported wrong final answers.
- **Current Weakness:** The support gate accepts string presence or token overlap without proving relation relevance or answer-type fit.
- **Desired Behavior:** Final-answer support should bind the candidate to the requested slot, current observation, relation label, answer type, and deterministic derivation when applicable.
- **Borrowed Pattern:** `harness_round02_02_2` requested-slot support and `harness_round02_01_7` targeted evidence arbitration.
- **Preserved Behavior:** Keep the winner's support-record finalization and commit-time canonicalization.
- **Implementation Shape:** Code-free direction: for each answer candidate, record which slot it fills, which observation supports it, whether the observation answers the relation, and whether the output format is city/date/number/list/name/category-specific.
- **Generalization Rationale:** Relation-aware support helps any retrieval setting with distractor snippets, aliases, adjacent dates, or broad categories.
- **Complexity:** Medium
- **Expected Impact:** Better SearchQA exact accuracy and fewer ToolHop wrong finals with `support_ok: True`.
- **Regression Risk:** Conservative support may block correct answers when evidence is terse; allow deterministic derivation and exact observed spans.

**[Direction 4: Dependency-Checked Hop Provenance]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Multi-hop provenance break after failed intermediate lookup.
- **Current Weakness:** The agent can transform a value that appears in evidence without proving it belongs to the requested dependency chain.
- **Desired Behavior:** Multi-hop routes should maintain a compact chain state: source entity, relation query, intermediate result, transform input, transform output, and final readiness.
- **Borrowed Pattern:** `harness_round02_02_3` ordered hop chain, reduced to a lightweight route-specific ledger.
- **Preserved Behavior:** Keep one executor and avoid broad debate.
- **Implementation Shape:** Code-free direction: only enable hop provenance for read-only multi-hop and transform routes; require final answers to cite completed slots in order; when a hop is blocked, force repair before transform or finalization.
- **Generalization Rationale:** Dependency-checked provenance applies across publications, genealogy, biographies, organizations, dates, and numeric transforms.
- **Complexity:** Medium
- **Expected Impact:** Higher ToolHop correctness and fewer `unable_to_determine` or wrong-proxy transform answers.
- **Regression Risk:** Full provenance tracking can inflate context; keep records short and route-gated.

**[Direction 5: Action-Side Failure-Class Repair State]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Guarded low-value exploration loop.
- **Current Weakness:** Guard observations are diagnostic text and do not force a different next action.
- **Desired Behavior:** After schema, unknown-tool, not-found, repeat, enum, authorization, or empty-action failures, the action module should update repair state and require a strategy change.
- **Borrowed Pattern:** `harness_round02_02_5` recovery router and `harness_round01_2` failed-call cooldown.
- **Preserved Behavior:** Keep hard schema preflight and current observation authority.
- **Implementation Shape:** Code-free direction: track failed signatures, banned invalid tool names, required schema keys, candidate identifier sources, and failure-class recovery requirements. Reset repair state only after new relevant evidence or a successful mutation.
- **Generalization Rationale:** Failure classes are reusable across APIs and tool families, independent of benchmark item content.
- **Complexity:** Medium
- **Expected Impact:** Fewer repeated failed calls, unknown-tool loops, and max-step endings.
- **Regression Risk:** Forced recovery can wander if the available tool set is small; keep fallbacks bounded and tied to pending slots.

**[Direction 6: Compact Route-Aware Memory Hints]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Coarse memory lessons without actionable routing.
- **Current Weakness:** Memory is correct but too broad, and retrieved trace sketches can be stale or non-operational.
- **Desired Behavior:** Memory should provide short route/failure-class hints that influence Planning and Action without injecting old identifiers as evidence.
- **Borrowed Pattern:** `dynamic_cheatsheet_provider_lite` distilled cheatsheet notes, `agent_workflow_memory_provider_lite` induced workflows, and `harness_round02_02_7` task/tool-family routing.
- **Preserved Behavior:** Keep memory-as-hint and current-observation authority.
- **Implementation Shape:** Code-free direction: store abstract records keyed by route, tool family, failure class, and recovery action; cap top-k; avoid raw trace snippets unless heavily summarized and explicitly marked as non-evidence.
- **Generalization Rationale:** Procedural hints transfer across unseen schemas better than old task traces.
- **Complexity:** Low
- **Expected Impact:** Lower prompt distraction and better alignment between memory reminders and action repair.
- **Regression Risk:** Over-compression can remove useful schema examples; preserve only schema patterns, not old values.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The next harness should be a planning-guided single executor with typed ledger discipline, verification-aware completion, and bounded repair. It should feel like the current winner with sharper internal state: compact plans, direct tool use, strict schema preflight, support records, and memory-as-hint remain, but finalization becomes all-slot and slot-bound rather than progress-based or span-based.

#### 6.2 Module-Level Blueprint

Planning Blueprint

Implement a compact typed plan contract that distinguishes route, evidence slots, dependency edges, required mutations, verification targets, answer format, terminal policy, and next safe action. Preserve the current short planning style. Avoid tool-call-shaped plans as initial plans, final-answer guesses in `next_tool_intent`, and putting read-only lookups in `required_mutations`. The evidence is 658/658 EnvScaler plans failing to produce intended ledger strings and QA ledgers drifting into nonzero mutations. The design is task-general because it classifies work by operation type rather than entity names.

Action Blueprint

Implement one executor with stronger internal state. Preserve hard schema preflight, repeated-call detection, support records, and commit-time canonicalization. Add all-required-mutations terminal readiness, slot-bound answer support, dependency-checked hop provenance for read-only multi-hop routes, and failure-class repair state after guard blocks. Avoid heavy multi-agent execution, progress-based partial commit as a generic rule, and full hop-chain overhead on stateful routes. The evidence is 297 EnvScaler partial commits, 207 wrong SearchQA support records, 134 wrong ToolHop support records, and frequent repeated failed calls. The design is task-general because it handles generic operation slots, relation slots, and failure classes.

Memory Blueprint

Implement compact route-aware procedural hints. Preserve memory-as-hint wording and current observations as authoritative. Borrow distilled cheatsheet/workflow style from memory references, but avoid raw long trace snippets, stale identifiers, or generated API skills. The evidence is that memory reminders were directionally correct but did not force repair in examples 3, 5, 53, and 490. The design is task-general because route and failure-class hints apply across tools without storing item-specific answers.

Builder / Wiring Blueprint

Keep the factory-compatible file layout and `PlanningClass` injection. Update metadata so harness name, round, candidate index, planning/action systems, and policy match the generated round. Preserve tool-agent binding and vector-tool memory wiring. Avoid changes to dataset, evaluator, backend model, or benchmark loop.

Interface Blueprint

Add a simple Planning -> Action state boundary. The action module should consume a normalized plan packet, not raw plan text. Action observations should update slot statuses and should be visible to summaries as compact status records. Final-answer and completion criteria should be shared through the same packet. Avoid complex orchestration layers; the interface should be a short checklist/status object.

#### 6.3 Minimal Required Changes

- Add a typed plan normalization step that rejects tool-call-shaped initial plans and separates evidence, mutation, transform, and verification slots.
- Replace progress-based stateful completion with all-required-mutations readiness.
- Disable or sharply constrain automatic partial commit unless all required slots are complete or explicitly impossible under a task-general blocker policy.
- Upgrade final-answer support from span/token presence to requested-slot support with answer-type checks.
- Add lightweight hop provenance for read-only multi-hop and transform routes.
- Add action-side repair state for schema, unknown-tool, not-found, repeat, enum, authorization, and empty-action failures.
- Convert memory output into compact route/failure-class hints and prevent memory-only values from becoming evidence.
- Correct builder/harness metadata for the new round and model identity.

#### 6.4 Optional Enhancements

- Add a non-acting ledger review checkpoint only when terminal readiness is uncertain or repeated repair state persists.
- Add deterministic local transform permission when all inputs are supported but the transform tool fails due to schema issues.
- Add a compact contradiction note when multiple candidate answers appear in evidence for the same requested slot.
- Add token-budget caps for hop provenance and memory hints to preserve the current winner's efficiency.
- Add a small route-specific answer-format checklist for dates, numbers, city-only spans, acronym expansions, and lists.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Generate or repair every initial plan into a typed route/evidence/mutation/verification/format/terminal packet.
- [Planning] Do not let a JSON tool-call proposal become the planning packet.
- [Planning] Keep read-only lookup and transform steps out of `required_mutations`.
- [Action] Keep one acting executor; do not introduce broad multi-agent execution.
- [Action] Preserve hard schema preflight, failed-signature tracking, and support-record finalization.
- [Action] Require all required stateful mutation slots to be succeeded or verified before `complete_task`.
- [Action] Do not use progress-plus-blocker partial commit as a generic completion policy.
- [Action] Bind every final answer to a requested slot, current observation, relation, and answer-format check.
- [Action] For multi-hop routes, require completed provenance slots before applying transforms or finalizing.
- [Action] After a guard block, update repair state so repeated invalid tools, schemas, identifiers, or queries are not selected again without new evidence.
- [Memory] Provide compact route/failure-class procedural hints, not long stale trace sketches.
- [Memory] Mark all memories as non-evidence and prevent memory-only values from being used as current tool arguments unless re-observed.
- [Builder] Keep harness factory compatibility and update metadata to match the generated harness and round.
- [Interface] Pass a normalized plan/status packet from Planning to Action instead of relying on raw string parsing.
- [Preserve] Preserve the current winner's format-contract canonicalization as a lightweight final commit layer.
- [Preserve] Preserve direct execution and low-overhead status records to avoid the cost profile of heavy orchestration.
- [Avoid] Do not hard-code benchmark entities, item IDs, golden answers, tool names from specific failed trajectories, or special cases such as Alice Chan, Star Trek, Pittsburgh, or genealogy names.
- [Avoid] Do not copy a whole peer harness; borrow only the module patterns that map to Stage 1 failure modes.
- [Avoid] Do not fix SearchQA by simply increasing search count; improve slot binding and answer arbitration.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
