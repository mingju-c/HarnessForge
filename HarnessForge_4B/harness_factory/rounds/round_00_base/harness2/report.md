# harness2 Analysis

## Structure
- Planning: explicit task planning with regular status summarization.
- Action: one primary agent uses the current task tools directly.
- Memory: reusable workflow notes and prior solutions.

## Aggregate Metrics
- Evaluated tasks: 80
- Exact accuracy: 51.2%
- Valid answer rate: 100.0%
- Average path score: 0.6744
- Average actions: 5.35
- Average tool calls: 5.49
- Prompt / completion / total tokens: 2899146 / 100883 / 3000029
- Average prompt / completion / total tokens: 36239.32 / 1261.04 / 37500.36
- Total runtime: 81.06 min
- Average runtime per task: 60.79 sec

## Overall Assessment
This is the strongest overall round1 harness in the current set because it combines the best exact accuracy with a relatively controlled cost profile. Its design stays close to the core ToolHop demand: clear planning, centralized execution, and modest memory assistance rather than aggressive branching. It is particularly well matched to multi-hop tool tasks that need stable sequential execution and careful tool selection. It is still weaker on strict string and datetime outputs, where the final normalization step remains less reliable than the retrieval chain itself.

## Failure Pattern Analysis
- The harness still shows a noticeable path-to-answer drop, which means it often decomposes the task correctly but misses the exact benchmark target at the end.
- Compared with weaker harnesses, its failures are less about under-reasoning and more about imperfect finish quality. The agent usually does enough work; it just does not always translate that work into the exact final answer.
- Some residual tool-schema errors remain in the failed set, so part of the remaining gap is not deep reasoning weakness but imperfect API discipline under pressure.
- The harness is strongest on number-oriented tasks and clearly weaker on formatting-sensitive outputs. That pattern suggests the main bottleneck is not entity tracing, but answer rendering and post-processing.

## Module-level Diagnosis
### Planning
- What Helps: Explicit planning is one of the harness's strengths. It gives the main agent a clearer execution frame and seems to reduce wasted wandering relative to other direct-execution variants.
- What Hurts: Planning still does not fully lock down the final answer shape. The harness can know what to do without enforcing the exact final form that ToolHop expects.

### Action
- What Helps: Centralized execution through one active agent is highly compatible with ToolHop. It preserves serial dependencies and avoids the coordination noise that hurts more parallel harnesses.
- What Hurts: The action loop is still missing a dedicated final verification layer for exact formatting and edge-case transformation. That is likely where much of the remaining accuracy gap lives.

### Memory
- What Helps: Reusable workflow memory appears to be helping in a pragmatic way. It likely supports familiar call patterns and stable task routing without overwhelming the main loop.
- What Hurts: Memory is still a secondary aid rather than a precision mechanism. It improves fluency more than it guarantees correctness on tricky last-step transformations.
