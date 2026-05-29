# harness6 Analysis

## Structure
- Planning: create a short parallel work outline for a fixed worker pool.
- Action: one coordinator delegates focused subtasks to generic workers and merges the results.
- Memory: reusable skill-like procedures can be surfaced during execution.

## Aggregate Metrics
- Evaluated tasks: 80
- Exact accuracy: 30.0%
- Valid answer rate: 100.0%
- Average path score: 0.4711
- Average actions: 1.24
- Average tool calls: 2.64
- Prompt / completion / total tokens: 299745 / 32453 / 332198
- Average prompt / completion / total tokens: 3746.81 / 405.66 / 4152.48
- Total runtime: 77.77 min
- Average runtime per task: 58.32 sec

## Overall Assessment
This harness keeps explicit cost low, but it under-delivers on quality because the worker-pool design is too shallow for ToolHop's dependency structure. The fixed-pool coordination style is appealing from an efficiency standpoint, yet it repeatedly shows that cheap delegation is not the same thing as reliable multi-hop execution. It may be more suitable for bounded subtasks where each worker receives a fully specified input and can solve independently. It is not a strong fit for chained tool tasks where downstream workers need exact upstream results before they can do anything meaningful.

## Failure Pattern Analysis
- Early termination is the main issue. With just 1.24 actions on average, the harness often delegates once, collects partial worker output, and commits before the chain has been validated.
- Worker reports are too weakly constrained by upstream state. When a subtask is underspecified, the worker tends to guess rather than explicitly request missing dependencies.
- The path score is materially above exact accuracy, which shows the harness sometimes reaches part of the correct chain but loses precision when merging worker outputs.
- This design is structurally better for light decomposition than for true dependency management. ToolHop punishes that mismatch very clearly.

## Module-level Diagnosis
### Planning
- What Helps: The short work outline keeps coordination overhead low and makes the overall execution policy easy to follow.
- What Hurts: Planning is too lightweight for the benchmark. It does not enforce dependency readiness strongly enough before tasks are handed to workers.

### Action
- What Helps: The fixed worker pool is cheap and operationally simple. For small independent subtasks, that simplicity could be valuable.
- What Hurts: The action layer is under-reasoned for ToolHop. The coordinator delegates too early, and the merge step is not rigorous enough to recover when a worker worked from incomplete context.

### Memory
- What Helps: Skill-like memory could, in principle, help workers reuse known tool patterns or small procedural routines.
- What Hurts: Memory does not offset the central execution flaw. The harness's main weakness is incorrect decomposition timing, not the absence of reusable local skills.
