# harness4 Analysis

## Structure
- Planning: decide how much parallel investigation the task deserves.
- Action: a coordinator launches multiple focused investigators, then synthesizes their findings.
- Memory: workflow traces can be retrieved to ground later decisions.

## Aggregate Metrics
- Evaluated tasks: 80
- Exact accuracy: 20.0%
- Valid answer rate: 100.0%
- Average path score: 0.2985
- Average actions: 1.35
- Average tool calls: 2.28
- Prompt / completion / total tokens: 328807 / 44542 / 373349
- Average prompt / completion / total tokens: 4110.09 / 556.77 / 4666.86
- Total runtime: 115.86 min
- Average runtime per task: 86.90 sec

## Overall Assessment
This harness is a clear example of low explicit cost per trace but weak return on quality. The design assumes that parallel investigation and coordinator synthesis will compensate for uncertainty, but ToolHop often needs controlled serial dependency resolution instead. It may be a better fit for evidence aggregation or verification-style tasks where branches are largely independent. It is a poor fit for multi-hop tool questions where downstream subtasks depend tightly on exact upstream entities and arguments.

## Failure Pattern Analysis
- The harness terminates far too early for the benchmark. Its average action depth is extremely low, and many failures look like one investigation wave followed immediately by synthesis and answer commitment.
- The coordinator is too eager to trust branch summaries. That is especially harmful in ToolHop, where a clean-sounding branch report can still be wrong if one dependency was never actually validated.
- The path score is also weak, so this is not only a final-answer problem. The harness frequently fails before it has built a reliable multi-hop chain at all.
- Parallel investigation is being used where sequential execution is required. That makes the system structurally mismatched to questions whose later steps depend on exact results from earlier tool calls.

## Module-level Diagnosis
### Planning
- What Helps: The planning idea is reasonable for tasks with genuine uncertainty because it tries to allocate effort based on perceived ambiguity.
- What Hurts: Planning overestimates the value of parallel evidence gathering for ToolHop. It does not sufficiently distinguish between independent uncertainty and strict dependency chains.

### Action
- What Helps: The coordinator-investigator split is clean and easy to interpret. In principle, it could work well for branch-and-compare problems.
- What Hurts: The action layer is severely under-reasoned for this benchmark. It launches branches, gathers shallow reports, and synthesizes too soon, leaving no robust repair path when a branch is wrong.

### Memory
- What Helps: Workflow-memory traces may help the coordinator recognize recurring orchestration patterns.
- What Hurts: Memory does not rescue the core mismatch here. The harness's main problem is not forgetting prior traces, but choosing the wrong execution topology for dependency-heavy tasks.
