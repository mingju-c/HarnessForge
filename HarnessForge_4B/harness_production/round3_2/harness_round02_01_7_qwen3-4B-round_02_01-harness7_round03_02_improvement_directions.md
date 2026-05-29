### PART 1: LOCALIZATION SUMMARY

The current winner under this Stage 2 brief is `harness_round02_01_7`, evaluated as `qwen3-4B-round_02_01-harness7` in `round03_02`. Its architecture is a direct single-executor guarded ReAct harness: `builder.py` wires `PlanningClass` from `planning_module/provider.py`, `ACTION_SYSTEM = "evidence_search_react"`, and `MEMORY_SYSTEM = "round02_search_evidence_memory"`. Planning tries to produce compact evidence and mutation packets. Action owns all real tool calls, schema preflight, repeated-call blocking, strict support records, SearchQA raw-query repair, answer canonicalization, route-aware terminal checks, and partial commit after blockers. Memory provides phase guidance, stores successes and failures, skips old SearchQA trajectory retrieval, and retrieves task-signature memories for ToolHop and EnvScaler.

Stage 1 identifies five dominant transferable failures. First, EnvScaler planning collapses into immediate tool-call JSON on all 658 stateful runs, so Action never receives a durable mutation checklist and often completes after partial progress. Second, guard blocks detect unknown tools, missing keys, repeated calls, and not-found or permission failures, but do not route concrete recovery. Third, SearchQA often has evidence but commits a distractor span, full sentence, or over-broad answer instead of the minimal requested raw span. Fourth, ToolHop multi-hop provenance breaks after failed intermediate lookups, causing transforms on the original subject, stale memory entities, or unrelated values. Fifth, memory retrieval for ToolHop and EnvScaler includes concrete old entity names, IDs, dates, UUIDs, and trace values that sometimes leak into current action.

Module attribution is therefore concentrated in Cross-Module Interface, Action, and Memory. Cross-Module Interface must make Planning's evidence, mutation, terminal, and provenance state enforceable by Action. Action must keep the single executor and hard guards, but add a bounded recovery router, final-answer relevance arbitration, and stricter completion criteria. Memory must preserve phase-aware procedural guidance and SearchQA leakage prevention while abstracting or quarantining old trace values.

The highest-leverage repair targets are: a structured Planning -> Action ledger for stateful mutations and multi-hop provenance; an Action-side failure-class recovery router; an evidence-linked raw-answer canonicalizer for short-answer retrieval; a terminal policy that blocks `complete_task` until the mutation ledger is satisfied; and Memory-side abstraction plus evidence quarantine. Behaviors to preserve are the direct single-executor topology, hard schema preflight, repeated-call cooldown, SearchQA raw-query first-search behavior, support-record logging, compact planning, and memory's distinction between observations, derived facts, hypotheses, and old memories.

### PART 2: HARNESS EXAMPLE REVIEW

#### Example: `harness_round02_02_1`

- **Observed Structure:** Compact evidence and mutation slot ledger, single executor, route-aware support gates, repeated-call recovery, and task-signature memory.
- **Relevant Strength:** Best full-run `round02_02` overall score with relatively low cost: mixed primary 0.4438, SearchQA search use 1.0, and lower average time/tokens than most round02 variants. It demonstrates a compact ledger can be fast enough for full evaluation.
- **Relevant Weakness / Risk:** It still trails its round01 parent and does not fully solve ToolHop provenance or EnvScaler score gaps. Its completion policy remains ledger-or-progress rather than strict full-checklist closure.
- **Related Winner Failure:** EnvScaler partial completion and planning/action ledger collapse.
- **Transferable Module Pattern:** Borrow the compact slot-ledger framing and keep ledger records short enough for frequent Action use.
- **Generalization Rationale:** A compact slot ledger is domain-agnostic: the same mechanism tracks required facts, API mutations, verification observations, and terminal readiness across different tool families.
- **Do Not Borrow:** Do not borrow any progress-based completion shortcut that permits `complete_task` before every required mutation is verified.
- **Transfer Confidence:** High

#### Example: `harness_round02_01_2`

