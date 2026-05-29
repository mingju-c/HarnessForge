### PART 1: LOCALIZATION SUMMARY

#### Summary

The current winner is `harness_round02_02_1` evaluated as `qwen3-4B-round_02_02-harness1` in `round03_03`. It is a direct single-executor ReAct harness with `slot_ledger_planning`, `slot_ledger_react`, and `slot_signature_memory`. Its useful core is compact planning intent, one mutating executor, hard schema preflight, repeated-call guarding, support-record finalization, and memory-as-procedural-hint discipline.

Stage 1 localizes the dominant failures to four transferable gaps. First, the Planning -> Action ledger contract is unreliable: many EnvScaler plans become JSON tool proposals rather than parseable route/evidence/mutation ledgers, so the action guard often sees `planned_mutations=0`. Second, the Action module's progress-based partial commit turns blockers into premature `complete_task` calls, producing high done rates with low exact state scores. Third, final-answer support is span-based rather than relation-grounded: wrong SearchQA and ToolHop answers often pass because the candidate string appears somewhere in evidence. Fourth, recovery after schema, not-found, repeat, and tool-execution errors is textual but not stateful, causing repeated low-value loops. Memory is a secondary issue: retrieved lessons are directionally useful but too trace-heavy and stale. Builder metadata is also stale because the `round_03_03` snapshot still identifies itself as `round02_02`.

The highest-leverage repair targets are a validated route ledger, stricter all-slot stateful completion, slot-bound final-answer support, bounded repair routing, and compact route-aware memory. The next harness should preserve the single-executor topology, schema preflight, current-observation evidence discipline, support records, and compactness, while borrowing only targeted peer patterns instead of whole architectures.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round01_4`

- **Observed Structure:** Single-executor harness with read-only evidence gates, explicit answer commitment rules, and procedural memory that treats prior memory as route advice only.
- **Relevant Strength:** Best complete round01 overall score (`0.4659`) and strongest complete round01 ToolHop correctness (`0.5659`), with reliable SearchQA search use.
- **Relevant Weakness / Risk:** It is not the cheapest candidate and does not solve the Stage 1 stateful ledger interface collapse by itself.
- **Related Winner Failure:** Final-answer support is span-based rather than relation-grounded; read-only work is mislabeled in planning.
- **Transferable Module Pattern:** Preserve read-only final-answer commitment rules that require observed or deterministically derived facts before committing.
- **Generalization Rationale:** Any retrieval or tool-hop task can return distractor spans; commitment should be tied to requested slots and derivations rather than raw answer occurrence.
- **Do Not Borrow:** Do not copy the full parent harness or regress to its higher runtime; borrow the evidence-gate principle only.
- **Transfer Confidence:** High

#### Example: `harness_round01_2`

- **Observed Structure:** Direct single-executor harness with exact schema emphasis, failed-call cooldown, concise repair reminders, and procedural memory for schema repair.
- **Relevant Strength:** Best cost-quality tradeoff among complete round01 runs, strong ToolHop correctness (`0.5543`), lower token and API-call cost than other complete round01 candidates, and zero max-step rate.
- **Relevant Weakness / Risk:** SearchQA is weaker than several peers, and cooldown alone does not create relation-grounded support.
- **Related Winner Failure:** Recovery after schema, not-found, and repeat failures is textual but not stateful.
- **Transferable Module Pattern:** Convert repeated failed calls into a cooldown-backed requirement to change identifier source, argument shape, relation path, or tool family.
- **Generalization Rationale:** Tool schemas, IDs, and relation names vary across domains, but the need to stop exact failed-call repetition is domain-agnostic.
- **Do Not Borrow:** Do not borrow weak SearchQA behavior or reduce search pressure on read-only tasks.
- **Transfer Confidence:** High

#### Example: `harness_round02_01_7`

- **Observed Structure:** Retrieval-focused direct harness with targeted search planning, support records, route-aware completion gates, and cautious arbitration among plausible answer spans.
- **Relevant Strength:** Best full-run round02_01 overall score (`0.4541`), best full-run round02_01 EnvScaler score (`0.4505`), strong SearchQA subEM (`0.4985`), and reliable search use.
- **Relevant Weakness / Risk:** Token cost is higher than the round01 parent, and ToolHop trails stronger ToolHop-focused examples.
- **Related Winner Failure:** Distractor-supported wrong final answers and repeated low-value SearchQA exploration.
- **Transferable Module Pattern:** Use targeted search pressure and candidate-support slots so the agent searches for missing evidence rather than repeating generic queries.
- **Generalization Rationale:** Targeted retrieval slots help any read-only QA setting by making the missing relation explicit before final commitment.
- **Do Not Borrow:** Do not expand prompt context heavily or add broad retrieval loops that inflate cost.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_3`

