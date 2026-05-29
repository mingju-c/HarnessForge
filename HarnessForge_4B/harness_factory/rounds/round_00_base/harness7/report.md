# harness7 Analysis

## Structure
- Planning: outline a few parallel angles worth checking.
- Action: launch a direct batch of generic solvers and compare their reports.
- Memory: maintain a compact running cheatsheet of reusable findings.

## Aggregate Metrics
- Evaluated tasks: 80
- Exact accuracy: 20.0%
- Valid answer rate: 100.0%
- Average path score: 0.3796
- Average actions: 1.04
- Average tool calls: 4.11
- Prompt / completion / total tokens: 292308 / 36178 / 328486
- Average prompt / completion / total tokens: 3653.85 / 452.23 / 4106.07
- Total runtime: 83.65 min
- Average runtime per task: 62.74 sec

## Overall Assessment
This harness is another strong negative example for ToolHop: it keeps explicit token cost low, but the quality collapse is severe because the whole design assumes that parallel solver diversity will compensate for weak dependency control. That assumption can make sense for open-ended QA or verification-style tasks, but it is poorly matched to serial tool chains. It is more suitable for tasks where multiple independent attempts can be compared without strict state sharing. It is much less suitable for benchmark items where one early entity or argument mistake poisons every downstream step.

## Failure Pattern Analysis
- The harness almost always stops too early. An average of 1.04 actions means most runs are effectively one batch of parallel guesses plus a synthesis step.
- Parallel reports are not being grounded tightly enough in tool observations. As a result, the final answer can look coherent while still being disconnected from the actual benchmark path.
- The path score is higher than the exact score, so some useful intermediate structure is being found, but the return from parallel branching is much weaker than the confidence it creates.
- The weakest categories are the ones that need disciplined post-processing and formatting, which is exactly where a loose parallel-solver architecture tends to break.

## Module-level Diagnosis
### Planning
- What Helps: The planning layer does keep the initial structure concise and easy to execute, which avoids the overhead of heavy orchestration.
- What Hurts: Planning is built around parallel-friendly angles rather than dependency-sensitive execution. That framing is fundamentally mismatched to many ToolHop tasks.

### Action
- What Helps: Batch execution can surface multiple hypotheses quickly, and that can be useful when branches are genuinely independent.
- What Hurts: The action layer relies too heavily on branch comparison instead of branch validation. It compares reports before ensuring that the reports are grounded in the right upstream facts.

### Memory
- What Helps: A compact cheatsheet is a sensible lightweight memory form and may help preserve recurring hints or tool usage patterns.
- What Hurts: The memory layer does not provide strong enough constraints to stabilize branch outputs. It stores useful fragments, but it does not fix the harness's core synthesis weakness.