- **Observed Structure:** Route-aware single executor with a read-only ledger review tool, strict support linkage, schema preflight, repeated-call cooldown, and task-signature memory.
- **Relevant Strength:** Full-run `round02_01` candidate with strong EnvScaler score 0.4495 and reliable SearchQA search use. It explicitly separates route classification, verifier review, final-answer support, and stateful terminal checks.
- **Relevant Weakness / Risk:** Extra verifier path raises tokens and API calls, and it still does not beat the parent overall. If used too frequently, ledger review becomes overhead rather than control.
- **Related Winner Failure:** Guard blocks without recovery, unsupported finalization, and terminal readiness confusion.
- **Transferable Module Pattern:** Borrow a bounded non-acting verifier/review concept for readiness and recovery, but trigger it only after ambiguity, guard blocks, or final-answer risk.
- **Generalization Rationale:** A non-acting verifier can inspect tool schemas, slot state, support records, and terminal contracts without creating unsafe parallel state mutations.
- **Do Not Borrow:** Do not enable review on every step or create a second acting agent.
- **Transfer Confidence:** High

#### Example: `harness_round02_02_3`

- **Observed Structure:** Multi-hop provenance harness with one executor, ordered source/relation/intermediate/transform/final slots, strict read-only support gates, and compact procedure memory.
- **Relevant Strength:** Best full-run `round02_02` ToolHop correctness and path score among that family. It directly demonstrates the hop-chain pattern needed for provenance failures.
- **Relevant Weakness / Risk:** It is expensive, with high time, tokens, API calls, and max-step markers, and it weakens EnvScaler done rate. The full policy is too costly as a global default.
- **Related Winner Failure:** Multi-hop ToolHop provenance breaks after failed intermediate lookups.
- **Transferable Module Pattern:** Borrow the ordered hop-chain record for read-only and transform routes only: source entity, relation tool, observed target, derived field, transform input, transform output, final value.
- **Generalization Rationale:** Multi-hop reasoning in any domain requires knowing which observation supports which downstream transform; this is independent of entity names or benchmark items.
- **Do Not Borrow:** Do not apply full hop-chain verbosity to simple SearchQA or stateful EnvScaler tasks.
- **Transfer Confidence:** High

#### Example: `harness_round02_01_5`

- **Observed Structure:** Fail-soft recovery harness that turns guard blocks into recovery routes, keeps a single executor, uses compact failure lessons, and preserves reliable search use.
- **Relevant Strength:** Strongest full-run `round02_01` SearchQA subEM at 0.5108, reliable search use, and an explicit recovery framing for schema, not-found, repeat, authorization, and empty-action cases.
- **Relevant Weakness / Risk:** Overall score trails `harness_round02_01_7`; ToolHop is weaker; soft support and partial completion can allow unsupported or incomplete commitments if copied directly.
- **Related Winner Failure:** Guard blocks detect errors but do not route recovery.
- **Transferable Module Pattern:** Borrow failure-class taxonomy and bounded recovery routes, but combine them with stricter support and mutation-ledger completion.
- **Generalization Rationale:** Failure classes transfer across tools even when tool names differ: schema errors, invalid IDs, not-found results, authorization failures, repeats, and empty steps recur in unseen APIs.
- **Do Not Borrow:** Do not borrow soft final support or progress-based partial completion as a default.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_5`

- **Observed Structure:** Recovery-router harness mapping schema, ID, enum, not-found, repeat, authorization, and empty-action failures to bounded repair routes.
- **Relevant Strength:** Best partial `round02_02` overall score and high partial EnvScaler done rate; its failure taxonomy is directly aligned with Stage 1's recovery gap.
- **Relevant Weakness / Risk:** It is partial-only and not standout on ToolHop or SearchQA. Recovery overhead must be reduced before full-run use.
- **Related Winner Failure:** Repeated guard-block loops and unknown-tool recovery failures.
- **Transferable Module Pattern:** Borrow the failure-class router as a compact Action helper or prompt protocol, especially for after-guard next-action constraints.
- **Generalization Rationale:** A failure-class router acts on abstract error types rather than memorized task traces.
- **Do Not Borrow:** Do not let recovery routing override the current ledger's pending slot or retry forever.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_6`

- **Observed Structure:** Commit-time format harness with compact answer-format and terminal contracts, route-aware support, repeated-call recovery, and normalization at final-answer time.
- **Relevant Strength:** Best full-run `round02_02` SearchQA subEM at 0.4985 and relatively efficient among full `round02_02` candidates. It shows exact-format control can be a lightweight add-on.
- **Relevant Weakness / Risk:** ToolHop remains weak compared with hop-chain candidates, and format normalization alone cannot repair broken evidence dependencies.
- **Related Winner Failure:** SearchQA overlong answers, raw-span failures, and terminal/format contract confusion.
- **Transferable Module Pattern:** Borrow a narrow commit-time format contract that predicts raw answer type, allows minimal span extraction, and preserves surface forms when requested.
- **Generalization Rationale:** Exact-answer tasks across domains require output contracts independent of benchmark labels: city-only, date-only, number-only, list-only, unit-preserving, or surface-form preserving.
- **Do Not Borrow:** Do not globally canonicalize dates or strip units; normalization must be route- and evidence-aware.
- **Transfer Confidence:** High

