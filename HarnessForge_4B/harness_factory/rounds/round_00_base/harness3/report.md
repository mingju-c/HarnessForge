# harness3 Analysis

## Structure
- Planning: augment the task, retrieve relevant memory, then route work deliberately.
- Action: a small mixed team combines one structured worker with several adaptive workers.
- Memory: reusable skill-like procedures can be surfaced during execution.

## Aggregate Metrics
- Evaluated tasks: 80
- Exact accuracy: 41.2%
- Valid answer rate: 100.0%
- Average path score: 0.6132
- Average actions: 2.00
- Average tool calls: 2.00
- Prompt / completion / total tokens: 1690650 / 29588 / 1720238
- Average prompt / completion / total tokens: 21133.12 / 369.85 / 21502.97
- Total runtime: 121.63 min
- Average runtime per task: 91.22 sec

## Overall Assessment
This harness is interesting because it gets meaningful value from structured candidate generation, but not enough value from the later synthesis layer. The cost profile is not low in wall-clock terms, yet the action depth stays very shallow because most of the work is hidden inside bundled ensemble steps. It is more suitable for tasks where multiple candidate answers can be generated and compared without strict serial dependency management. It is less suitable for ToolHop cases where one wrong vote or one bad synthesis choice can override a correct intermediate chain.

## Failure Pattern Analysis
- The dominant weakness is synthesis failure rather than search failure. In several cases the harness appears to have access to a correct candidate, but the vote-and-synthesize stage still lands on the wrong final answer.
- Because the harness compresses a lot of reasoning into `ensemble_executor` and `vote_and_synthesize`, it becomes harder to recover once the aggregation layer drifts. The pipeline is short, but brittle.
- The path score remains much stronger than exact accuracy, which again suggests the harness often identifies useful intermediate structure while losing precision at final commitment.
- This design is better at broad exploration than at strict answer discipline. That makes it feel closer to QA-style candidate comparison than to deterministic multi-hop tool execution.

## Module-level Diagnosis
### Planning
- What Helps: The planning layer correctly recognizes that some tasks benefit from a mix of stable and adaptive reasoning. That is a sensible high-level strategy for uncertain tasks.
- What Hurts: Planning does not enforce enough structure on the downstream synthesizer. Once multiple candidates exist, the harness lacks a strong rule for preferring the most evidence-grounded answer over the most plausible-looking one.

### Action
- What Helps: The mixed-team action design gives the harness useful breadth. It can surface alternative paths quickly and avoid single-path tunnel vision.
- What Hurts: The bundled action protocol is too coarse for ToolHop. When the final vote is wrong, there is no explicit repair loop that reopens the chain and checks the actual tool-grounded evidence step by step.

### Memory
- What Helps: Skill-like memory is a good conceptual match for recurring transformation patterns, and it likely helps the harness produce structured candidate approaches quickly.
- What Hurts: Memory does not solve the main failure mode here, which is not a lack of candidate generation but weak arbitration between candidates. The harness remembers patterns more easily than it verifies them.
