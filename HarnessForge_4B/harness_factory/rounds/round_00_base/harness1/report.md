# harness1 Analysis

## Structure
- Planning: compact initial planning with periodic progress refreshes.
- Action: one primary agent works directly with the available task tools.
- Memory: lightweight retrieval of prior takeaways when they help.

## Aggregate Metrics
- Evaluated tasks: 80
- Exact accuracy: 48.8%
- Valid answer rate: 100.0%
- Average path score: 0.7132
- Average actions: 5.91
- Average tool calls: 6.08
- Prompt / completion / total tokens: 4035201 / 123945 / 4159146
- Average prompt / completion / total tokens: 50440.01 / 1549.31 / 51989.32
- Total runtime: 78.17 min
- Average runtime per task: 58.63 sec

## Overall Assessment
This is a fairly balanced harness for ToolHop: it reaches one of the stronger exact accuracies in the round, and it does so without collapsing into shallow one-shot behavior. The main tradeoff is cost, because the direct single-agent loop still spends a large number of tokens when it gets stuck. It is better suited to serial multi-hop questions where one agent can carry the entity chain from retrieval to transformation without handoff noise. It is less well suited to tasks that require strict final formatting, especially string and time normalization, because its path score is much stronger than its exact answer score.

## Failure Pattern Analysis
- The largest pattern is partial-success failure: the harness often follows the correct intermediate path, but loses accuracy at final answer commitment. The high gap between path score and exact accuracy is the clearest signal here.
- When runs fail, they tend to keep calling tools rather than converging. This suggests the harness has useful persistence, but weak stopping and repair rules once the main path becomes ambiguous.
- String-heavy and formatting-sensitive questions remain fragile. The agent can often identify the right entity chain, yet still miss the benchmark because the final transformation or normalization step is wrong.
- Tool-schema mistakes still appear in the failure set, so some of the wasted cost comes from calling roughly relevant tools with slightly wrong argument structures rather than from pure reasoning failure.

## Module-level Diagnosis
### Planning
- What Helps: The compact planning pass is a good fit for ToolHop because it gives the agent a simple serial roadmap without creating too much coordination overhead.
- What Hurts: Planning is not strong enough to control the final commitment step. The harness often has the right decomposition, but the plan is not enforced tightly enough at answer synthesis time.

### Action
- What Helps: Direct execution through a single primary agent is a real advantage on dependency-heavy tasks. It avoids the coordination loss that shows up in weaker multi-agent harnesses.
- What Hurts: The action loop is too willing to keep exploring after signal quality drops. That drives token usage up in failures and still does not reliably produce a correct final answer.

### Memory
- What Helps: Lightweight memory seems useful as a soft nudge rather than a dominating mechanism. It likely helps recover familiar tool patterns without taking control away from the main execution loop.
- What Hurts: The memory layer does not appear strong enough to fix final-answer brittleness. It helps the harness stay on path more than it helps the harness finish cleanly.