#### Example: `harness_round01_3`

- **Observed Structure:** Partial round01 stateful mutation-ledger harness with required state mutations, expected verification, and terminal criteria.
- **Relevant Strength:** The design directly targets stateful completion and reached strong partial SearchQA/stateful signals on a 200-task run.
- **Relevant Weakness / Risk:** Partial-only, weak ToolHop, and high token cost for the slice. It should be treated as a design ingredient rather than a quality parent.
- **Related Winner Failure:** EnvScaler done-but-partial completion without a complete mutation checklist.
- **Transferable Module Pattern:** Borrow the idea of explicit required mutations with verification observations and terminal criteria.
- **Generalization Rationale:** Stateful tasks in any API environment can be decomposed into requested mutation rows with verification evidence.
- **Do Not Borrow:** Do not copy the full policy or promote it as a global architecture without ToolHop repair.
- **Transfer Confidence:** Medium

#### Example: `harness_round01_6`

- **Observed Structure:** Provenance-aware memory harness separating live observations, derived facts, hypotheses, and old memory.
- **Relevant Strength:** Strong partial overall score and useful memory labeling. It directly addresses the Stage 1 memory-leak weakness by preventing old memory from masquerading as current evidence.
- **Relevant Weakness / Risk:** Partial-only and weaker ToolHop than the strongest full candidates. Provenance labels alone are insufficient unless Action enforces them.
- **Related Winner Failure:** Retrieved memory contains concrete old trace values that leak into current action.
- **Transferable Module Pattern:** Borrow provenance-labeled memory formatting and memory-as-procedure-only discipline.
- **Generalization Rationale:** Separating current evidence from old procedural hints prevents stale entity and ID transfer across unseen tasks.
- **Do Not Borrow:** Do not expose long old trajectory snippets or concrete values without masking.
- **Transfer Confidence:** Medium

#### Example: `harness_round02_02_8`

- **Observed Structure:** Low-overhead light-ledger variant with one executor, evidence support records, recovery state, softer gates, sparse memory, and no explicit review tool.
- **Relevant Strength:** Best partial `round02_02` EnvScaler score and done rate, lowest partial runtime/tokens/max-step markers. It is useful as a cost-control example.
- **Relevant Weakness / Risk:** Weak ToolHop and SearchQA subEM; soft gates can preserve efficiency but fail answer arbitration.
- **Related Winner Failure:** High token cost and long blocked traces after guard loops.
- **Transferable Module Pattern:** Borrow light ledger compression and sparse memory exposure after the stricter ledger and support rules are in place.
- **Generalization Rationale:** Compact state representations and sparse reminders reduce cost across domains.
- **Do Not Borrow:** Do not borrow soft support gates or relaxed repeat behavior for final-answer correctness.
- **Transfer Confidence:** Medium

#### Example: `harness5`

- **Observed Structure:** Heavy AgentOrchestra-style multi-agent harness with broader role coordination and fusion memory.
- **Relevant Strength:** It shows that richer checking can improve coverage in some cases.
- **Relevant Weakness / Risk:** Highest token cost and max-step rate in the seed pool; heavy orchestration appears too costly for the local model and mixed task setting.
- **Related Winner Failure:** Mostly a negative control for the temptation to add broad multi-agent collaboration.
- **Transferable Module Pattern:** Borrow only the abstract separation between executor and verifier responsibilities, compressed into a non-acting verifier.
- **Generalization Rationale:** Verification is useful, but multiple acting agents are unsafe for stateful environments and costly for simple retrieval.
- **Do Not Borrow:** Do not copy full AgentOrchestra, broad fusion memory exposure, or multiple environment-acting agents.
- **Transfer Confidence:** Low

### PART 3: MODULE TRANSFER MATRIX

