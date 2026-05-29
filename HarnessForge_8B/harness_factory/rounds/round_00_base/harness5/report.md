# harness5 Analysis

## Structure
- Planning: decompose the objective into tracked sub-tasks with explicit status updates.
- Action: a hierarchical coordinator advances the plan while checking progress after key actions.
- Memory: graph-style text and tool memory supports reuse across runs.

## Aggregate Metrics
- Evaluated tasks: 80
- Exact accuracy: 47.5%
- Valid answer rate: 100.0%
- Average path score: 0.6495
- Average actions: 6.78
- Average tool calls: 8.04
- Prompt / completion / total tokens: 6304600 / 153100 / 6457700
- Average prompt / completion / total tokens: 78807.50 / 1913.75 / 80721.25
- Total runtime: 90.66 min
- Average runtime per task: 67.99 sec

## Overall Assessment
This harness delivers respectable quality, but it pays heavily for it. The explicit decomposition and progress tracking do help on multi-hop tasks, yet the additional planning and checking overhead drives token usage much higher than the return justifies. It is a reasonable fit for tasks where visible task state and controlled execution matter more than raw efficiency. It is a weaker fit for large-scale evaluation settings where you need similar quality at much lower cost, because its coordination loop is simply too expensive.

## Failure Pattern Analysis
- The most obvious issue is over-coordination. The harness does useful work, but it repeatedly spends tokens on plan maintenance and progress checks that do not translate into proportional accuracy gains.
- The path score is again noticeably stronger than exact accuracy, so even with all the extra structure, the final commitment step remains less reliable than the intermediate reasoning chain.
- Failure traces often look long rather than shallow. This means the harness's main problem is not early stopping, but inefficient persistence that still fails to guarantee a correct finish.
- The design appears better at keeping work organized than at making final answers exact. In ToolHop, that distinction matters a lot because the benchmark rewards precise completion, not only sensible decomposition.

## Module-level Diagnosis
### Planning
- What Helps: Planning is a genuine strength here. The harness is good at breaking the task into explicit units and maintaining visibility over what should happen next.
- What Hurts: Planning is too verbose and too active. It keeps paying coordination cost even when the next best move is already obvious, which hurts efficiency without fixing the remaining accuracy gap.

### Action
- What Helps: The action layer benefits from tracked plan state, which makes it less likely to skip necessary subproblems in the middle of a multi-hop chain.
- What Hurts: The action loop is over-instrumented. It performs too many progress checks and too much plan bookkeeping relative to the marginal value of those extra steps.

### Memory
- What Helps: Graph-style memory is a sensible match for structured multi-hop execution and likely helps preserve intermediate relations across runs.
- What Hurts: Memory still does not solve the final-answer problem. It supports organization and reuse better than it supports exact last-step correctness.