- **Observed Structure:** Single-executor hop-chain harness that records source entity, relation result, intermediate value, transform, and final value for multi-hop tasks.
- **Relevant Strength:** Best full-run round02_02 ToolHop correctness and path score (`0.5174` / `0.5212`) and explicit hop provenance.
- **Relevant Weakness / Risk:** Costly in time, tokens, and API calls; weak EnvScaler done rate; not suitable as a full policy for stateful tasks.
- **Related Winner Failure:** Final-answer support is span-based rather than relation-grounded; ToolHop loops after failed transforms.
- **Transferable Module Pattern:** Borrow lightweight hop provenance records for read-only and ToolHop routes: source -> relation -> transform -> answer.
- **Generalization Rationale:** Multi-hop tasks in many domains require preserving which observation supports each relation and transform.
- **Do Not Borrow:** Do not apply the full expensive hop-chain policy to stateful routes or add heavy provenance for simple one-hop tasks.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_4`

- **Observed Structure:** Stateful workflow harness with mutation progress and verification signals before terminal completion, while preserving one executor.
- **Relevant Strength:** General mutation-readiness idea with good full-run EnvScaler done rate (`0.8936`) and moderate cost.
- **Relevant Weakness / Risk:** Overall quality is below the current winner and ToolHop is weaker.
- **Related Winner Failure:** Partial commit turns blockers into premature completion; stateful plans are not converted into a reliable mutation ledger.
- **Transferable Module Pattern:** Track required state mutations and verification signals as route-specific terminal criteria.
- **Generalization Rationale:** Exact final-state tasks across EHR, scheduling, account management, and logistics need all requested mutations to be observed or verified.
- **Do Not Borrow:** Do not copy optional ledger review overhead or weaker read-only QA behavior.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_5`