| Target Module | Winner Problem | Generalized Capability Gap | Borrow From | Borrow Pattern | Generalization Rationale | Avoid From Example | Confidence | Implementation Complexity |
|---|---|---|---|---|---|---|---|---|
| Planning | EnvScaler plans become first-action JSON and ToolHop plans do not enforce dependencies | Missing normalized task packet with required mutations, hop dependencies, terminal policy, and answer format | `harness_round02_02_1`, `harness_round01_3` | Compact slot and mutation ledger planning | Structured planning fields transfer across stateful, lookup, and transform tasks | Long or verbose planning from costly hop-chain variants | High | Medium |
| Action - tool-use repair | Guard blocks diagnose errors but do not route recovery | Missing bounded failure-class recovery after schema, ID, enum, not-found, repeat, authorization, and empty-action failures | `harness_round02_01_5`, `harness_round02_02_5` | Failure-class router with next-action constraints | Error classes recur across unseen tool schemas | Soft support and unbounded fail-soft completion from recovery variants | High | Medium |
| Action - answer arbitration | SearchQA final answers are evidence-present but wrong or overlong | Missing relevance-linked support and minimal raw-span canonicalization | `harness_round02_02_6`, `harness_round02_01_2` | Commit-time format contract plus bounded non-acting support review | Exact-answer tasks need slot-specific support and raw output across domains | Global date canonicalization or review on every simple answer | High | Medium |
| Action - orchestration | Single executor lacks verification, but heavy multi-agent execution is risky | Need one executor plus bounded non-acting verifier, not multiple actors | `harness_round02_01_2`, negative control `harness5` | Triggered verifier for guard clusters and final readiness | Non-acting verification is safe for stateful tools and useful for read-only tasks | Full AgentOrchestra, parallel acting, broad debate | High | Medium |
| Memory | Old concrete traces leak into current ToolHop and EnvScaler action | Missing abstract procedural memory and memory-value quarantine | `harness_round01_6`, `harness_round02_02_7` | Provenance-labeled, task-signature memory with masked concrete values | Workflow and failure-class memories transfer better than old entity names or IDs | Cerebra-style broad memory exposure and long trajectory snippets | Medium | Medium |
| Cross-Module Interface | Planning text is advisory and Action uses heuristic ledger only | Missing enforceable Planning -> Action ledger and terminal contract | `harness_round02_02_1`, `harness_round02_02_3` | Runtime ledger for mutation closure and hop provenance | Stateful and multi-hop tasks both need durable slot status independent of domain | Progress-based completion shortcuts | High | High |
| Builder/Wiring | Metadata and context do not guarantee plan/action contract visibility | Need local wiring for policy metadata, ledger settings, and memory quarantine flags | None; repair within winner pattern | Expose harness policy and route configuration to modules | Clear metadata helps Stage 3 and later diagnostics compare behavior | Whole-architecture replacement | Medium | Low |

### PART 4: PRESERVE / BORROW / AVOID

#### Preserve

- Preserve the single acting executor in Action because it avoids conflicting state mutations and already solves many simple SearchQA and ToolHop cases.
- Preserve hard schema preflight in Action because unknown tools, extra keys, and missing keys are frequent and must not silently execute.
- Preserve repeated-call and low-value-repeat blocking in Action because Stage 1 shows repeat loops are common; the repair should route after blocks, not remove them.
- Preserve SearchQA raw-query first-search behavior in Action because successful SearchQA runs often solve with one raw search and one exact final answer.
- Preserve support-record logging in Action because it provides the right hook for stronger answer arbitration.
- Preserve compact planning packets in Planning because simple tasks should not pay for heavy orchestration.
- Preserve Memory's SearchQA no-retrieval policy because it prevents old answer/query leakage on short-answer retrieval tasks.
- Preserve phase-aware memory reminders that separate observed facts, derived facts, hypotheses, and old procedural hints.

#### Borrow

- Borrow from `harness_round02_02_1` into Cross-Module Interface: compact slot-ledger structure; expected benefit is enforceable task state with manageable cost; it generalizes because slots can represent facts, mutations, and terminal criteria.
- Borrow from `harness_round02_01_2` into Action: triggered non-acting ledger review; expected benefit is safer finalization and recovery after ambiguous evidence or guard clusters; it generalizes because it checks contracts rather than entities.
- Borrow from `harness_round02_02_3` into Planning and Action: ordered hop provenance for read-only transform tasks; expected benefit is fewer wrong-entity transforms; it generalizes to any dependency chain.
- Borrow from `harness_round02_01_5` and `harness_round02_02_5` into Action: failure-class recovery taxonomy; expected benefit is fewer unknown-tool, repeat, not-found, and authorization loops; it generalizes because error classes are domain-neutral.
- Borrow from `harness_round02_02_6` into Action: commit-time format contract and minimal canonicalization; expected benefit is better raw-answer exactness; it generalizes across date, city, number, unit, alias, and list answers.
- Borrow from `harness_round01_6` into Memory: provenance-labeled memory and old-memory quarantine; expected benefit is less stale entity/ID leakage; it generalizes because memory should transfer procedures, not values.
- Borrow from `harness_round02_02_8` into Action and Memory only as a cost-control pattern: compact ledgers and sparse memory exposure; expected benefit is lower token growth after stricter logic is added.

#### Avoid

- Avoid full AgentOrchestra-style `harness5` because multiple acting roles and broad fusion memory create complexity, cost, and state-safety regression.
- Avoid open-ended debate or parallel acting from router/debate patterns because stateful tools require one mutating executor; the risk is complexity and unsafe execution.
- Avoid soft support as the default from fail-soft variants because Stage 1 errors include plausible but unsupported answers; the risk is correctness regression.
- Avoid progress-based `complete_task` as a normal completion criterion because EnvScaler already has 563 done-but-partial runs; the risk is incomplete stateful success.
- Avoid applying full hop-chain verbosity to all routes because SearchQA and simple lookups need a fast path; the risk is cost and latency.
- Avoid global date or answer canonicalization because SearchQA sometimes requires evidence surface forms; the risk is exact-match regression.
- Avoid storing or retrieving concrete old entity names, UUIDs, answers, or trace arguments in Memory because Stage 1 shows those values can leak into current action; the risk is stale-memory contamination.
- Avoid benchmark-specific patches for observed item IDs, names, answers, entities, or golden traces; the risk is weak transfer and overfitting.

### PART 5: CONCRETE IMPROVEMENT DIRECTIONS

**[Direction 1: Enforceable Evidence, Hop, and Mutation Ledger]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Stateful plan contract collapses into first-action JSON and completion lacks a required-mutation ledger; Multi-hop ToolHop provenance breaks after failed intermediate lookups
- **Current Weakness:** Planning emits advisory text or malformed tool-call JSON, while Action relies on heuristic observation counts and local support records.
- **Desired Behavior:** The new harness should maintain a compact runtime ledger with route, evidence slots, dependency edges, hop provenance slots, required mutation rows, verification observations, blockers, terminal policy, and answer format.
- **Borrowed Pattern:** `harness_round02_02_1` compact slot ledger; `harness_round02_02_3` ordered hop-chain pattern; `harness_round01_3` mutation verification idea
- **Preserved Behavior:** Keep compact planning and single-executor execution.
- **Implementation Shape:** Require Planning to output a valid packet. If the model emits tool-call JSON as a plan, normalize it into a minimal packet rather than treating it as the checklist. Action updates ledger entries after each observation. `final_answer` requires completed relevant evidence/hop slots; `complete_task` requires all required mutations verified or explicitly marked impossible with a non-terminal blocker.
- **Generalization Rationale:** Evidence slots, dependency edges, mutation rows, and terminal readiness are task-general abstractions for search, ToolHop, and stateful APIs.
- **Complexity:** High
- **Expected Impact:** Should reduce EnvScaler done-but-partial runs, ToolHop wrong-entity transforms, and premature terminal calls.
- **Regression Risk:** Too much ledger overhead may slow SearchQA; simple read-only tasks should receive a one-slot fast ledger.

**[Direction 2: Failure-Class Recovery Router With Bounded Non-Acting Review]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Guard blocks detect tool errors but do not route recovery
- **Current Weakness:** `ROUND02_GUARD_BLOCK` gives text advice, but the model often repeats invalid calls, invents unavailable tools, or finalizes from blockers.
- **Desired Behavior:** After each guard block or failed observation, Action should classify the failure and constrain the next step: repair missing keys from current observations, drop unsupported extras only when safe, discover valid enum/ID sources through list/get/search tools, switch slots after repeated failure, or trigger a short non-acting verifier review.
- **Borrowed Pattern:** `harness_round02_01_5` and `harness_round02_02_5` failure-class recovery; `harness_round02_01_2` bounded ledger review
- **Preserved Behavior:** Keep hard schema preflight, failed-signature tracking, and repeated-call blocking.
- **Implementation Shape:** Add a small recovery state containing failure class, failed tool, failed arguments, observed valid alternatives, pending ledger slot, retry budget, and next-action class. The verifier is non-acting and may only approve retry, request an alternate valid tool class, or block terminal commitment.
- **Generalization Rationale:** Schema, ID, enum, not-found, authorization, repeat, and empty-action failures appear across unseen tool environments.
- **Complexity:** Medium
- **Expected Impact:** Should reduce repeated-failed-call and low-value-repeat buckets in ToolHop and EnvScaler while preserving strict validation.
- **Regression Risk:** Recovery may oversteer if it ignores current task semantics; every route must be tied to a pending ledger slot.