- **Observed Structure:** Fail-soft recovery harness that maps schema, ID, enum, not-found, repeat, authorization, and empty-action failures to bounded repair routes.
- **Relevant Strength:** Best partial round02_02 score (`0.4175`) and explicitly useful recovery-router design.
- **Relevant Weakness / Risk:** Partial 200-task run only, higher token cost than the light-ledger variant, and not a standout for SearchQA or ToolHop.
- **Related Winner Failure:** Guarded low-value exploration loop after schema, not-found, repeat, and tool errors.
- **Transferable Module Pattern:** Use a failure-class taxonomy to route the next action: schema repair, broader lookup, enum inspection, alternate identifier source, deterministic transform, or terminal delay.
- **Generalization Rationale:** These failure classes are tool-interface behaviors, not benchmark-specific item patterns.
- **Do Not Borrow:** Do not keep progress-based partial completion after blockers; that is directly implicated in Stage 1 failures.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_8`

- **Observed Structure:** Low-overhead light-ledger variant with one executor, compact evidence/recovery records, softer gates, and sparse memory exposure.
- **Relevant Strength:** Best partial round02_02 EnvScaler score and done rate (`0.4575` / `0.9174`) with lowest partial round02_02 runtime, token cost, and max-step marker rate.
- **Relevant Weakness / Risk:** Weakest partial round02_02 ToolHop score and low SearchQA subEM.
- **Related Winner Failure:** Need to preserve winner speed while adding stricter ledger and support checks.
- **Transferable Module Pattern:** Keep ledger records compact and avoid extra review tools unless a route-specific blocker requires them.
- **Generalization Rationale:** Compact state makes stricter verification affordable across long stateful and read-only tasks.
- **Do Not Borrow:** Do not borrow soft gates or relaxed repeat limits where Stage 1 requires stricter completion and repair discipline.
- **Transfer Confidence:** Medium

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style multi-agent harness with richer coordination and fusion memory.
- **Relevant Strength:** Demonstrates that broader role coverage can sometimes help SearchQA use search and EnvScaler coverage.
- **Relevant Weakness / Risk:** Highest token cost, high max-step rate, and heavy handoff overhead for a 4B model.
- **Related Winner Failure:** Mostly a negative control for orchestration choices.
- **Transferable Module Pattern:** At most borrow the idea of a non-acting verifier, not multi-actor execution.
- **Generalization Rationale:** Stage 1 failures are ledger, terminal, support, and repair problems inside a single-executor harness; heavy orchestration does not directly fix the interface contract.
- **Do Not Borrow:** Do not introduce multiple acting agents or broad debate for stateful tasks.
- **Transfer Confidence:** Low

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Cross-Module Interface | Action sees malformed or missing plan ledger fields, especially `planned_mutations=0` on stateful tasks | Missing typed Planning -> Action contract for route, evidence, mutations, verification, and terminal criteria | `harness_round02_02_4`, `harness_round01_3` | Route-specific mutation-readiness checklist with required operation slots and verification targets | Exact stateful work in any domain requires knowing all requested operations before completion | Avoid soft progress-only completion from current winner and fail-soft variants | High | Medium |
| Planning | Read-only lookup and transform steps are mislabeled as mutations; some plans seed final answers prematurely | Route semantics are not validated before execution | `harness_round01_4`, `harness_round02_01_7` | Evidence-slot planning with targeted search/candidate-support slots and no premature final answer in `next_tool_intent` | Separating evidence, transform, and mutation slots transfers across QA, ToolHop, and stateful tasks | Avoid verbose planning transcripts or full harness replacement | High | Medium |
| Action: terminal readiness | `complete_task` fires after partial progress and blockers | Lacks all-slot stateful completion gate | `harness_round02_02_4` | Mutation readiness states: pending, succeeded, verified, blocked-recoverable, blocked-irrecoverable | Final-state tasks reward exact state, not local progress | Avoid `partial_commit_on_blocker` from current winner and fail-soft variants | High | Medium |
| Action: final-answer support | Wrong answers pass because candidate spans appear in evidence | Lacks relation-grounded candidate arbitration | `harness_round02_02_3`, `harness_round01_4` | Lightweight hop provenance and slot-bound support records | Multi-hop and retrieval tasks require proving candidate relation, not just candidate presence | Avoid full costly hop-chain policy on all routes | High | Medium |
| Action: tool-use repair | Guard messages do not force strategy changes after failures | Lacks bounded repair-state routing | `harness_round01_2`, `harness_round02_02_5` | Failed-call cooldown plus failure-class repair routes | Schema, ID, enum, not-found, and repeat failures recur across tool APIs | Avoid relaxed repeat limits and unbounded recovery loops | High | Medium |
| Action: orchestration | No verifier, but failures do not require heavy acting teams | Need lightweight non-acting checks only at commitment or repeated blockers | `harness_round02_01_2`, negative control `harness5` | Optional non-acting audit/checkpoint for final support or stateful completion, not extra acting agents | Non-acting checks can improve commitment without state conflicts | Avoid AgentOrchestra-style multi-actor execution and high memory exposure | Medium | Low to Medium |
| Memory | Retrieved lessons are stale, long, and trace-heavy | Needs compact route/failure-class procedural memory | `harness_round02_02_7`, `harness_round01_6` | Route/tool-family memory routing with provenance labels and short abstract lessons | Abstract recovery lessons transfer better than environment-local trace snippets | Avoid long raw trace sketches and stale IDs | Medium | Low |
| Builder/Wiring | Round identity and metadata remain stale | Harness metadata does not match actual generation round | None; repair within winner pattern | Update harness name, round, pairing reason, and policy metadata consistently | Correct metadata supports evaluation, registry comparison, and future generation traceability | Avoid changing factory contracts | High | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve the single-executor action topology in Action because successful EnvScaler trajectories show one continuous executor can repair identifiers and complete long workflows without multi-agent state conflicts.
- Preserve hard schema preflight in Action because it catches malformed tool calls before execution and provides recoverable error evidence.
- Preserve support-record finalization in Action because it blocks unsupported first-step final answers and gives Stage 3 a natural place to attach slot-bound evidence.
- Preserve compact planning intent in Planning because route, evidence slots, dependencies, and terminal policy are the right transferable abstractions once validated.
- Preserve memory-as-hint discipline in Memory because old memories should not override current observations or current tool schemas.
- Preserve compactness and low overhead from the current winner because it is the fastest full-run round02_02 candidate and heavy peer harnesses show clear cost risk.

#### Borrow

- Borrow from `harness_round01_4` into Action the read-only evidence-gate pattern; expected benefit is fewer distractor-supported final answers; it generalizes because current observations and deterministic derivations are required in all retrieval domains.
- Borrow from `harness_round01_2` into Action the failed-call cooldown pattern; expected benefit is fewer schema and repeat loops; it generalizes because repeated failed signatures are API-interface failures, not domain facts.
- Borrow from `harness_round02_02_3` into Action the lightweight hop-provenance pattern; expected benefit is relation-grounded ToolHop support; it generalizes because source, relation, transform, and final slots appear in many multi-hop tasks.
- Borrow from `harness_round02_02_4` into Cross-Module Interface and Action the mutation-readiness checklist; expected benefit is lower premature EnvScaler completion; it generalizes because exact state mutation completion is domain-independent.
- Borrow from `harness_round02_02_5` into Action the failure-class recovery router; expected benefit is bounded repair after schema, ID, enum, not-found, repeat, authorization, and empty-action errors; it generalizes across tool families.
- Borrow from `harness_round02_02_8` into Planning/Action compact ledger discipline; expected benefit is preserving speed while adding checks; it generalizes because concise state is useful on long tasks.
- Borrow from `harness_round01_6` and `harness_round02_02_7` into Memory provenance-labeled, route-aware memory formatting; expected benefit is less stale trace distraction; it generalizes because all tasks need current evidence separated from old hints.

#### Avoid

- Avoid copying `harness5` heavy multi-agent orchestration; risk is high token cost, handoff overhead, and state conflicts; it should not enter Stage 3 because Stage 1 failures are ledger/support/repair gaps, not lack of acting agents; risk type is complexity and regression.
- Avoid current winner's `partial_commit_on_blocker` behavior; risk is premature stateful completion; it should not enter Stage 3 because 297 EnvScaler partial commits correlate with failures; risk type is direct regression.
- Avoid full `harness_round02_02_3` hop-chain policy on every route; risk is high cost and weak EnvScaler performance; it should not enter Stage 3 beyond lightweight provenance for read-only chains; risk type is complexity and weak transfer to stateful tasks.
- Avoid soft support gates from fail-soft recovery variants; risk is accepting wrong answers or incomplete state; Stage 3 needs stricter slot-bound support and all-slot completion; risk type is regression.
- Avoid long raw memory traces with environment-local IDs; risk is stale schema/entity contamination; it should not enter Stage 3 because Stage 1 already found memory snippets noisy; risk type is weak transfer evidence.
- Avoid benchmark-specific patches for EHR, mood entries, genealogy names, SearchQA entities, or known failed item IDs; risk is overfitting; Stage 3 must repair route-general module behavior; risk type is irrelevance and evaluation leakage.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Validated Route Ledger Contract]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Planning-to-action mutation ledger collapse on EnvScaler tasks
- **Current Weakness:** The action module parses raw plan text with line-prefix heuristics, so JSON-like plans silently erase required mutation state.
- **Desired Behavior:** The new harness should expose a validated route ledger with explicit `route`, `evidence_slots`, `dependency_edges`, `mutation_slots`, `verification_targets`, `answer_format`, and `terminal_policy` before execution.
- **Borrowed Pattern:** `harness_round02_02_4` mutation-readiness checklist and `harness_round02_02_8` compact ledger discipline.
- **Preserved Behavior:** Keep compact planning and single-executor action.
- **Implementation Shape:** Code-free design: planning emits a strict compact schema; a lightweight validator repairs or normalizes malformed fields; action reads a structured ledger object or a canonical text block with guaranteed field names. Read-only lookup steps must become evidence or transform slots, not mutation slots.
- **Generalization Rationale:** Every unseen task needs the executor to know what must be observed, changed, transformed, or verified before commitment.
- **Complexity:** Medium
- **Expected Impact:** Lower EnvScaler partial completion and better terminal readiness; fewer route-semantic errors in SearchQA and ToolHop.
- **Regression Risk:** Overly rigid validation could reject useful plans; the validator should normalize concise plans rather than create long replanning loops.

**[Direction 2: All-Slot Stateful Completion Gate]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Blocker-after-progress premature completion
- **Current Weakness:** `partial_commit_on_blocker` and `ledger_or_progress` allow completion after one successful mutation or successful real call even when required operations failed.
- **Desired Behavior:** The action module should call `complete_task` only when every required mutation slot is succeeded or verified, or when an explicit irrecoverable blocker policy is reached without falsely reporting completion.
- **Borrowed Pattern:** `harness_round02_02_4` mutation readiness; negative lesson from current winner and fail-soft variants.
- **Preserved Behavior:** Keep one mutating executor and hard schema preflight.
- **Implementation Shape:** Track mutation slots as pending/succeeded/verified/blocked-recoverable/blocked-irrecoverable. Successful observation text should update only the matching operation slot. Repeated failures should trigger repair routing, not completion.
- **Generalization Rationale:** Stateful domains differ in tools, but exact final-state completion always depends on all requested operations.
- **Complexity:** Medium
- **Expected Impact:** Fewer low-score `Task Completed` outcomes, lower false done rate, and better EnvScaler score buckets.
- **Regression Risk:** Too-strict completion could increase max-step or nontermination; include a bounded blocked-state exit that does not call successful completion unless allowed by the environment contract.

**[Direction 3: Slot-Bound Answer Support and Hop Provenance]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Distractor-supported wrong final answers
- **Current Weakness:** The support gate accepts answer strings or overlapping tokens in evidence without proving the requested relation or transform.
- **Desired Behavior:** Final answers should be accepted only when each requested answer slot has a source observation, relation binding, optional transform, and final candidate derivation.
- **Borrowed Pattern:** `harness_round02_02_3` hop provenance and `harness_round01_4` read-only evidence gate.
- **Preserved Behavior:** Keep support records and commit-time canonicalization, but make them relation-aware.
- **Implementation Shape:** For read-only and ToolHop routes, maintain compact support records: slot, source tool, source text, extracted candidate, relation/condition, transform, contradiction note, final value. Boolean and comparison questions require both sides. "Not found" answers require explicit answer-format permission.
- **Generalization Rationale:** Distractor spans appear in any retrieval corpus; slot-bound provenance is reusable across entities, relations, dates, counts, and transforms.
- **Complexity:** Medium
- **Expected Impact:** Fewer wrong supported final answers in SearchQA and ToolHop; higher subEM and answer correctness.
- **Regression Risk:** If too conservative, the agent may over-search; cap evidence gathering and allow deterministic transforms from observed inputs.

**[Direction 4: Bounded Failure-Class Repair Router]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Guarded low-value exploration loop
- **Current Weakness:** Guard feedback is textual and does not force a changed strategy after repeated failures.
- **Desired Behavior:** The next action after a failed call should be routed by failure class to a different repair move, not another same-signature retry.
- **Borrowed Pattern:** `harness_round01_2` failed-call cooldown and `harness_round02_02_5` recovery router.
- **Preserved Behavior:** Keep schema preflight, failed-signature tracking, and concise recovery messages.
- **Implementation Shape:** Maintain a compact repair state keyed by slot and call signature. Schema errors trigger exact-schema retry or argument drop/fill. Not-found errors trigger broader list/search/get. Enum errors trigger valid-option inspection. Repeat errors force a new identifier source or relation path. Transform-tool schema failure allows local deterministic calculation when inputs are observed.
- **Generalization Rationale:** Tool APIs across domains fail through recurring interface classes, so a bounded repair router transfers without knowing task-specific entities.
- **Complexity:** Medium
- **Expected Impact:** Fewer repeated failed calls, fewer low-value search loops, better ToolHop path completion, and lower token waste.
- **Regression Risk:** Forced diversification can wander; expire repair state after new useful evidence and cap repair attempts per slot.

**[Direction 5: Compact Route-Aware Memory Lessons]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Long stale failure snippets as weak workflow hints
- **Current Weakness:** Memory retrieval can inject long raw traces with stale IDs, schemas, and truncated failed calls.
- **Desired Behavior:** Memory should provide short, route-aware, failure-class lessons and provenance labels, not environment-local traces.
- **Borrowed Pattern:** `harness_round01_6` provenance-aware memory and `harness_round02_02_7` task/tool-family routing.
- **Preserved Behavior:** Keep memory as a soft procedural hint and preserve current-observation authority.
- **Implementation Shape:** Store abstract records keyed by route, tool family, failure class, and repair principle. At BEGIN, inject at most two short lessons. During execution, inject only phase reminders relevant to the current blocker.
- **Generalization Rationale:** Abstract procedural lessons transfer across unseen tasks, while stale entity IDs do not.
- **Complexity:** Low
- **Expected Impact:** Less prompt distraction, more stable planning, and fewer copied stale schemas.
- **Regression Risk:** Over-compression may remove useful schema reminders; keep one concise schema principle when schema errors dominate.

**[Direction 6: Round-Consistent Builder Metadata]**
- **Target Module:** Builder/Wiring
- **Stage 1 Failure Addressed:** Builder / wiring identity mismatch
- **Current Weakness:** The `round_03_03` snapshot still declares `round02_02` names, metadata, and pairing identifiers.
- **Desired Behavior:** Stage 3 should generate consistent harness identity, round, candidate index, policy metadata, and description while preserving factory compatibility.
- **Borrowed Pattern:** None
- **Preserved Behavior:** Keep the current factory contract and provider wiring shape.
- **Implementation Shape:** Update constants and metadata only; do not alter external evaluator assumptions or module import contracts.
- **Generalization Rationale:** Accurate metadata is necessary for registry comparison, trace attribution, and later evolution prompts.
- **Complexity:** Low
- **Expected Impact:** Cleaner experiment tracking and fewer downstream prompt mismatches.
- **Regression Risk:** Renaming imports incorrectly could break factory loading; keep module class names and exports compatible.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The Stage 3 harness should be a planning-guided, single-executor ReAct harness with compact verified ledgers, strict stateful completion, relation-grounded answer support, and bounded repair routing. It should feel like the current winner tightened at its weak joints: still direct, low-overhead, and schema-aware, but no longer willing to treat partial progress as completion or span occurrence as proof.

#### 6.2 Module-Level Blueprint

##### Planning Blueprint

Implement route-specific compact planning with validated fields for evidence slots, dependency edges, mutation slots, verification targets, answer format, and terminal policy. Preserve the winner's short plan packets and summary updates. Avoid JSON tool-call plans as initial planning output and avoid putting concrete final answers into `next_tool_intent` before evidence exists. The evidence is the 579/658 EnvScaler tool-like plans and the read-only mutation drift found in Stage 1. The design is task-general because every task can be classified into read-only lookup, multi-hop lookup, deterministic transform, stateful mutation, or mixed route.

##### Action Blueprint

Keep one executor as the only component allowed to mutate state or call task tools. Implement stricter terminal readiness, slot-bound support records, and bounded repair state. Preserve schema preflight, failed-signature tracking, support records, date/binary canonicalization, and concise recovery messages. Avoid multiple acting agents, progress-based partial completion, and repeated same-query loops. Evidence comes from 297 EnvScaler partial commits, 202/205 incorrect SearchQA tasks with `support_ok: True`, and 393 repeated failed calls overall. The design is task-general because it operates on tool-call outcomes, slots, relations, and failure classes rather than benchmark entities.

Agent collaboration should remain minimal. If a verifier is added, it must be non-acting and local: a compact audit before `final_answer` or `complete_task`, not a separate worker that touches the environment. This borrows the safe part of route-verifier examples while avoiding heavy AgentOrchestra-style cost and handoff risk.

##### Memory Blueprint

Implement compact route-aware memory that provides phase guidance and failure-class lessons. Preserve the observed/derived/hypothesis distinction and the rule that memory never counts as current evidence. Avoid long raw trace snippets, stale IDs, and broad token-overlap retrieval that injects unrelated old failures. Evidence comes from Stage 1 example 460, where old EHR failure traces were lengthy but did not prevent the actual ledger failure. The design is task-general because it stores reusable repair procedures, not task-specific facts.

##### Builder / Wiring Blueprint

Keep `builder.py`, provider exports, context preparation, and tool binding compatible with the harness factory. Update harness name, round metadata, policy names, and `Description.md` so they match the new round and generated design. Avoid changing evaluator-facing contracts or external benchmark behavior. The design is task-general because clean metadata and stable wiring support future comparison independent of task domain.

##### Interface Blueprint

Create a simple Planning -> Action contract. Action should be able to read a canonical ledger object or text block with guaranteed fields. Action observations should update slot status in the ledger, and terminal checks should consult this updated slot state. Avoid a complex new orchestration layer; the interface should be a checklist/status summary, not a separate planning service. Evidence comes from the `planned_mutations=0` collapse in stateful tasks and nonzero planned mutation drift in read-only tasks. The design is task-general because all routes need shared commitment criteria.

#### 6.3 Minimal Required Changes

- Add validated route ledger fields and reject or repair tool-call-shaped initial plans before action begins.
- Separate read-only evidence slots, deterministic transform slots, and stateful mutation slots.
- Disable or replace progress-based partial commit; require all stateful mutation slots to be succeeded or verified before `complete_task`.
- Upgrade final-answer support from span/token match to requested-slot support with relation and transform provenance.
- Add bounded failure-class repair state for schema, repeat, not-found, enum, authorization, empty-action, and transform-tool failures.
- Compress memory records into short route/failure-class procedural lessons with provenance labels.
- Update builder metadata and description to the new round and harness identity.

#### 6.4 Optional Enhancements

- Add a non-acting local audit only before final answer or stateful completion when slot support is ambiguous.
- Add a deterministic-transform helper policy that permits local arithmetic/string/date transforms after inputs are observed and transform tools fail.
- Add compact query-diversification hints for SearchQA after two low-value repeated searches.
- Add a small ledger status tool only if it is disabled by default or invoked under strict blocker conditions.
- Add narrow output-format canonicalization for dates, binary strings, lists, and aliases, provided it never substitutes for missing evidence.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] The initial plan must be a compact validated ledger, not a JSON tool-call proposal.
- [Planning] The plan must classify route as read-only lookup, multi-hop lookup, deterministic transform, stateful mutation, mixed, or unknown.
- [Planning] Read-only search, lookup, and transform steps must not be placed in `required_mutations`.
- [Planning] `next_tool_intent` may name a tool purpose but must not propose a concrete unsupported final answer.
- [Action] Only one executor may call task tools or mutate environment state.
- [Action] `complete_task` must require all required mutation slots to be succeeded or verified.
- [Action] A blocker after partial progress must trigger repair or explicit blocked-state handling, not automatic successful completion.
- [Action] Final-answer support must bind the candidate to requested slots, relations, source observations, and deterministic transforms.
- [Action] Span occurrence in a search result is insufficient support when the relation or comparison is unverified.
- [Action] Repeated failed calls must enter a bounded repair route that changes identifier source, schema shape, query, relation path, or tool family.
- [Action] Transform-tool failures may be repaired by deterministic local computation only when all input values are already observed.
- [Action] Any verifier must be non-acting, local, and route-triggered; do not add multiple acting agents.
- [Memory] Memory must be compact, route-aware, provenance-labeled, and treated only as procedural guidance.
- [Memory] Do not retrieve long raw trace snippets with stale environment IDs unless explicitly summarized into abstract lessons.
- [Builder] Harness name, round metadata, description, and policy labels must match the generated round and design.
- [Interface] Planning and Action must share the same canonical ledger fields and terminal criteria.
- [Preserve] Preserve hard schema preflight, failed-signature tracking, support-record finalization, compact planning, and current-observation authority.
- [Avoid] Do not copy whole peer harnesses or introduce heavy AgentOrchestra-style orchestration.
- [Avoid] Do not hard-code benchmark item IDs, answers, entity names, tool traces, or golden values.
- [Avoid] Do not improve SearchQA by merely increasing search count; improve slot binding and query targeting.
- [Avoid] Do not improve EnvScaler done rate by relaxing completion; improve exact mutation closure.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