**[Direction 3: SearchQA-Safe Evidence Arbitration and Raw-Span Canonicalization]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** SearchQA final answers are evidence-present but not relevance- or span-canonicalized
- **Current Weakness:** The current support check proves an answer appears in evidence, but not that it is the relevant minimal answer for the question slot.
- **Desired Behavior:** For SearchQA and other short-answer retrieval routes, preserve raw-question first search, then finalize only a minimal supported span or complete requested list tied to the question slot. If the proposed answer is a full sentence containing a smaller supported answer, canonicalize to the raw span before `final_answer`.
- **Borrowed Pattern:** `harness_round02_02_6` format contract; `harness_round02_01_2` support review; preserve current winner's SearchQA raw-query guard
- **Preserved Behavior:** Keep SearchQA memory suppression, raw first-query repair, and support records.
- **Implementation Shape:** Add answer-type hints such as person, place, date, number, unit, title, alias, list, or description. Record candidate answer, source evidence record, surface match, minimal span, and distractor check. Restore evidence date surface for SearchQA unless the task explicitly requests normalization.
- **Generalization Rationale:** Exact short-answer retrieval in unseen domains requires relevance and raw-format discipline, not benchmark-specific answer knowledge.
- **Complexity:** Medium
- **Expected Impact:** Should improve SearchQA exact match and reduce wrong-but-supported distractor answers and overlong outputs.
- **Regression Risk:** Over-trimming may remove required units, aliases, or multi-item list members; the canonicalizer must preserve explicit format requirements.

**[Direction 4: Strict Stateful Completion Contract]**
- **Target Module:** Cross-Module Interface
- **Stage 1 Failure Addressed:** Stateful plan contract collapses into first-action JSON and completion lacks a required-mutation ledger
- **Current Weakness:** `completion_policy = "progress"` and partial commit allow completion after one successful mutation plus a blocker, even when the task has many required changes.
- **Desired Behavior:** Normal `complete_task` should be allowed only when the mutation ledger is complete. Partial completion should be a separate exceptional path that records which requirements are impossible, which observed blocker proves impossibility, and why no valid recovery route remains.
- **Borrowed Pattern:** `harness_round01_3` mutation verification; compactness from `harness_round02_02_8`
- **Preserved Behavior:** Preserve ability to make partial state progress and avoid duplicate terminal calls.
- **Implementation Shape:** Separate `terminal_ready`, `partial_blocked_ready`, and `not_ready`. `terminal_ready` requires all mutation rows verified. `partial_blocked_ready` cannot masquerade as full completion and should be rare; it should not auto-submit merely after one success.
- **Generalization Rationale:** Any stateful API task can require multiple independent changes; completing after partial progress is domain-independent failure.
- **Complexity:** Medium
- **Expected Impact:** Should reduce EnvScaler done-but-partial cases, especially after guard loops.
- **Regression Risk:** If too strict, tasks with irreversible external blockers may time out; the exceptional partial path must be bounded but available.

**[Direction 5: Abstract Memory and Evidence Quarantine]**
- **Target Module:** Memory
- **Stage 1 Failure Addressed:** Retrieved memory contains concrete old trace values that leak into current action
- **Current Weakness:** Retrieved memories contain concrete old entities, IDs, dates, UUIDs, and trace snippets, and Action has no guard against using memory-only values as current evidence.
- **Desired Behavior:** Memory should retrieve abstract, provenance-labeled procedural lessons rather than concrete traces. Concrete old values should be masked or omitted. Action should treat memory as non-evidence and reject memory-only values as tool arguments unless they also appear in the current task or current observations.
- **Borrowed Pattern:** `harness_round01_6` provenance-aware memory; `harness_round02_02_7` task-signature/tool-family routing
- **Preserved Behavior:** Preserve phase-aware reminders, failure lessons, and SearchQA no-retrieval/no-ingestion policy.
- **Implementation Shape:** Store lessons as failure-class or workflow rules, for example "after not-found ID failure, call list/get by current entity before retrying exact update." Downweight benchmark wrapper tokens. Mark memory blocks as `procedure_hint_only`. Track current-evidence strings separately from memory strings in Action.
- **Generalization Rationale:** Abstract procedure memories transfer across unseen tasks; stale values do not.
- **Complexity:** Medium
- **Expected Impact:** Should reduce ToolHop stale-entity failures and EnvScaler stale-ID/UUID errors while preserving useful recovery hints.
- **Regression Risk:** Over-masking could remove useful schema examples; keep tool-shape examples but replace concrete values with placeholders.

**[Direction 6: Compactness and Triggered Verification Budget]**
- **Target Module:** Action
- **Stage 1 Failure Addressed:** Guard-block loops, high token cost, and long blocked traces after repeated failures
- **Current Weakness:** Strict gates and memory retrieval can increase context length, but the enabled verifier/recovery mechanisms are not targeted enough.
- **Desired Behavior:** Verification, ledger review, and memory retrieval should be triggered by risk: final-answer ambiguity, guard clusters, repeated failures, or stateful terminal readiness. Simple direct SearchQA and one-hop ToolHop should stay fast.
- **Borrowed Pattern:** `harness_round02_02_8` light ledger and sparse memory exposure; negative lesson from `harness5` heavy orchestration
- **Preserved Behavior:** Preserve direct ReAct execution and support records.
- **Implementation Shape:** Use short ledger status lines, cap recent evidence records, retrieve no more than a small number of abstract memories, and avoid verifier calls when the ledger has a single completed slot with direct support.
- **Generalization Rationale:** Mixed unseen workloads include both simple and complex tasks; cost-aware triggering prevents the repair harness from regressing fast cases.
- **Complexity:** Low
- **Expected Impact:** Should reduce token growth while keeping stronger checks available for high-risk cases.
- **Regression Risk:** If triggers are too sparse, verifier benefits may disappear; final-answer and terminal-risk triggers must be mandatory.

### PART 6: GENERATION BLUEPRINT

#### 6.1 Candidate Harness Personality

The Stage 3 candidate should be a ledger-grounded direct ReAct harness: one acting executor, compact planning, strict schema guards, bounded recovery routing, short non-acting verification only when risk is high, SearchQA-safe raw retrieval, and memory that transfers procedures without leaking old values. The personality is direct but accountable: do not add broad orchestration, but make every final answer and stateful completion cite a current slot, support record, or verified mutation row.

#### 6.2 Module-Level Blueprint

**Planning Blueprint**

Implement a stricter compact packet with route, evidence slots, dependency edges, hop chain fields, required mutations, answer-format contract, terminal tool, and verification questions. Preserve short plans and periodic summaries. Avoid accepting first-action JSON as a valid plan; if the model emits that shape, normalize it into route and checklist fields before Action uses it. Evidence from Stage 1 shows all EnvScaler plans collapsed into tool-call JSON, so the generated Planning module must make stateful requirements explicit. This is task-general because slots and mutations are abstract workflow units.

**Action Blueprint, including concrete agent collaboration / orchestration if applicable**

Keep one executor as the only component that can call environment tools. Add a non-acting verifier/review mode, triggered only before risky finalization, after repeated guard blocks, or before stateful completion. Implement schema preflight, failed-call cooldown, failure-class recovery state, support records, SearchQA raw-query first-search repair, evidence-linked final-answer checks, and strict mutation-ledger completion. Preserve current support logging and canonicalization. Avoid full multi-agent execution, open-ended debate, global soft support, and progress-only completion. The evidence is Stage 1's repeated guard loops, SearchQA distractor answers, ToolHop wrong-entity transforms, and EnvScaler done-but-partial failures. This is task-general because Action reasons over schemas, observations, ledgers, and terminal contracts.

**Memory Blueprint**

Provide phase-aware guidance at BEGIN and sparse IN steps. Keep SearchQA old-memory suppression. Retrieve by route, tool family, workflow signature, and failure class rather than wrapper text. Store and retrieve abstract failure lessons and successful procedures with concrete values masked. Label every memory block as `procedure_hint_only`, not current evidence. Avoid long old trace snippets, concrete IDs, entity names, UUIDs, dates, or answers. Stage 1 showed `Donnchad Midi` and old dispute UUIDs leaking into current runs; the repair should prevent memory-only values from becoming tool arguments. This transfers because procedural recovery lessons are domain-neutral.

**Builder / Wiring Blueprint**

Keep harness factory compatibility: `builder.py`, `__init__.py`, `Description.md`, and the three provider modules. Wire the planning class, action system, memory system, project root, max tool calls, and harness metadata. Add policy metadata for ledger mode, recovery router, SearchQA fast path, memory quarantine, and strict completion. Preserve existing tool back-binding and OWL memory compatibility. Avoid metadata that says the wrong generation round or hides active policy settings. Builder changes are lightweight but important for later analysis and validation.

**Interface Blueprint, if needed**

Create a simple Planning -> Action runtime contract. The contract should expose a current ledger status with route, pending evidence slots, completed evidence slots, blocked slots, required mutations, verified mutations, terminal readiness, answer-format contract, and memory quarantine state. Action observations should update this ledger after each step. Memory -> Action should be explicitly non-evidential: the action module may read procedural hints, but concrete values from memory do not count as current evidence. This interface is needed because Stage 1 failures were not caused by one module alone; they arose when useful planning and memory concepts stayed advisory rather than enforceable.

#### 6.3 Minimal Required Changes

- Add a Planning -> Action ledger that represents evidence slots, hop dependencies, required mutations, verification observations, terminal policy, and answer format.
- Normalize malformed plan-as-tool JSON into a task packet before execution, especially for stateful routes.
- Block normal `complete_task` until every required mutation row is verified; remove one-success partial auto-completion as a normal path.
- Add an Action recovery router for schema, unknown-tool, missing-key, extra-key, invalid-enum, not-found, authorization, repeat, and empty-action failures.
- Add SearchQA-safe finalization: raw-question first search, current-evidence support, minimal raw-span or complete-list canonicalization, and evidence surface preservation for dates unless requested otherwise.
- Add multi-hop provenance checks so transform inputs must come from completed current-observation slots.
- Convert retrieved memory into masked, abstract procedure hints and prevent memory-only values from becoming current evidence.

#### 6.4 Optional Enhancements

- Add a lightweight non-acting `ledger_review` helper only if it is triggered by final-answer ambiguity, repeated guard blocks, or stateful terminal checks.
- Add route-specific ledger compression so simple SearchQA uses one evidence slot while ToolHop uses ordered hop slots and EnvScaler uses mutation rows.
- Add answer-type hints for person/place/date/number/unit/title/list/alias answers if they remain short and evidence-grounded.
- Add a small budget status line that reports recent evidence count, pending slots, failed signatures, and terminal readiness.
- Add memory scoring features for active tool names and failure classes, with benchmark wrapper tokens downweighted.

### PART 7: STAGE 3 CONSTRAINTS

- [Planning] Generate compact task packets with route, evidence slots, dependency edges, required mutations, answer format, terminal policy, and verification questions.
- [Planning] Do not allow a `{"think": ..., "tools": ...}` object to be the effective plan for stateful tasks; normalize or repair it into a checklist.
- [Planning] For multi-hop tasks, represent source entity, relation result, derived field, transform input, transform output, and final value as linked slots.
- [Action] Keep exactly one environment-acting executor.
- [Action] Preserve hard schema preflight, repeated-failed-call blocking, low-value-repeat blocking, and support-record logging.
- [Action] Add a bounded failure-class recovery router tied to pending ledger slots.
- [Action] Add non-acting verification only as a triggered readiness or recovery check; it must not call environment tools.
- [Action] For SearchQA, preserve raw-question first search before evidence exists and preserve evidence surface form for final spans unless the task asks for normalization.
- [Action] For final answers, require the candidate to be tied to the relevant current evidence or derived slot, not merely any evidence record.
- [Action] For transforms, require the transform input to come from a completed current-observation slot.
- [Action] Do not use progress-only completion as normal EnvScaler success; `complete_task` requires verified mutation ledger completion.
- [Memory] Keep SearchQA old-memory retrieval and ingestion suppressed unless memories are fully abstract and leakage-safe.
- [Memory] Store failure lessons and successful procedures as masked, abstract procedural rules rather than concrete old traces.
- [Memory] Label retrieved memories as procedure hints and never as current evidence.
- [Builder] Preserve harness factory compatibility and expose active policy metadata for ledger, recovery, SearchQA, completion, and memory quarantine.
- [Interface] Make Planning -> Action ledger state readable by Action code or prompts at every step.
- [Interface] Make Memory -> Action quarantine explicit: a concrete memory value cannot be used as a tool argument unless present in the current task or current observation.
- [Preserve] Preserve the winner's direct low-hop retrieval behavior and schema-guarded single-executor style.
- [Avoid] Do not copy whole peer harnesses; borrow only targeted module patterns tied to Stage 1 failures.
- [Avoid] Do not add item-specific answers, entity names, IDs, UUIDs, tool traces, or benchmark-specific golden values.
- [Avoid] Do not add heavy multi-agent orchestration, parallel acting, or broad debate for stateful tasks.
- [Avoid] Do not globally canonicalize dates, units, aliases, or lists without checking the requested answer format and evidence surface.

### PART 8: READY SIGNAL

```text
READY_FOR_HARNESS_GENERATION
```
