## Example Harness: harness1

### Harness Identity
- Planning system: flash_searcher
- Action system: single_react
- Default memory system: expel
- Default bench type: None
- Pairing reason: fallback_single_react

### Description
Harness summary:
- Planning: compact initial planning with periodic progress refreshes.
- Execution: one primary agent works directly with the available task tools.
- Memory: lightweight retrieval of prior takeaways when they help.
- Default bench: caller-provided

Coordination pattern:
- Keep the loop simple: plan once, execute directly, and summarize as needed.
- Prefer direct tool use over delegation.
- Fall back cleanly when no harness-specific execution layer is available.

Runtime notes:
- Generated bundle: `harness1`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.

### Performance Snapshot
- Evaluated tasks: 80
- Exact accuracy: 48.75%
- Valid answer rate: 100.00%
- Average path score: 0.7132
- Average actions: 5.9125
- Average tool calls: 6.075
- Average total tokens: 51989.32
- Average runtime (sec): 58.63
- Source result file: output/toolhop_round1_harness1/toolhop_flash_searcher_flash_searcher_expel_local_qwen3-aevolve_closed_results.jsonl

### Performance Report
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

### Bundle Files
<<<FILE:builder.py>>>
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Agents.agents import ToolCallingAgent
from module_action.base_action import ActionContext
from .action_module.provider import ACTION_SYSTEM, get_provider
from .memory_module.provider import MEMORY_SYSTEM as DEFAULT_MEMORY_SYSTEM
from .planning_module.provider import PLANNING_SYSTEM, PlanningClass


HARNESS_NAME = "harness1"
DEFAULT_BENCH_TYPE = None
PAIRING_REASON = "fallback_single_react"


def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
    if tool is not None and hasattr(tool, "agent"):
        setattr(tool, "agent", agent)


def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
    if getattr(agent, "planning_system", None) != "owl":
        return
    if not hasattr(agent, "web_memory") or agent.web_memory is None:
        agent.web_memory = []
    if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
        agent.reasoning_memory = []


def prepare_context(context: ActionContext) -> ActionContext:
    bench_type = context.bench_type or DEFAULT_BENCH_TYPE
    prompts_type = context.prompts_type or PLANNING_SYSTEM
    prepared_kwargs = dict(context.kwargs)
    prepared_kwargs["planning_class"] = PlanningClass
    return replace(
        context,
        planning_system=PLANNING_SYSTEM,
        action_system=ACTION_SYSTEM,
        prompts_type=prompts_type,
        bench_type=bench_type,
        project_root=Path(__file__).resolve().parent,
        kwargs=prepared_kwargs,
    )


def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
    prepared_context = prepare_context(context)
    action_provider = get_provider()
    agent = action_provider.build(prepared_context)

    setattr(agent, "planning_system", prepared_context.planning_system)
    setattr(agent, "action_system", prepared_context.action_system)
    setattr(agent, "harness_name", HARNESS_NAME)
    setattr(
        agent,
        "harness_metadata",
        {
            "planning_system": PLANNING_SYSTEM,
            "action_system": ACTION_SYSTEM,
            "default_bench_type": DEFAULT_BENCH_TYPE,
            "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
            "pairing_reason": PAIRING_REASON,
        },
    )

    if prepared_context.vector_tool is not None:
        prepared_context.vector_tool.memory = agent.memory

    _bind_agent_reference(agent, prepared_context.process_tool)
    _bind_agent_reference(agent, prepared_context.end_process_tool)
    _bind_agent_reference(agent, prepared_context.delete_memory_tool)
    _bind_agent_reference(agent, prepared_context.executor_tool)
    _bind_agent_reference(agent, prepared_context.refine_tool)

    _ensure_owl_memory(agent)
    return agent
<<<END_FILE>>>
<<<FILE:Description.md>>>
Harness summary:
- Planning: compact initial planning with periodic progress refreshes.
- Execution: one primary agent works directly with the available task tools.
- Memory: lightweight retrieval of prior takeaways when they help.
- Default bench: caller-provided

Coordination pattern:
- Keep the loop simple: plan once, execute directly, and summarize as needed.
- Prefer direct tool use over delegation.
- Fall back cleanly when no harness-specific execution layer is available.

Runtime notes:
- Generated bundle: `harness1`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
<<<END_FILE>>>
<<<FILE:__init__.py>>>
from .builder import (
    ACTION_SYSTEM,
    DEFAULT_BENCH_TYPE,
    DEFAULT_MEMORY_SYSTEM,
    PAIRING_REASON,
    PLANNING_SYSTEM,
    HARNESS_NAME,
    build_agent_from_context,
)

__all__ = [
    "HARNESS_NAME",
    "PLANNING_SYSTEM",
    "ACTION_SYSTEM",
    "DEFAULT_BENCH_TYPE",
    "DEFAULT_MEMORY_SYSTEM",
    "PAIRING_REASON",
    "build_agent_from_context",
]
<<<END_FILE>>>
<<<FILE:planning_module/provider.py>>>
import textwrap
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from rich.rule import Rule
from rich.text import Text
from module_planning.base_planning import BasePlanning

def populate_template(template: str, variables: Dict[str, Any]) -> str:
    """
    Fill Jinja2 template with variables.

    Args:
        template: Jinja2 template string
        variables: Template variable dictionary

    Returns:
        str: Filled string
    """
    # Use default Undefined instead of StrictUndefined to handle auto-generated templates
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        # Retry with lenient undefined handling for auto-generated templates
        compiled_template = Template(template)
        try:
            return compiled_template.render(**variables)
        except Exception as e2:
            raise Exception(f"Error during jinja template rendering: {type(e2).__name__}: {e2}")


class PlanningProvider(BasePlanning):
    """
    Planning implementation for a compact single-agent loop.

    This class provides concrete implementations of planning methods:
    - topology_initialize: Generates initial task plan (replaces planning_step)
    - adaptation: Generates periodic progress summaries (replaces summary_step)
    """

    def __init__(
        self,
        model: Callable[[List[Dict[str, str]]], ChatMessage],
        tools: Dict[str, Tool],
        prompt_templates: Dict[str, Any],
        memory: AgentMemory,
        logger: AgentLogger
    ):
        super().__init__(model, tools, prompt_templates, memory, logger)

    def topology_initialize(self, task: str) -> PlanningStep:
        """
        Generate initial task plan and record to memory and logger.

        This method replaces the MultiStepAgent.planning_step() method with identical functionality:
        1. Build planning prompt messages
        2. Call LLM to generate plan
        3. Extract plan content and reasoning process
        4. Record to memory (via self.memory.steps.append)
        5. Output to logger (via self.logger.log)

        Args:
            task: Task description to execute

        Returns:
            PlanningStep: Step object containing plan information with fields:
                - model_input_messages: Message list sent to model
                - plan: Generated plan text
                - plan_think: Plan thinking content (currently empty string)
                - plan_reasoning: Model reasoning content
        """
        # Build system prompt messages
        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["planning"]["initial_plan"],
                            variables={
                                "tools": self.tools,
                                "task": task,
                            },
                        ),
                    }
                ],
            },
        ]
        memory_guidance = self.append_memory_guidance(input_messages)

        # Build task input messages
        task_messages = [{
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": populate_template(self.prompt_templates["planning"]["task_input"], variables={"task": task})}],
        }]

        # Call model to generate plan
        chat_message_plan: ChatMessage = self.model(input_messages + task_messages)
        think_content = chat_message_plan.reasoning_content
        plans = chat_message_plan.content
        plans_think, plans_answer = "", plans

        # Format plan text for log output
        final_plan_redaction = textwrap.dedent(
            f"""Here is the plan of action that I will follow to solve the task:\n```\n{plans_answer}\n```\n"""
        )

        # Output to logger
        self.logger.log(
            Rule("[bold]Initial plan", style="orange"),
            Text(final_plan_redaction),
            level=LogLevel.INFO,
        )

        # Create PlanningStep object
        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plans_answer,
            plan_think=plans_think,
            plan_reasoning=think_content,
            memory_guidance=memory_guidance,
        )

        # Record to memory
        self.memory.steps.append(planning_step)

        return planning_step


    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]]
    ) -> SummaryStep:
        """
        Generate execution progress summary and record to memory and logger.

        This method replaces the MultiStepAgent.summary_step() method with identical functionality:
        1. Read execution history from memory
        2. Build summary prompt messages
        3. Call LLM to generate summary
        4. Extract summary content and reasoning process
        5. Record to memory (via self.memory.steps.append)
        6. Output to logger (via self.logger.log)

        Args:
            task: Task description to execute
            step: Current step number for context prompting
            write_memory_to_messages: Function to convert memory steps to message list

        Returns:
            SummaryStep: Step object containing summary information with fields:
                - model_input_messages: Message list sent to model
                - summary: Generated summary text
                - summary_reasoning: Model reasoning content
        """
        # Read execution history from memory (skip system prompt)
        memory_messages = write_memory_to_messages(None, False)[1:]

        # Build summary prompt pre and post messages
        update_pre_messages = {
            "role": MessageRole.SYSTEM,
            "content": [{"type": "text", "text": populate_template(
                self.prompt_templates["summary"]["update_pre_messages"],
                variables={"task": task, "step": step}
            )}],
        }
        update_post_messages = {
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": populate_template(
                self.prompt_templates["summary"]["update_post_messages"],
                variables={"task": task, "step": step}
            )}],
        }

        # Combine complete input messages
        input_messages = [update_pre_messages] + memory_messages + [update_post_messages]

        # Call model to generate summary
        chat_message_summary: ChatMessage = self.model(input_messages)

        summary_answer = chat_message_summary.content
        summary_cot_content = chat_message_summary.reasoning_content

        # Format summary text for log output
        final_summary_redaction = textwrap.dedent(
            f"""
            Here is my summary of action to solve the task:
            ```
            {summary_answer}
            ```"""
        )

        # Create SummaryStep object
        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_answer,
            summary_reasoning=summary_cot_content,
        )

        # Record to memory
        self.memory.steps.append(summary_step)

        # Output to logger
        self.logger.log(
            Rule("[bold]Summary", style="orange"),
            Text(final_summary_redaction),
            level=LogLevel.INFO,
        )

        return summary_step

PLANNING_SYSTEM = 'flash_searcher'
PLANNING_MODULE = 'flash_searcher'
PlanningClass = PlanningProvider

__all__ = ['PLANNING_SYSTEM', 'PLANNING_MODULE', 'PlanningProvider', 'PlanningClass']
<<<END_FILE>>>
<<<FILE:action_module/provider.py>>>
from __future__ import annotations

from typing import Any

from module_action.base_action import ActionContext, BaseActionProvider


class ActionProvider(BaseActionProvider):
    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = "single_react"
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = context.planning_system

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        return self.create_agent(
            context,
            tools=tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )


ACTION_SYSTEM = "single_react"
ACTION_MODULE = "single_react"

SingleReactActionProvider = ActionProvider


def get_provider():
    return ActionProvider()


__all__ = [
    "ACTION_SYSTEM",
    "ACTION_MODULE",
    "ActionProvider",
    "get_provider",
    "SingleReactActionProvider",
]
<<<END_FILE>>>
<<<FILE:memory_module/provider.py>>>
import os
import json
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from module_memory.base_memory import BaseMemoryProvider, atomic_write_json, file_lock
from module_memory.memory_types import (
    MemoryRequest,
    MemoryResponse,
    TrajectoryData,
    MemoryType,
    MemoryItem,
    MemoryStatus,
)

try:
    from sentence_transformers import SentenceTransformer
    _embedding_import_error = None
except Exception as e:
    _embedding_import_error = e
    SentenceTransformer = None
from module_memory.providers.model_loader import load_sentence_transformer

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class MemoryProvider(BaseMemoryProvider):

    def __init__(self, config: Optional[dict] = None):
        super().__init__(MemoryType.EXPEL, config)
        self.insights_file_path = self.config.get("insights_file_path", "./storage/expel/insights.json")
        self.success_trajectories_file_path = self.config.get("success_trajectories_file_path", "./storage/expel/success_trajectories.json")
        self.top_k = int(self.config.get("top_k", 1))
        self.search_weights = self.config.get("search_weights", {"text": 0.3, "semantic": 0.7})
        self.embedding_model_name = self.config.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
        self.embedding_model_cache = self.config.get("embedding_model_cache", "./storage/models")

        self.model = self.config.get("model")

        self.insights: List[Dict[str, Any]] = []
        self.success_trajectories: List[Dict[str, Any]] = []

        self._insights_vectorizer: Optional[TfidfVectorizer] = None
        self._insights_matrix = None
        self._success_vectorizer: Optional[TfidfVectorizer] = None
        self._success_matrix = None
        self._embedding_model: Optional[SentenceTransformer] = None
        self._success_embeddings = None

    def initialize(self) -> bool:
        try:
            insights_dir = os.path.dirname(self.insights_file_path)
            success_dir = os.path.dirname(self.success_trajectories_file_path)
            if insights_dir:
                os.makedirs(insights_dir, exist_ok=True)
            if success_dir:
                os.makedirs(success_dir, exist_ok=True)

            if os.path.exists(self.insights_file_path):
                with open(self.insights_file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.insights = loaded if isinstance(loaded, list) else loaded.get("insights", [])
            else:
                self.insights = []

            if os.path.exists(self.success_trajectories_file_path):
                with open(self.success_trajectories_file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.success_trajectories = loaded if isinstance(loaded, list) else loaded.get("success_trajectories", [])
            else:
                self.success_trajectories = []

            if SentenceTransformer is None and _embedding_import_error is not None:
                print(f"Warning: sentence-transformers not available: {_embedding_import_error}")
            else:
                self._embedding_model = load_sentence_transformer(
                    model_name=self.embedding_model_name,
                    cache_dir=self.embedding_model_cache,
                    allow_unavailable=SentenceTransformer is None,
                )

            self._build_indices()
            return True
        except Exception as e:
            print(f"Error initializing ExpeL provider: {e}")
            return False

    def _build_indices(self):
        insight_texts = [item.get("text", "") for item in self.insights]
        self._insights_vectorizer = TfidfVectorizer(stop_words='english') if insight_texts else None
        self._insights_matrix = (
            self._insights_vectorizer.fit_transform(insight_texts) if self._insights_vectorizer and insight_texts else None
        )
        success_texts = [item.get("trajectory_text", "") for item in self.success_trajectories]
        self._success_vectorizer = TfidfVectorizer(stop_words='english') if success_texts else None
        self._success_matrix = (
            self._success_vectorizer.fit_transform(success_texts) if self._success_vectorizer and success_texts else None
        )
        if self._embedding_model is not None and success_texts:
            self._success_embeddings = self._embedding_model.encode(
                success_texts,
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        else:
            self._success_embeddings = None

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status == MemoryStatus.IN:
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0,
                request_id=str(uuid.uuid4()),
            )

        memories: List[MemoryItem] = []
        try:
            query = request.query or ""
            insight_results = self._text_search(query, corpus="insights", top_k=self.top_k)
            success_results = self._hybrid_success_search(query, top_k=self.top_k)

            for r in insight_results:
                item = self.insights[r["index"]]
                insight_type = item.get("type", "success")
                content = self._format_insight_content(item.get("text", ""), request.status, insight_type)
                if not content:
                    continue
                memories.append(MemoryItem(
                    id=item.get("id", f"insight_{r['index']}"),
                    content=content,
                    metadata={
                        "type": "insight",
                        "insight_type": insight_type,
                        "score": r["score"],
                        "source": item.get("source", "expel"),
                        "timestamp": item.get("timestamp"),
                        "status": request.status.value,
                    },
                    score=float(r["score"]) if r.get("score") is not None else None,
                ))

            for r in success_results:
                item = self.success_trajectories[r["index"]]
                content = self._format_success_content(item, request.status)
                if not content:
                    continue
                memories.append(MemoryItem(
                    id=item.get("id", f"success_{r['index']}"),
                    content=content,
                    metadata={
                        "type": "success",
                        "score": r["score"],
                        "query": item.get("query", ""),
                        "timestamp": item.get("timestamp"),
                        "status": request.status.value,
                    },
                    score=float(r["score"]) if r.get("score") is not None else None,
                ))

            memories.sort(key=lambda m: (m.score or 0.0), reverse=True)
            memories = memories[: max(self.top_k, len(memories))]
            return MemoryResponse(
                memories=memories,
                memory_type=self.memory_type,
                total_count=len(memories),
                request_id=str(uuid.uuid4()),
            )
        except Exception as e:
            print(f"Error providing ExpeL memory: {e}")
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)

    def _text_search(self, query: str, corpus: str, top_k: int) -> List[Dict[str, Any]]:
        if not query.strip():
            return []
        if corpus == "insights":
            if not self._insights_vectorizer or self._insights_matrix is None:
                return []
            qv = self._insights_vectorizer.transform([query])
            sims = cosine_similarity(qv, self._insights_matrix).flatten()
            indices = sims.argsort()[-top_k:][::-1]
            return [{"index": int(i), "score": float(sims[i])} for i in indices]
        elif corpus == "success":
            if not self._success_vectorizer or self._success_matrix is None:
                return []
            qv = self._success_vectorizer.transform([query])
            sims = cosine_similarity(qv, self._success_matrix).flatten()
            indices = sims.argsort()[-top_k:][::-1]
            return [{"index": int(i), "score": float(sims[i])} for i in indices]
        return []

    def _hybrid_success_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        text_results = self._text_search(query, corpus="success", top_k=top_k * 2)
        sem_results: List[Dict[str, Any]] = []
        if self._embedding_model is not None and self.success_trajectories:
            q_emb = self._embedding_model.encode(query, convert_to_numpy=True)
            embs = self._success_embeddings
            if embs is not None and len(embs) == len(self.success_trajectories):
                sims = cosine_similarity([q_emb], embs)[0]
                indices = sims.argsort()[-top_k * 2:][::-1]
                sem_results = [{"index": int(i), "score": float(sims[i])} for i in indices]
            score_map: Dict[int, float] = {}
            for r in text_results:
                score_map[r["index"]] = score_map.get(r["index"], 0.0) + float(self.search_weights.get("text", 0.5)) * float(r["score"])
            for r in sem_results:
                score_map[r["index"]] = score_map.get(r["index"], 0.0) + float(self.search_weights.get("semantic", 0.5)) * float(r["score"])
            merged = sorted(score_map.items(), key=lambda x: x[1], reverse=True)[: top_k]
            return [{"index": int(i), "score": float(s)} for i, s in merged]
        return text_results[:top_k]

    def _format_insight_content(self, text: str, status: MemoryStatus, insight_type: str = "success") -> str:
        if insight_type == "failure":
            if status == MemoryStatus.BEGIN:
                return f"ExpeL Failure Insight: {text}"
            elif status == MemoryStatus.IN:
                return None
            return f"ExpeL Warning: {text}"
        else:
            if status == MemoryStatus.BEGIN:
                return f"ExpeL Success Insight: {text}"
            elif status == MemoryStatus.IN:
                return None
            return f"ExpeL Tip: {text}"

    def _format_success_content(self, item: Dict[str, Any], status: MemoryStatus) -> str:
        query = item.get("query", "")
        traj = item.get("trajectory_text", "")
        result = item.get("result", "")
        if status == MemoryStatus.BEGIN:
            return f"ExpeL Similar successful case for '{query}':\n{traj}"
        elif status == MemoryStatus.IN:
            return None
        return f"ExpeL Success Pattern: {traj}"

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        try:
            metadata = trajectory_data.metadata or {}
            is_correct = metadata.get("is_correct", False)

            if not self.model:
                print("Error: No model provided for ExpeL memory extraction")
                return False, "Error: No model provided for ExpeL memory extraction"

            insights = self._extract_insights_with_llm(trajectory_data, is_correct)
            absorbed_memory = ""

            if insights:
                self._append_insights(insights, is_correct)
                absorbed_memory += f"Extracted insights: {insights}"

            if is_correct:
                self._append_success_trajectory(trajectory_data)
                absorbed_memory += f" | Stored successful trajectory"

            self._build_indices()
            return True, absorbed_memory
        except Exception as e:
            error_msg = f"Error taking in ExpeL memory: {e}"
            print(error_msg)
            return False, error_msg

    def _extract_insights_with_llm(self, trajectory_data: TrajectoryData, is_correct: bool = True) -> List[str]:
        try:
            trajectory_text = self._format_trajectory_for_model(trajectory_data)

            if is_correct:
                prompt = f"""Analyze the following successful task execution and extract simple, actionable insights.

Task Question: {trajectory_data.query}

Execution Trajectory:
{trajectory_text}

Task Result: {trajectory_data.result if trajectory_data.result else "Task completed successfully"}

Extract 3-6 simple insights that could help with similar future tasks. Each insight should be:
- One clear, actionable sentence
- Focused on what worked well or what to remember
- Useful for similar problem types
- Written as a direct tip or lesson

Format: Return only the insights, one per line, no categories or prefixes.

Example format:
Always verify search results with multiple sources before concluding
Break down complex problems into smaller, manageable steps
Use specific keywords when searching for technical information"""
            else:
                prompt = f"""Analyze the following failed task execution and extract simple, actionable insights to avoid similar failures.

Task Question: {trajectory_data.query}

Execution Trajectory:
{trajectory_text}

Task Result: {trajectory_data.result if trajectory_data.result else "Task failed or produced incorrect result"}

Extract 3-6 simple insights that could help avoid similar failures in future tasks. Each insight should be:
- One clear, actionable sentence
- Focused on what went wrong or what to avoid
- Useful for preventing similar mistakes
- Written as a direct warning or lesson learned

Format: Return only the insights, one per line, no categories or prefixes.

Example format:
Avoid relying on single sources without cross-verification
Double-check calculations before providing final answers
Ensure search queries are specific enough to find relevant information"""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]

            response = self.model(messages)
            content = getattr(response, "content", str(response))

            insights = []
            for line in content.strip().split('\n'):
                line = line.strip()
                line = line.lstrip('•-*123456789. ')
                for prefix in ["Do:", "Avoid:", "Insight:", "Tip:", "Note:"]:
                    if line.startswith(prefix):
                        line = line[len(prefix):].strip()
                        break

                if line and len(line) > 10:
                    insights.append(line)

            return insights[:4]

        except Exception as e:
            print(f"Error extracting insights with LLM: {e}")
            return []

    def _format_trajectory_for_model(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return "No execution trajectory available"

        trajectory_parts = []
        trajectory_parts.append(f"Task: {trajectory_data.query}")
        trajectory_parts.append("")

        for i, step in enumerate(trajectory_data.trajectory, 1):
            step_type = step.get('type', 'step')
            content = step.get('content', '')
            trajectory_parts.append(f"Step {i} ({step_type}): {content}")

        if trajectory_data.result:
            trajectory_parts.append("")
            trajectory_parts.append(f"Final Result: {trajectory_data.result}")

        return "\n".join(trajectory_parts)

    def _append_insights(self, insights: List[str], is_correct: bool = True):
        os.makedirs(os.path.dirname(self.insights_file_path), exist_ok=True)
        insight_type = "success" if is_correct else "failure"
        with file_lock(self.insights_file_path):
            cur: List[Dict[str, Any]] = []
            if os.path.exists(self.insights_file_path):
                try:
                    with open(self.insights_file_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        cur = loaded if isinstance(loaded, list) else loaded.get("insights", [])
                except Exception:
                    cur = []

            for text in insights:
                cur.append({
                    "id": str(uuid.uuid4()),
                    "text": text,
                    "source": "expel",
                    "type": insight_type,
                    "timestamp": datetime.now().isoformat(),
                })

            atomic_write_json(self.insights_file_path, cur, indent=2)
        self.insights = cur

    def _refine_successful_trajectory_with_llm(self, trajectory_data: TrajectoryData) -> str:
        try:
            trajectory_text = self._format_trajectory_for_model(trajectory_data)

            prompt = f"""Analyze the following successful task execution and create a structured step-by-step summary.

Task Question: {trajectory_data.query}

Successful Execution Trajectory:
{trajectory_text}

Task Result: {trajectory_data.result if trajectory_data.result else "Task completed successfully"}

Create a clear, numbered step-by-step summary of the successful approach that can be reused for similar tasks.

Requirements:
- Format as numbered steps: "1. [Action/Strategy]", "2. [Action/Strategy]", etc.
- Each step should be one clear, actionable sentence
- Focus on the key decisions and actions that led to success
- Make steps generalizable for similar problem types
- Include 4-8 main steps maximum
- Be concise but specific about what was done and why

Example format:
1. Break down the complex question into specific searchable components
2. Use targeted search queries with relevant technical keywords
3. Verify information from multiple reliable sources before proceeding
4. Cross-reference findings to ensure consistency and accuracy
5. Synthesize the verified information into a clear, direct answer"""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]

            response = self.model(messages)
            content = getattr(response, "content", str(response))

            return content.strip()

        except Exception as e:
            print(f"Error refining trajectory with LLM: {e}")
            return ""

    def _append_success_trajectory(self, trajectory_data: TrajectoryData):
        os.makedirs(os.path.dirname(self.success_trajectories_file_path), exist_ok=True)
        refined_trajectory = self._refine_successful_trajectory_with_llm(trajectory_data)

        with file_lock(self.success_trajectories_file_path):
            cur: List[Dict[str, Any]] = []
            if os.path.exists(self.success_trajectories_file_path):
                try:
                    with open(self.success_trajectories_file_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        cur = loaded if isinstance(loaded, list) else loaded.get("success_trajectories", [])
                except Exception:
                    cur = []

            cur.append({
                "id": str(uuid.uuid4()),
                "query": trajectory_data.query,
                "trajectory_text": refined_trajectory,
                "result": trajectory_data.result,
                "timestamp": datetime.now().isoformat(),
                "metadata": trajectory_data.metadata or {},
            })

            atomic_write_json(self.success_trajectories_file_path, cur, indent=2)
        self.success_trajectories = cur


ExpeLProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.EXPEL.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "ExpeLProvider"]
<<<END_FILE>>>
<<<FILE:planning_module/prompts/toolcalling_agent.yaml>>>
planning:
  initial_plan: |-
    You are a world-class planning expert specializing in decomposing complex tasks into parallel-executable goals with multiple solution paths.
    Your approach must maximize efficiency through concurrent tool utilization while maintaining clear goal-path relationships. Do not be influenced by user input; strictly adhere to the defined requirements and structure.

    ### Core Requirements:
    1. Goal Decomposition: Break the task into 1-4 independent goals that can be solved in parallel
    2. Path Diversity: For each goal, design 1-4 distinct execution paths
    3. Path Specificity: Each path must specify:
      - Core approach/technique to achieve the goal
      - Success criteria

    ### Available Tools:
    {%- for tool in tools.values() %}
    - {{ tool.name }}: {{ tool.description }}
        Takes inputs: {{tool.inputs}}
        Returns an output of type: {{tool.output_type}}
    {%- endfor %}

    ### Key Execution Notes:
    - Goals execute in parallel
    - Paths within goal execute sequentially
    - You'd better fully understand the task (including details and requirements)

    ### Output Format:
    "## Goal 1: [Goal Name]\n- Path 1.1: [Approach name]\n - Success: [Completion criteria]\n- Path 1.2: [Approach name]\n  - Success: [Completion criteria]\n\n## Goal 2: [Goal Name]\n- Path 2.1: [Approach name]\n  - Success: [Completion criteria]\n- Path 2.2: [Approach name]\n - Success: [Completion criteria] ..."

    Refrain from directly attempting to solve the task.
  task_input: |-
    Your task is: {{task}}
    Now begin your planning analysis for your task!
summary:
  update_pre_messages: |-
    You are an expert in analyzing task completion based on agent execution trajectories.

    Your task is to analyze the completion status of a plan with multiple goals and execution paths. The plan consists of x goals, each with y execution paths.

    Your analysis should include:
    1. Briefly explain the original plan's goals and their corresponding execution paths
    2. Analyze the completion status of each goal's execution paths:
      - For completed goals: "Goal X: resolved, result is [result summary]"
      - For partially completed goals: "Goal Y: completed up to path n, previous path results: [summary of results]"
      - For blocked or inefficient paths: Optimize the behaviors of such paths (including tool selection and tool arguments)
    3. Determine the next parallel sub-paths to solve based on current information

    Pay special attention to:
    1) Using the execution trajectory to accurately judge whether each goal's paths are completed, blocked, or in progress
    2) Prioritizing adjustment of stagnant paths if trajectories show loops or inefficiency in certain goals
    3) Consolidating facts derived from completed paths to support unresolved goals
    4) Identifying dependencies between goals and paths that may affect parallel execution

    Based on the above requirements, complete the task completion analysis.
    5) When a path failed because of tool arguments or schema mismatch, recommend a concrete corrected retry instead of repeating the same call
  update_post_messages: |-
    Based on the agent execution trajectory, analyze the task completion status and provide recommendations for next steps.

    ** Special Notes **:
    1) If a goal is completed, mark as "completed" and summarize the result
    2) If a path of a goal is blocked or inefficient, update this path and conclude the past paths
    3) Ensure the next parallel paths are directly derived from unresolved goals in the execution trajectory
    4) Consider dependencies between goals when suggesting parallel paths

    ** Output Format **:

    ## Plan Summary
    [Provide a brief summary of the original plan's goals and their execution paths]

    ## Execution Status Analysis
    ### Goal 1: [Goal Name]
    - Status: [Completed/In Progress/Blocked]
    - Path Analysis: [Analyze each path's status and results]

    ### Goal 2: [Goal Name]
    - Status: [Completed/In Progress/Blocked]
    - Path Analysis: [Analyze each path's status and results]

    [Continue for all goals]

    ## Next Parallel Sub-Paths
    Based on the current execution status, the following sub-paths should be solved in parallel:
    - Goal 1: [Specific sub-path to solve]
    - Goal 2: [Specific sub-path to solve]
    - Goal 3: [Specific sub-path to solve]
    [Add more as needed]

    Now complete your analysis!
<<<END_FILE>>>
<<<FILE:action_module/prompts/toolcalling_agent.yaml>>>
system_prompt: |-
  You are a closed-set ReAct tool-using assistant.

  Your job is to solve the user's task by reasoning step by step, calling the provided tools when needed, and calling final_answer as soon as the answer is supported by the observed evidence.

  **Your ReAct Process:**
  1. **THINK**: Analyze the current situation, what you already know, what is still missing, and whether the answer may already be supported.
  2. **ACT**: If more evidence is needed, call the most appropriate available tool using the required JSON format.
  3. **OBSERVE**: Read the tool result carefully and update your understanding.
  4. **REPEAT**: Continue this Think-Act-Observe cycle until you can provide the final answer, then stop immediately with final_answer.

  **ToolCallingAgent Output Contract:**
  - Every non-final response must be one strict JSON object only.
  - Do not include markdown, code fences, or any text outside JSON.
  - Use exactly this shape:
    {
      "think": "brief reasoning for the next action",
      "tools": [
        {"name": "actual_tool_name", "arguments": {"arg": "value"}}
      ]
    }
  - Tool names and argument keys must exactly match the available tool schemas.
  - Never invent tools, arguments, files, APIs, or observations.
  - Every non-final step must contain at least one valid tool call.
  - Never return an empty tools list. If no more tool is needed, call final_answer instead.
  - If a tool call fails because of invalid arguments, unsupported fields, or schema mismatch, inspect the schema and correct the arguments on the next step instead of repeating the same bad call.
  - Never repeat an identical failed tool call unless the observation gives a concrete reason that the exact same call should now succeed.

  **Important Guidelines:**
  - **Always start with THINKING**: Before any action, analyze what you know and what you still need.
  - **One tool call at a time by default**: Use a single tool call unless multiple calls are truly independent.
  - **Observe and think again**: After each tool call, use the new observation to decide the next step.
  - **Schema discipline is mandatory**: Read the tool schema carefully and use only the listed argument names and types. Never substitute alternative argument names.
  - **Do not loop on the same failed pattern**: If the same strategy already failed and you gained no new evidence, change tools, revise arguments, or finalize if possible.
  - **Retry with adaptation, not repetition**: When progress is weak, explicitly change the tool choice, arguments, or strategy. A retry must be meaningfully different from the failed attempt.
  - **Do not over-search**: If the remaining work is only a simple deterministic transformation of observed evidence, do not call another lookup tool.
  - **Provide final answer as soon as supported**: Once the requested value, or all values needed to compute it, are already observed, call final_answer immediately.

  **Answer Policy:**
  - Base the final answer only on observed evidence.
  - Do not override, reinterpret, or recompute a supported observed result unless a new observation proves the earlier result wrong.
  - Keep the final answer concise and task-specific.
  - For short-answer or multi-hop lookup tasks, return the raw answer value in final_answer.

final_answer:
  pre_messages: |-
    You need to produce the final answer from the task, plan, memory, and observed tool results.

  post_messages: |-
    Return strict JSON only:

    {
      "think": "brief reason why the answer is supported",
      "answer": "the final answer"
    }

    Rules:
    - The answer field must contain only the requested final answer.
    - Do not call any non-final tool here.
    - Do not add markdown or extra commentary.
    - If the observed evidence already determines the answer, answer directly instead of hedging.
    - Base the answer on observations only; do not invent missing intermediate values.
    - For short-answer or multi-hop lookup tasks, return the raw short answer only.

    Task:
    {{task}}

step:
  pre_messages: |-
    Continue the ReAct loop using the current task, plan, memory, and previous tool observations.

    Available tool schemas:
    {{tool_functions_json}}

    Original task:
    {{task}}

    Decision rules:
    - **THINK** about the next missing fact, the next verification, or why the answer is already supported.
    - Select only tools from the available schemas above.
    - Use exact JSON argument objects that match the schema.
    - Read the tool schemas carefully before every call. Never substitute alternative argument names.
    - Prefer one tool call unless multiple calls are truly independent.
    - Never emit an empty tools list.
    - If you cannot justify a new valid tool call from the observations, call final_answer instead.
    - If the current evidence already supports the answer, call final_answer and no other tool.
    - If a tool failed because of arguments or schema mismatch, your next step should repair the arguments or choose a different valid tool.
    - Never repeat an identical failed call with identical arguments unless the observation explicitly justifies it.
    - If one or two retries of the same strategy already failed and no new evidence was gained, switch tools or finalize if possible.
    - Otherwise call at least one tool.

    Return strict JSON only:
    {
      "think": "brief ReAct thought for the next action",
      "tools": [
        {"name": "actual_tool_name", "arguments": {"arg": "value"}}
      ]
    }
<<<END_FILE>>>

## Example Harness: harness2

### Harness Identity
- Planning system: concise_reflection
- Action system: concise_reflection
- Default memory system: agent_kb
- Default bench type: None
- Pairing reason: fallback_single_react

### Description
Harness summary:
- Planning: explicit task planning with regular status summarization.
- Execution: one primary agent uses the current task tools directly.
- Memory: reusable workflow notes and prior solutions.
- Default bench: caller-provided

Coordination pattern:
- Start with a clearer plan than the base single-agent loop.
- Keep execution centralized in one active agent.
- Fall back cleanly when no harness-specific execution layer is available.

Runtime notes:
- Generated bundle: `harness2`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.

### Performance Snapshot
- Evaluated tasks: 80
- Exact accuracy: 51.25%
- Valid answer rate: 100.00%
- Average path score: 0.6744
- Average actions: 5.35
- Average tool calls: 5.4875
- Average total tokens: 37500.36
- Average runtime (sec): 60.79
- Source result file: output/toolhop_round1_harness2/toolhop_flash_searcher_flash_searcher_agent_kb_local_qwen3-aevolve_closed_results.jsonl

### Performance Report
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

### Bundle Files
<<<FILE:builder.py>>>
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Agents.agents import ToolCallingAgent
from module_action.base_action import ActionContext
from .action_module.provider import ACTION_SYSTEM, get_provider
from .memory_module.provider import MEMORY_SYSTEM as DEFAULT_MEMORY_SYSTEM
from .planning_module.provider import PLANNING_SYSTEM, PlanningClass


HARNESS_NAME = "harness2"
DEFAULT_BENCH_TYPE = None
PAIRING_REASON = "fallback_single_react"


def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
    if tool is not None and hasattr(tool, "agent"):
        setattr(tool, "agent", agent)


def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
    if getattr(agent, "planning_system", None) != "owl":
        return
    if not hasattr(agent, "web_memory") or agent.web_memory is None:
        agent.web_memory = []
    if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
        agent.reasoning_memory = []


def prepare_context(context: ActionContext) -> ActionContext:
    bench_type = context.bench_type or DEFAULT_BENCH_TYPE
    prompts_type = context.prompts_type or PLANNING_SYSTEM
    prepared_kwargs = dict(context.kwargs)
    prepared_kwargs["planning_class"] = PlanningClass
    return replace(
        context,
        planning_system=PLANNING_SYSTEM,
        action_system=ACTION_SYSTEM,
        prompts_type=prompts_type,
        bench_type=bench_type,
        project_root=Path(__file__).resolve().parent,
        kwargs=prepared_kwargs,
    )


def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
    prepared_context = prepare_context(context)
    action_provider = get_provider()
    agent = action_provider.build(prepared_context)

    setattr(agent, "planning_system", prepared_context.planning_system)
    setattr(agent, "action_system", prepared_context.action_system)
    setattr(agent, "harness_name", HARNESS_NAME)
    setattr(
        agent,
        "harness_metadata",
        {
            "planning_system": PLANNING_SYSTEM,
            "action_system": ACTION_SYSTEM,
            "default_bench_type": DEFAULT_BENCH_TYPE,
            "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
            "pairing_reason": PAIRING_REASON,
        },
    )

    if prepared_context.vector_tool is not None:
        prepared_context.vector_tool.memory = agent.memory

    _bind_agent_reference(agent, prepared_context.process_tool)
    _bind_agent_reference(agent, prepared_context.end_process_tool)
    _bind_agent_reference(agent, prepared_context.delete_memory_tool)
    _bind_agent_reference(agent, prepared_context.executor_tool)
    _bind_agent_reference(agent, prepared_context.refine_tool)

    _ensure_owl_memory(agent)
    return agent
<<<END_FILE>>>
<<<FILE:Description.md>>>
Harness summary:
- Planning: explicit task planning with regular status summarization.
- Execution: one primary agent uses the current task tools directly.
- Memory: reusable workflow notes and prior solutions.
- Default bench: caller-provided

Coordination pattern:
- Start with a clearer plan than the base single-agent loop.
- Keep execution centralized in one active agent.
- Fall back cleanly when no harness-specific execution layer is available.

Runtime notes:
- Generated bundle: `harness2`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
<<<END_FILE>>>
<<<FILE:__init__.py>>>
from .builder import (
    ACTION_SYSTEM,
    DEFAULT_BENCH_TYPE,
    DEFAULT_MEMORY_SYSTEM,
    PAIRING_REASON,
    PLANNING_SYSTEM,
    HARNESS_NAME,
    build_agent_from_context,
)

__all__ = [
    "HARNESS_NAME",
    "PLANNING_SYSTEM",
    "ACTION_SYSTEM",
    "DEFAULT_BENCH_TYPE",
    "DEFAULT_MEMORY_SYSTEM",
    "PAIRING_REASON",
    "build_agent_from_context",
]
<<<END_FILE>>>
<<<FILE:planning_module/provider.py>>>
import textwrap
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from rich.rule import Rule
from rich.text import Text
from module_planning.base_planning import BasePlanning

def populate_template(template: str, variables: Dict[str, Any]) -> str:
    """
    Fill Jinja2 template with variables.

    Args:
        template: Jinja2 template string
        variables: Template variable dictionary

    Returns:
        str: Filled string
    """
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")


class PlanningProvider(BasePlanning):
    """
    Planning implementation for a deliberate single-agent planner.

    This class provides concrete implementations of planning methods:
    - topology_initialize: Generates initial task plan (replaces planning_step)
    - adaptation: Generates periodic progress summaries (replaces summary_step)
    """

    def __init__(
        self,
        model: Callable[[List[Dict[str, str]]], ChatMessage],
        tools: Dict[str, Tool],
        prompt_templates: Dict[str, Any],
        memory: AgentMemory,
        logger: AgentLogger
    ):
        super().__init__(model, tools, prompt_templates, memory, logger)

    def topology_initialize(self, task: str) -> PlanningStep:
        """
        Generate initial task plan and record to memory and logger.

        This method replaces the MultiStepAgent.planning_step() method with identical functionality:
        1. Build planning prompt messages
        2. Call LLM to generate plan
        3. Extract plan content and reasoning process
        4. Record to memory (via self.memory.steps.append)
        5. Output to logger (via self.logger.log)

        Args:
            task: Task description to execute

        Returns:
            PlanningStep: Step object containing plan information with fields:
                - model_input_messages: Message list sent to model
                - plan: Generated plan text
                - plan_think: Plan thinking content (currently empty string)
                - plan_reasoning: Model reasoning content
        """
        # Build system prompt messages
        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["planning"]["initial_plan"],
                            variables={
                                "tools": self.tools,
                            },
                        ),
                    }
                ],
            },
        ]
        memory_guidance = self.append_memory_guidance(input_messages)

        # Build task input messages
        task_messages = [{
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": populate_template(self.prompt_templates["planning"]["task_input"], variables={"task": task})}],
        }]

        # Call model to generate plan
        chat_message_plan: ChatMessage = self.model(input_messages + task_messages)
        think_content = chat_message_plan.reasoning_content
        plans = chat_message_plan.content
        plans_think, plans_answer = "", plans

        # Format plan text for log output
        final_plan_redaction = textwrap.dedent(
            f"""Here is the plan of action that I will follow to solve the task:\n```\n{plans_answer}\n```\n"""
        )

        # Output to logger
        self.logger.log(
            Rule("[bold]Initial plan", style="orange"),
            Text(final_plan_redaction),
            level=LogLevel.INFO,
        )

        # Create PlanningStep object
        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plans_answer,
            plan_think=plans_think,
            plan_reasoning=think_content,
            memory_guidance=memory_guidance,
        )

        # Record to memory
        self.memory.steps.append(planning_step)

        return planning_step


    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]]
    ) -> SummaryStep:
        """
        Generate execution progress summary and record to memory and logger.

        This method replaces the MultiStepAgent.summary_step() method with identical functionality:
        1. Read execution history from memory
        2. Build summary prompt messages
        3. Call LLM to generate summary
        4. Extract summary content and reasoning process
        5. Record to memory (via self.memory.steps.append)
        6. Output to logger (via self.logger.log)

        Args:
            task: Task description to execute
            step: Current step number for context prompting
            write_memory_to_messages: Function to convert memory steps to message list

        Returns:
            SummaryStep: Step object containing summary information with fields:
                - model_input_messages: Message list sent to model
                - summary: Generated summary text
                - summary_reasoning: Model reasoning content
        """
        # Read execution history from memory (skip system prompt)
        memory_messages = write_memory_to_messages(None, False)[1:]

        # Build summary prompt pre and post messages
        update_pre_messages = {
            "role": MessageRole.SYSTEM,
            "content": [{"type": "text", "text": self.prompt_templates["summary"]["update_pre_messages"]}],
        }
        update_post_messages = {
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": self.prompt_templates["summary"]["update_post_messages"]}],
        }

        # Combine complete input messages
        input_messages = [update_pre_messages] + memory_messages + [update_post_messages]

        # Call model to generate summary
        chat_message_summary: ChatMessage = self.model(input_messages)

        summary_answer = chat_message_summary.content
        summary_cot_content = chat_message_summary.reasoning_content

        # Format summary text for log output
        final_summary_redaction = textwrap.dedent(
            f"""
            Here is my summary of action to solve the task:
            ```
            {summary_answer}
            ```"""
        )

        # Create SummaryStep object
        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_answer,
            summary_reasoning=summary_cot_content,
        )

        # Record to memory
        self.memory.steps.append(summary_step)

        # Output to logger
        self.logger.log(
            Rule("[bold]Summary", style="orange"),
            Text(final_summary_redaction),
            level=LogLevel.INFO,
        )

        return summary_step

PLANNING_SYSTEM = 'concise_reflection'
PLANNING_MODULE = 'concise_reflection'
PlanningClass = PlanningProvider

__all__ = ['PLANNING_SYSTEM', 'PLANNING_MODULE', 'PlanningProvider', 'PlanningClass']
<<<END_FILE>>>
<<<FILE:action_module/provider.py>>>
from __future__ import annotations

from typing import Any

from _harness_guards import ReflectionCriticTool
from module_action.base_action import ActionContext, BaseActionProvider


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "concise_reflection"
    DEFAULT_SUMMARY_INTERVAL = 4

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = context.planning_system

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        verifier = ReflectionCriticTool(
            context=context,
            name="verify_before_final",
            description=(
                "Non-environment verifier. Call before final_answer when the answer "
                "or completion claim is ready; it checks support, schema discipline, "
                "and repeated failures without touching the task environment."
            ),
        )
        root_tools = self.normalize_tools([*tools, verifier])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        verifier.bind_agent(agent, root_tools)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_SUMMARY_INTERVAL
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "concise_reflection",
                "plan_lines_max": 3,
                "reflection_interval": agent.summary_interval,
                "final_verifier": verifier.name,
            },
        )
        return agent


ACTION_SYSTEM = "concise_reflection"
ACTION_MODULE = "concise_reflection"

ConciseReflectionActionProvider = ActionProvider


def get_provider():
    return ActionProvider()


__all__ = [
    "ACTION_SYSTEM",
    "ACTION_MODULE",
    "ActionProvider",
    "get_provider",
    "ConciseReflectionActionProvider",
]
<<<END_FILE>>>
<<<FILE:memory_module/provider.py>>>
import json
import os
import uuid
from typing import List, Optional, Dict, Any
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None
from module_memory.providers.model_loader import load_sentence_transformer

from module_memory.base_memory import BaseMemoryProvider, atomic_write_json, file_lock
from module_memory.memory_types import (
    MemoryRequest,
    MemoryResponse,
    TrajectoryData,
    MemoryType,
    MemoryItem,
    MemoryStatus
)

def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                         cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    return load_sentence_transformer(
        model_name=model_name,
        cache_dir=cache_dir,
        allow_unavailable=SentenceTransformer is None,
    )


@dataclass
class WorkflowInstance:
    workflow_id: str = field(default_factory=lambda: str(datetime.now().timestamp()))
    query: str = ""
    agent_planning: Optional[str] = None
    search_agent_planning: Optional[str] = None
    agent_experience: Optional[str] = None
    search_agent_experience: Optional[str] = None
    query_embedding: Optional[np.ndarray] = None
    plan_embedding: Optional[np.ndarray] = None
    search_plan_embedding: Optional[np.ndarray] = None


class AgenticKnowledgeBase:

    def __init__(self, json_file_paths=None, model_cache_dir: str = './storage/models'):
        self.workflows: Dict[str, WorkflowInstance] = {}
        self.embedding_model = load_embedding_model(
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            cache_dir=model_cache_dir
        )

        self.field_components = {
            'query': {
                'vectorizer': TfidfVectorizer(stop_words='english'),
                'matrix': None,
                'workflow_ids': []
            },
        }

        if json_file_paths:
            self.load_initial_data(json_file_paths)
            self.finalize_index()

    def load_initial_data(self, json_file_paths):
        for json_path in json_file_paths:
            if not os.path.exists(json_path):
                raise FileNotFoundError(f'JSON file not found: {json_path}')
            self.parse_json_file(json_path)

    def _load_json_with_fallback(self, json_file_path: str):
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with open(json_file_path, "r", encoding=encoding) as f:
                    return json.load(f)
            except UnicodeDecodeError:
                continue
        with open(json_file_path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)

    def parse_json_file(self, json_file_path):
        try:
            data = self._load_json_with_fallback(json_file_path)
            batch = []
            for item in data:
                try:
                    instance = WorkflowInstance(
                        query = item.get('question', ''),
                        agent_planning = item.get('agent_planning'),
                        search_agent_planning = item.get('search_agent_planning'),
                        agent_experience = item.get('agent_experience'),
                        search_agent_experience = item.get('search_agent_experience')
                    )
                    batch.append(instance)
                except KeyError as e:
                    continue
            for instance in batch:
                self.workflows[instance.workflow_id] = instance
        except Exception as e:
            print(f"Error parsing file: {json_file_path} | {e}")

    def add_workflow_instance(self, workflow: WorkflowInstance):
        self.workflows[workflow.workflow_id] = workflow
        return workflow

    def finalize_index(self):
        self.build_tfidf_indices()
        self.build_embeddings()

    def build_tfidf_indices(self):
        field_data = {
            'query': [],
        }

        for workflow in self.workflows.values():
            field_data['query'].append(workflow.query)

        for field in ['query']:
            if len(field_data[field]) == 0:
                continue

            vectorizer = self.field_components[field]['vectorizer']
            self.field_components[field]['matrix'] = vectorizer.fit_transform(field_data[field])
            self.field_components[field]['workflow_ids'] = list(self.workflows.keys())

    def build_embeddings(self):
        if self.embedding_model is None:
            for workflow in self.workflows.values():
                workflow.query_embedding = None
            return

        workflows = list(self.workflows.values())
        batch_size = 32

        queries = [w.query for w in workflows]
        query_embeddings = self.embedding_model.encode(
            queries,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True
        )

        for i, workflow in enumerate(workflows):
            workflow.query_embedding = query_embeddings[i]

    def field_text_search(self, query: str, field: str, top_k: int = 3) -> List[dict]:
        component = self.field_components[field]
        if component['matrix'] is None or not component['workflow_ids']:
            return []

        query_vec = component['vectorizer'].transform([query])
        similarities = cosine_similarity(query_vec, component['matrix']).flatten()
        top_indices = similarities.argsort()[-top_k:][::-1]

        return [{
            'workflow_id': component['workflow_ids'][idx],
            'score': float(similarities[idx]),
            'field': field,
            'content': getattr(self.workflows[component['workflow_ids'][idx]],
                             field if field != 'search_plan' else 'search_agent_planning')
        } for idx in top_indices]

    def field_semantic_search(self, query: str, field: str, top_k: int = 3) -> List[dict]:
        if self.embedding_model is None:
            return []

        query_embedding = self.embedding_model.encode(query, convert_to_numpy=True)

        embedding_field_map = {
            'query': 'query_embedding',
        }

        content_field_map = {
            'query': 'query',
        }

        embeddings = []
        workflows = []
        for wf_id, workflow in self.workflows.items():
            emb = getattr(workflow, embedding_field_map[field], None)
            if emb is not None:
                embeddings.append(emb)
                workflows.append(workflow)

        if not embeddings:
            return []

        similarities = cosine_similarity([query_embedding], embeddings)[0]
        top_indices = similarities.argsort()[-top_k:][::-1]

        return [{
            'workflow_id': workflows[idx].workflow_id,
            'score': float(similarities[idx]),
            'field': field,
            'content': getattr(workflows[idx], content_field_map[field], "")
        } for idx in top_indices]


class AKB_Manager:

    def __init__(self, json_file_paths=None, model_cache_dir: str = './storage/models'):
        self.knowledge_base = AgenticKnowledgeBase(
            json_file_paths=json_file_paths,
            model_cache_dir=model_cache_dir
        )

    def hybrid_search(self, query: str, top_k: int = 5,
                      weights: Dict[str, float] = None) -> List[dict]:
        weights = weights or {'text': 0.5, 'semantic': 0.5}
        field_weights = {'query': 1.0}

        score_board = defaultdict(float)

        for field in ['query']:
            for result in self.knowledge_base.field_text_search(query, field, top_k*2):
                score_board[result['workflow_id']] += weights['text'] * field_weights[field] * result['score']
            for result in self.knowledge_base.field_semantic_search(query, field, top_k*2):
                score_board[result['workflow_id']] += weights['semantic'] * field_weights[field] * result['score']

        sorted_results = sorted(score_board.items(), key=lambda x: x[1], reverse=True)[:top_k]

        detailed_results = []
        for wf_id, total_score in sorted_results:
            workflow = self.knowledge_base.workflows[wf_id]
            detailed_results.append({
                'workflow_id': wf_id,
                'total_score': total_score,
                'query': workflow.query,
                'plan': workflow.agent_planning,
                'search_plan': workflow.search_agent_planning,
                'agent_experience': workflow.agent_experience,
                'search_agent_experience': workflow.search_agent_experience
            })

        return detailed_results

    def search_by_text(self, query: str, field: str = "query", top_k: int = 3) -> List[dict]:
        results = []
        for result in self.knowledge_base.field_text_search(query, field, top_k):
            workflow = self.get_workflow_details(result['workflow_id'])
            results.append({
                'workflow_id': result['workflow_id'],
                'score': result['score'],
                'content': {
                    'query': workflow.query,
                    'plan': workflow.agent_planning,
                    'search_plan': workflow.search_agent_planning,
                    'agent_experience': workflow.agent_experience,
                    'search_agent_experience': workflow.search_agent_experience
                }
            })
        return sorted(results, key=lambda x: x['score'], reverse=True)[:top_k]

    def search_by_semantic(self, query: str, field: str = "query", top_k: int = 3) -> List[dict]:
        results = []
        for result in self.knowledge_base.field_semantic_search(query, field, top_k):
            workflow = self.get_workflow_details(result['workflow_id'])
            results.append({
                'workflow_id': result['workflow_id'],
                'score': result['score'],
                'content': {
                    'query': workflow.query,
                    'plan': workflow.agent_planning,
                    'search_plan': workflow.search_agent_planning,
                    'agent_experience': workflow.agent_experience,
                    'search_agent_experience': workflow.search_agent_experience
                }
            })
        return sorted(results, key=lambda x: x['score'], reverse=True)[:top_k]

    def get_workflow_details(self, workflow_id: str) -> Optional[WorkflowInstance]:
        return self.knowledge_base.workflows.get(workflow_id)


class MemoryProvider(BaseMemoryProvider):

    DEFAULT_PROMPTS = {
        'student_agent_reason': """Extract key information from user query to construct efficient search terms for retrieving the most relevant results.

Requirements:
1. Analyze the user's question to identify core concepts, terminology, and keywords
2. Extract contextual information and constraints that may impact search quality
3. Break down complex questions into searchable components
4. Identify the domain, subject matter, and specific needs of the question

Output format:
<core concepts or topics of the question>

Ensure search terms are specific enough to retrieve relevant information while maintaining sufficient breadth to capture related cases.
Combine technical terminology with everyday expressions to optimize search effectiveness.

Here is the user query:
{{user_query}}"""
    }

    def __init__(self, config: Optional[dict] = None):
        super().__init__(MemoryType.AGENT_KB, config)

        self.kb_database_path = self.config.get(
            "kb_database_path",
            "./storage/agent_kb/agent_kb_database.json"
        )
        self.top_k = self.config.get("top_k", 3)
        self.search_weights = self.config.get(
            "search_weights",
            {'text': 0.5, 'semantic': 0.5}
        )

        self.model_cache_dir = self.config.get(
            "model_cache_dir",
            "./storage/models"
        )

        self.model = self.config.get("model", None)
        self.akb_manager: Optional[AKB_Manager] = None

    def initialize(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.kb_database_path), exist_ok=True)

            if not os.path.exists(self.kb_database_path):
                atomic_write_json(self.kb_database_path, [], indent=2)

            self.akb_manager = AKB_Manager(
                json_file_paths=[self.kb_database_path],
                model_cache_dir=self.model_cache_dir
            )
            return True

        except Exception as e:
            print(f"Error initializing Agent KB provider: {e}")
            return False

    def _reason_for_retrieval(self, request: MemoryRequest) -> str:
        if not self.model:
            return request.query

        reason_prompt = self.DEFAULT_PROMPTS['student_agent_reason']
        prompt = reason_prompt.replace('{{user_query}}', request.query)

        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]

            response = self.model(messages)
            refined_query = getattr(response, "content", str(response)).strip()

            return refined_query if refined_query else request.query

        except Exception as e:
            print(f"Error in reasoning step: {e}")
            return request.query

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if not self.akb_manager:
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0,
                request_id=str(uuid.uuid4())
            )

        if request.status != MemoryStatus.BEGIN:
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0,
                request_id=str(uuid.uuid4())
            )

        try:
            refined_query = self._reason_for_retrieval(request)

            search_results = self.akb_manager.hybrid_search(
                query=refined_query,
                top_k=self.top_k,
                weights=self.search_weights
            )

            if not search_results:
                return MemoryResponse(
                    memories=[],
                    memory_type=self.memory_type,
                    total_count=0,
                    request_id=str(uuid.uuid4())
                )

            synthesized_content = self._synthesize_all_memories(search_results, request)

            memory_item = MemoryItem(
                id=f"synthesized_{uuid.uuid4()}",
                content=synthesized_content,
                metadata={
                    'num_sources': len(search_results),
                    'source_queries': [r['query'] for r in search_results],
                    'avg_score': sum(r['total_score'] for r in search_results) / len(search_results),
                    'status': request.status.value,
                    'original_query': request.query,
                    'refined_query': refined_query
                },
                score=sum(r['total_score'] for r in search_results) / len(search_results)
            )

            return MemoryResponse(
                memories=[memory_item],
                memory_type=self.memory_type,
                total_count=1,
                request_id=str(uuid.uuid4())
            )

        except Exception as e:
            print(f"Error providing memory: {e}")
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0,
                request_id=str(uuid.uuid4())
            )

    def _synthesize_all_memories(self, results: List[Dict[str, Any]], request: MemoryRequest) -> str:
        try:
            if request.status == MemoryStatus.BEGIN:
                student_guidance = self._synthesize_student_guidance(results, request)
                teacher_guidance = self._synthesize_teacher_guidance(results, request)

                return (
                    "AGENT-KB Student Guidance:\n"
                    f"{student_guidance}\n\n"
                    "AGENT-KB Teacher Guidance:\n"
                    f"{teacher_guidance}"
                )

            queries = [r['query'] for r in results if r.get('query')]
            return f"AGENT-KB Guidance: {'; '.join(queries)}"

        except Exception as e:
            print(f"Error synthesizing memories: {e}")
            queries = [r.get('query', '') for r in results if r.get('query')]
            joined = '; '.join(queries) if queries else results[0].get('query', '')
            return f"AGENT-KB Guidance: {joined}"

    def _synthesize_student_guidance(self, results: List[Dict[str, Any]], request: MemoryRequest) -> str:
        try:
            if not self.model:
                all_plans = []
                for r in results:
                    if r.get('plan'):
                        all_plans.append(r['plan'])
                    if r.get('search_plan'):
                        all_plans.append(r['search_plan'])
                return ' '.join(all_plans) if all_plans else results[0].get('query', '')

            all_planning_content = []
            for i, result in enumerate(results, 1):
                source_parts = []

                if result.get('query'):
                    source_parts.append(f"Similar task:\n{result['query']}")

                suggestions = []
                if result.get('plan'):
                    suggestions.append(result['plan'])
                if result.get('search_plan'):
                    suggestions.append(result['search_plan'])

                if suggestions:
                    source_parts.append(f"Suggestions:\n{' '.join(suggestions)}")

                if source_parts:
                    all_planning_content.append('\n'.join(source_parts))

            if not all_planning_content:
                return results[0].get('query', '')

            matched_content = "\n\n".join(all_planning_content)

            prompt = f"""Analyze similar tasks and past experiences to generate concise, actionable suggestions for improving the current plan. Based on the patterns identified in relevant tasks and insights from the knowledge base, provide specific recommendations.

**Key Requirements:**
1. Focus exclusively on technical/behavioral improvements derived from similar task patterns and experience.
2. Provide root-cause solutions and implementation strategies based on past successes.
3. Provide 2-3 specific suggestions only.
4. Format output strictly as:
   1. [Specific suggestion 1]
   2. [Specific suggestion 2]
   ...
5. Use gentle, suggestive language rather than directive commands.
No headings, explanations, or markdown.

**Current Task:** {request.query}

**You can refer to similar tasks, plans, and corresponding experience to provide your suggestions:**
{matched_content}"""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            response = self.model(messages)
            guidance = getattr(response, "content", str(response)).strip()

            return guidance if guidance else '; '.join([r.get('query', '') for r in results])

        except Exception as e:
            print(f"Error synthesizing student guidance: {e}")
            return results[0].get('query', '')

    def _synthesize_teacher_guidance(self, results: List[Dict[str, Any]], request: MemoryRequest) -> str:
        try:
            if not self.model:
                all_experiences = []
                for r in results:
                    if r.get('agent_experience'):
                        all_experiences.append(r['agent_experience'])
                    if r.get('search_agent_experience'):
                        all_experiences.append(r['search_agent_experience'])
                return ' '.join(all_experiences) if all_experiences else results[0].get('query', '')

            all_experience_content = []
            for i, result in enumerate(results, 1):
                source_content = []
                if result.get('query'):
                    source_content.append(f"Query: {result['query']}")
                if result.get('agent_experience'):
                    source_content.append(f"Agent Experience: {result['agent_experience']}")
                if result.get('search_agent_experience'):
                    source_content.append(f"Search Experience: {result['search_agent_experience']}")

                if source_content:
                    all_experience_content.append(
                        f"Source {i} (Score: {result.get('total_score', 0):.3f}):\n" +
                        "\n".join(source_content)
                    )

            if not all_experience_content:
                return results[0].get('query', '')

            agent_context = ""
            if request and request.context:
                max_context_length = 1000
                truncated_context = request.context
                if len(request.context) > max_context_length:
                    truncated_context = "... [truncated]\n" + request.context[-max_context_length:]
                agent_context = f"\n\nCurrent Agent Context:\n{truncated_context}"

            matched_content = "\n\n".join(all_experience_content)

            prompt = f"""You are an experienced AI agent teacher synthesizing multiple experience entries to provide unified operational guidance.

Current Task: {request.query}

Retrieved Experience Entries ({len(results)} sources):
{matched_content}{agent_context}

Based on ALL the matched experience above, synthesize cohesive, unified operational guidance for the agent. Your guidance should:

1. Integrate techniques and methods from all sources
2. Combine common pitfalls and best practices across sources
3. Provide specific, actionable execution tips

Requirements:
- Be specific and comprehensive (2-3 sentences)
- Focus on detailed operations and practical techniques
- Present a unified perspective synthesizing all sources
- Provide concrete, actionable suggestions
- Help refine and improve the current approach based on collective experience
- Use gentle, suggestive language rather than directive commands.
Provide only the synthesized guidance text with no additional explanations or source references."""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            response = self.model(messages)
            guidance = getattr(response, "content", str(response)).strip()

            return guidance if guidance else '; '.join([r.get('query', '') for r in results])

        except Exception as e:
            print(f"Error synthesizing teacher guidance: {e}")
            return results[0].get('query', '')



    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        """
        Ingest new memory by intelligently summarizing trajectory with model
        Only processes successful task executions
        """
        try:
            if not self.model:
                error_msg = "Error: No model provided for memory summarization"
                print(error_msg)
                return False, error_msg

            # Check if task was successful before processing
            if not self._is_task_successful(trajectory_data):
                msg = "Skipping memory ingestion: Task was not successful"
                print(msg)
                return False, msg

            # Use model to intelligently summarize the trajectory
            memory_summary = self._summarize_trajectory_with_model(trajectory_data)

            if not memory_summary:
                error_msg = "Error: Model summarization failed"
                print(error_msg)
                return False, error_msg

            # Create new workflow instance data with model-generated summaries
            new_workflow = {
                "question": trajectory_data.query,
                "agent_planning": memory_summary.get("agent_planning", ""),
                "search_agent_planning": memory_summary.get("search_agent_planning", ""),
                "agent_experience": memory_summary.get("agent_experience", ""),
                "search_agent_experience": memory_summary.get("search_agent_experience", ""),
                "timestamp": datetime.now().isoformat(),
                "metadata": trajectory_data.metadata or {}
            }

            # Append to database file (ensure dir)
            os.makedirs(os.path.dirname(self.kb_database_path), exist_ok=True)
            with file_lock(self.kb_database_path):
                if os.path.exists(self.kb_database_path):
                    try:
                        with open(self.kb_database_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                    except Exception:
                        data = []
                else:
                    data = []

                if not isinstance(data, list):
                    data = []

                data.append(new_workflow)
                atomic_write_json(self.kb_database_path, data, indent=2)

            # Reinitialize the manager to include new data
            self.akb_manager = AKB_Manager(json_file_paths=[self.kb_database_path])

            absorbed_memory = f"Summarized trajectory: {memory_summary}"
            return True, absorbed_memory

        except Exception as e:
            error_msg = f"Error taking in memory: {e}"
            print(error_msg)
            return False, error_msg

    def _is_task_successful(self, trajectory_data: TrajectoryData) -> bool:
        try:
            metadata = trajectory_data.metadata or {}

            if 'is_correct' in metadata:
                return metadata['is_correct'] is True

            if 'success' in metadata:
                return metadata['success'] is True
            if 'task_success' in metadata:
                return metadata['task_success'] is True

            return False

        except Exception as e:
            print(f"Error determining task success: {e}")
            return False

    def _format_trajectory_for_model(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return "No execution trajectory available"

        trajectory_parts = []
        trajectory_parts.append(f"Task: {trajectory_data.query}")
        trajectory_parts.append("")

        for i, step in enumerate(trajectory_data.trajectory, 1):
            step_type = step.get('type', 'step')
            content = step.get('content', '')
            trajectory_parts.append(f"Step {i} ({step_type}): {content}")

        if trajectory_data.result:
            trajectory_parts.append("")
            trajectory_parts.append(f"Final Result: {trajectory_data.result}")

        return "\n".join(trajectory_parts)

    def _summarize_trajectory_with_model(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, str]]:
        """
        Use model to intelligently summarize the trajectory into structured memory components
        """
        try:
            # Prepare trajectory content for model
            trajectory_text = self._format_trajectory_for_model(trajectory_data)

            # Create enhanced summarization prompt based on high-quality examples
            prompt = f"""You are an expert AI agent trainer analyzing a successful task execution to extract high-quality memory patterns for future similar tasks.

TASK ANALYSIS:
Question: {trajectory_data.query}

Execution Trajectory:
{trajectory_text}

Final Result: {trajectory_data.result if trajectory_data.result else "Task completed successfully"}

MEMORY EXTRACTION INSTRUCTIONS:
Extract structured memory components that capture the strategic thinking and methodological approaches used in this successful execution. Focus on actionable insights, specific techniques, and reusable patterns.

Please provide detailed analysis in the following JSON format:

{{
    "agent_planning": "Detailed strategic planning approach with numbered steps, decision-making criteria, tool selection rationale, and problem decomposition strategy",
    "search_agent_planning": "Comprehensive search strategy including query formulation techniques, source prioritization methods, information extraction approaches, and result validation processes",
    "agent_experience": "Key lessons learned, successful methodologies, best practices discovered, error avoidance strategies, and general principles that can guide future similar tasks",
    "search_agent_experience": "Search-specific insights including effective query patterns, reliable source types, information validation techniques, and data processing approaches"
}}

QUALITY REQUIREMENTS:
1. Each field must contain substantial, specific content (minimum 2-3 detailed sentences)
2. Focus on ACTIONABLE strategies and CONCRETE methodologies, not generic descriptions
3. Include specific decision points, tool choices, and reasoning patterns
4. Emphasize successful techniques that led to task completion
5. Extract transferable knowledge that applies to similar problem types
6. Use professional, instructional language as if training another agent
7. Include specific examples or patterns where applicable

EXAMPLES OF HIGH-QUALITY CONTENT:
- Agent Planning: "1. Decompose the inquiry: Identify entities using biographical clues... 2. Data/Tool Use Decisions: Use search to resolve identity and find detailed biography... 3. Delegation Strategy: Author identification requires multi-clue queries..."
- Search Experience: "Construct layered queries that combine multiple discriminators (facts, dates, roles) to improve specificity... Select sources with documented editorial oversight..."

Return ONLY the JSON object with no additional text or explanations."""

            # Call model for summarization using proper message format
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]

            try:
                response = self.model(messages)
                response_text = response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                print(f"Error calling model: {e}")
                return None

            # Extract JSON from response
            try:
                # Try to find JSON in response
                import re

                # First try to parse the entire response as JSON
                try:
                    memory_summary = json.loads(response_text.strip())
                except json.JSONDecodeError:
                    # If that fails, try to extract JSON block
                    json_match = re.search(r'\{.*?\}', response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        memory_summary = json.loads(json_str)
                    else:
                        print(f"Warning: No JSON found in model response: {response_text[:500]}...")
                        return None

                # Validate required fields and content quality
                required_fields = ["agent_planning", "search_agent_planning", "agent_experience", "search_agent_experience"]
                if all(field in memory_summary and memory_summary[field].strip() for field in required_fields):
                    # Additional quality check - ensure substantial content
                    if all(len(memory_summary[field].strip()) >= 50 for field in required_fields):
                        print(f"Successfully extracted high-quality memory summary")
                        return memory_summary
                    else:
                        print(f"Warning: Memory content too brief, requires more detailed analysis")
                        return None
                else:
                    print(f"Warning: Missing or empty required fields in model response: {list(memory_summary.keys())}")
                    return None

            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse JSON from model response: {e}")
                print(f"Response text: {response_text[:500]}...")
                return None

        except Exception as e:
            print(f"Error in model summarization: {e}")
            return None


AgentKBProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.AGENT_KB.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "AgentKBProvider"]
<<<END_FILE>>>
<<<FILE:planning_module/prompts/toolcalling_agent.yaml>>>
planning:
  initial_plan: |-
    You are the concise planner for a single-executor tool agent.

    Produce at most 3 short lines:
    1. What evidence or state changes are needed.
    2. The safest first tool/action direction.
    3. The stop condition and final verifier condition.

    Do not create subtasks, dependency graphs, parallel workers, debate, or long plans.
    Mention that failed calls require changed arguments, a changed tool, or finalization if enough evidence exists.
  task_input: |-
    Task:
    {{task}}
summary:
  update_pre_messages: |-
    You are the concise reflection module for a single-executor tool agent.

    Review only the recent trajectory. Focus on:
    - established observations
    - repeated or failed calls
    - the next valid tool/action
    - whether the agent should call verify_before_final and then final_answer
  update_post_messages: |-
    Return at most 5 lines:
    evidence:
    failed_or_repeated:
    next_action:
    verifier_needed: yes/no
    ready_to_final: yes/no
<<<END_FILE>>>
<<<FILE:action_module/prompts/toolcalling_agent.yaml>>>
system_prompt: |-
  You are a concise reflection tool-using assistant.

  Operate as one executor, not a team. Keep the plan short, use the provided tools directly, reflect every few steps, and verify before the final answer.

  Core rules:
  - Use only tool names and argument keys from the current schema.
  - Prefer one tool call per step.
  - Do not invent tools, records, files, IDs, APIs, or observations.
  - If a tool fails, the next attempt must change the tool, change the arguments, or stop if enough evidence exists.
  - When the answer or state completion seems ready, call verify_before_final once, then call final_answer or the task terminal tool.
  - For state-changing tasks, preserve transaction order and avoid speculative updates.

  Return strict JSON only:
  {
    "think": "brief next-step reasoning",
    "tools": [
      {"name": "actual_tool_name", "arguments": {"arg": "value"}}
    ]
  }

final_answer:
  pre_messages: |-
    Produce the final answer only after checking the trajectory and verifier feedback.

  post_messages: |-
    Return strict JSON only:

    {
      "think": "brief reason why the answer is supported",
      "answer": "the final answer"
    }

    Rules:
    - The answer field must contain only the requested answer or completion result.
    - Base the answer on observations only.
    - For short-answer or retrieval-style QA tasks, return the raw short answer.
    - For stateful tasks, only claim completion when required state changes or the terminal completion tool support it.

    Task:
    {{task}}

step:
  pre_messages: |-
    Continue the concise single-executor loop.

    Available tool schemas:
    {{tool_functions_json}}

    Original task:
    {{task}}

    Decision checklist:
    - What is the one missing fact or state transition?
    - Does the next tool name exist exactly in the schema?
    - Are the argument keys copied from the schema?
    - Did the same call already fail? If yes, change strategy.
    - Is the answer already supported? If yes, call verify_before_final, then final_answer.

    Return strict JSON only:
    {
      "think": "brief reasoning",
      "tools": [
        {"name": "actual_tool_name", "arguments": {"arg": "value"}}
      ]
    }
<<<END_FILE>>>

## Example Harness: harness3

### Harness Identity
- Planning system: guarded_joy_agent
- Action system: guarded_joy_agent
- Default memory system: memp
- Default bench type: None
- Pairing reason: matched_same_name

### Description
Harness summary:
- Planning: augment the task, retrieve relevant memory, then route work deliberately.
- Execution: a small mixed team combines one structured worker with several adaptive workers.
- Memory: reusable skill-like procedures can be surfaced during execution.
- Default bench: caller-provided

Coordination pattern:
- Use one stable planner-executor for high-precision work.
- Run several adaptive workers for broader exploration.
- Compare the returned candidates before committing to an answer.

Runtime notes:
- Generated bundle: `harness3`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.

### Performance Snapshot
- Evaluated tasks: 80
- Exact accuracy: 41.25%
- Valid answer rate: 100.00%
- Average path score: 0.6132
- Average actions: 2.0
- Average tool calls: 2.0
- Average total tokens: 21502.97
- Average runtime (sec): 91.22
- Source result file: output/toolhop_round1_harness3/toolhop_flash_searcher_flash_searcher_skillweaver_local_qwen3-aevolve_closed_results.jsonl

### Performance Report
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

### Bundle Files
<<<FILE:builder.py>>>
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Agents.agents import ToolCallingAgent
from module_action.base_action import ActionContext
from .action_module.provider import ACTION_SYSTEM, get_provider
from .memory_module.provider import MEMORY_SYSTEM as DEFAULT_MEMORY_SYSTEM
from .planning_module.provider import PLANNING_SYSTEM, PlanningClass


HARNESS_NAME = "harness3"
DEFAULT_BENCH_TYPE = None
PAIRING_REASON = "matched_same_name"


def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
    if tool is not None and hasattr(tool, "agent"):
        setattr(tool, "agent", agent)


def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
    if getattr(agent, "planning_system", None) != "owl":
        return
    if not hasattr(agent, "web_memory") or agent.web_memory is None:
        agent.web_memory = []
    if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
        agent.reasoning_memory = []


def prepare_context(context: ActionContext) -> ActionContext:
    bench_type = context.bench_type or DEFAULT_BENCH_TYPE
    prompts_type = context.prompts_type or PLANNING_SYSTEM
    prepared_kwargs = dict(context.kwargs)
    prepared_kwargs["planning_class"] = PlanningClass
    return replace(
        context,
        planning_system=PLANNING_SYSTEM,
        action_system=ACTION_SYSTEM,
        prompts_type=prompts_type,
        bench_type=bench_type,
        project_root=Path(__file__).resolve().parent,
        kwargs=prepared_kwargs,
    )


def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
    prepared_context = prepare_context(context)
    action_provider = get_provider()
    agent = action_provider.build(prepared_context)

    setattr(agent, "planning_system", prepared_context.planning_system)
    setattr(agent, "action_system", prepared_context.action_system)
    setattr(agent, "harness_name", HARNESS_NAME)
    setattr(
        agent,
        "harness_metadata",
        {
            "planning_system": PLANNING_SYSTEM,
            "action_system": ACTION_SYSTEM,
            "default_bench_type": DEFAULT_BENCH_TYPE,
            "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
            "pairing_reason": PAIRING_REASON,
        },
    )

    if prepared_context.vector_tool is not None:
        prepared_context.vector_tool.memory = agent.memory

    _bind_agent_reference(agent, prepared_context.process_tool)
    _bind_agent_reference(agent, prepared_context.end_process_tool)
    _bind_agent_reference(agent, prepared_context.delete_memory_tool)
    _bind_agent_reference(agent, prepared_context.executor_tool)
    _bind_agent_reference(agent, prepared_context.refine_tool)

    _ensure_owl_memory(agent)
    return agent
<<<END_FILE>>>
<<<FILE:Description.md>>>
Harness summary:
- Planning: augment the task, retrieve relevant memory, then route work deliberately.
- Execution: a small mixed team combines one structured worker with several adaptive workers.
- Memory: reusable skill-like procedures can be surfaced during execution.
- Default bench: caller-provided

Coordination pattern:
- Use one stable planner-executor for high-precision work.
- Run several adaptive workers for broader exploration.
- Compare the returned candidates before committing to an answer.

Runtime notes:
- Generated bundle: `harness3`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
<<<END_FILE>>>
<<<FILE:__init__.py>>>
from .builder import (
    ACTION_SYSTEM,
    DEFAULT_BENCH_TYPE,
    DEFAULT_MEMORY_SYSTEM,
    PAIRING_REASON,
    PLANNING_SYSTEM,
    HARNESS_NAME,
    build_agent_from_context,
)

__all__ = [
    "HARNESS_NAME",
    "PLANNING_SYSTEM",
    "ACTION_SYSTEM",
    "DEFAULT_BENCH_TYPE",
    "DEFAULT_MEMORY_SYSTEM",
    "PAIRING_REASON",
    "build_agent_from_context",
]
<<<END_FILE>>>
<<<FILE:planning_module/provider.py>>>
import json
import textwrap
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from rich.rule import Rule
from rich.text import Text
from module_planning.base_planning import BasePlanning

def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")


class PlanningProvider(BasePlanning):

    def _get_role_planning_templates(self, role: Dict[str, str]) -> Dict[str, str]:
        if role["name"] == "PE-Worker":
            return {
                "initial_plan": (
                    "### Roadmap (One-time)\n"
                    "1. Identify the key task requirements and missing information.\n"
                    "2. Use the available tools to gather, inspect, validate, or compute the needed evidence.\n"
                    "3. Cross-check critical findings when necessary.\n"
                    "4. Produce a definitive answer.\n"
                    "[STRICT] Follow the roadmap. No re-planning."
                ),
                "task_input": "Task: {{task}}. Generate roadmap.",
            }
        if role["name"] == "ReAct-Worker":
            return {
                "initial_plan": "### ReAct Strategy\nLoop: Think -> Act -> Observe.",
                "task_input": "Task: {{task}}. State strategy.",
            }
        return self.prompt_templates.get("planning", {})

    def _get_role_summary_templates(self, role: Dict[str, str]) -> Dict[str, str]:
        if role["name"] == "PE-Worker":
            return {
                "update_pre_messages": "Reporting progress...",
                "update_post_messages": "Summarize status versus roadmap. No re-planning.",
            }
        if role["name"] == "ReAct-Worker":
            return {
                "update_pre_messages": "Analyzing exploration...",
                "update_post_messages": "Summarize findings and adapt if blocked.",
            }
        return self.prompt_templates.get("summary", {})

    def _get_role_info(self) -> Dict[str, str]:
        explicit_role = getattr(self, "role_info", None)
        if isinstance(explicit_role, dict) and explicit_role.get("name"):
            return explicit_role

        content = self.prompt_templates.get("system_prompt", "")
        if "coordination agent" in content.lower():
            return {"name": "Task Augmentation", "style": "bold yellow", "title_suffix": ""}
        if "plan-and-execute expert" in content.lower():
            return {"name": "PE-Worker", "style": "cyan", "title_suffix": " Roadmap"}
        if "react expert" in content.lower():
            return {"name": "ReAct-Worker", "style": "magenta", "title_suffix": " Strategy"}
        return {"name": "Worker", "style": "blue", "title_suffix": " Planning"}

    def topology_initialize(self, task: str) -> PlanningStep:
        role = self._get_role_info()
        planning_templates = self._get_role_planning_templates(role)
        retrieved_knowledge = ""

        # 1. Semantic Memory Retrieval (Supervisor only)
        if role['name'] == "Task Augmentation":
            vector_tool = self.tools.get("vector_similarity_retrieve")
            if vector_tool:
                try:
                    # Search through current memory steps (which include historical Knowledge Units)
                    retrieved_knowledge = vector_tool.forward(task)
                    if "No historical action steps" in retrieved_knowledge or "Error" in retrieved_knowledge:
                        retrieved_knowledge = ""
                    else:
                        # Token Optimization: Strictly truncate historical context
                        if len(retrieved_knowledge) > 500:
                            retrieved_knowledge = retrieved_knowledge[:500] + "... (truncated)"

                        # Format history to be clearly distinct from current task
                        retrieved_knowledge = f"\n[PAST EXPERIENCE (For Reference Only)]:\n{retrieved_knowledge}"
                        self.logger.log(Text("\n[Semantic Memory] Relevant historical context retrieved.", style="italic cyan"), level=LogLevel.INFO)
                except Exception:
                    retrieved_knowledge = ""

        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            planning_templates["initial_plan"],
                            variables={"tools": self.tools, "retrieved_knowledge": retrieved_knowledge, "task": task},
                        ),
                    }
                ],
            },
        ]
        memory_guidance = self.append_memory_guidance(input_messages)
        task_messages = [{
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": populate_template(planning_templates["task_input"], variables={"task": task})}],
        }]

        chat_message_plan: ChatMessage = self.model(input_messages + task_messages)
        plans_answer = chat_message_plan.content
        think_content = getattr(chat_message_plan, "reasoning_content", "")

        title = f"{role['name']}{role['title_suffix']}"

        self.logger.log(
            Rule(title, style=role['style']),
            Text(f"\n{plans_answer}\n"),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plans_answer,
            plan_think="",
            plan_reasoning=think_content,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]]
    ) -> SummaryStep:
        role = self._get_role_info()
        if role['name'] == "Task Augmentation":
            return SummaryStep(model_input_messages=[], summary="Monitoring ensemble execution...", summary_reasoning="")
        summary_templates = self._get_role_summary_templates(role)

        # Worker Summary Policy: STRICTLY Progress-only, NO re-planning.
        memory_messages = write_memory_to_messages(None, False)[1:]
        summary_policy = "\n[SUMMARY POLICY]: Report progress ONLY. DO NOT change the initial roadmap or propose new plans."

        input_messages = [
            {"role": MessageRole.SYSTEM, "content": [{"type": "text", "text": summary_templates["update_pre_messages"] + summary_policy}]},
            *memory_messages,
            {"role": MessageRole.USER, "content": [{"type": "text", "text": summary_templates["update_post_messages"]}]}
        ]

        chat_message_summary: ChatMessage = self.model(input_messages)
        summary_answer = chat_message_summary.content
        summary_cot = getattr(chat_message_summary, "reasoning_content", "")

        self.logger.log(
            Rule(f"{role['name']} Execution Summary", style="blue"),
            Text(f"\n{summary_answer}\n"),
            level=LogLevel.INFO,
        )

        summary_step = SummaryStep(input_messages, summary_answer, summary_cot)
        self.memory.steps.append(summary_step)
        return summary_step

PLANNING_SYSTEM = 'guarded_joy_agent'
PLANNING_MODULE = 'guarded_joy_agent'
PlanningClass = PlanningProvider

__all__ = ['PLANNING_SYSTEM', 'PLANNING_MODULE', 'PlanningProvider', 'PlanningClass']
<<<END_FILE>>>
<<<FILE:action_module/provider.py>>>
from __future__ import annotations

from typing import Any

from Agents.agents import ToolCallingAgent
from Agents.tools import EnsembleTool, VoteTool

from _harness_guards import guard_task_tools
from module_action.base_action import ActionContext, BaseActionProvider


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "guarded_joy_agent"
    REACT_WORKERS = 2
    DEFAULT_WORKER_MAX_STEPS = 7

    def _worker_max_steps(self, context: ActionContext) -> int:
        remaining_budget = max(1, context.max_steps - 3)
        return max(4, min(self.DEFAULT_WORKER_MAX_STEPS, remaining_budget))

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = self.PROMPTS_TYPE
        guarded_tools = guard_task_tools(
            tools,
            policy_label="guarded_joy_worker",
            max_real_tool_calls=self._worker_max_steps(context),
        )
        self.coordinator_role = {
            "name": "Task Augmentation",
            "style": "bold yellow",
            "title_suffix": "",
            "responsibility": "Augment the task, retrieve procedural memory, orchestrate a small guarded ensemble, and stop early.",
        }
        self.pe_role = {
            "name": "PE-Worker",
            "style": "cyan",
            "title_suffix": " Roadmap",
            "responsibility": "Plan once, execute along a stable roadmap, and avoid repeated failed tool calls.",
        }
        self.react_role = {
            "name": "ReAct-Worker",
            "style": "magenta",
            "title_suffix": " Strategy",
            "responsibility": "Explore briefly, then change strategy after any failed observation.",
        }
        planning_class = context.kwargs.get("planning_class")

        self.pe_worker = self.create_subagent(
            context,
            tools=guarded_tools,
            planning_system=self.organization_planning_system,
            planning_class=planning_class,
            prompt_templates=self.prompt_templates["pe_worker"],
            name="pe_expert",
            max_steps=self._worker_max_steps(context),
            summary_interval=context.max_steps + 1,
            description=(
                "Expert at structured logic and high-reliability reports. "
                "Follows a guarded Plan-Execute paradigm."
            ),
        )
        if getattr(self.pe_worker, "planning", None) is not None:
            self.pe_worker.planning.role_info = self.pe_role

        self.react_workers = [
            self.create_subagent(
                context,
                tools=guarded_tools,
                planning_system=self.organization_planning_system,
                planning_class=planning_class,
                prompt_templates=self.prompt_templates["react_worker"],
                name=f"react_expert_{i}",
                max_steps=self._worker_max_steps(context),
                summary_interval=context.max_steps + 1,
                description=(
                    "Fast reactive expert for exploratory search. "
                    "Follows guarded ReAct with early stop."
                ),
            )
            for i in range(1, self.REACT_WORKERS + 1)
        ]
        for worker in self.react_workers:
            if getattr(worker, "planning", None) is not None:
                worker.planning.role_info = self.react_role

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        ensemble_tool = EnsembleTool(
            pe_worker=self.pe_worker,
            react_workers=self.react_workers,
        )
        vote_tool = VoteTool(model=context.model)
        root_tools = self.normalize_tools([ensemble_tool, vote_tool, context.vector_tool])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        if getattr(agent, "planning", None) is not None:
            agent.planning.role_info = self.coordinator_role
        agent.managed_agents = {
            worker.name: worker for worker in [self.pe_worker] + self.react_workers
        }
        ensemble_tool.agent = agent
        vote_tool.agent = agent
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "guarded_joy_agent",
                "pe_workers": 1,
                "react_workers": len(self.react_workers),
                "worker_max_steps": self._worker_max_steps(context),
                "guarded_worker_tools": True,
            },
        )
        return agent

ACTION_SYSTEM = 'guarded_joy_agent'
ACTION_MODULE = 'guarded_joy_agent'

def get_provider():
    return ActionProvider()

__all__ = ['ACTION_SYSTEM', 'ACTION_MODULE', 'ActionProvider', 'get_provider']
<<<END_FILE>>>
<<<FILE:memory_module/provider.py>>>
"""
SkillWeaver provider for unified memory system
"""

import os
import importlib.util
import uuid
import re
import ast
import inspect
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable

from module_memory.base_memory import BaseMemoryProvider, atomic_write_text, file_lock
from module_memory.memory_types import (
    MemoryRequest,
    MemoryResponse,
    TrajectoryData,
    MemoryType,
    MemoryItem,
    MemoryItemType,
    MemoryStatus
)

# Import unified tool wrapper
from storage.tools.tool_wrapper import ToolWrapper


class MemoryProvider(BaseMemoryProvider):
    """
    SkillWeaver memory provider that manages generated skills
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(MemoryType.SKILLWEAVER, config)

        # Configuration
        self.skills_file_path = self.config.get(
            "skills_file_path",
            "./storage/skillweaver/skillweaver_generated_skills.py",
        )
        # Optional skills directory: load all *.py files if provided
        self.skills_dir = self.config.get("skills_dir", "./storage/skillweaver")

        # Optional model used directly for LLM-driven code generation
        self.model = self.config.get("model")

        # Skills registry
        self.skills_registry: Dict[str, Callable] = {}
        self.skills_metadata: Dict[str, Dict[str, Any]] = {}

        # Logger
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(asctime)s] [SkillWeaver] [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # Initialize unified tool wrapper
        self.tool_wrapper = ToolWrapper(model=self.model, logger=self.logger)

    def initialize(self) -> bool:
        """Initialize SkillWeaver provider by loading existing skills"""
        try:
            # Ensure storage directories exist
            if self.skills_dir:
                os.makedirs(self.skills_dir, exist_ok=True)
            parent_dir = os.path.dirname(self.skills_file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            # Prefer loading from directory when available, else fallback to single file
            if os.path.isdir(self.skills_dir):
                self._load_skills_from_dir(self.skills_dir)
            elif os.path.exists(self.skills_file_path):
                self._load_skills_from_file(self.skills_file_path)
            # If neither exists, still return True to allow future ingestion to create files
            return True
        except Exception as e:
            print(f"Error initializing SkillWeaver provider: {e}")
            return False

    def _load_skills_from_file(self, file_path: str):
        """Load skills from a single generated skills file"""
        try:
            spec = importlib.util.spec_from_file_location("skillweaver_skills", file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._populate_registry_from_module(module)
        except Exception as e:
            print(f"Error loading skills from file {file_path}: {e}")

    def _load_skills_from_dir(self, dir_path: str):
        """Load skills from all .py files in a directory"""
        try:
            for filename in os.listdir(dir_path):
                if not filename.endswith(".py") or filename.startswith("__"):
                    continue
                file_path = os.path.join(dir_path, filename)
                try:
                    spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self._populate_registry_from_module(module)
                except Exception as inner_e:
                    print(f"Error loading skills from {file_path}: {inner_e}")
        except Exception as e:
            print(f"Error scanning skills directory {dir_path}: {e}")

    def _populate_registry_from_module(self, module):
        """Extract public callables from a module as skills and capture their metadata"""
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if callable(obj):
                self.skills_registry[name] = obj
                docstring = getattr(obj, "__doc__", "") or ""
                self.skills_metadata[name] = {
                    "description": (docstring.split("\n")[0] if docstring else name),
                    "full_docstring": docstring,
                    "module": getattr(module, "__name__", "skillweaver_skills"),
                }

    def _reload_skills(self):
        """Reload skills after ingestion"""
        self.skills_registry.clear()
        self.skills_metadata.clear()
        self.tool_wrapper.clear_cache()  # Clear tool wrapper cache when reloading
        if os.path.isdir(self.skills_dir):
            self._load_skills_from_dir(self.skills_dir)
        elif os.path.exists(self.skills_file_path):
            self._load_skills_from_file(self.skills_file_path)

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        """
        Provide memory by searching for relevant skills
        """
        try:
            if request.status != MemoryStatus.BEGIN:
                return MemoryResponse(
                    memories=[],
                    memory_type=self.memory_type,
                    total_count=0,
                    request_id=str(uuid.uuid4()),
                )

            # Simple keyword matching for skills
            relevant_skills = []
            query_lower = request.query.lower()

            for skill_name, metadata in self.skills_metadata.items():
                description = metadata.get("description", "").lower()
                docstring = metadata.get("full_docstring", "").lower()

                # Score based on keyword matches
                score = 0.0
                for word in query_lower.split():
                    if word in skill_name.lower():
                        score += 2.0
                    elif word in description:
                        score += 1.5
                    elif word in docstring:
                        score += 1.0

                if score > 0:
                    relevant_skills.append({
                        "skill_name": skill_name,
                        "metadata": metadata,
                        "score": score,
                    })

            # Sort by score and take top results
            relevant_skills.sort(key=lambda x: x["score"], reverse=True)
            top_skills = relevant_skills[:3]

            # Convert to MemoryItem format
            memories: List[MemoryItem] = []
            for skill_info in top_skills:
                skill_name = skill_info["skill_name"]
                function_obj = self.skills_registry.get(skill_name)
                if not function_obj:
                    continue
                content = self._format_skill_content(skill_name, skill_info["metadata"], request.status)

                # Wrap function as a runtime tool
                wrapped_tool = self._wrap_tool(function_obj, skill_name)

                memory_item = MemoryItem(
                    id=f"skill_{skill_name}",
                    content=content,
                    metadata={
                        "skill_name": skill_name,
                        "description": skill_info["metadata"].get("description", ""),
                        "score": skill_info["score"],
                        "callable": function_obj,  # Keep original function
                        "wrapped_tool": wrapped_tool,  # Add wrapped tool
                        "status": request.status.value,
                    },
                    score=skill_info["score"],
                    type=MemoryItemType.API,
                )
                memories.append(memory_item)

            return MemoryResponse(
                memories=memories,
                memory_type=self.memory_type,
                total_count=len(memories),
                request_id=str(uuid.uuid4()),
            )
        except Exception as e:
            print(f"Error providing SkillWeaver memory: {e}")
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)

    def _wrap_tool(self, tool_func: Callable, tool_name: str) -> Optional[Any]:
        """Wrap Python function as Tool object using unified ToolWrapper"""
        return self.tool_wrapper.wrap_function(tool_func, tool_name)

    def _format_skill_content(self, skill_name: str, metadata: Dict, status: MemoryStatus) -> str:
        """Format skill content for API-type memory - content will be handled by main file"""
        try:
            if status == MemoryStatus.BEGIN:
                return f"SkillWeaver Available skill: {skill_name}\nDescription: {metadata.get('description', '')}"
            elif status == MemoryStatus.IN:
                return None  # SkillWeaver only provides memory in BEGIN phase
            return f"SkillWeaver Skill: {skill_name}: {metadata.get('description', '')}"
        except Exception as e:
            print(f"Error formatting skill content: {e}")
            return f"SkillWeaver Skill: {skill_name}"

    def _extract_function_from_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Extract the first function from Python code using AST and return its name and the code block."""
        try:
            tree = ast.parse(code)
            func_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            if not func_defs:
                return None
            func = func_defs[0]
            func_name = func.name
            # Best-effort: return the full code as provided (we won't slice exact function body)
            return {"name": func_name, "code": code}
        except Exception:
            return None

    def _is_dangerous_code(self, code: str) -> bool:
        """Basic static checks to avoid dangerous operations in generated skills."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Block eval/exec/compile and raw open
                    if isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval", "compile", "__import__"}:
                        return True
                    if isinstance(node.func, ast.Name) and node.func.id == "open":
                        return True
                if isinstance(node, ast.Attribute):
                    if node.attr in {"system", "popen", "spawn", "remove", "rmdir"}:
                        return True
            return False
        except Exception:
            return True

    def _append_skill_to_file(self, function_name: str, code: str) -> bool:
        """Append skill code to the aggregator file, creating header if needed and avoiding duplicates."""
        try:
            os.makedirs(os.path.dirname(self.skills_file_path) or ".", exist_ok=True)
            with file_lock(self.skills_file_path):
                existing = ""
                if os.path.exists(self.skills_file_path):
                    with open(self.skills_file_path, "r", encoding="utf-8") as f:
                        existing = f.read()
                else:
                    existing = (
                        '"""\nSkillWeaver Generated Skills\nAuto-generated and continuously updated by UnifiedMemory SkillWeaverProvider.\nThis file contains dynamically generated skills.\n"""\n\n'
                    )
                if f"def {function_name}(" in existing:
                    return True
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_content = existing + f"\n# Generated on {timestamp}\n{code}\n\n"
                atomic_write_text(self.skills_file_path, new_content)
            return True
        except Exception as e:
            print(f"Error saving generated skill: {e}")
            return False

    def _generate_skill_from_trajectory(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, str]]:
        """Use the injected model to generate a new skill function based on the trajectory."""
        if self.model is None:
            return None
        try:
            # Build prompt (aligned with project conventions)
            trajectory_json = None
            try:
                import json as _json
                trajectory_json = _json.dumps(trajectory_data.trajectory, indent=2, ensure_ascii=False)
            except Exception:
                trajectory_json = str(trajectory_data.trajectory)
            prompt = f"""You are an expert Python programmer specializing in creating reusable, generic functions. Your task is to analyze a successful task execution and extract a GENERAL, PARAMETERIZED skill that can be reused for similar problems.

CRITICAL REQUIREMENTS:
- Create a GENERIC function that accepts parameters, NOT a function that returns hardcoded values
- The function must be REUSABLE for different inputs of the same type of problem
- Focus on the METHODOLOGY and APPROACH, not the specific data from this execution
- Make the function PARAMETERIZED so it can handle various inputs

Original Task:
{trajectory_data.query}

Agent's Successful Trajectory:
```json
{trajectory_json}
```

ANALYSIS INSTRUCTIONS:
1. Identify the CORE METHODOLOGY or ALGORITHM used in the successful execution
2. Abstract away specific values, URLs, names, or data points from this particular task
3. Focus on the GENERAL PATTERN that could apply to similar problems
4. Create a function that takes relevant parameters as input

FUNCTION REQUIREMENTS:
1. Write a single, self-contained Python function that is GENERIC and PARAMETERIZED
2. Use descriptive parameter names and include type hints
3. Include comprehensive docstring with Args and Returns sections
4. Add proper error handling and input validation
5. The function should work for DIFFERENT inputs of the same problem type
6. DO NOT hardcode specific values from this execution - make them parameters instead

EXAMPLE OF GOOD vs BAD:
❌ BAD: def get_population(): return 1234567  # Returns hardcoded value
✅ GOOD: def get_population_from_source(source_url: str, location: str) -> int  # Generic, parameterized

Output ONLY the Python code for this generic function inside a single markdown code block:"""
            messages = [{"role": "user", "content": prompt}]
            response = self.model(messages)
            content = getattr(response, "content", str(response))
            # Extract python code block
            m = re.search(r"```python\n(.*?)```", content, re.DOTALL)
            code = m.group(1).strip() if m else content.strip()
            # Validate
            if self._is_dangerous_code(code):
                return None
            func_info = self._extract_function_from_code(code)
            if not func_info:
                return None
            return {"name": func_info["name"], "code": code}
        except Exception:
            return None

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        """
        Ingest new memory by generating new skills from trajectory using the injected model.
        Only extracts skills from trajectories with correct answers to avoid learning bad patterns.
        """
        try:
            # Check if the trajectory has correct answer - only learn from successful cases
            metadata = trajectory_data.metadata or {}
            is_correct = metadata.get("is_correct", False)
            task_success = bool(metadata.get("task_success", metadata.get("is_correct", False)))

            if not is_correct:
                msg = f"SkillWeaverProvider: skipping skill extraction - answer is incorrect (is_correct={is_correct})"
                print(msg)
                return True, msg  # Return True to not block the pipeline, but don't extract skills

            if not task_success:
                msg = f"SkillWeaverProvider: skipping skill extraction - task execution failed (task_success={task_success})"
                print(msg)
                return True, msg  # Return True to not block the pipeline, but don't extract skills

            print(f"SkillWeaverProvider: extracting skill from correct trajectory (is_correct={is_correct}, task_success={task_success})")

            skill = self._generate_skill_from_trajectory(trajectory_data)
            if not skill:
                # No model or failed generation; succeed silently to avoid blocking
                msg = "SkillWeaverProvider: generation skipped (no model or validation failed)"
                print(msg)
                return True, msg

            saved = self._append_skill_to_file(skill["name"], skill["code"])
            if saved:
                self._reload_skills()
                msg = f"SkillWeaverProvider: successfully extracted and saved skill '{skill['name']}' from correct trajectory"
                print(msg)
                absorbed_memory = {
                    "skill_name": skill['name'],
                    "description": skill.get('description', ''),
                    "code": skill['code']
                }
                return saved, f"Generated skill: {absorbed_memory}"
            else:
                return saved, f"Failed to save skill: {skill['name']}"
        except Exception as e:
            error_msg = f"Error taking in SkillWeaver memory: {e}"
            print(error_msg)
            return False, error_msg


from module_memory.providers.memp_memory_provider import MempMemoryProvider


SkillWeaverProvider = MemoryProvider
MemoryProvider = MempMemoryProvider
MEMORY_SYSTEM = MemoryType.MEMP.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "SkillWeaverProvider", "MempMemoryProvider"]
<<<END_FILE>>>
<<<FILE:planning_module/prompts/toolcalling_agent.yaml>>>
planning:
  initial_plan: |-
    ### Guarded Task Augmentation
    [OUTPUT INSTRUCTION]: Strictly provide ONLY the following fields. NO other text.
    - Task: [Provide ONLY the core question description from {{task}}. DO NOT include any answers or findings from History.]
    - History: {{ retrieved_knowledge if retrieved_knowledge else "None" }}
    - Complexity: [Determine: Simple/Complex]
    - Experts: PE: 1, ReAct: [1 if Simple, 2 if Complex; never more than 2]
    - Guard: [Name the most important tool-schema/repetition risk and the stop condition.]

    [STRICT RULE]: The 'Task' field must only reflect the user's request, NOT the results found in 'History'.
    [RECOVERY RULE]: after a failed observation, the next strategy must repair arguments, switch tools, or stop if evidence is sufficient.
    [STOP]: YOUR OUTPUT MUST END HERE.
  task_input: 'Task: {{task}}'
<<<END_FILE>>>
<<<FILE:action_module/prompts/toolcalling_agent.yaml>>>
system_prompt: |-
  You are a guarded JOY coordination agent. Solve the task by:
  1. CALL `ensemble_executor` with the original task.
  2. CALL `vote_and_synthesize` once experts report back.
  3. CALL `final_answer` with the final verdict.

  [RULES]
  - Use a JSON list of tool calls: [{"name": "...", "arguments": {...}}]
  - Use key "name" for the tool name and "arguments" for parameters.
  - Do NOT call `vector_similarity_retrieve` directly; it is handled automatically when needed.
  - Do not solve the task directly yourself; orchestrate the expert set.
  - When calling `vote_and_synthesize`, the argument key must be `candidates`, not `answers`.
  - Pass the raw JSON output of `ensemble_executor` directly as `candidates`.
  - Do not repeat a failed orchestration call with the same arguments unless a new observation explains why it should now work.
  - If an expert report shows schema mismatch or invalid arguments, direct the next attempt to repair the arguments rather than repeating the same mistake.
  - Keep orchestration small: one ensemble round, one synthesis round, then final when possible.
  - If the ensemble reports repeated failed tool calls, do not rerun the same pattern; synthesize the best supported partial answer or issue a repaired one-shot retry.

  ### Tools
  {%- for tool in tools.values() %}
  - {{ tool.name }}: {{ tool.description }}
  {%- endfor %}
step:
  pre_messages: |-
    [DIRECTIVE]
    1. REVIEW HISTORY: Do not repeat failed orchestration calls.
    2. PHASE ENFORCEMENT:
       - If `ensemble_executor` has not been called, call it now.
       - If expert results are available, call `vote_and_synthesize(task={{task|tojson}}, candidates=<ensemble_executor JSON output>)`.
       - If the verdict is ready, call `final_answer`.
    3. ARGUMENT DISCIPLINE:
       - Never call `vote_and_synthesize` with `answers=...`; always use `candidates=...`.
    4. ADAPTIVE RECOVERY:
       - If experts made invalid tool calls or repeated failures, your next orchestration step must push them to change arguments, tool choice, or strategy.
       - Never relaunch the same failing orchestration pattern without a concrete fix.

    [FORMAT]
    Return a JSON list of tool calls only.

    Tool Definitions:
    {{tool_functions_json}}

    Task: {{task}}
pe_worker:
  system_prompt: |-
    You are a guarded Plan-and-Execute Expert.
    1. Build a roadmap once.
    2. Execute the roadmap using the currently available tools.
    3. Return a grounded final answer.

    [CRITICAL]
    - Plan only once and stay aligned to the roadmap.
    - Use only currently available tools. Do not invent unavailable search tools.
    - Follow each listed tool schema exactly; use the provided argument names and types.
    - Never substitute alternative argument names or call unavailable tools.
    - If a tool call fails because of invalid arguments or schema mismatch, repair the arguments on the next attempt instead of repeating the same failed call.
    - Never repeat an identical failed call unless the observation explicitly justifies it.
    - If a guarded tool blocks a call, immediately change strategy or finalize with supported evidence.
    - Stop early when observations are enough; do not continue just to fill the roadmap.
    - Base your final answer only on observations; do not replace a supported observed result with a new guess.
    - Output only one JSON object:
      {"think": "...", "tools": [{"name": "...", "arguments": {...}}]}

    ### Tools
    {%- for tool in tools.values() %}
    - {{ tool.name }}: {{ tool.description }}
    {%- endfor %}
  step:
    pre_messages: |-
      1. REVIEW HISTORY: Look at previous observations and avoid repeating failed actions.
      2. ROADMAP ADHERENCE: Follow the roadmap, but adjust tool arguments or the next concrete tool choice if current evidence is insufficient.
      3. USE ONLY AVAILABLE TOOLS.
      4. Read the tool schemas carefully; every argument object must match the listed keys exactly.
      5. If progress is weak, change the tool choice, arguments, or strategy; do not retry blindly.

      Task: {{task}}
      Return JSON only.
  final_answer:
    pre_messages: Finalizing Plan-Execute answer.
    post_messages: 'Return JSON: {"think": "...", "answer": "..."}'
react_worker:
  system_prompt: |-
    You are a guarded ReAct Expert.
    Loop: Thought -> Action -> Observation.

    [CRITICAL]
    - Use only the currently available tools.
    - Adapt quickly when a tool call does not make progress.
    - Follow each listed tool schema exactly; use the provided argument names and types.
    - Never substitute alternative argument names or call unavailable tools.
    - If a tool call fails because of invalid arguments or schema mismatch, repair the arguments on the next attempt instead of repeating the same failed call.
    - Never repeat an identical failed call unless the observation explicitly justifies it.
    - If the same strategy fails once, the next step must use a different valid tool, different arguments, or final_answer.
    - Stop early when the answer is supported; avoid long exploratory loops.
    - Base your final answer only on observations; do not replace a supported observed result with a new guess.
    - Output only one JSON object:
      {"think": "...", "tools": [{"name": "...", "arguments": {...}}]}

    ### Tools
    {%- for tool in tools.values() %}
    - {{ tool.name }}: {{ tool.description }}
    {%- endfor %}
  step:
    pre_messages: |-
      [DIRECTIVE]
      1. REVIEW HISTORY: Do not repeat failed tool calls or identical arguments.
      2. ADAPTATION: If progress is weak, change the tool choice, arguments, or strategy.
      3. USE ONLY AVAILABLE TOOLS.
      4. Read the tool schemas carefully; every argument object must match the listed keys exactly.
      5. If a tool failed because of invalid arguments, your next attempt must correct the arguments or switch tools.
      6. If a guard blocks a repeated failed call, do not retry that call.

      Task: {{task}}
      Return JSON only.
  final_answer:
    pre_messages: Finalizing ReAct answer.
    post_messages: 'Return JSON: {"think": "...", "answer": "..."}'
final_answer:
  pre_messages: Ensemble arbitration complete.
  post_messages: 'Final answer for: {{task}}. Return JSON {think, answer}.'
critic:
  prompt: |-
    Judge expert answers for: {{task}}

    ### Candidates
    {%- for cand in candidates %}
    - EXPERT: {{ cand.agent_name }}
    - ANSWER: {{ cand.answer }}
    - TRACE: {{ cand.message_object.intermediate_evidence | tojson }}
    {%- endfor %}

    ### Instructions
    1. Check compliance, evidence, and logic.
    2. If a majority answer is supported by evidence, prioritize it.
    3. Return JSON: {"think": "...", "verdict_answer": "...", "confidence": 0.0-1.0}
    [CRITICAL] A definitive answer is required.
distiller:
  prompt: |-
    ### Distill Knowledge Unit
    Problem: {{task}}
    Trace: {{trajectory}}
    Answer: {{answer}}
    Format:
    [Problem]: ...
    [Strategy]: ...
    [Findings]: ...
    [Conclusion]: ...
    (Return block only)
<<<END_FILE>>>

## Example Harness: harness4

### Harness Identity
- Planning system: reflection_critic
- Action system: reflection_critic
- Default memory system: agent_workflow_memory
- Default bench type: None
- Pairing reason: matched_same_name

### Description
Harness summary:
- Planning: decide how much parallel investigation the task deserves.
- Execution: a coordinator launches multiple focused investigators, then synthesizes their findings.
- Memory: workflow traces can be retrieved to ground later decisions.
- Default bench: caller-provided

Coordination pattern:
- Start with parallel evidence gathering.
- Consolidate intermediate findings before final synthesis.
- Use the coordinator only for orchestration and final answer assembly.

Runtime notes:
- Generated bundle: `harness4`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.

### Performance Snapshot
- Evaluated tasks: 80
- Exact accuracy: 20.00%
- Valid answer rate: 100.00%
- Average path score: 0.2985
- Average actions: 1.35
- Average tool calls: 2.275
- Average total tokens: 4666.86
- Average runtime (sec): 86.9
- Source result file: output/toolhop_round1_harness4/toolhop_flash_searcher_flash_searcher_agent_workflow_memory_local_qwen3-aevolve_closed_results.jsonl

### Performance Report
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

### Bundle Files
<<<FILE:builder.py>>>
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Agents.agents import ToolCallingAgent
from module_action.base_action import ActionContext
from .action_module.provider import ACTION_SYSTEM, get_provider
from .memory_module.provider import MEMORY_SYSTEM as DEFAULT_MEMORY_SYSTEM
from .planning_module.provider import PLANNING_SYSTEM, PlanningClass


HARNESS_NAME = "harness4"
DEFAULT_BENCH_TYPE = None
PAIRING_REASON = "matched_same_name"


def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
    if tool is not None and hasattr(tool, "agent"):
        setattr(tool, "agent", agent)


def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
    if getattr(agent, "planning_system", None) != "owl":
        return
    if not hasattr(agent, "web_memory") or agent.web_memory is None:
        agent.web_memory = []
    if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
        agent.reasoning_memory = []


def prepare_context(context: ActionContext) -> ActionContext:
    bench_type = context.bench_type or DEFAULT_BENCH_TYPE
    prompts_type = context.prompts_type or PLANNING_SYSTEM
    prepared_kwargs = dict(context.kwargs)
    prepared_kwargs["planning_class"] = PlanningClass
    return replace(
        context,
        planning_system=PLANNING_SYSTEM,
        action_system=ACTION_SYSTEM,
        prompts_type=prompts_type,
        bench_type=bench_type,
        project_root=Path(__file__).resolve().parent,
        kwargs=prepared_kwargs,
    )


def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
    prepared_context = prepare_context(context)
    action_provider = get_provider()
    agent = action_provider.build(prepared_context)

    setattr(agent, "planning_system", prepared_context.planning_system)
    setattr(agent, "action_system", prepared_context.action_system)
    setattr(agent, "harness_name", HARNESS_NAME)
    setattr(
        agent,
        "harness_metadata",
        {
            "planning_system": PLANNING_SYSTEM,
            "action_system": ACTION_SYSTEM,
            "default_bench_type": DEFAULT_BENCH_TYPE,
            "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
            "pairing_reason": PAIRING_REASON,
        },
    )

    if prepared_context.vector_tool is not None:
        prepared_context.vector_tool.memory = agent.memory

    _bind_agent_reference(agent, prepared_context.process_tool)
    _bind_agent_reference(agent, prepared_context.end_process_tool)
    _bind_agent_reference(agent, prepared_context.delete_memory_tool)
    _bind_agent_reference(agent, prepared_context.executor_tool)
    _bind_agent_reference(agent, prepared_context.refine_tool)

    _ensure_owl_memory(agent)
    return agent
<<<END_FILE>>>
<<<FILE:Description.md>>>
Harness summary:
- Planning: decide how much parallel investigation the task deserves.
- Execution: a coordinator launches multiple focused investigators, then synthesizes their findings.
- Memory: workflow traces can be retrieved to ground later decisions.
- Default bench: caller-provided

Coordination pattern:
- Start with parallel evidence gathering.
- Consolidate intermediate findings before final synthesis.
- Use the coordinator only for orchestration and final answer assembly.

Runtime notes:
- Generated bundle: `harness4`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
<<<END_FILE>>>
<<<FILE:__init__.py>>>
from .builder import (
    ACTION_SYSTEM,
    DEFAULT_BENCH_TYPE,
    DEFAULT_MEMORY_SYSTEM,
    PAIRING_REASON,
    PLANNING_SYSTEM,
    HARNESS_NAME,
    build_agent_from_context,
)

__all__ = [
    "HARNESS_NAME",
    "PLANNING_SYSTEM",
    "ACTION_SYSTEM",
    "DEFAULT_BENCH_TYPE",
    "DEFAULT_MEMORY_SYSTEM",
    "PAIRING_REASON",
    "build_agent_from_context",
]
<<<END_FILE>>>
<<<FILE:planning_module/provider.py>>>
import textwrap
import json
import re
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from rich.rule import Rule
from rich.text import Text

from module_planning.base_planning import BasePlanning
from Agents.memory import ActionStep, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import LogLevel


def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")


class PlanningProvider(BasePlanning):
    """
    Coordination planning:
    Step 1: call the parallel investigation tool exactly once
    Step 2: call `final_answer` exactly once
    """

    def _is_expert_mode(self) -> bool:
        role_info = getattr(self, "role_info", None)
        if isinstance(role_info, dict):
            role_name = str(role_info.get("name", "")).lower()
            if "expert" in role_name:
                return True
            if "coordinator" in role_name:
                return False
        return "coordination_internal" not in self.prompt_templates and "cosight_internal" not in self.prompt_templates

    def topology_initialize(self, task: str) -> PlanningStep:
        """
        Let the model decide how many experts (1-4) are needed based on task complexity.
        If this is an internal expert, generate a simple research plan via LLM.
        """
        if self._is_expert_mode():
            expert_plan_prompt = f"As an expert researcher, provide a very concise, step-by-step research plan (max 3 steps) for this task: {task}\nReturn ONLY the plan text."
            try:
                input_messages = []
                memory_guidance = self.append_memory_guidance(input_messages)
                input_messages.append({"role": "user", "content": [{"type": "text", "text": expert_plan_prompt}]})
                resp = self.model(input_messages)
                plan_text = getattr(resp, "content", str(resp)).strip()
            except Exception:
                plan_text = "Analyze task requirements and use available tools to gather and verify evidence."
                memory_guidance = None

            self.logger.log(
                Rule("Expert Plan", style="green"),
                Text(f"Proposed Research Strategy:\n{plan_text}\n"),
                level=LogLevel.INFO,
            )

            planning_step = PlanningStep(
                model_input_messages=[],
                plan=plan_text,
                plan_think="",
                plan_reasoning="Expert-level research strategy generated.",
                memory_guidance=memory_guidance,
            )
            self.memory.steps.append(planning_step)
            return planning_step

        judge_prompt = f"""Analyze the following task and decide how many experts (integer 1-4) are needed to solve it reliably.
Consider complexity, potential for conflicting information, and depth of research required.
Task: {task}
Return ONLY a JSON object: {{"num_expert": N, "reasoning": "..."}}"""

        try:
            input_messages = []
            input_messages.append({"role": "user", "content": [{"type": "text", "text": judge_prompt}]})
            memory_guidance = self.append_memory_guidance(input_messages)
            resp = self.model(input_messages)
            out = getattr(resp, "content", str(resp))
            match = re.search(r"\{.*\}", out, re.DOTALL)
            data = json.loads(match.group(0)) if match else {}
            num_expert = int(data.get("num_expert", 3))
            num_expert = max(1, min(4, num_expert))
            reasoning = data.get("reasoning", "Dynamic expert count based on task complexity.")
        except (AttributeError, ValueError):
            num_expert = 3
            reasoning = "Defaulting to 3 experts due to analysis failure."
            memory_guidance = None

        plan_text = json.dumps([{"name": "expert_parallel", "arguments": {"task": task, "num_expert": num_expert}}])
        plan_reasoning = f"Analysis: {reasoning} -> Protocol starts with 'expert_parallel' for {num_expert} experts."

        self.logger.log(
            Rule("Execution", style="orange"),
            Text(f"Complexity analysis complete: Using {num_expert} experts. Initializing expert group...\nReasoning: {reasoning}\nPlan: {plan_text}\n"),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=[],
            plan=plan_text,
            plan_think="",
            plan_reasoning=plan_reasoning,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]],
    ) -> SummaryStep:

        summary_step = SummaryStep(
            model_input_messages="",
            summary="",
            summary_reasoning="",
        )
        return summary_step

class ReflectionPlanningProvider(BasePlanning):
    def topology_initialize(self, task: str) -> PlanningStep:
        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["planning"]["initial_plan"],
                            {"task": task, "tools": self.tools},
                        ),
                    }
                ],
            }
        ]
        memory_guidance = self.append_memory_guidance(input_messages)
        response = self.model(
            input_messages
            + [
                {
                    "role": MessageRole.USER,
                    "content": [
                        {
                            "type": "text",
                            "text": populate_template(
                                self.prompt_templates["planning"].get("task_input", "Task:\n{{task}}"),
                                {"task": task},
                            ),
                        }
                    ],
                }
            ]
        )
        plan_text = getattr(response, "content", str(response)).strip()
        plan_reasoning = getattr(response, "reasoning_content", "") or ""
        self.logger.log(
            Rule("Short Reflection Plan", style="orange"),
            Text(f"\n{plan_text}\n"),
            level=LogLevel.INFO,
        )
        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plan_text,
            plan_think="",
            plan_reasoning=plan_reasoning,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]],
    ) -> SummaryStep:
        memory_messages = write_memory_to_messages(None, False)[1:]
        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["summary"]["update_pre_messages"],
                            {"task": task, "step": step},
                        ),
                    }
                ],
            },
            *memory_messages,
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["summary"]["update_post_messages"],
                            {"task": task, "step": step},
                        ),
                    }
                ],
            },
        ]
        response = self.model(input_messages)
        summary_text = getattr(response, "content", str(response)).strip()
        summary_reasoning = getattr(response, "reasoning_content", "") or ""
        self.logger.log(
            Rule("Critic Reflection", style="orange"),
            Text(f"\n{summary_text}\n"),
            level=LogLevel.INFO,
        )
        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_text,
            summary_reasoning=summary_reasoning,
        )
        self.memory.steps.append(summary_step)
        return summary_step


PLANNING_SYSTEM = 'reflection_critic'
PLANNING_MODULE = 'reflection_critic'
PlanningProvider = ReflectionPlanningProvider
PlanningClass = ReflectionPlanningProvider

__all__ = ['PLANNING_SYSTEM', 'PLANNING_MODULE', 'PlanningProvider', 'PlanningClass']
<<<END_FILE>>>
<<<FILE:action_module/provider.py>>>
from __future__ import annotations

from typing import Any

from _harness_guards import ReflectionCriticTool, guard_task_tools
from module_action.base_action import ActionContext, BaseActionProvider


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "reflection_critic"
    DEFAULT_SUMMARY_INTERVAL = 6

    def _real_tool_budget(self, context: ActionContext) -> int:
        return max(8, min(12, context.max_steps // 2))

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.PROMPTS_TYPE)
        self.organization_planning_system = context.planning_system

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        guarded_tools = guard_task_tools(
            tools,
            policy_label="reflection_critic",
            max_real_tool_calls=self._real_tool_budget(context),
        )
        critic = ReflectionCriticTool(
            context=context,
            name="critic_reflect",
            description=(
                "Non-environment critic. It checks valid tools, reasonable arguments, "
                "repeated failures, and whether to stop. It never calls the task tools."
            ),
        )
        root_tools = self.normalize_tools([*guarded_tools, critic])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        critic.bind_agent(agent, root_tools)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_SUMMARY_INTERVAL
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "short_planner_single_executor_critic",
                "critic_tool": critic.name,
                "reflection_interval": agent.summary_interval,
                "no_environment_access_for_critic": True,
                "real_tool_budget": self._real_tool_budget(context),
            },
        )
        return agent

ACTION_SYSTEM = 'reflection_critic'
ACTION_MODULE = 'reflection_critic'

def get_provider():
    return ActionProvider()

__all__ = ['ACTION_SYSTEM', 'ACTION_MODULE', 'ActionProvider', 'get_provider']
<<<END_FILE>>>
<<<FILE:memory_module/provider.py>>>
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import uuid
import time
import logging
import numpy as np
from typing import Any, Dict, List, Optional
import re

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None
from module_memory.providers.model_loader import load_sentence_transformer

from module_memory.base_memory import BaseMemoryProvider, atomic_write_json, file_lock
from module_memory.memory_types import (
    MemoryRequest,
    MemoryResponse,
    MemoryItem,
    MemoryItemType,
    TrajectoryData,
    MemoryType,
    MemoryStatus,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                         cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    return load_sentence_transformer(
        model_name=model_name,
        cache_dir=cache_dir,
        allow_unavailable=SentenceTransformer is None,
    )


def _now_ts() -> float:
    return time.time()

def cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    if doc_vecs.size == 0:
        return np.array([])

    norm_query = np.linalg.norm(query_vec)
    norm_docs = np.linalg.norm(doc_vecs, axis=1)

    norm_docs[norm_docs == 0] = 1e-10
    if norm_query == 0:
        norm_query = 1e-10

    dot_products = np.dot(doc_vecs, query_vec)

    similarities = dot_products / (norm_docs * norm_query)
    return similarities

class MemoryProvider(BaseMemoryProvider):
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            raise ValueError("AgentWorkflowMemoryProvider requires an explicit config dict.")
        super().__init__(memory_type=MemoryType.AGENT_WORKFLOW_MEMORY, config=config)

        required = ["store_path", "top_k", "enable_induction"]
        if any(k not in self.config for k in required):
            raise KeyError(f"Missing required config keys: {[k for k in required if k not in self.config]}")

        model_name = self.config.get("embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2")
        cache_dir = self.config.get("embedding_cache_dir", "./storage/models")
        self._embedding_model = load_embedding_model(model_name=model_name, cache_dir=cache_dir)

        self.model = self.config.get("model")
        if self.model is None:
            logger.info(
                "No LLM model provided for AgentWorkflowMemoryProvider initialization. "
                "Workflow induction will fall back to trajectory reconstruction."
            )

        self._items: List[MemoryItem] = []
        self._cached_embeddings: Optional[np.ndarray] = None

    @staticmethod
    def _lexical_score(query: str, content: str) -> float:
        query_tokens = set(re.findall(r"\w+", query.lower()))
        content_tokens = set(re.findall(r"\w+", content.lower()))
        if not query_tokens or not content_tokens:
            return 0.0
        return len(query_tokens & content_tokens) / len(query_tokens)

    def _load_store(self) -> None:
        path = self.config["store_path"]
        if not os.path.exists(path):
            logger.info("No memory file found. Starting with empty memory.")
            self._items = []
            self._cached_embeddings = None
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._items = []
            for rec in data.get('memories', []):
                self._items.append(MemoryItem(
                    id=rec.get("id") or str(uuid.uuid4()),
                    content=rec.get("content"),
                    metadata=rec.get("metadata") or {},
                    score=None,
                    type=MemoryItemType(rec.get("type") or MemoryItemType.TEXT.value),
                ))

            embeddings_list = data.get('embeddings', [])

            if embeddings_list and len(embeddings_list) == len(self._items):
                self._cached_embeddings = np.array(embeddings_list, dtype=np.float32)
                logger.info(f"Loaded {len(self._items)} memories and embeddings from {path}")
            else:
                self._cached_embeddings = None
                logger.info(f"Loaded {len(self._items)} memories from {path} (embeddings mismatch or missing).")

        except Exception as e:
            logger.error(f"Error loading memories: {e}. Starting fresh.")
            self._items = []
            self._cached_embeddings = None

    def _save_store(self) -> None:
        path = self.config["store_path"]
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

            memories_data = [{
                "id": item.id,
                "content": item.content,
                "metadata": item.metadata,
                "type": item.type.value,
            } for item in self._items]

            embeddings_data = []
            if self._cached_embeddings is not None:
                embeddings_data = self._cached_embeddings.tolist()

            data = {
                'memories': memories_data,
                'embeddings': embeddings_data
            }

            atomic_write_json(path, data, indent=4)

        except Exception as e:
            logger.error(f"Error saving memories to {path}: {e}")

    def _ensure_embeddings(self) -> None:
        if self._embedding_model is None:
            self._cached_embeddings = None
            return

        current_count = len(self._items)
        if current_count == 0:
            self._cached_embeddings = None
            return

        if self._cached_embeddings is not None and len(self._cached_embeddings) == current_count:
            return

        logger.info(f"Embeddings missing or out of sync. Re-calculating for {current_count} items...")

        texts = [str(it.content or "") for it in self._items]

        embeddings = self._embedding_model.encode(texts, convert_to_numpy=True)
        self._cached_embeddings = embeddings

        self._save_store()

    def _reconstruct_trajectory_string(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return "No execution trajectory available"

        trajectory_parts = []
        task_desc = getattr(trajectory_data, 'query', None) or getattr(trajectory_data, 'input', None) or "Unknown Task"
        trajectory_parts.append(f"Task: {task_desc}")
        trajectory_parts.append("")

        for i, step in enumerate(trajectory_data.trajectory, 1):
            if isinstance(step, dict):
                step_type = step.get('type', 'step')
                content = step.get('content', '')
            else:
                step_type = getattr(step, 'type', 'step')
                content = getattr(step, 'content', str(step))

            trajectory_parts.append(f"Step {i} ({step_type}): {content}")

        if trajectory_data.result:
            trajectory_parts.append("")
            trajectory_parts.append(f"Final Result: {trajectory_data.result}")

        return "\n".join(trajectory_parts)

    def _induce_workflow(self, data: TrajectoryData) -> Optional[str]:
        if not self.config["enable_induction"]:
            return None
        if self.model is None:
            return None

        formatted_trajectory = self._reconstruct_trajectory_string(data)

        prompt = f"""You are an expert analyst for tasks.
Your goal is to extract a generic, reusable workflow from the specific execution trajectory provided below.

Guidelines:
1. **Abstraction**: Convert specific inputs (e.g., filenames, URLs, numbers) into descriptive variable names.
2. **Invariance**: Keep the logical steps and tool names invariant.
3. **Format**: Output strictly valid JSON containing the workflow text.

Output JSON Schema:
{{
    "workflow": "The concise text summary of the steps (under 200 words)"
}}

Trajectory to analyze:
{formatted_trajectory}"""

        messages = [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ]

        response = self.model(messages)
        refined_query = getattr(response, "content", str(response)).strip()

        cleaned_text = refined_query.replace("```json", "").replace("```", "").strip()

        try:
            result = json.loads(cleaned_text)
            return result.get("workflow")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON output: {e}")
            return None

    def initialize(self) -> bool:
        self._load_store()
        self._ensure_embeddings()
        logger.info("AgentWorkflowMemory initialized with %d items.", len(self._items))
        return True

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status != MemoryStatus.BEGIN:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=len(self._items))

        if not self._items:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=len(self._items))

        k = int(self.config["top_k"])
        scores: Optional[np.ndarray] = None
        if self._embedding_model is not None and self._cached_embeddings is not None and len(self._cached_embeddings) == len(self._items):
            query_embedding = self._embedding_model.encode([request.query], convert_to_numpy=True)[0]
            scores = cosine_similarity(query_embedding, self._cached_embeddings)
            top_indices = np.argsort(scores)[::-1][:k]
        else:
            ranked = sorted(
                (
                    (idx, self._lexical_score(request.query, str(item.content or "")))
                    for idx, item in enumerate(self._items)
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            top_indices = [idx for idx, score in ranked[:k] if score > 0]
            if not top_indices and self._items:
                top_indices = list(range(min(k, len(self._items))))

        results: List[MemoryItem] = []
        for idx in top_indices:
            score = float(scores[idx]) if scores is not None else self._lexical_score(request.query, str(self._items[idx].content or ""))

            original_item = self._items[idx]

            result_item = MemoryItem(
                id=original_item.id,
                content=original_item.content,
                metadata=original_item.metadata,
                score=score,
                type=original_item.type
            )
            results.append(result_item)

        return MemoryResponse(
            memories=results,
            memory_type=self.memory_type,
            total_count=len(self._items),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        meta = trajectory_data.metadata or {}

        if not meta.get("is_correct", False):
            return False, "Skipped: Trajectory not correct"

        abstracted_text = self._induce_workflow(trajectory_data)

        query = trajectory_data.query

        if abstracted_text and abstracted_text.strip():
            workflow_content = abstracted_text.strip()
        else:
            workflow_content = self._reconstruct_trajectory_string(trajectory_data)

        wf_text = f"Query: {query}\nWorkflow: {workflow_content}"
        meta.setdefault("created_at", _now_ts())

        item = MemoryItem(
            id=str(uuid.uuid4()),
            content=wf_text,
            metadata=meta,
            type=MemoryItemType.TEXT,
        )

        new_embedding = None
        if self._embedding_model is not None:
            new_embedding = self._embedding_model.encode([wf_text], convert_to_numpy=True)[0]

        with file_lock(self.config["store_path"]):
            self._load_store()
            self._items.append(item)
            if new_embedding is not None:
                if self._cached_embeddings is None:
                    self._cached_embeddings = np.array([new_embedding])
                else:
                    self._cached_embeddings = np.vstack([self._cached_embeddings, new_embedding])

            self._save_store()

        return True, f"Ingested {item.content[:50]}..."


AgentWorkflowMemoryProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.AGENT_WORKFLOW_MEMORY.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "AgentWorkflowMemoryProvider"]
<<<END_FILE>>>
<<<FILE:planning_module/prompts/toolcalling_agent.yaml>>>
planning:
  initial_plan: |-
    You are the short planner for a reflection-critic single-executor agent.

    Create a compact plan with exactly 3 bullets:
    - evidence/state still needed
    - safest first real tool action
    - stop condition: final_answer for QA, terminal completion tool for completed state-change tasks, critic_reflect only after suspicious failures

    Do not call or plan expert_parallel, camv, debate, or multiple agents.
  task_input: |-
    Task:
    {{task}}
summary:
  update_pre_messages: |-
    You are the critic reflection module. You do not operate the environment.
    Check only: tool existence, argument reasonableness, repeated failures, and whether stopping is justified.
  update_post_messages: |-
    Return concise fields:
    supported:
    schema_or_repeat_issue:
    next_safe_move:
    should_stop: yes/no
<<<END_FILE>>>
<<<FILE:action_module/prompts/toolcalling_agent.yaml>>>
system_prompt: |-
  You are a reflection-critic single-executor agent.

  Protocol:
  1. Follow the short plan.
  2. Use the real task tools directly and sequentially.
  3. Call critic_reflect after a suspicious failure pattern or before a risky final_answer.
  4. If the task exposes a terminal completion tool such as complete_task and the required state changes are done, call that terminal tool directly.
  5. For QA tasks, call final_answer as soon as the answer is supported.

  Critic boundary:
  - critic_reflect never operates the environment.
  - It only checks tool existence, argument reasonableness, repeated failures, and stop conditions.

  Rules:
  - Use only the tools provided in the schema.
  - Prefer one real environment tool per step.
  - Do not invent tools, arguments, IDs, records, or observations.
  - If a guarded tool blocks a repeated failed call, change strategy immediately.
  - For read-only QA or multi-hop lookup final answers, the answer field must be the raw answer only, with no evidence prose.
  - For state-change tasks, do not answer with prose when a terminal completion tool exists; complete the state changes and call the terminal tool.
  - Return one strict JSON object only.
step:
  pre_messages: |
    Reflection-critic loop for task:
    {{task}}

    Available tool schemas:
    {{tool_functions_json}}

    Decision checklist:
    - Is a real tool call still needed, and does its name exist exactly?
    - Are arguments consistent with the schema?
    - Did this exact call fail already? If yes, do not repeat it.
    - If the task has complete_task/task_completed and state changes are done, call that terminal tool now.
    - If this is a QA/read-only task and the answer is supported, call final_answer with the raw answer only.
    - If a failure repeats or a tool seems invalid, call critic_reflect once, then change strategy.
    - Do not call critic_reflect repeatedly for the same issue.

    Return strict JSON only:
    {"think": "...", "tools": [{"name": "...", "arguments": {...}}]}
final_answer:
  pre_messages: Provide the raw final answer only. Do not include evidence, explanation, labels, or markdown.
  post_messages: |-
    Return JSON: {"think": "...", "answer": "..."}
    Task: {{task}}
expert_internal:
  system_prompt: |-
    You are an autonomous specialist. Solve tasks using the currently available tools.

    # Process
    1. Gather evidence or perform analysis with available tools.
    2. Resolve conflicts or uncertainties if they appear.
    3. Call `final_answer` when done.

    # Tools
    {%- for tool in tools.values() %}
    - {{ tool.name }}: {{ tool.description }}
    {%- endfor %}
  step:
    pre_messages: |-
      Task: {{task}}

      # Rules
      1. Choose the tool or tools that best advance the task.
      2. You must provide the required arguments for each tool.
      3. Use only the tools listed below.
      4. Return only the JSON object.
      5. Read the tool schema carefully and use only the listed argument names.
      6. If a tool call fails because of invalid arguments, fix the arguments on the next step instead of repeating the same bad call.
      7. Never repeat an identical failed call unless the observation explicitly justifies it.

      Tools: {{tool_functions_json}}
      Return JSON: {"think": "...", "tools": [{"name": "...", "arguments": {...}}]}
  final_answer:
    pre_messages: Provide the final synthesized answer.
    post_messages: 'Return JSON: {"think": "...", "answer": "..."}'
coordination_internal:
  expert_planner:
    prompt: |-
      # Role: Expert Specialist {{expert_id}} - Planner
      Task: {{task}}
      Verified Global Facts: {{facts_snapshot}}
      Previous Failures: {{failure_context}}

      # Instructions
      Analyze the task and decompose it into a Directed Acyclic Graph of steps.
      Focus on resolving unknowns, validating assumptions, and using the available tools effectively.
      Include recovery-minded steps: when a likely tool/schema mismatch happens, repair the arguments or change strategy instead of repeating the same failure.

      Output the plan as a concise set of objectives.
  expert_react:
    system_prompt: |-
      # Role: Expert {{expert_id}} - TRSF Specialist
      You are an autonomous expert agent following the TRSF (Tool -> Notes -> Facts) protocol.

      # Task Context
      Task: "{{task}}"
      Your Plan: {{dag_plan}}

      # TRSF Process-Internal Loop
      1. Action: Call tools to gather evidence, validate claims, or perform analysis.
      2. TRSF Check: Every observation is checked against your current facts module.
      3. Extra Verification: If you detect a conflict or inconsistency, spend your next step performing additional targeted validation before proceeding.

      # Instructions
      - Decompose multifaceted tasks into targeted operations.
      - Prioritize grounded, verifiable observations.
      - Read tool schemas carefully and use only the listed argument names and types.
      - If a tool call fails because of invalid arguments or schema mismatch, your next step must repair the arguments or pick a different tool.
      - Never repeat an identical failed call unless the observation explicitly justifies it.
      - When you have enough information or have resolved all local conflicts, call `final_answer`.

      # Context
      - Global Facts (Verified): {{facts_snapshot}}
      - Previous Attempts / EBA Repair: {{failure_context}}

      # Tools Available
      {%- for tool in tools.values() %}
      - {{ tool.name }}: {{ tool.description }}
      {%- endfor %}

      # Output Format
      To use a tool, return JSON:
      {"tool": "actual_tool_name", "arguments": {...}}

      To signal completion, return:
      {"tool": "final_answer", "arguments": {}}
  extract_notes:
    prompt: |-
      # Information Extraction
      Task: {{task}}
      Tool Execution Trajectory:
      {{tool_records}}

      # Instructions
      Extract key evidence snippets and intermediate insights from the trajectory.
      For every factual claim found, record a supporting reference in `source_url` (use a URL when applicable, otherwise a stable source identifier) and a supporting excerpt in `source_snippet`.

      Return JSON: {"notes": ["Note 1 with support...", "Note 2 with support...", ...]}
  expert:
    prompt: |-
      # Role: Expert Specialist {{expert_id}} - Fact Extractor
      Task: {{task}}
      Verified Global Facts: {{facts_snapshot}}
      Evidence Gathered in this round: {{notes}}

      # Instructions
      1. Analyze gathered evidence and verified global facts.
      2. Formulate a grounded, concise answer.
      3. Extract atomic, verifiable claims from your answer.
      4. For each claim, provide:
         - `key`: standard identifier
         - `value`: factual value
         - `confidence`: 0.0 to 1.0
         - `source_url`: exact supporting reference or source identifier
         - `source_snippet`: exact supporting excerpt

      # Critical Rules
      - Do not extract negative claims such as "unknown", "not found", or "missing".
      - Only extract positive factual assertions that you have support for.
      - If you have no positive facts, return an empty list for `facts_local`.

      Output strict JSON:
      {
        "answer": "...",
        "facts_local": [
          {
            "key": "entity.property",
            "value": "fact value",
            "confidence": 0.9,
            "source_url": "support reference",
            "source_snippet": "supporting excerpt"
          }
        ]
      }
  normalization:
    prompt: |-
      # Fact Normalization
      Task: {{task}}
      Raw Claims:
      {{claims}}

      # Instructions
      1. Map claims to high-level standard keys (`entity.property`).
      2. Preserve qualitative explanations in the `value` field.
      3. Pass through `confidence`, `source_url`, and `source_snippet`.
      4. Do not keep claims that are purely negative or logically inconsistent.

      Return strict JSON array:
      [{"key": "...", "value": "...", "confidence": 0.9, "source_url": "...", "source_snippet": "..."}]
  verification_query:
    prompt: |-
      # Role: Verification Planner
      Task Context: {{task}}
      Claim to Verify: {{key}} = {{value}}

      # Instructions
      Generate a concise verification request or tool query to check this specific claim.
      Focus on the most discriminative identifiers.
      Return only the query string.
  judge:
    prompt: |-
      # Role: Verification Judge
      Task Context: {{task}}
      Claim to Verify: {{key}} = {{value}}

      # Evidence
      [PRIMARY OBSERVATIONS]
      {{web_obs}}

      [ADDITIONAL OBSERVATIONS]
      {{page_obs}}

      # Instructions
      1. Determine whether the evidence SUPPORTS, CONTRADICTS, or is NEUTRAL regarding the claim.
      2. Set `supported` to true only if the evidence confirms the value.
      3. Set `is_contradicted` to true only if the evidence explicitly provides a different value for the same key.
      4. If evidence is missing or ambiguous, keep the judgment neutral.

      Return strict JSON:
      {"supported": true, "is_contradicted": false, "evidence_snippet": "...", "url": "...", "reason": "..."}
  decision:
    prompt: |-
      # Integrative Synthesis (CAMV Stage 4)
      Task: {{task}}
      Verified Fact Anchors:
      {{supported_snapshot}}

      # Instructions
      1. Check whether the verified anchors contain positive evidence for every required factual detail in the task.
      2. If any required detail is missing, set "ready": false.
      3. If "ready": false, use "next_failure_context" to describe exactly what is still missing.
      4. Reconstruct a coherent reasoning trace leading to the final answer.

      Output JSON: {"ready": true/false, "final_answer": "...", "next_failure_context": "..."}
  fallback:
    prompt: |-
      Task: {{task}}
      Supported facts:
      {{supported_snapshot}}
      Give a best-effort, traceable final answer based only on verified information.
  static_plan: '[{"name": "expert_parallel", "arguments": {"task": "{{task}}", "num_expert": 3}}]'
<<<END_FILE>>>

## Example Harness: harness5

### Harness Identity
- Planning system: agentorchestra
- Action system: agentorchestra
- Default memory system: cerebra_fusion_memory
- Default bench type: None
- Pairing reason: matched_same_name

### Description
Harness summary:
- Planning: decompose the objective into tracked sub-tasks with explicit status updates.
- Execution: a hierarchical coordinator advances the plan while checking progress after key actions.
- Memory: graph-style text and tool memory supports reuse across runs.
- Default bench: caller-provided

Coordination pattern:
- Break the objective into manageable units before execution.
- Keep plan state synchronized with explicit progress tools.
- Synthesize only after the tracked work items are resolved.

Runtime notes:
- Generated bundle: `harness5`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.

### Performance Snapshot
- Evaluated tasks: 80
- Exact accuracy: 47.50%
- Valid answer rate: 100.00%
- Average path score: 0.6495
- Average actions: 6.775
- Average tool calls: 8.0375
- Average total tokens: 80721.25
- Average runtime (sec): 67.99
- Source result file: output/toolhop_round1_harness5/toolhop_flash_searcher_flash_searcher_cerebra_fusion_memory_local_qwen3-aevolve_closed_results.jsonl

### Performance Report
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

### Bundle Files
<<<FILE:builder.py>>>
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Agents.agents import ToolCallingAgent
from module_action.base_action import ActionContext
from .action_module.provider import ACTION_SYSTEM, get_provider
from .memory_module.provider import MEMORY_SYSTEM as DEFAULT_MEMORY_SYSTEM
from .planning_module.provider import PLANNING_SYSTEM, PlanningClass


HARNESS_NAME = "harness5"
DEFAULT_BENCH_TYPE = None
PAIRING_REASON = "matched_same_name"


def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
    if tool is not None and hasattr(tool, "agent"):
        setattr(tool, "agent", agent)


def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
    if getattr(agent, "planning_system", None) != "owl":
        return
    if not hasattr(agent, "web_memory") or agent.web_memory is None:
        agent.web_memory = []
    if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
        agent.reasoning_memory = []


def prepare_context(context: ActionContext) -> ActionContext:
    bench_type = context.bench_type or DEFAULT_BENCH_TYPE
    prompts_type = context.prompts_type or PLANNING_SYSTEM
    prepared_kwargs = dict(context.kwargs)
    prepared_kwargs["planning_class"] = PlanningClass
    return replace(
        context,
        planning_system=PLANNING_SYSTEM,
        action_system=ACTION_SYSTEM,
        prompts_type=prompts_type,
        bench_type=bench_type,
        project_root=Path(__file__).resolve().parent,
        kwargs=prepared_kwargs,
    )


def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
    prepared_context = prepare_context(context)
    action_provider = get_provider()
    agent = action_provider.build(prepared_context)

    setattr(agent, "planning_system", prepared_context.planning_system)
    setattr(agent, "action_system", prepared_context.action_system)
    setattr(agent, "harness_name", HARNESS_NAME)
    setattr(
        agent,
        "harness_metadata",
        {
            "planning_system": PLANNING_SYSTEM,
            "action_system": ACTION_SYSTEM,
            "default_bench_type": DEFAULT_BENCH_TYPE,
            "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
            "pairing_reason": PAIRING_REASON,
        },
    )

    if prepared_context.vector_tool is not None:
        prepared_context.vector_tool.memory = agent.memory

    _bind_agent_reference(agent, prepared_context.process_tool)
    _bind_agent_reference(agent, prepared_context.end_process_tool)
    _bind_agent_reference(agent, prepared_context.delete_memory_tool)
    _bind_agent_reference(agent, prepared_context.executor_tool)
    _bind_agent_reference(agent, prepared_context.refine_tool)

    _ensure_owl_memory(agent)
    return agent
<<<END_FILE>>>
<<<FILE:Description.md>>>
Harness summary:
- Planning: decompose the objective into tracked sub-tasks with explicit status updates.
- Execution: a hierarchical coordinator advances the plan while checking progress after key actions.
- Memory: graph-style text and tool memory supports reuse across runs.
- Default bench: caller-provided

Coordination pattern:
- Break the objective into manageable units before execution.
- Keep plan state synchronized with explicit progress tools.
- Synthesize only after the tracked work items are resolved.

Runtime notes:
- Generated bundle: `harness5`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The builder keeps the current `ActionContext` flow and only normalizes planning/action pairing.
<<<END_FILE>>>
<<<FILE:__init__.py>>>
from .builder import (
    ACTION_SYSTEM,
    DEFAULT_BENCH_TYPE,
    DEFAULT_MEMORY_SYSTEM,
    PAIRING_REASON,
    PLANNING_SYSTEM,
    HARNESS_NAME,
    build_agent_from_context,
)

__all__ = [
    "HARNESS_NAME",
    "PLANNING_SYSTEM",
    "ACTION_SYSTEM",
    "DEFAULT_BENCH_TYPE",
    "DEFAULT_MEMORY_SYSTEM",
    "PAIRING_REASON",
    "build_agent_from_context",
]
<<<END_FILE>>>
<<<FILE:planning_module/provider.py>>>
import textwrap
import json
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from rich.rule import Rule
from rich.text import Text
from module_planning.base_planning import BasePlanning

def populate_template(template: str, variables: Dict[str, Any]) -> str:
    """
    Fill Jinja2 template with variables.
    """
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")

class PlanningProvider(BasePlanning):
    """
    Planning implementation for hierarchical task decomposition.
    Includes task decomposition and state management.
    """

    def __init__(
        self,
        model: Callable[[List[Dict[str, str]]], ChatMessage],
        tools: Dict[str, Tool],
        prompt_templates: Dict[str, Any],
        memory: AgentMemory,
        logger: AgentLogger
    ):
        super().__init__(model, tools, prompt_templates, memory, logger)
        self.orchestra_tasks = []

    def topology_initialize(self, task: str) -> PlanningStep:
        self.logger.log(
            Rule("[bold]Task Planning", style="cyan"),
            level=LogLevel.INFO,
        )

        system_message = {
            "role": MessageRole.SYSTEM,
            "content": [
                {
                    "type": "text",
                    "text": populate_template(
                        self.prompt_templates["planning"]["initial_plan"],
                        variables={"task": task},
                    ),
                }
            ],
        }
        task_message = {
            "role": MessageRole.USER,
            "content": [
                {
                    "type": "text",
                    "text": populate_template(
                        self.prompt_templates["planning"].get("task_input", "User Objective: {{task}}"),
                        variables={"task": task},
                    ),
                }
            ],
        }
        messages = [system_message]
        memory_guidance = self.append_memory_guidance(messages)
        model_messages = messages + [task_message]

        try:
            # Use the model to decompose the task
            response: ChatMessage = self.model(model_messages)
            content = (response.content or "").strip()
            if not content:
                raise ValueError("Empty planning content")

            # Basic cleanup of the response content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            tasks_data = json.loads(content.strip())

            if not isinstance(tasks_data, list):
                raise ValueError("Model response is not a list")

            self.orchestra_tasks = []
            for i, t in enumerate(tasks_data):
                self.orchestra_tasks.append({
                    "id": i,
                    "description": t.get("description", "Unknown task"),
                    "priority": t.get("priority", "medium"),
                    "category": t.get("category", "general"),
                    "status": "pending",
                    "result": None
                })

            plan_text = "\n".join([f"{i}. [{t['priority'].upper()}] {t['description']}" for i, t in enumerate(self.orchestra_tasks)])
            self.logger.log(
                Text(f"Decomposed objective into {len(self.orchestra_tasks)} tasks:\n{plan_text}"),
                level=LogLevel.INFO
            )

        except Exception as e:
            self.logger.log(
                Text(
                    f"Failed to decompose task via LLM: {str(e)}. Falling back to single-task mode."
                ),
                level=LogLevel.ERROR,
            )
            self.orchestra_tasks = [{
                "id": 0,
                "description": task,
                "priority": "high",
                "category": "general",
                "status": "pending",
                "result": None
            }]
            plan_text = f"1. [HIGH] {task}"

        planning_step = PlanningStep(
            model_input_messages=model_messages,
            plan=plan_text,
            plan_think="Automated task decomposition completed. The system is ready for structured execution.",
            plan_reasoning="Hierarchical decomposition into manageable steps. The model must now use 'check_plan_progress' to begin execution and follow the mandatory JSON output format strictly.",
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]]
    ) -> SummaryStep:
        self.logger.log(
            Rule("[bold]Progress Check & Summary", style="cyan"),
            level=LogLevel.INFO,
        )

        # Get all messages including the system prompt and previous steps
        memory_messages = write_memory_to_messages()

        # Construct messages for the model to generate a summary
        messages = memory_messages + [
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["summary"]["update_post_messages"],
                            variables={
                                "task": task,
                                "step": step,
                                "orchestra_tasks": json.dumps(self.orchestra_tasks, indent=2, ensure_ascii=False)
                            }
                        ),
                    }
                ],
            }
        ]

        try:
            response: ChatMessage = self.model(messages)
            summary_content = response.content
            summary_reasoning = getattr(response, "reasoning_content", "Periodic status review for hierarchical orchestration.")

            self.logger.log(
                Text(f"Strategic Summary (Step {step}):\n{summary_content}"),
                level=LogLevel.INFO
            )

            summary_step = SummaryStep(
                model_input_messages=messages,
                summary=summary_content,
                summary_reasoning=summary_reasoning,
            )
        except Exception as e:
            self.logger.log(
                Text(f"Failed to generate summary: {str(e)}"),
                level=LogLevel.ERROR,
            )
            summary_step = SummaryStep(
                model_input_messages=[],
                summary="Monitoring execution progress. Summary generation failed, but the process continues.",
                summary_reasoning=f"Error: {str(e)}",
            )

        self.memory.steps.append(summary_step)
        return summary_step

PLANNING_SYSTEM = 'agentorchestra'
PLANNING_MODULE = 'agentorchestra'
PlanningClass = PlanningProvider

__all__ = ['PLANNING_SYSTEM', 'PLANNING_MODULE', 'PlanningProvider', 'PlanningClass']
<<<END_FILE>>>
<<<FILE:action_module/provider.py>>>
from __future__ import annotations

from typing import Any

from Agents.tools import CheckPlanProgress, UpdatePlanStatus

from module_action.base_action import ActionContext, BaseActionProvider


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "agentorchestra"

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        self.update_tool = UpdatePlanStatus(agent=None)
        self.check_tool = CheckPlanProgress(agent=None)
        primary_tools = self.get_primary_task_tools(context, include_reasoning=True)
        return primary_tools + [self.update_tool, self.check_tool]

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = self.PROMPTS_TYPE

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        agent = self.create_agent(
            context,
            tools=tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        self.update_tool.agent = agent
        self.check_tool.agent = agent
        return agent

ACTION_SYSTEM = 'agentorchestra'
ACTION_MODULE = 'agentorchestra'

def get_provider():
    return ActionProvider()

__all__ = ['ACTION_SYSTEM', 'ACTION_MODULE', 'ActionProvider', 'get_provider']
<<<END_FILE>>>
<<<FILE:memory_module/provider.py>>>
"""
Cerebra Fusion Memory Provider

through a graph-backed architecture with intelligent routing and continuous optimization.

"""

import os
import json
import uuid
import re
import ast
import hashlib
import importlib.util
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
from datetime import datetime
from collections import defaultdict
from enum import Enum

import numpy as np

# Vectorization and semantic models
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None
from module_memory.providers.model_loader import load_sentence_transformer

# Unified memory base imports
from module_memory.base_memory import BaseMemoryProvider, atomic_write_json, atomic_write_text, file_lock
from module_memory.memory_types import (
    MemoryRequest,
    MemoryResponse,
    MemoryItem,
    MemoryItemType,
    TrajectoryData,
    MemoryStatus,
    MemoryType
)

# Tool wrapper for API memory
try:
    from storage.tools.tool_wrapper import ToolWrapper
except ImportError:
    ToolWrapper = None


# =========================================================================
# Utility Functions
# =========================================================================

def _safe_get_model_response(model, prompt: str) -> Optional[str]:
    """Robust LLM invocation helper returning string content or None."""
    if model is None:
        return None

    try:
        # Minimal compatibility with smolagents or OpenAI-style clients
        try:
            from smolagents.models import MessageRole
            messages = [{"role": MessageRole.USER, "content": [{"type": "text", "text": prompt}]}]
            resp = model(messages)
            result = getattr(resp, "content", str(resp)).strip()
            return result
        except Exception:
            # Fallback: direct call style
            resp = model(prompt)
            result = str(resp).strip()
            return result
    except Exception:
        return None


def _load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                          cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    return load_sentence_transformer(
        model_name=model_name,
        cache_dir=cache_dir,
        allow_unavailable=SentenceTransformer is None,
    )


class EdgeType(Enum):
    """Types of edges in the memory graph."""
    SAME_TASK = "same_task"          # Nodes from same task execution
    SIMILAR_CONCEPT = "similar"       # Semantically similar content
    DEPENDS_ON = "depends"            # Dependency relationship
    COOCCURS = "cooccurs"             # Frequently retrieved together


@dataclass
class NexusEdge:
    """Graph edge with type and weight for dynamic optimization."""
    source: str
    target: str
    edge_type: EdgeType
    weight: float = 1.0
    usage_count: int = 0
    success_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize edge to dictionary."""
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "created_at": self.created_at,
            "metadata": self.metadata
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'NexusEdge':
        """Deserialize edge from dictionary."""
        return NexusEdge(
            source=data["source"],
            target=data["target"],
            edge_type=EdgeType(data["edge_type"]),
            weight=data.get("weight", 1.0),
            usage_count=data.get("usage_count", 0),
            success_count=data.get("success_count", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


@dataclass
class NexusNode:
    """Graph node representing a memory unit."""
    id: str
    node_type: str  # "task", "pattern", "playbook", "checklist", "failure", "success"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    signature: str = ""  # Content hash for deduplication


@dataclass
class GraphIndex:
    """Multi-granularity indices for nodes."""
    tfidf_vectorizer: Optional[TfidfVectorizer] = None
    tfidf_matrix: Optional[Any] = None
    node_ids: List[str] = field(default_factory=list)
    embeddings: Optional[np.ndarray] = None


# =========================================================================
# Tool Components
# =========================================================================

@dataclass
class ToolRecord:
    """Metadata for a stored tool."""
    name: str
    description: str
    code: str
    domain: str = "general"
    tags: List[str] = field(default_factory=list)
    usage_count: int = 0
    success_count: int = 0
    signature: str = ""


# =========================================================================
# Main Provider
# =========================================================================

class MemoryProvider(BaseMemoryProvider):
    """
    Cerebra Fusion Memory Provider: Unified Text + Tool Memory System

    Configuration:
    - enable_tool_memory: bool (default: True) - Enable tool memory path
    - consolidation_interval: int (default: 50) - Tasks between consolidations
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(self._get_declared_memory_type(), config or {})

        # Core configuration
        self.storage_dir = self.config.get("storage_dir", "./storage/cerebra_fusion")
        os.makedirs(self.storage_dir, exist_ok=True)

        self.db_path = self.config.get("db_path", os.path.join(self.storage_dir, "cf_database.json"))
        self.model_cache_dir = self.config.get("model_cache_dir", "./storage/models")

        # Text memory configuration
        self.top_k = int(self.config.get("top_k", 5))
        self.search_weights = self.config.get("search_weights", {"text": 0.2, "semantic": 0.8})
        self.min_score = float(self.config.get("min_score", 0.22))
        self.min_score_in_phase = float(self.config.get("min_score_in_phase", 0.22))

        # Graph configuration
        self.semantic_edge_threshold = float(self.config.get("semantic_edge_threshold", 0.75))
        self.max_neighbors_expand = int(self.config.get("max_neighbors_expand", 3))
        self.enable_graph_expansion = bool(self.config.get("enable_graph_expansion", True))

        # Tool memory configuration (new)
        self.enable_tool_memory = bool(self.config.get("enable_tool_memory", True))
        self.tools_storage_path = self.config.get("tools_storage_path",
                                                   os.path.join(self.storage_dir, "tools_storage.py"))
        self.max_tool_candidates = int(self.config.get("max_tool_candidates", 3))

        # Consolidation configuration
        self.consolidation_interval = int(self.config.get("consolidation_interval", 50))
        self.task_counter = 0

        # Models
        self.embedding_model = _load_embedding_model(cache_dir=self.model_cache_dir)
        self.model = self.config.get("model", None)

        # Graph store
        self.nodes: Dict[str, NexusNode] = {}
        self.edges: List[NexusEdge] = []

        # Tool store
        self.tools: Dict[str, ToolRecord] = {}
        self.tools_registry: Dict[str, Callable] = {}
        self.tool_wrapper = None
        if self.enable_tool_memory and ToolWrapper:
            self.tool_wrapper = ToolWrapper(model=self.model, logger=None)

        # Indices
        self.text_index = GraphIndex(tfidf_vectorizer=TfidfVectorizer(stop_words='english'))
        self.tool_embeddings: Optional[np.ndarray] = None
        self.tool_names_index: List[str] = []

        # Track memory usage for success rate calculation
        # Maps request_id -> {"node_ids": [...], "edge_pairs": [(source, target), ...]}
        self.active_usage_tracking: Dict[str, Dict[str, Any]] = {}

        # Initialize storage
        self._load_or_initialize_db()
        self._finalize_indices()

    def initialize(self) -> bool:
        """Initialize the memory provider."""
        try:
            if not self.nodes:
                self._seed_core_patterns()
                self._persist_db()
            if not self.text_index.node_ids:
                self._finalize_indices()
            if self.enable_tool_memory:
                self._load_tools()
            return True
        except Exception as e:
            print(f"Failed to initialize CerebraFusionMemoryProvider: {e}")
            return False

    @staticmethod
    def _get_declared_memory_type():
        """Get memory type enum."""
        try:
            return MemoryType.CEREBRA_FUSION_MEMORY
        except Exception:
            class _ShimEnum:
                CEREBRA_FUSION_MEMORY = "cerebra_fusion_memory"
            return _ShimEnum.CEREBRA_FUSION_MEMORY

    # =========================================================================
    # Text Memory Path
    # =========================================================================

    def _load_or_initialize_db(self):
        """Load existing graph database or initialize with seed patterns."""
        if not os.path.exists(self.db_path):
            self._seed_core_patterns()
            self._persist_db()
            return

        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load nodes
            for n in data.get("nodes", []):
                node = NexusNode(
                    id=n["id"],
                    node_type=n["node_type"],
                    content=n["content"],
                    metadata=n.get("metadata", {}),
                    created_at=n.get("created_at", datetime.now().isoformat()),
                    signature=n.get("signature", "")
                )
                self.nodes[node.id] = node

            # Load edges
            for e in data.get("edges", []):
                self.edges.append(NexusEdge.from_dict(e))

            # Load tools if enabled
            if self.enable_tool_memory:
                for t in data.get("tools", []):
                    tool = ToolRecord(
                        name=t["name"],
                        description=t["description"],
                        code=t["code"],
                        domain=t.get("domain", "general"),
                        tags=t.get("tags", []),
                        usage_count=t.get("usage_count", 0),
                        success_count=t.get("success_count", 0),
                        signature=t.get("signature", "")
                    )
                    self.tools[tool.name] = tool

            print(f"[CEREBRA FUSION LOAD] Loaded {len(self.nodes)} nodes, {len(self.edges)} edges, {len(self.tools)} tools")

        except Exception as e:
            print(f"[CEREBRA FUSION LOAD] Error loading database: {e}, reinitializing")
            self.nodes.clear()
            self.edges.clear()
            self.tools.clear()
            self._seed_core_patterns()
            self._persist_db()

    def _seed_core_patterns(self):
        """Initialize memory with essential abstract patterns (from Cerebra)."""
        seeds = [
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="pattern",
                content="Preserve source phrasing when explicitly requested; avoid over-normalization of reported values.",
                metadata={"category": "format_policy"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="pattern",
                content="When progress is incomplete, consider alternate access methods and define clear completion criteria.",
                metadata={"category": "continuation_tactics"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="checklist",
                content="Verify target entity matches question requirements before finalizing answer.",
                metadata={"category": "final_check"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content="For sports data: use site-restricted search, handle pagination, validate completeness.",
                metadata={"domain": "sports"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content="For author attribution: check visible byline first; if absent, consider organizational attribution.",
                metadata={"domain": "content_sites"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content="For archived content: try multiple access paths if one fails.",
                metadata={"domain": "archives"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content="For aggregated data: confirm correct entity before extracting details.",
                metadata={"domain": "aggregators"}
            ),
        ]
        for node in seeds:
            node.signature = self._compute_signature(node.content)
            self.nodes[node.id] = node

    def _persist_db(self):
        """Save graph and tools to JSON file."""
        data = {
            "nodes": [vars(n) for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "tools": [vars(t) for t in self.tools.values()] if self.enable_tool_memory else [],
            "metadata": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "total_tools": len(self.tools),
                "last_updated": datetime.now().isoformat()
            }
        }
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        atomic_write_json(self.db_path, data, indent=2)
        print(f"[CEREBRA FUSION PERSIST] Saved {len(self.nodes)} nodes, {len(self.edges)} edges, {len(self.tools)} tools")

    def _finalize_indices(self):
        """Build TF-IDF and semantic embeddings indices for text memory."""
        if not self.nodes:
            return

        # Build corpus from node contents
        corpus = [node.content for node in self.nodes.values()]
        self.text_index.node_ids = list(self.nodes.keys())

        # Build TF-IDF matrix
        self.text_index.tfidf_matrix = self.text_index.tfidf_vectorizer.fit_transform(corpus)

        # Build semantic embeddings if model available
        if self.embedding_model is not None:
            self.text_index.embeddings = self.embedding_model.encode(
                corpus, batch_size=32, convert_to_numpy=True, show_progress_bar=False
            )
            print(f"[CEREBRA FUSION INDEX] Built indices: {len(corpus)} nodes, TF-IDF + embeddings")
        else:
            self.text_index.embeddings = None
            print(f"[CEREBRA FUSION INDEX] Built indices: {len(corpus)} nodes, TF-IDF only")

    def _build_semantic_edges(self, new_node: NexusNode) -> int:
        """Build semantic similarity edges between new node and existing similar nodes."""
        if self.embedding_model is None or self.text_index.embeddings is None or not self.text_index.node_ids:
            return 0

        edges_created = 0
        new_embedding = self.embedding_model.encode(new_node.content, convert_to_numpy=True)

        for idx, existing_node_id in enumerate(self.text_index.node_ids):
            if existing_node_id == new_node.id:
                continue

            existing_node = self.nodes.get(existing_node_id)
            if not existing_node or existing_node.node_type != new_node.node_type:
                continue

            # Calculate similarity
            similarity = cosine_similarity([new_embedding], [self.text_index.embeddings[idx]])[0][0]

            if similarity >= self.semantic_edge_threshold:
                # Check if edge already exists
                edge_exists = any(
                    (e.source == new_node.id and e.target == existing_node_id) or
                    (e.source == existing_node_id and e.target == new_node.id)
                    for e in self.edges
                )

                if not edge_exists:
                    # Create bidirectional edges
                    self.edges.append(NexusEdge(
                        source=new_node.id,
                        target=existing_node_id,
                        edge_type=EdgeType.SIMILAR_CONCEPT,
                        weight=float(similarity),
                        metadata={"similarity_score": float(similarity)}
                    ))
                    self.edges.append(NexusEdge(
                        source=existing_node_id,
                        target=new_node.id,
                        edge_type=EdgeType.SIMILAR_CONCEPT,
                        weight=float(similarity),
                        metadata={"similarity_score": float(similarity)}
                    ))
                    edges_created += 2

        if edges_created > 0:
            print(f"[CEREBRA FUSION GRAPH] Created {edges_created} semantic edges for {new_node.node_type}")
        return edges_created

    def _get_neighbors(self, node_id: str, edge_types: Optional[List[EdgeType]] = None) -> List[Tuple[str, float]]:
        """Get neighbors of a node, optionally filtered by edge type."""
        neighbors = []
        for edge in self.edges:
            if edge.source == node_id:
                if edge_types is None or edge.edge_type in edge_types:
                    neighbors.append((edge.target, edge.weight))
        return neighbors

    def _graph_expand(self, initial_results: List[Tuple[str, float]], query: str) -> Tuple[List[Tuple[str, float]], List[Tuple[str, str]]]:
        """Expand retrieval results by adding semantically connected neighbors.

        Returns:
            Tuple of (expanded_results, edges_used)
            - expanded_results: List of (node_id, score) pairs
            - edges_used: List of (source_id, target_id) pairs used in expansion
        """
        if not self.enable_graph_expansion or not initial_results:
            return initial_results, []

        candidates = {node_id: score for node_id, score in initial_results}
        edges_used = []

        for node_id, base_score in initial_results:
            neighbors = self._get_neighbors(node_id, edge_types=[EdgeType.SIMILAR_CONCEPT])
            sorted_neighbors = sorted(neighbors, key=lambda x: x[1], reverse=True)[:self.max_neighbors_expand]

            for neighbor_id, edge_weight in sorted_neighbors:
                if neighbor_id not in self.nodes:
                    continue

                propagated_score = base_score * edge_weight * 0.7
                candidates[neighbor_id] = max(candidates.get(neighbor_id, 0), propagated_score)
                edges_used.append((node_id, neighbor_id))

        # Track edge usage
        for source, target in edges_used:
            for edge in self.edges:
                if edge.source == source and edge.target == target:
                    edge.usage_count += 1

        expanded_results = sorted(candidates.items(), key=lambda x: x[1], reverse=True)

        if len(expanded_results) > len(initial_results):
            print(f"[CEREBRA FUSION GRAPH] Expanded from {len(initial_results)} to {len(expanded_results)} candidates")

        return expanded_results, edges_used

    def _hybrid_search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Hybrid search combining TF-IDF and semantic embeddings."""
        scores = defaultdict(float)

        # TF-IDF search
        if self.text_index.tfidf_matrix is not None and self.text_index.node_ids:
            q_vec = self.text_index.tfidf_vectorizer.transform([query])
            tf_scores = cosine_similarity(q_vec, self.text_index.tfidf_matrix).flatten()
            for idx, s in enumerate(tf_scores):
                scores[self.text_index.node_ids[idx]] += self.search_weights.get("text", 0.5) * float(s)

        # Semantic search
        if self.text_index.embeddings is not None and self.embedding_model is not None and self.text_index.node_ids:
            q_emb = self.embedding_model.encode(query, convert_to_numpy=True)
            sem_scores = cosine_similarity([q_emb], self.text_index.embeddings)[0]
            for idx, s in enumerate(sem_scores):
                scores[self.text_index.node_ids[idx]] += self.search_weights.get("semantic", 0.5) * float(s)

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    def _reason_about_task(self, request: MemoryRequest) -> Dict[str, Any]:
        """
        Analyze task to generate a focused retrieval query.
        """
        base_query = request.query

        if self.model:
            prompt_parts = [
                "Analyze this task to determine what past experience would be most helpful.\n\n",
                f"Task: {base_query}\n",
                f"Status: {request.status.value.upper()}\n"
            ]

            if request.status == MemoryStatus.IN and hasattr(request, 'context') and request.context:
                context_preview = request.context[-800:] if len(request.context) > 800 else request.context
                prompt_parts.extend([
                    "\nCurrent Progress:\n",
                    f"{context_preview}\n\n",
                    "Based on progress: What has been attempted? What challenges remain?\n\n"
                ])

            prompt_parts.append(
                "Generate a retrieval focus for semantic search over past experience.\n\n"
                "Guidelines:\n"
                "1. Use abstract concepts, not specific details\n"
                "2. Focus on HOW/WHAT-KIND rather than entities\n"
                "3. Include action verbs (e.g., 'handling', 'extracting')\n"
                "4. Describe strategy type, not task itself\n"
                "5. Keep concise: 1-2 sentences max\n\n"
                "Return ONLY JSON:\n"
                '{"retrieval_focus": "your focus here"}'
            )

            prompt = "".join(prompt_parts)
            resp = _safe_get_model_response(self.model, prompt)
            if resp:
                try:
                    parsed = json.loads(self._extract_json(resp))
                    if "retrieval_focus" in parsed:
                        return {
                            "retrieval_focus": parsed["retrieval_focus"],
                            "status": request.status.value,
                            "query_text": base_query
                        }
                except Exception:
                    pass

        return {
            "retrieval_focus": base_query,
            "status": request.status.value,
            "query_text": base_query
        }

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON object from text if extra tokens present."""
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        try:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return m.group(0)
        except Exception:
            pass
        return text

    def _compose_text_guidance(self, request: MemoryRequest, reason: Dict[str, Any], top_nodes: List[NexusNode]) -> str:
        """
        Compose concise, actionable guidance using LLM synthesis.
        """
        if self.model and len(top_nodes) >= 2:
            return self._compose_with_llm_synthesis(request, reason, top_nodes)
        else:
            return self._compose_simple_fallback(request, top_nodes)

    def _compose_with_llm_synthesis(self, request: MemoryRequest, reason: Dict[str, Any], top_nodes: List[NexusNode]) -> str:
        """Use LLM to synthesize retrieved patterns into concise guidance."""
        if request.status == MemoryStatus.BEGIN:
            max_chars = 350
            max_sentences = 2
        elif request.status == MemoryStatus.IN:
            max_chars = 200
            max_sentences = 2
        else:
            max_chars = 400
            max_sentences = 2

        retrieved_items = []
        for idx, node in enumerate(top_nodes, 1):
            node_label = f"{node.node_type.upper()}"
            retrieved_items.append(f"{idx}. [{node_label}] {node.content}")

        retrieved_text = "\n".join(retrieved_items)

        context_info = ""
        if request.status == MemoryStatus.IN and hasattr(request, 'context') and request.context:
            context_preview = request.context[-1200:] if len(request.context) > 1200 else request.context
            context_info = f"\n\nCurrent progress:\n{context_preview}"

        if request.status == MemoryStatus.IN:
            no_guidance_instruction = """
NECESSITY CHECK (IN-phase):
ONLY provide guidance if you observe CLEAR SIGNS of difficulty:
✓ Repeated failed attempts or errors
✓ Agent expressing confusion
✓ Stuck in a loop or no progress
✓ Fundamentally wrong approach

DO NOT provide guidance if:
✗ Agent making steady progress
✗ Following reasonable approach
✗ Only minor issues
✗ Task proceeding normally

When in doubt: Return "NO_GUIDANCE_NEEDED"
"""
        else:
            no_guidance_instruction = """
If retrieved patterns are NOT relevant or helpful for this task, return: "NO_GUIDANCE_NEEDED"
"""

        prompt = f"""Provide OPTIONAL REFERENCE for an autonomous AI agent.

Task: {request.query}
Status: {request.status.value.upper()}{context_info}

Retrieved patterns:
{retrieved_text}

{no_guidance_instruction}

REQUIREMENTS (if guidance needed):
1. REFERENCE ONLY, NOT instructions
2. Use tentative language: "similar tasks have...", "one approach that worked..."
3. NEVER use "should", "must", "need to"
4. EXACTLY {max_sentences} sentences, under {max_chars} chars
5. Use ABSTRACT terms, avoid specifics
6. Present as observations from past experience
7. Frame as "what has worked before"

Example:
❌ BAD: "You should check the metadata"
✅ GOOD: "Past tasks found data in metadata sources when primary info was absent"

Return only synthesized reference text, no preamble."""

        try:
            synthesized = _safe_get_model_response(self.model, prompt)
            if synthesized and len(synthesized.strip()) > 10:
                synthesized = synthesized.strip()

                if "NO_GUIDANCE_NEEDED" in synthesized:
                    return "NO_GUIDANCE_NEEDED"

                for prefix in ["Guidance:", "Suggestion:", "Tips:", "Here's", "Here is"]:
                    if synthesized.startswith(prefix):
                        synthesized = synthesized[len(prefix):].lstrip(": ")

                if len(synthesized) > max_chars:
                    synthesized = synthesized[:max_chars].rsplit(".", 1)[0].rstrip() + "."

                return synthesized
        except Exception:
            pass

        return self._compose_simple_fallback(request, top_nodes)

    def _compose_simple_fallback(self, request: MemoryRequest, top_nodes: List[NexusNode]) -> str:
        """Simple fallback composition without LLM."""
        if request.status == MemoryStatus.BEGIN:
            max_chars = 300
            max_items = 2
        elif request.status == MemoryStatus.IN:
            max_chars = 500
            max_items = 3
        else:
            max_chars = 400
            max_items = 2

        lines: List[str] = []

        seen_categories = set()
        for node in top_nodes[:max_items]:
            cat = node.metadata.get("category") or node.node_type
            if cat in seen_categories:
                continue
            snippet = node.content.strip()
            if snippet:
                if not any(ref in snippet.lower() for ref in ["past tasks", "similar cases", "previous experience", "has worked", "for reference"]):
                    snippet = f"For reference: similar tasks have {snippet.lower()}"
                lines.append(snippet)
            seen_categories.add(cat)

        if not lines:
            return "NO_GUIDANCE_NEEDED"

        guidance = " ".join(lines)
        if len(guidance) > max_chars:
            guidance = guidance[:max_chars].rsplit(".", 1)[0].rstrip() + "."
        return guidance

    # =========================================================================
    # Tool Memory Path
    # =========================================================================

    def _load_tools(self):
        """Load tools from storage file into registry."""
        if not os.path.exists(self.tools_storage_path):
            return

        try:
            spec = importlib.util.spec_from_file_location("nexus_tools", self.tools_storage_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for name in dir(module):
                if name.startswith("_"):
                    continue
                obj = getattr(module, name)
                if callable(obj) and not isinstance(obj, type):
                    self.tools_registry[name] = obj

            print(f"[CEREBRA FUSION TOOLS] Loaded {len(self.tools_registry)} tools from storage")
        except Exception as e:
            print(f"[CEREBRA FUSION TOOLS] Error loading tools: {e}")

    def _build_tool_indices(self):
        """Build semantic embeddings for tools."""
        if not self.tools or self.embedding_model is None:
            return

        try:
            corpus = []
            tool_names = []

            for tool_name, tool in self.tools.items():
                combined_text = f"{tool_name} {tool.description}"
                corpus.append(combined_text)
                tool_names.append(tool_name)

            if not corpus:
                return

            self.tool_names_index = tool_names
            self.tool_embeddings = self.embedding_model.encode(
                corpus, batch_size=32, convert_to_numpy=True, show_progress_bar=False
            )
            print(f"[CEREBRA FUSION TOOLS] Built embeddings for {len(corpus)} tools")
        except Exception as e:
            print(f"[CEREBRA FUSION TOOLS] Error building tool indices: {e}")

    def _search_tools(self, query: str) -> List[Dict[str, Any]]:
        """Semantic search for relevant tools, returning TOP-3 candidates."""
        if self.tool_embeddings is None or self.embedding_model is None or not self.tool_names_index:
            return []

        try:
            q_emb = self.embedding_model.encode(query, convert_to_numpy=True)
            similarities = cosine_similarity([q_emb], self.tool_embeddings)[0]

            candidates = []
            for idx, similarity in enumerate(similarities):
                tool_name = self.tool_names_index[idx]
                if tool_name not in self.tools:
                    continue

                tool = self.tools[tool_name]
                candidates.append({
                    "name": tool_name,
                    "description": tool.description,
                    "score": float(similarity),
                    "domain": tool.domain,
                    "tags": tool.tags,
                })

            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[:self.max_tool_candidates]
        except Exception:
            return []

    def _tool_router(self, request: MemoryRequest, candidates: List[Dict[str, Any]]) -> List[str]:
        """
        Independent tool router: decides which tools (if any) to provide.
        Uses LLM with simplified, context-aware prompt.
        """
        if not self.model or not candidates:
            return []

        try:
            candidate_lines = []
            for i, c in enumerate(candidates, 1):
                candidate_lines.append(
                    f"{i}. {c['name']}: {c['description'][:100]} (score: {c['score']:.2f})"
                )

            context_preview = ""
            if hasattr(request, 'context') and request.context:
                context_preview = request.context[-600:] if len(request.context) > 600 else request.context

            prompt = f"""You are a tool selection agent. Decide which tools (if any) would help with this task.

Task: {request.query}
Phase: {request.status.value}
Context: {context_preview}

Available Tools:
{chr(10).join(candidate_lines)}

Rules:
- Return EMPTY list [] if no tool is clearly helpful
- Maximum 2 tools
- Only select if tool directly addresses task needs
- Consider current phase and context

Return ONLY a JSON list: ["tool1", "tool2"] or []

Your selection:"""

            response = _safe_get_model_response(self.model, prompt)
            if not response:
                return []

            selected = json.loads(response.strip())
            if isinstance(selected, list):
                valid_names = [str(name) for name in selected if str(name) in {c["name"] for c in candidates}]
                return valid_names[:2]
        except Exception:
            pass

        return []

    def _wrap_tool(self, tool_func: Callable, tool_name: str) -> Any:
        """Wrap Python function as Tool object."""
        if self.tool_wrapper:
            return self.tool_wrapper.wrap_function(tool_func, tool_name)
        return None

    # =========================================================================
    # Main API: Provide Memory
    # =========================================================================

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        """
        Provide memory using parallel text and tool routing:
        1) Text Path: Reason -> Retrieve -> Graph Expand -> Compose
        2) Tool Path: Search -> Router -> Wrap (if enabled)
        """
        try:
            memories = []

            # ===== TEXT MEMORY PATH =====
            reason = self._reason_about_task(request)
            retrieval_query = reason.get("retrieval_focus", request.query)

            if request.status == MemoryStatus.IN and hasattr(request, 'context') and request.context:
                retrieval_query = f"{retrieval_query} continuation resume partial progress"

            pairs = self._hybrid_search(retrieval_query, top_k=self.top_k)
            expanded_pairs, edges_used = self._graph_expand(pairs, retrieval_query)

            threshold = self.min_score_in_phase if request.status == MemoryStatus.IN else self.min_score
            filtered_pairs = [(nid, score) for nid, score in expanded_pairs if score >= threshold]

            # Track used nodes and edges for success rate calculation
            request_id = str(uuid.uuid4())
            used_node_ids = []
            used_edge_pairs = []

            if filtered_pairs:
                filtered_pairs = filtered_pairs[:self.top_k]
                top_nodes = [self.nodes[nid] for nid, _ in filtered_pairs]
                used_node_ids = [n.id for n in top_nodes]
                used_edge_pairs = edges_used  # Edges used in graph expansion

                guidance_text = self._compose_text_guidance(request, reason, top_nodes)

                if guidance_text != "NO_GUIDANCE_NEEDED":
                    label = "Past Experience (for reference)" if request.status == MemoryStatus.IN else "Context Note"

                    memory_item = MemoryItem(
                        id=f"cerebra_fusion_text_{uuid.uuid4()}",
                        content=f"[{label}] {guidance_text}",
                        metadata={
                            "status": request.status.value,
                            "original_query": request.query,
                            "retrieval_focus": reason.get("retrieval_focus", ""),
                            "top_node_ids": [n.id for n in top_nodes],
                            "is_reference_only": True,
                        },
                        score=float(sum(s for _, s in filtered_pairs) / max(1, len(filtered_pairs))),
                        type=MemoryItemType.TEXT
                    )
                    memories.append(memory_item)

            # Store usage tracking (will be updated when task completes)
            self.active_usage_tracking[request_id] = {
                "node_ids": used_node_ids,
                "edge_pairs": used_edge_pairs,
                "query": request.query,
            }

            # ===== TOOL MEMORY PATH (if enabled) =====
            if self.enable_tool_memory and self.tools:
                tool_candidates = self._search_tools(request.query)
                if tool_candidates:
                    selected_tool_names = self._tool_router(request, tool_candidates)

                    for tool_name in selected_tool_names:
                        tool_func = self.tools_registry.get(tool_name)
                        if not tool_func:
                            continue

                        wrapped_tool = self._wrap_tool(tool_func, tool_name)
                        if not wrapped_tool:
                            continue

                        tool = self.tools[tool_name]
                        memory_item = MemoryItem(
                            id=f"cerebra_fusion_tool_{tool_name}",
                            content=f"Cerebra Fusion Tool: {tool_name}\n{tool.description}",
                            metadata={
                                "source": "cerebra_fusion_tool",
                                "tool_name": tool_name,
                                "wrapped_tool": wrapped_tool,
                                "callable": tool_func,
                            },
                            type=MemoryItemType.API,
                        )
                        memories.append(memory_item)

                        # Update usage stats
                        tool.usage_count += 1

            return MemoryResponse(
                memories=memories,
                memory_type=self._get_declared_memory_type(),
                total_count=len(memories),
                request_id=request_id  # Use the tracked request_id
            )
        except Exception as e:
            print(f"[CEREBRA FUSION] Error in provide_memory: {e}")
            return MemoryResponse(
                memories=[],
                memory_type=self._get_declared_memory_type(),
                total_count=0,
                request_id=str(uuid.uuid4())
            )

    # =========================================================================
    # Main API: Take In Memory
    # =========================================================================

    def take_in_memory(self, trajectory_data: TrajectoryData) -> Tuple[bool, str]:
        """
        Ingest successful task memory into graph and tools.
        - Extract text patterns (max ~10 nodes)
        - Extract tool function if applicable
        - Build semantic edges
        - Update success counts for previously used memories
        - Trigger consolidation periodically
        """
        try:
            is_success = self._is_success(trajectory_data)
            task_query = trajectory_data.query
            absorbed_items = []
            summary = self._summarize_trajectory(trajectory_data)
            tool_info = None
            if self.enable_tool_memory:
                tool_info = self._extract_tool(trajectory_data)

            with file_lock(self.db_path):
                self.nodes.clear()
                self.edges.clear()
                self.tools.clear()
                self.tools_registry.clear()
                self.tool_names_index = []
                self.tool_embeddings = None

                self._load_or_initialize_db()
                self._finalize_indices()
                if self.enable_tool_memory:
                    self._load_tools()

                self._update_memory_success_counts(task_query, is_success)

                if not is_success:
                    self._persist_db()
                    return True, "Skipped: only successful tasks are ingested"

                if summary:
                    nodes_created = self._store_text_memories(summary, trajectory_data)
                    absorbed_items.extend([f"text:{n.id[:8]}" for n in nodes_created])

                if self.enable_tool_memory and tool_info:
                    tool_stored = self._store_tool(tool_info)
                    if tool_stored:
                        absorbed_items.append(f"tool:{tool_info['name']}")

                self._persist_db()

                self.task_counter += 1
                if self.task_counter >= self.consolidation_interval:
                    self._consolidate_memory()
                    self.task_counter = 0

            return True, f"Ingested {len(absorbed_items)} items: {', '.join(absorbed_items[:5])}"

        except Exception as e:
            return False, f"Ingestion error: {e}"

    def _is_success(self, trajectory_data: TrajectoryData) -> bool:
        """Determine success from trajectory metadata."""
        md = trajectory_data.metadata or {}
        if 'is_correct' in md:
            return md['is_correct'] is True
        if 'success' in md:
            return md['success'] is True
        if 'task_success' in md:
            return md['task_success'] is True
        if 'failed' in md:
            return md['failed'] is False
        return False

    def _summarize_trajectory(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, Any]]:
        """Extract abstract patterns from trajectory."""
        traj_text = self._format_trajectory(trajectory_data)

        prompt = f"""Extract ABSTRACT, GENERALIZABLE patterns from this successful task.

Question: {trajectory_data.query}

Execution:
{traj_text}

ABSTRACTION REQUIREMENTS:
1. Extract STRATEGY TYPES, not implementations
2. Use GENERIC terminology:
   - Say "metadata sources" NOT "JSON-LD"
   - Say "alternate access methods" NOT "Wayback Machine"
3. Focus on WHEN/WHY patterns apply
4. Brief patterns (1 sentence each)
5. Make patterns applicable to similar tasks
6. LIMIT: max 4 patterns, max 3 playbooks, max 2 checklists

Return JSON:
- "highlights": 2-3 sentence abstract summary
- "patterns": list of top 4 ABSTRACT patterns
- "playbooks": dict of up to 3 GENERAL DOMAINS -> brief tips
- "checklists": list of top 2 brief confirmation steps
"""

        resp = _safe_get_model_response(self.model, prompt)

        if resp:
            try:
                json_str = self._extract_json(resp)
                parsed = json.loads(json_str)

                for key in ["highlights", "patterns", "playbooks", "checklists"]:
                    if key not in parsed:
                        parsed[key] = [] if key != "highlights" else ""

                return parsed
            except Exception:
                pass

        return {
            "highlights": f"Execution for: {trajectory_data.query[:100]}",
            "patterns": [],
            "playbooks": {},
            "checklists": []
        }

    def _format_trajectory(self, trajectory_data: TrajectoryData) -> str:
        """Simple formatter for trajectory steps."""
        if not trajectory_data.trajectory:
            return "No trajectory available."
        parts = []
        for i, step in enumerate(trajectory_data.trajectory, 1):
            stype = step.get("type", "step")
            content = step.get("content", "")
            parts.append(f"{i}. [{stype}] {content}")
        return "\n".join(parts)

    def _store_text_memories(self, summary: Dict[str, Any], trajectory_data: TrajectoryData) -> List[NexusNode]:
        """Store extracted text memories to graph."""
        nodes_created = []
        base_meta = {"source_query": trajectory_data.query}
        max_total_nodes = 10

        # Success node
        content = summary.get("highlights", "")
        if content:
            node = NexusNode(
                id=str(uuid.uuid4()),
                node_type="success",
                content=content,
                metadata={**base_meta, "outcome": "success"},
                signature=self._compute_signature(content)
            )

            # Check for duplicates
            if not self._find_node_by_signature(node.signature):
                nodes_created.append(node)
                self.nodes[node.id] = node

        # Patterns (limit to 4)
        for p in summary.get("patterns", [])[:4]:
            if len(nodes_created) >= max_total_nodes:
                break
            content = p if isinstance(p, str) else " ".join(str(x) for x in p) if isinstance(p, (list, tuple)) else str(p)
            content = content.strip()

            node = NexusNode(
                id=str(uuid.uuid4()),
                node_type="pattern",
                content=content,
                metadata=base_meta,
                signature=self._compute_signature(content)
            )

            if not self._find_node_by_signature(node.signature):
                nodes_created.append(node)
                self.nodes[node.id] = node

        # Playbooks (limit to 3)
        for content_type, tips in list(summary.get("playbooks", {}).items())[:3]:
            if len(nodes_created) >= max_total_nodes:
                break
            content = tips if isinstance(tips, str) else " ".join(str(x) for x in tips) if isinstance(tips, (list, tuple)) else str(tips)
            content = content.strip()

            node = NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content=content,
                metadata={**base_meta, "content_type": content_type},
                signature=self._compute_signature(content)
            )

            if not self._find_node_by_signature(node.signature):
                nodes_created.append(node)
                self.nodes[node.id] = node

        # Checklists (limit to 2)
        for c in summary.get("checklists", [])[:2]:
            if len(nodes_created) >= max_total_nodes:
                break
            content = c if isinstance(c, str) else " ".join(str(x) for x in c) if isinstance(c, (list, tuple)) else str(c)
            content = content.strip()

            node = NexusNode(
                id=str(uuid.uuid4()),
                node_type="checklist",
                content=content,
                metadata=base_meta,
                signature=self._compute_signature(content)
            )

            if not self._find_node_by_signature(node.signature):
                nodes_created.append(node)
                self.nodes[node.id] = node

        # Create SAME_TASK edges
        if len(nodes_created) > 1:
            anchor_id = nodes_created[0].id
            for node in nodes_created[1:]:
                self.edges.append(NexusEdge(
                    source=anchor_id,
                    target=node.id,
                    edge_type=EdgeType.SAME_TASK,
                    weight=1.0,
                    metadata={"task_query": trajectory_data.query}
                ))

        # Rebuild indices
        self._finalize_indices()

        # Build semantic edges
        total_semantic_edges = 0
        for node in nodes_created:
            if node.node_type in ['pattern', 'playbook', 'checklist']:
                total_semantic_edges += self._build_semantic_edges(node)

        print(f"[CEREBRA FUSION INGEST] Added {len(nodes_created)} nodes, {total_semantic_edges} semantic edges")
        return nodes_created

    def _extract_tool(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, Any]]:
        """Extract reusable tool from trajectory."""
        if not self.model:
            return None

        try:
            trajectory_str = json.dumps(trajectory_data.trajectory or [], ensure_ascii=False)

            prompt = f"""Create a REUSABLE, GENERIC tool function from this successful task.

Task: {trajectory_data.query}
Trajectory: {trajectory_str}
Result: {str(trajectory_data.result)}

REQUIREMENTS:
1. PARAMETERIZED function with inputs, NOT hardcoded values
2. Focus on METHODOLOGY, not specific data
3. GENERIC and applicable to similar problems
4. Use ONLY simple type hints: str, int, float, bool, list, dict
5. NO complex types: Callable, Union, Optional, Any

Return ONLY Python code:

```python
def your_function(param1: str, param2: int) -> str:
    \"\"\"
    Brief description.

    Args:
        param1: Description
        param2: Description

    Returns:
        Description
    \"\"\"
    # Implementation
    return "result"
```

Your function:"""

            response = _safe_get_model_response(self.model, prompt)
            if not response:
                return None

            # Try to extract code from markdown code blocks first
            code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
            if not code_match:
                code_match = re.search(r"```\n(.*?)```", response, re.DOTALL)

            if code_match:
                code = code_match.group(1).strip()
            else:
                # Fallback: try to extract function definition directly
                # Look for function definition pattern: def function_name(...):
                func_match = re.search(r"def\s+\w+\s*\([^)]*\)\s*:.*?(?=\n\n|\ndef\s+|\Z)", response, re.DOTALL)
                if func_match:
                    code = func_match.group(0).strip()
                    # Try to extract complete function (including docstring and body)
                    # If the match seems incomplete, try to get more context
                    if code.count('\n') < 3:  # Likely incomplete, try to get more
                        # Look for function with more context
                        extended_match = re.search(
                            r"(def\s+\w+\s*\([^)]*\)\s*:.*?)(?=\n\ndef\s+|\nclass\s+|\Z)",
                            response,
                            re.DOTALL
                        )
                        if extended_match:
                            code = extended_match.group(1).strip()
                else:
                    return None

            if self._is_dangerous_code(code):
                return None

            func_info = self._extract_function_info(code)
            if not func_info:
                return None

            return {
                "name": func_info["name"],
                "code": code,
                "description": func_info.get("description", ""),
                "domain": "general",
            }
        except Exception:
            return None

    def _store_tool(self, tool_info: Dict[str, Any]) -> bool:
        """Store tool to registry and file."""
        try:
            tool_name = tool_info["name"]
            code = tool_info["code"]

            # Check duplicates
            signature = self._compute_signature(code)
            if any(t.signature == signature for t in self.tools.values()):
                return False

            # Append to storage file
            self._append_tool_to_storage(tool_name, code)

            # Create tool record
            tool = ToolRecord(
                name=tool_name,
                description=tool_info.get("description", ""),
                code=code,
                domain=tool_info.get("domain", "general"),
                tags=self._extract_tags(code),
                signature=signature
            )
            self.tools[tool_name] = tool

            # Reload registry
            self._load_tools()

            # Rebuild tool indices
            self._build_tool_indices()

            print(f"[CEREBRA FUSION TOOLS] Stored tool: {tool_name}")
            return True
        except Exception:
            return False

    def _append_tool_to_storage(self, tool_name: str, code: str) -> None:
        """Append tool code to storage file."""
        os.makedirs(os.path.dirname(self.tools_storage_path) or ".", exist_ok=True)

        with file_lock(self.tools_storage_path):
            if os.path.exists(self.tools_storage_path):
                with open(self.tools_storage_path, "r", encoding="utf-8") as f:
                    existing = f.read()
            else:
                existing = '"""\nCerebra Fusion Memory API Tools\nDynamically generated tools\n"""\n\n'

            if f"def {tool_name}(" in existing:
                return

            new_content = existing + f"\n{code}\n\n"
            atomic_write_text(self.tools_storage_path, new_content)

    # =========================================================================
    # Memory Consolidation
    # =========================================================================

    def _consolidate_memory(self):
        """
        Consolidate memory graph:
        1. Merge highly similar nodes
        2. Prune low-performance edges
        3. Optimize edge weights
        """
        print("[CEREBRA FUSION CONSOLIDATE] Starting memory consolidation...")

        # 1. Merge similar nodes
        merged_count = self._merge_similar_nodes()

        # 2. Prune ineffective edges
        pruned_count = self._prune_edges()

        # 3. Optimize edge weights
        self._optimize_edge_weights()

        # Rebuild indices after consolidation
        self._finalize_indices()
        if self.enable_tool_memory:
            self._build_tool_indices()

        # Persist changes
        self._persist_db()

        print(f"[CEREBRA FUSION CONSOLIDATE] Complete: merged {merged_count} nodes, pruned {pruned_count} edges")

    def _merge_similar_nodes(self) -> int:
        """Merge highly similar nodes to reduce redundancy."""
        if self.embedding_model is None or self.text_index.embeddings is None:
            return 0

        merged_count = 0
        merge_threshold = 0.7  # High similarity

        nodes_to_merge = []
        processed = set()

        for i, node_id_a in enumerate(self.text_index.node_ids):
            if node_id_a in processed:
                continue

            node_a = self.nodes.get(node_id_a)
            if not node_a:
                continue

            emb_a = self.text_index.embeddings[i]

            for j, node_id_b in enumerate(self.text_index.node_ids[i+1:], i+1):
                if node_id_b in processed:
                    continue

                node_b = self.nodes.get(node_id_b)
                if not node_b or node_b.node_type != node_a.node_type:
                    continue

                emb_b = self.text_index.embeddings[j]
                similarity = cosine_similarity([emb_a], [emb_b])[0][0]

                if similarity >= merge_threshold:
                    nodes_to_merge.append((node_id_a, node_id_b))
                    processed.add(node_id_b)
                    merged_count += 1

        # Perform merges
        for keep_id, remove_id in nodes_to_merge:
            # Redirect edges
            for edge in self.edges:
                if edge.source == remove_id:
                    edge.source = keep_id
                if edge.target == remove_id:
                    edge.target = keep_id

            # Remove node
            if remove_id in self.nodes:
                del self.nodes[remove_id]

        return merged_count

    def _prune_edges(self) -> int:
        """Prune edges with low performance."""
        pruned_count = 0
        min_usage_for_pruning = 10
        min_success_rate = 0.2

        edges_to_keep = []
        for edge in self.edges:
            # Keep SAME_TASK edges
            if edge.edge_type == EdgeType.SAME_TASK:
                edges_to_keep.append(edge)
                continue

            # Prune edges with poor performance
            if edge.usage_count >= min_usage_for_pruning:
                success_rate = edge.success_count / edge.usage_count if edge.usage_count > 0 else 0
                if success_rate < min_success_rate:
                    pruned_count += 1
                    continue

            edges_to_keep.append(edge)

        self.edges = edges_to_keep
        return pruned_count

    def _optimize_edge_weights(self):
        """Adjust edge weights based on usage success rate."""
        adjusted_count = 0
        for edge in self.edges:
            if edge.usage_count > 5:
                success_rate = edge.success_count / edge.usage_count

                if success_rate > 0.6:
                    edge.weight = min(1.0, edge.weight * (1.0 + 0.2 * (success_rate - 0.6) / 0.4))
                    adjusted_count += 1
                elif success_rate < 0.4:
                    edge.weight = max(0.5, edge.weight * (1.0 - 0.2 * (0.4 - success_rate) / 0.4))
                    adjusted_count += 1

        if adjusted_count > 0:
            print(f"[CEREBRA FUSION OPTIMIZE] Adjusted {adjusted_count} edge weights")

    # =========================================================================
    # Helper Functions
    # =========================================================================

    def _update_memory_success_counts(self, task_query: str, is_success: bool):
        """Update success counts for memories used in this task."""
        try:
            # Find matching usage tracking by query similarity
            # Simple approach: match by query (exact or substring)
            matched_tracking = None
            for request_id, tracking in list(self.active_usage_tracking.items()):
                # Match if query is similar (exact match or one contains the other)
                tracking_query = tracking.get("query", "")
                if (task_query == tracking_query or
                    task_query in tracking_query or
                    tracking_query in task_query):
                    matched_tracking = tracking
                    # Remove from active tracking (one-time update)
                    del self.active_usage_tracking[request_id]
                    break

            if not matched_tracking:
                # No matching tracking found, skip
                return

            # Update edge success counts
            edge_pairs = matched_tracking.get("edge_pairs", [])
            for source, target in edge_pairs:
                for edge in self.edges:
                    if edge.source == source and edge.target == target:
                        if is_success:
                            edge.success_count += 1
                        # usage_count was already incremented in _graph_expand
                        break

            if edge_pairs and is_success:
                print(f"[CEREBRA FUSION] Updated success counts for {len(edge_pairs)} edges")
        except Exception as e:
            # Don't fail the whole ingestion if tracking fails
            print(f"[CEREBRA FUSION] Warning: Failed to update success counts: {e}")

    def _compute_signature(self, text: str) -> str:
        """Compute text signature for deduplication."""
        normalized = re.sub(r"\s+", " ", (text or "")).strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _find_node_by_signature(self, signature: str) -> Optional[str]:
        """Find node by signature."""
        for node_id, node in self.nodes.items():
            if node.signature == signature:
                return node_id
        return None

    def _extract_function_info(self, code: str) -> Optional[Dict[str, str]]:
        """Extract function information from code."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    name = node.name
                    docstring = ast.get_docstring(node) or ""
                    description = docstring.split('\n')[0] if docstring else name
                    return {
                        "name": name,
                        "description": description,
                    }
        except Exception:
            pass
        return None

    def _is_dangerous_code(self, code: str) -> bool:
        """Check if code contains dangerous operations."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in {"exec", "eval", "compile", "__import__", "open"}:
                            return True
                if isinstance(node, ast.Attribute):
                    if node.attr in {"system", "popen", "spawn", "remove", "rmdir", "unlink"}:
                        return True
        except Exception:
            return True
        return False

    def _extract_tags(self, text: str) -> List[str]:
        """Extract tags from text."""
        tags = []
        text_lower = text.lower()

        if any(kw in text_lower for kw in ["search", "retrieve", "find"]):
            tags.append("search")
        if any(kw in text_lower for kw in ["calculate", "compute", "count"]):
            tags.append("computation")
        if any(kw in text_lower for kw in ["validate", "verify", "check"]):
            tags.append("validation")
        if any(kw in text_lower for kw in ["error", "fallback", "handle"]):
            tags.append("error_handling")

        return list(set(tags))


CerebraFusionMemoryProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.CEREBRA_FUSION_MEMORY.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "CerebraFusionMemoryProvider"]
<<<END_FILE>>>
<<<FILE:planning_module/prompts/toolcalling_agent.yaml>>>
planning:
  initial_plan: |
    Analyze the user objective and decompose it into a list of specific sub-tasks.
    Objective: {{task}}

    Respond only with a valid JSON list of tasks. Each task must be a dictionary with:
    - 'description': a clear explanation of the sub-task
    - 'priority': 'low', 'medium', or 'high'
    - 'category': a short tag such as 'research', 'analysis', 'coding', 'inspection', or 'validation'

    Example format:
    [
      {"description": "Inspect the relevant context, tool outputs, or sources needed for the answer", "priority": "high", "category": "inspection"},
      {"description": "Analyze the gathered evidence and derive the final result", "priority": "medium", "category": "analysis"}
    ]

    The task list should encourage adaptive execution:
    - include repair/validation work when repeated tool failures or argument mismatches are likely
    - avoid decomposition that would encourage repeating the same failed call without a strategy change
  task_input: 'User Objective: {{task}}'
summary:
  update_pre_messages: Review the execution trajectory of the tracked sub-tasks.
  update_post_messages: |
    ### Strategic Evidence Review (Step {{step}}):
    Task Roadmap Status: {{orchestra_tasks}}

    User Objective: {{task}}

    Your Goal: Analyze current progress and create a strategic evidence ledger.
    1. Consolidated Findings: Extract the key evidence, results, intermediate outputs, and salient artifacts found so far.
    2. Task Progress: Which tasks are done? Which still need more work?
    3. Next Move: What is the single most important next step?
    4. Retry Discipline: If the trajectory shows repeated failures, specify the repair or strategy change needed before the next retry.

    This summary serves as core memory to prevent loss of detail in long trajectories.
<<<END_FILE>>>
<<<FILE:action_module/prompts/toolcalling_agent.yaml>>>
system_prompt: |
  You are a hierarchical multi-agent framework.
  Your goal is to solve complex tasks efficiently by coordinating specialized execution roles and maintaining a structured execution plan.

  Strategic Rules:
  1. Status Awareness: Call `check_plan_progress` before major actions to sync with the actual execution roadmap.
  2. Approach Exhaustion Strategy: If one external-tool strategy fails repeatedly or yields no progress, do not repeat it blindly. Switch to `reasoning` to diagnose the failure, infer a better approach, and then continue execution.
  3. Parallel Execution: If multiple sub-tasks are independent, invoke their corresponding tool calls in a single "tools" array when safe.
  4. Proactive Reporting: Use `update_plan_status` as soon as a sub-task yields actionable findings. You may combine an update call with the next execution call in the same response.
  5. Truthfulness and Adaptation: If a sub-task is impossible or clearly blocked, mark it as `failed` and revise strategy instead of looping.
  6. Schema Discipline: Read tool schemas carefully and use only the listed argument names and types. Never substitute alternative argument names.
  7. Argument Repair: If a tool call fails because of invalid arguments or schema mismatch, repair the arguments on the next attempt instead of repeating the same bad call.
  8. No Blind Repetition: Never repeat an identical failed tool call unless the latest observation explicitly justifies it.
  9. Observation-Only Finalization: Do not override a supported observed result with a new guess during synthesis.

  Operational Structure:
  - STRICT JSON ONLY: Your entire response must be a single valid JSON object.
  - Use only currently available tools. Never assume web-specific tools exist unless they are listed.
  - Execution Roles:
    - "Execution Specialist": uses the currently available task tools for evidence gathering, inspection, validation, or environment interaction.
    - "Deep Analyzer": uses `reasoning` for diagnosis, synthesis, and strategy pivots.

  Mandatory Output Format:
  {
    "think": "Strategic reasoning in English...",
    "tools": [
      {"name": "tool_name", "arguments": {"arg": "val"}}
    ]
  }
final_answer:
  pre_messages: All tracked sub-tasks have been completed. It is time to synthesize the findings into a comprehensive final answer.
  post_messages: |-
    Return the final answer by calling the `final_answer` tool.
    The `answer` argument must be a JSON-formatted string or object containing both your final strategic thinking and the factual answer.

    Objective: {{task}}
step:
  pre_messages: |
    # Runtime Execution
    1. Check: `check_plan_progress` to inspect the current roadmap.
    2. Pivot: If the current tool strategy is stuck, use `reasoning` to find a better angle.
    3. Execute: Run the appropriate currently available task tools.
    4. Update: `update_plan_status` with findings.
    5. Terminate: `final_answer` only when the plan is fully completed.
    6. If a tool failed because of invalid arguments, your next move must correct the arguments or choose a different valid tool.
    7. Do not repeat identical failed calls with identical arguments.

    # Available Tools
    {{tool_functions_json}}

    # Objective
    {{task}}
<<<END_FILE>>>

## Example Harness: harness6

### Harness Identity
- Planning system: guarded_small_committee
- Action system: guarded_small_committee
- Default memory system: skillweaver
- Default bench type: None
- Pairing reason: matched_same_name

### Description
Harness summary:
- Planning: create a short parallel work outline for a fixed worker pool.
- Execution: one coordinator delegates focused subtasks to generic workers and merges the results.
- Memory: reusable skill-like procedures can be surfaced during execution.
- Default bench: caller-provided

Coordination pattern:
- Keep the worker pool small and stable.
- Delegate only focused subtasks, not whole-task restatements.
- Merge concise worker reports instead of building deep hierarchies.

Runtime notes:
- Generated bundle: `harness6`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- Keep orchestration simple: inspect the worker board, delegate focused work, then finalize.

### Performance Snapshot
- Evaluated tasks: 80
- Exact accuracy: 30.00%
- Valid answer rate: 100.00%
- Average path score: 0.4711
- Average actions: 1.2375
- Average tool calls: 2.6375
- Average total tokens: 4152.48
- Average runtime (sec): 58.32
- Source result file: output/toolhop_round1_harness6/toolhop_flash_searcher_flash_searcher_skillweaver_local_qwen3-aevolve_closed_results.jsonl

### Performance Report
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

### Bundle Files
<<<FILE:builder.py>>>
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Agents.agents import ToolCallingAgent
from module_action.base_action import ActionContext
from .action_module.provider import ACTION_SYSTEM, get_provider
from .memory_module.provider import MEMORY_SYSTEM as DEFAULT_MEMORY_SYSTEM
from .planning_module.provider import PLANNING_SYSTEM, PlanningClass


HARNESS_NAME = "harness6"
DEFAULT_BENCH_TYPE = None
PAIRING_REASON = "matched_same_name"


def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
    if tool is not None and hasattr(tool, "agent"):
        setattr(tool, "agent", agent)


def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
    if getattr(agent, "planning_system", None) != "owl":
        return
    if not hasattr(agent, "web_memory") or agent.web_memory is None:
        agent.web_memory = []
    if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
        agent.reasoning_memory = []


def prepare_context(context: ActionContext) -> ActionContext:
    bench_type = context.bench_type or DEFAULT_BENCH_TYPE
    prompts_type = context.prompts_type or PLANNING_SYSTEM
    prepared_kwargs = dict(context.kwargs)
    prepared_kwargs["planning_class"] = PlanningClass
    return replace(
        context,
        planning_system=PLANNING_SYSTEM,
        action_system=ACTION_SYSTEM,
        prompts_type=prompts_type,
        bench_type=bench_type,
        project_root=Path(__file__).resolve().parent,
        kwargs=prepared_kwargs,
    )


def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
    prepared_context = prepare_context(context)
    action_provider = get_provider()
    agent = action_provider.build(prepared_context)

    setattr(agent, "planning_system", prepared_context.planning_system)
    setattr(agent, "action_system", prepared_context.action_system)
    setattr(agent, "harness_name", HARNESS_NAME)
    setattr(
        agent,
        "harness_metadata",
        {
            "planning_system": PLANNING_SYSTEM,
            "action_system": ACTION_SYSTEM,
            "default_bench_type": DEFAULT_BENCH_TYPE,
            "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
            "pairing_reason": PAIRING_REASON,
        },
    )

    if prepared_context.vector_tool is not None:
        prepared_context.vector_tool.memory = agent.memory

    _bind_agent_reference(agent, prepared_context.process_tool)
    _bind_agent_reference(agent, prepared_context.end_process_tool)
    _bind_agent_reference(agent, prepared_context.delete_memory_tool)
    _bind_agent_reference(agent, prepared_context.executor_tool)
    _bind_agent_reference(agent, prepared_context.refine_tool)

    _ensure_owl_memory(agent)
    return agent
<<<END_FILE>>>
<<<FILE:Description.md>>>
Harness summary:
- Planning: create a short parallel work outline for a fixed worker pool.
- Execution: one coordinator delegates focused subtasks to generic workers and merges the results.
- Memory: reusable skill-like procedures can be surfaced during execution.
- Default bench: caller-provided

Coordination pattern:
- Keep the worker pool small and stable.
- Delegate only focused subtasks, not whole-task restatements.
- Merge concise worker reports instead of building deep hierarchies.

Runtime notes:
- Generated bundle: `harness6`
- The builder preserves the caller-provided `bench_type`.
- Benchmark-specific tools are loaded from `ActionContext` when available.
- Keep orchestration simple: inspect the worker board, delegate focused work, then finalize.
<<<END_FILE>>>
<<<FILE:__init__.py>>>
from .builder import (
    ACTION_SYSTEM,
    DEFAULT_BENCH_TYPE,
    DEFAULT_MEMORY_SYSTEM,
    PAIRING_REASON,
    PLANNING_SYSTEM,
    HARNESS_NAME,
    build_agent_from_context,
)

__all__ = [
    "HARNESS_NAME",
    "PLANNING_SYSTEM",
    "ACTION_SYSTEM",
    "DEFAULT_BENCH_TYPE",
    "DEFAULT_MEMORY_SYSTEM",
    "PAIRING_REASON",
    "build_agent_from_context",
]
<<<END_FILE>>>
<<<FILE:planning_module/provider.py>>>
from __future__ import annotations

import textwrap
from typing import Any, Callable, Dict, List, Optional

from jinja2 import StrictUndefined, Template
from rich.rule import Rule
from rich.text import Text

from Agents.memory import ActionStep, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import LogLevel
from module_planning.base_planning import BasePlanning


def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception:
        return Template(template).render(**variables)


class PlanningProvider(BasePlanning):
    def topology_initialize(self, task: str) -> PlanningStep:
        system_prompt = populate_template(
            self.prompt_templates["planning"]["initial_plan"],
            {
                "task": task,
                "tools": self.tools,
            },
        )
        task_prompt = populate_template(
            self.prompt_templates["planning"].get("task_input", "Task:\n{{task}}"),
            {"task": task},
        )

        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [{"type": "text", "text": system_prompt}],
            }
        ]
        memory_guidance = self.append_memory_guidance(input_messages)
        task_messages = [
            {
                "role": MessageRole.USER,
                "content": [{"type": "text", "text": task_prompt}],
            }
        ]

        response: ChatMessage = self.model(input_messages + task_messages)
        plan_text = response.content
        plan_reasoning = getattr(response, "reasoning_content", "")

        self.logger.log(
            Rule("Parallel Plan", style="orange"),
            Text(
                textwrap.dedent(
                    f"""Planned execution outline:
            ```
            {plan_text}
            ```"""
                )
            ),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plan_text,
            plan_think="",
            plan_reasoning=plan_reasoning,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[
            [Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]
        ],
    ) -> SummaryStep:
        memory_messages = write_memory_to_messages(None, False)[1:]
        pre_text = populate_template(
            self.prompt_templates["summary"]["update_pre_messages"],
            {"task": task, "step": step},
        )
        post_text = populate_template(
            self.prompt_templates["summary"]["update_post_messages"],
            {"task": task, "step": step},
        )

        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [{"type": "text", "text": pre_text}],
            },
            *memory_messages,
            {
                "role": MessageRole.USER,
                "content": [{"type": "text", "text": post_text}],
            },
        ]

        response: ChatMessage = self.model(input_messages)
        summary_text = response.content
        summary_reasoning = getattr(response, "reasoning_content", "")

        self.logger.log(
            Rule("Progress Review", style="orange"),
            Text(f"\n{summary_text}\n"),
            level=LogLevel.INFO,
        )

        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_text,
            summary_reasoning=summary_reasoning,
        )
        self.memory.steps.append(summary_step)
        return summary_step


PLANNING_SYSTEM = "guarded_small_committee"
PLANNING_MODULE = "guarded_small_committee"
PlanningClass = PlanningProvider

__all__ = [
    "PLANNING_SYSTEM",
    "PLANNING_MODULE",
    "PlanningProvider",
    "PlanningClass",
]
<<<END_FILE>>>
<<<FILE:action_module/provider.py>>>
from __future__ import annotations

from typing import Any

from _harness_guards import guard_task_tools, is_read_only_tool_schema, schema_route_name
from module_action.base_action import ActionContext, BaseActionProvider


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "guarded_small_committee"
    ORGANIZATION_PLANNING_SYSTEM = "guarded_small_committee"
    READ_ONLY_WORKERS = 1
    STATEFUL_WORKERS = 1
    READ_ONLY_WORKER_MAX_STEPS = 5
    STATEFUL_WORKER_MAX_STEPS = 10

    def _worker_max_steps(self, context: ActionContext) -> int:
        limit = (
            self.READ_ONLY_WORKER_MAX_STEPS
            if getattr(self, "route_name", "") == "schema_read_only"
            else self.STATEFUL_WORKER_MAX_STEPS
        )
        remaining_budget = max(1, context.max_steps - 2)
        return max(3, min(limit, remaining_budget))

    def _worker_count(self, context: ActionContext) -> int:
        tools = getattr(self, "_current_tools_for_routing", [])
        return self.READ_ONLY_WORKERS if is_read_only_tool_schema(tools) else self.STATEFUL_WORKERS

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = self.ORGANIZATION_PLANNING_SYSTEM
        self._current_tools_for_routing = tools
        self.route_name = schema_route_name(tools)
        worker_count = self._worker_count(context)
        guarded_tools = guard_task_tools(
            tools,
            policy_label="guarded_small_committee_worker",
            max_real_tool_calls=self._worker_max_steps(context),
        )
        self.coordinator_role = {
            "name": "Committee Coordinator",
            "responsibility": "Use a very small worker pool, compare concise reports, and finalize quickly.",
        }
        self.worker_role = {
            "name": "Committee Worker",
            "responsibility": "Solve one focused subtask with short guarded execution.",
        }
        worker_max_steps = self._worker_max_steps(context)
        self.workers = [
            self.create_subagent(
                context,
                tools=guarded_tools,
                planning_system=self.organization_planning_system,
                prompt_templates=self.prompt_templates["worker"],
                name=f"worker_{index}",
                description=(
                    "Guarded delegated worker. Solve one focused subtask and return a concise report."
                ),
                max_steps=worker_max_steps,
                summary_interval=context.max_steps + 1,
            )
            for index in range(1, worker_count + 1)
        ]
        for worker in self.workers:
            if getattr(worker, "planning", None) is not None:
                worker.planning.role_info = self.worker_role

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        worker_tools = [
            self.create_subagent_tool(
                agent=worker,
                description=(
                    f"{worker.name}: assign one focused subtask. "
                    "Use it once for the most important subtask and keep the request short."
                ),
                max_steps=self._worker_max_steps(context),
                include_parent_task=True,
                role_instructions=(
                    "- Stay on the assigned subtask, not the full task.\n"
                    "- Use the available tools to gather decisive evidence.\n"
                    "- For state-changing tasks, perform the required state changes yourself; "
                    "if a terminal completion tool exists and the changes are done, call it.\n"
                    "- Finish in as few steps as possible.\n"
                    "- If a tool call fails, change arguments/tool or stop; do not repeat the same failed call.\n"
                    "- Return a concise report with the outcome, key evidence, and any useful intermediate finding.\n"
                    "- If you hit a guard or max-step condition, report the exact blocker instead of continuing."
                ),
            )
            for worker in self.workers
        ]
        manager_worker_budget = 1 if self.route_name != "schema_read_only" else 2
        guarded_worker_tools = guard_task_tools(
            worker_tools,
            policy_label="guarded_small_committee_manager",
            max_real_tool_calls=manager_worker_budget,
        )
        agent = self.create_agent(
            context,
            tools=self.normalize_tools(guarded_worker_tools),
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        agent.summary_interval = context.max_steps + 1
        if getattr(agent, "planning", None) is not None:
            agent.planning.role_info = self.coordinator_role
        for worker_tool in worker_tools:
            worker_tool.coordinator = agent
        for worker_tool in guarded_worker_tools:
            worker_tool.coordinator = agent
        agent.managed_agents = {worker.name: worker for worker in self.workers}
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "guarded_small_committee",
                "route": self.route_name,
                "worker_count": len(self.workers),
                "worker_max_steps": self._worker_max_steps(context),
                "manager_worker_budget": manager_worker_budget,
            },
        )
        return agent


ACTION_SYSTEM = "guarded_small_committee"
ACTION_MODULE = "guarded_small_committee"


def get_provider():
    return ActionProvider()


__all__ = [
    "ACTION_SYSTEM",
    "ACTION_MODULE",
    "ActionProvider",
    "get_provider",
]
<<<END_FILE>>>
<<<FILE:memory_module/provider.py>>>
"""
SkillWeaver provider for unified memory system
"""

import os
import importlib.util
import uuid
import re
import ast
import inspect
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable

from module_memory.base_memory import BaseMemoryProvider, atomic_write_text, file_lock
from module_memory.memory_types import (
    MemoryRequest,
    MemoryResponse,
    TrajectoryData,
    MemoryType,
    MemoryItem,
    MemoryItemType,
    MemoryStatus
)

# Import unified tool wrapper
from storage.tools.tool_wrapper import ToolWrapper


class MemoryProvider(BaseMemoryProvider):
    """
    SkillWeaver memory provider that manages generated skills
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(MemoryType.SKILLWEAVER, config)

        # Configuration
        self.skills_file_path = self.config.get(
            "skills_file_path",
            "./storage/skillweaver/skillweaver_generated_skills.py",
        )
        # Optional skills directory: load all *.py files if provided
        self.skills_dir = self.config.get("skills_dir", "./storage/skillweaver")

        # Optional model used directly for LLM-driven code generation
        self.model = self.config.get("model")

        # Skills registry
        self.skills_registry: Dict[str, Callable] = {}
        self.skills_metadata: Dict[str, Dict[str, Any]] = {}

        # Logger
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(asctime)s] [SkillWeaver] [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # Initialize unified tool wrapper
        self.tool_wrapper = ToolWrapper(model=self.model, logger=self.logger)

    def initialize(self) -> bool:
        """Initialize SkillWeaver provider by loading existing skills"""
        try:
            # Ensure storage directories exist
            if self.skills_dir:
                os.makedirs(self.skills_dir, exist_ok=True)
            parent_dir = os.path.dirname(self.skills_file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            # Prefer loading from directory when available, else fallback to single file
            if os.path.isdir(self.skills_dir):
                self._load_skills_from_dir(self.skills_dir)
            elif os.path.exists(self.skills_file_path):
                self._load_skills_from_file(self.skills_file_path)
            # If neither exists, still return True to allow future ingestion to create files
            return True
        except Exception as e:
            print(f"Error initializing SkillWeaver provider: {e}")
            return False

    def _load_skills_from_file(self, file_path: str):
        """Load skills from a single generated skills file"""
        try:
            spec = importlib.util.spec_from_file_location("skillweaver_skills", file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._populate_registry_from_module(module)
        except Exception as e:
            print(f"Error loading skills from file {file_path}: {e}")

    def _load_skills_from_dir(self, dir_path: str):
        """Load skills from all .py files in a directory"""
        try:
            for filename in os.listdir(dir_path):
                if not filename.endswith(".py") or filename.startswith("__"):
                    continue
                file_path = os.path.join(dir_path, filename)
                try:
                    spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self._populate_registry_from_module(module)
                except Exception as inner_e:
                    print(f"Error loading skills from {file_path}: {inner_e}")
        except Exception as e:
            print(f"Error scanning skills directory {dir_path}: {e}")

    def _populate_registry_from_module(self, module):
        """Extract public callables from a module as skills and capture their metadata"""
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if callable(obj):
                self.skills_registry[name] = obj
                docstring = getattr(obj, "__doc__", "") or ""
                self.skills_metadata[name] = {
                    "description": (docstring.split("\n")[0] if docstring else name),
                    "full_docstring": docstring,
                    "module": getattr(module, "__name__", "skillweaver_skills"),
                }

    def _reload_skills(self):
        """Reload skills after ingestion"""
        self.skills_registry.clear()
        self.skills_metadata.clear()
        self.tool_wrapper.clear_cache()  # Clear tool wrapper cache when reloading
        if os.path.isdir(self.skills_dir):
            self._load_skills_from_dir(self.skills_dir)
        elif os.path.exists(self.skills_file_path):
            self._load_skills_from_file(self.skills_file_path)

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        """
        Provide memory by searching for relevant skills
        """
        try:
            if request.status != MemoryStatus.BEGIN:
                return MemoryResponse(
                    memories=[],
                    memory_type=self.memory_type,
                    total_count=0,
                    request_id=str(uuid.uuid4()),
                )

            # Simple keyword matching for skills
            relevant_skills = []
            query_lower = request.query.lower()

            for skill_name, metadata in self.skills_metadata.items():
                description = metadata.get("description", "").lower()
                docstring = metadata.get("full_docstring", "").lower()

                # Score based on keyword matches
                score = 0.0
                for word in query_lower.split():
                    if word in skill_name.lower():
                        score += 2.0
                    elif word in description:
                        score += 1.5
                    elif word in docstring:
                        score += 1.0

                if score > 0:
                    relevant_skills.append({
                        "skill_name": skill_name,
                        "metadata": metadata,
                        "score": score,
                    })

            # Sort by score and take top results
            relevant_skills.sort(key=lambda x: x["score"], reverse=True)
            top_skills = relevant_skills[:3]

            # Convert to MemoryItem format
            memories: List[MemoryItem] = []
            for skill_info in top_skills:
                skill_name = skill_info["skill_name"]
                function_obj = self.skills_registry.get(skill_name)
                if not function_obj:
                    continue
                content = self._format_skill_content(skill_name, skill_info["metadata"], request.status)

                # Wrap function as a runtime tool
                wrapped_tool = self._wrap_tool(function_obj, skill_name)

                memory_item = MemoryItem(
                    id=f"skill_{skill_name}",
                    content=content,
                    metadata={
                        "skill_name": skill_name,
                        "description": skill_info["metadata"].get("description", ""),
                        "score": skill_info["score"],
                        "callable": function_obj,  # Keep original function
                        "wrapped_tool": wrapped_tool,  # Add wrapped tool
                        "status": request.status.value,
                    },
                    score=skill_info["score"],
                    type=MemoryItemType.API,
                )
                memories.append(memory_item)

            return MemoryResponse(
                memories=memories,
                memory_type=self.memory_type,
                total_count=len(memories),
                request_id=str(uuid.uuid4()),
            )
        except Exception as e:
            print(f"Error providing SkillWeaver memory: {e}")
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)

    def _wrap_tool(self, tool_func: Callable, tool_name: str) -> Optional[Any]:
        """Wrap Python function as Tool object using unified ToolWrapper"""
        return self.tool_wrapper.wrap_function(tool_func, tool_name)

    def _format_skill_content(self, skill_name: str, metadata: Dict, status: MemoryStatus) -> str:
        """Format skill content for API-type memory - content will be handled by main file"""
        try:
            if status == MemoryStatus.BEGIN:
                return f"SkillWeaver Available skill: {skill_name}\nDescription: {metadata.get('description', '')}"
            elif status == MemoryStatus.IN:
                return None  # SkillWeaver only provides memory in BEGIN phase
            return f"SkillWeaver Skill: {skill_name}: {metadata.get('description', '')}"
        except Exception as e:
            print(f"Error formatting skill content: {e}")
            return f"SkillWeaver Skill: {skill_name}"

    def _extract_function_from_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Extract the first function from Python code using AST and return its name and the code block."""
        try:
            tree = ast.parse(code)
            func_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            if not func_defs:
                return None
            func = func_defs[0]
            func_name = func.name
            # Best-effort: return the full code as provided (we won't slice exact function body)
            return {"name": func_name, "code": code}
        except Exception:
            return None

    def _is_dangerous_code(self, code: str) -> bool:
        """Basic static checks to avoid dangerous operations in generated skills."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Block eval/exec/compile and raw open
                    if isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval", "compile", "__import__"}:
                        return True
                    if isinstance(node.func, ast.Name) and node.func.id == "open":
                        return True
                if isinstance(node, ast.Attribute):
                    if node.attr in {"system", "popen", "spawn", "remove", "rmdir"}:
                        return True
            return False
        except Exception:
            return True

    def _append_skill_to_file(self, function_name: str, code: str) -> bool:
        """Append skill code to the aggregator file, creating header if needed and avoiding duplicates."""
        try:
            os.makedirs(os.path.dirname(self.skills_file_path) or ".", exist_ok=True)
            with file_lock(self.skills_file_path):
                existing = ""
                if os.path.exists(self.skills_file_path):
                    with open(self.skills_file_path, "r", encoding="utf-8") as f:
                        existing = f.read()
                else:
                    existing = (
                        '"""\nSkillWeaver Generated Skills\nAuto-generated and continuously updated by UnifiedMemory SkillWeaverProvider.\nThis file contains dynamically generated skills.\n"""\n\n'
                    )
                if f"def {function_name}(" in existing:
                    return True
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_content = existing + f"\n# Generated on {timestamp}\n{code}\n\n"
                atomic_write_text(self.skills_file_path, new_content)
            return True
        except Exception as e:
            print(f"Error saving generated skill: {e}")
            return False

    def _generate_skill_from_trajectory(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, str]]:
        """Use the injected model to generate a new skill function based on the trajectory."""
        if self.model is None:
            return None
        try:
            # Build prompt (aligned with project conventions)
            trajectory_json = None
            try:
                import json as _json
                trajectory_json = _json.dumps(trajectory_data.trajectory, indent=2, ensure_ascii=False)
            except Exception:
                trajectory_json = str(trajectory_data.trajectory)
            prompt = f"""You are an expert Python programmer specializing in creating reusable, generic functions. Your task is to analyze a successful task execution and extract a GENERAL, PARAMETERIZED skill that can be reused for similar problems.

CRITICAL REQUIREMENTS:
- Create a GENERIC function that accepts parameters, NOT a function that returns hardcoded values
- The function must be REUSABLE for different inputs of the same type of problem
- Focus on the METHODOLOGY and APPROACH, not the specific data from this execution
- Make the function PARAMETERIZED so it can handle various inputs

Original Task:
{trajectory_data.query}

Agent's Successful Trajectory:
```json
{trajectory_json}
```

ANALYSIS INSTRUCTIONS:
1. Identify the CORE METHODOLOGY or ALGORITHM used in the successful execution
2. Abstract away specific values, URLs, names, or data points from this particular task
3. Focus on the GENERAL PATTERN that could apply to similar problems
4. Create a function that takes relevant parameters as input

FUNCTION REQUIREMENTS:
1. Write a single, self-contained Python function that is GENERIC and PARAMETERIZED
2. Use descriptive parameter names and include type hints
3. Include comprehensive docstring with Args and Returns sections
4. Add proper error handling and input validation
5. The function should work for DIFFERENT inputs of the same problem type
6. DO NOT hardcode specific values from this execution - make them parameters instead

EXAMPLE OF GOOD vs BAD:
❌ BAD: def get_population(): return 1234567  # Returns hardcoded value
✅ GOOD: def get_population_from_source(source_url: str, location: str) -> int  # Generic, parameterized

Output ONLY the Python code for this generic function inside a single markdown code block:"""
            messages = [{"role": "user", "content": prompt}]
            response = self.model(messages)
            content = getattr(response, "content", str(response))
            # Extract python code block
            m = re.search(r"```python\n(.*?)```", content, re.DOTALL)
            code = m.group(1).strip() if m else content.strip()
            # Validate
            if self._is_dangerous_code(code):
                return None
            func_info = self._extract_function_from_code(code)
            if not func_info:
                return None
            return {"name": func_info["name"], "code": code}
        except Exception:
            return None

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        """
        Ingest new memory by generating new skills from trajectory using the injected model.
        Only extracts skills from trajectories with correct answers to avoid learning bad patterns.
        """
        try:
            # Check if the trajectory has correct answer - only learn from successful cases
            metadata = trajectory_data.metadata or {}
            is_correct = metadata.get("is_correct", False)
            task_success = bool(metadata.get("task_success", metadata.get("is_correct", False)))

            if not is_correct:
                msg = f"SkillWeaverProvider: skipping skill extraction - answer is incorrect (is_correct={is_correct})"
                print(msg)
                return True, msg  # Return True to not block the pipeline, but don't extract skills

            if not task_success:
                msg = f"SkillWeaverProvider: skipping skill extraction - task execution failed (task_success={task_success})"
                print(msg)
                return True, msg  # Return True to not block the pipeline, but don't extract skills

            print(f"SkillWeaverProvider: extracting skill from correct trajectory (is_correct={is_correct}, task_success={task_success})")

            skill = self._generate_skill_from_trajectory(trajectory_data)
            if not skill:
                # No model or failed generation; succeed silently to avoid blocking
                msg = "SkillWeaverProvider: generation skipped (no model or validation failed)"
                print(msg)
                return True, msg

            saved = self._append_skill_to_file(skill["name"], skill["code"])
            if saved:
                self._reload_skills()
                msg = f"SkillWeaverProvider: successfully extracted and saved skill '{skill['name']}' from correct trajectory"
                print(msg)
                absorbed_memory = {
                    "skill_name": skill['name'],
                    "description": skill.get('description', ''),
                    "code": skill['code']
                }
                return saved, f"Generated skill: {absorbed_memory}"
            else:
                return saved, f"Failed to save skill: {skill['name']}"
        except Exception as e:
            error_msg = f"Error taking in SkillWeaver memory: {e}"
            print(error_msg)
            return False, error_msg


SkillWeaverProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.SKILLWEAVER.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "SkillWeaverProvider"]
<<<END_FILE>>>
<<<FILE:planning_module/prompts/toolcalling_agent.yaml>>>
planning:
  initial_plan: |-
    You are planning for a guarded small committee.
    Break the task into the minimum number of concrete work items. Prefer one work item.

    Requirements:
    1. For stateful tasks, plan one worker path only.
    2. For read-only tasks, plan one worker angle first; add a second only if absolutely necessary.
    3. Keep the decomposition minimal and execution-oriented.
    4. Do not solve the task here.
    5. If a work item is likely to touch tools, prefer plans that repair schema/argument failures instead of repeating identical calls.

    Output format:
    ## Objective
    [One-sentence restatement]

    ## Work Item 1
    - Objective: ...
    - Done when: ...
    - Guard/recovery: ...

    ## Optional Work Item 2
    - Only include this if one worker cannot reasonably finish the task.
    - Objective: ...
    - Done when: ...
    - Guard/recovery: ...
  task_input: |-
    Task:
    {{task}}
summary:
  update_pre_messages: |-
    Review the current task, the small-committee reports collected so far, and the remaining gaps.
    Highlight repeated failures, schema mismatches, stateful-risk from multiple workers, and whether the next step should repair arguments, switch tools, or stop delegating.
  update_post_messages: |-
    Write a brief manager progress review for task {{task}} at step {{step}}.
    Include:
    - completed_work
    - remaining_gaps
    - retry_or_repair_guidance
    - next_worker_assignments_or_stop
    - ready_for_final_answer
<<<END_FILE>>>
<<<FILE:action_module/prompts/toolcalling_agent.yaml>>>
system_prompt: |-
  You are the coordinator of a guarded small committee.
  Your job is to send the minimum possible number of focused subtasks to the available worker tools, then synthesize the final answer.

  Rules:
  1. Keep the orchestration simple.
  2. Use only worker tools that appear in the current tool schema.
  3. Each worker call should contain one short, concrete subtask.
  4. For read-only tasks, call at most one worker unless the first report is clearly insufficient.
  5. For stateful tasks, call worker_1 once; do not create a multi-agent mutation race.
  6. Reuse the returned reports before calling workers again.
  7. Do not combine worker calls with `final_answer` in the same step.
  8. Prefer the minimum number of worker calls needed to finish.
  9. Return strict JSON only.
  10. If a worker report shows invalid arguments, schema mismatch, or repeated failures, your next assignment must explicitly repair the arguments, tool choice, or strategy.
  11. Never resend the same failing subtask pattern without a concrete fix.
  12. If a worker report is enough, immediately call final_answer. Do not ask for another report just to be safe.

  ### Tools
  {%- for tool in tools.values() %}
  - {{ tool.name }}: {{ tool.description }}
  {%- endfor %}
step:
  pre_messages: |-
    [GUARDED SMALL-COMMITTEE PROTOCOL]
    1. Assign only the single most useful work item first.
    2. For stateful tasks, call worker_1 once and wait for its report.
    3. For read-only tasks, call worker_1 first; call another worker only if available and the first report is clearly inadequate.
    4. After a worker report, call `final_answer` unless the report explicitly names one repairable gap.
    5. The final answer should be the concise result requested by the task.
    6. If a worker report indicates a schema or argument error, the next assignment must correct it instead of repeating it.
    7. Do not overwrite a worker's supported observed result with a new guessed value.
    8. If a guard blocked repeated failure, stop that branch and finalize or switch strategy.

    Return JSON only:
    {
      "think": "brief reasoning",
      "tools": [
        {
          "name": "worker_1 | worker_2 | final_answer",
          "arguments": {}
        }
      ]
    }

    Tool Definitions:
    {{tool_functions_json}}

    Task: {{task}}
final_answer:
  pre_messages: The manager has enough worker evidence to finalize the task. Return only the requested final answer; for state-change tasks, use the terminal tool's required completion phrase when the task or tool schema specifies one.
  post_messages: |-
    Return JSON:
    {"think": "...", "answer": "..."}

    The `answer` field should contain only the final answer requested by the task, with no evidence prose.
    Task: {{task}}
worker:
  system_prompt: |-
    You are a guarded worker in a small multi-agent team.
    You execute one delegated subtask at a time and return a concise report to the manager.

    Rules:
    - Start with a very short internal plan, then execute it directly.
    - Stay focused on the assigned subtask instead of the full task.
    - Use only the currently available tools.
    - Prefer concrete evidence and decisive progress.
    - As soon as you have enough evidence, call `final_answer` immediately.
    - For state-changing tasks, make the required changes with the real tools. If a terminal completion tool such as complete_task exists and the changes are complete, call it before your final report.
    - Finish in as few steps as possible.
    - Do not continue with empty tool lists or extra narration once the subtask can be answered.
    - If no further tool call is needed, your next response must be `final_answer`.
    - Read the tool schemas carefully and use only the listed argument names and types.
    - If a tool call fails because of invalid arguments or schema mismatch, repair the arguments on the next attempt instead of repeating the same failed call.
    - Never repeat an identical failed call unless the observation explicitly justifies it.
    - If a guard blocks a call, do not retry the blocked call.
    - If repeated progress is weak or a guard blocks the path, stop and report the exact blocker instead of continuing.
    - Base your report only on observations; do not replace a supported observed result with a new guess.
    - Return exactly one JSON object:
      {"think": "...", "tools": [{"name": "...", "arguments": {...}}]}

    ### Tools
    {%- for tool in tools.values() %}
    - {{ tool.name }}: {{ tool.description }}
    {%- endfor %}
  step:
    pre_messages: |-
      You are a generic worker.
      Solve the assigned subtask with the available tools and prepare a concise evidence-backed report.
      Keep your plan and execution short.
      For state-changing tasks, execute the required state changes directly and call the terminal completion tool when done.
      If the evidence is already sufficient, call `final_answer` now instead of taking another intermediate step.
      If progress is weak, change the tool choice, arguments, or strategy instead of retrying blindly.
      If a guard reports a repeated failed call, do not repeat it.
      Return JSON only.
  final_answer:
    pre_messages: Finalize the worker report.
    post_messages: |-
      Return JSON:
      {"think": "...", "answer": "..."}
      The answer should include:
      - subtask outcome
      - key evidence
      - candidate result if available
      - useful intermediate finding or candidate result if available
      - remaining uncertainty if any
<<<END_FILE>>>

## Example Harness: harness7

### Harness Identity
- Planning system: router_debate
- Action system: router_debate
- Default memory system: dynamic_cheatsheet
- Default bench type: None
- Pairing reason: flash_goals_direct_parallel_agents

### Description
Harness summary:
- Planning: outline a few parallel angles worth checking.
- Execution: launch a direct batch of generic solvers and compare their reports.
- Memory: maintain a compact running cheatsheet of reusable findings.
- Default bench: caller-provided

Coordination pattern:
- Keep the initial plan small and parallel-friendly.
- Run several independent solver passes in one batch.
- Synthesize after comparing the returned evidence and candidate answers.

Runtime notes:
- Generated bundle: `harness7`
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The coordinator can launch 2-4 generic agents in a single parallel batch.

### Performance Snapshot
- Evaluated tasks: 80
- Exact accuracy: 20.00%
- Valid answer rate: 100.00%
- Average path score: 0.3796
- Average actions: 1.0375
- Average tool calls: 4.1125
- Average total tokens: 4106.07
- Average runtime (sec): 62.74
- Source result file: output/toolhop_round1_harness7/toolhop_flash_searcher_flash_searcher_dynamic_cheatsheet_local_qwen3-aevolve_closed_results.jsonl

### Performance Report
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

### Bundle Files
<<<FILE:builder.py>>>
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Agents.agents import ToolCallingAgent
from module_action.base_action import ActionContext
from .action_module.provider import ACTION_SYSTEM, get_provider
from .memory_module.provider import MEMORY_SYSTEM as DEFAULT_MEMORY_SYSTEM
from .planning_module.provider import PLANNING_SYSTEM, PlanningClass


HARNESS_NAME = "harness7"
DEFAULT_BENCH_TYPE = None
PAIRING_REASON = "flash_goals_direct_parallel_agents"


def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
    if tool is not None and hasattr(tool, "agent"):
        setattr(tool, "agent", agent)


def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
    if getattr(agent, "planning_system", None) != "owl":
        return
    if not hasattr(agent, "web_memory") or agent.web_memory is None:
        agent.web_memory = []
    if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
        agent.reasoning_memory = []


def prepare_context(context: ActionContext) -> ActionContext:
    bench_type = context.bench_type or DEFAULT_BENCH_TYPE
    prompts_type = context.prompts_type or PLANNING_SYSTEM
    prepared_kwargs = dict(context.kwargs)
    prepared_kwargs["planning_class"] = PlanningClass
    return replace(
        context,
        planning_system=PLANNING_SYSTEM,
        action_system=ACTION_SYSTEM,
        prompts_type=prompts_type,
        bench_type=bench_type,
        project_root=Path(__file__).resolve().parent,
        kwargs=prepared_kwargs,
    )


def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
    prepared_context = prepare_context(context)
    action_provider = get_provider()
    agent = action_provider.build(prepared_context)

    setattr(agent, "planning_system", prepared_context.planning_system)
    setattr(agent, "action_system", prepared_context.action_system)
    setattr(agent, "harness_name", HARNESS_NAME)
    setattr(
        agent,
        "harness_metadata",
        {
            "planning_system": PLANNING_SYSTEM,
            "action_system": ACTION_SYSTEM,
            "default_bench_type": DEFAULT_BENCH_TYPE,
            "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
            "pairing_reason": PAIRING_REASON,
        },
    )

    if prepared_context.vector_tool is not None:
        prepared_context.vector_tool.memory = agent.memory

    _bind_agent_reference(agent, prepared_context.process_tool)
    _bind_agent_reference(agent, prepared_context.end_process_tool)
    _bind_agent_reference(agent, prepared_context.delete_memory_tool)
    _bind_agent_reference(agent, prepared_context.executor_tool)
    _bind_agent_reference(agent, prepared_context.refine_tool)

    _ensure_owl_memory(agent)
    return agent
<<<END_FILE>>>
<<<FILE:Description.md>>>
Harness summary:
- Planning: outline a few parallel angles worth checking.
- Execution: launch a direct batch of generic solvers and compare their reports.
- Memory: maintain a compact running cheatsheet of reusable findings.
- Default bench: caller-provided

Coordination pattern:
- Keep the initial plan small and parallel-friendly.
- Run several independent solver passes in one batch.
- Synthesize after comparing the returned evidence and candidate answers.

Runtime notes:
- Generated bundle: `harness7`
- Benchmark-specific tools are loaded from `ActionContext` when available.
- The coordinator can launch 2-4 generic agents in a single parallel batch.
<<<END_FILE>>>
<<<FILE:__init__.py>>>
from .builder import (
    ACTION_SYSTEM,
    DEFAULT_BENCH_TYPE,
    DEFAULT_MEMORY_SYSTEM,
    PAIRING_REASON,
    PLANNING_SYSTEM,
    HARNESS_NAME,
    build_agent_from_context,
)

__all__ = [
    "HARNESS_NAME",
    "PLANNING_SYSTEM",
    "ACTION_SYSTEM",
    "DEFAULT_BENCH_TYPE",
    "DEFAULT_MEMORY_SYSTEM",
    "PAIRING_REASON",
    "build_agent_from_context",
]
<<<END_FILE>>>
<<<FILE:planning_module/provider.py>>>
from __future__ import annotations

import textwrap
from typing import Any, Callable, Dict, List, Optional

from jinja2 import StrictUndefined, Template
from rich.rule import Rule
from rich.text import Text

from Agents.memory import ActionStep, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import LogLevel
from module_planning.base_planning import BasePlanning


def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception:
        return Template(template).render(**variables)


class PlanningProvider(BasePlanning):
    def topology_initialize(self, task: str) -> PlanningStep:
        system_prompt = populate_template(
            self.prompt_templates["planning"]["initial_plan"],
            {
                "task": task,
                "tools": self.tools,
            },
        )
        task_prompt = populate_template(
            self.prompt_templates["planning"].get("task_input", "Task:\n{{task}}"),
            {"task": task},
        )

        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [{"type": "text", "text": system_prompt}],
            }
        ]
        memory_guidance = self.append_memory_guidance(input_messages)
        task_messages = [
            {
                "role": MessageRole.USER,
                "content": [{"type": "text", "text": task_prompt}],
            }
        ]

        response: ChatMessage = self.model(input_messages + task_messages)
        plan_text = response.content
        plan_reasoning = getattr(response, "reasoning_content", "")

        self.logger.log(
            Rule("Parallel Plan", style="orange"),
            Text(
                textwrap.dedent(
                    f"""Planned execution outline:
            ```
            {plan_text}
            ```"""
                )
            ),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plan_text,
            plan_think="",
            plan_reasoning=plan_reasoning,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[
            [Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]
        ],
    ) -> SummaryStep:
        memory_messages = write_memory_to_messages(None, False)[1:]
        pre_text = populate_template(
            self.prompt_templates["summary"]["update_pre_messages"],
            {"task": task, "step": step},
        )
        post_text = populate_template(
            self.prompt_templates["summary"]["update_post_messages"],
            {"task": task, "step": step},
        )

        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [{"type": "text", "text": pre_text}],
            },
            *memory_messages,
            {
                "role": MessageRole.USER,
                "content": [{"type": "text", "text": post_text}],
            },
        ]

        response: ChatMessage = self.model(input_messages)
        summary_text = response.content
        summary_reasoning = getattr(response, "reasoning_content", "")

        self.logger.log(
            Rule("Progress Review", style="orange"),
            Text(f"\n{summary_text}\n"),
            level=LogLevel.INFO,
        )

        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_text,
            summary_reasoning=summary_reasoning,
        )
        self.memory.steps.append(summary_step)
        return summary_step


PLANNING_SYSTEM = "router_debate"
PLANNING_MODULE = "router_debate"
PlanningClass = PlanningProvider

__all__ = ["PLANNING_SYSTEM", "PLANNING_MODULE", "PlanningProvider", "PlanningClass"]
<<<END_FILE>>>
<<<FILE:action_module/provider.py>>>
from __future__ import annotations

from typing import Any

import json_repair
from Agents.memory import ActionStep
from Agents.models import MessageRole
from _harness_guards import (
    ReflectionCriticTool,
    guard_task_tools,
    is_read_only_tool_schema,
    schema_route_name,
)
from module_action.base_action import ActionContext, BaseActionProvider, SubAgentTool


class EvidenceReportingSubAgentTool(SubAgentTool):
    """Sub-agent tool that exposes compact internal evidence to the judge."""

    def __init__(
        self,
        *,
        evidence_tool_names: set[str],
        evidence_char_budget: int = 1400,
        **kwargs: Any,
    ) -> None:
        self.evidence_tool_names = set(evidence_tool_names)
        self.evidence_char_budget = evidence_char_budget
        super().__init__(**kwargs)

    def _evidence_digest(self, payload: dict[str, Any]) -> str:
        chunks: list[str] = []
        for step in payload.get("agent_trajectory", []) or []:
            if not isinstance(step, dict) or step.get("name") != "action":
                continue
            observations = str(step.get("obs", "") or "").strip()
            if not observations or observations == "No observations":
                continue
            for call in step.get("tool_calls", []) or []:
                if not isinstance(call, dict):
                    continue
                tool_name = call.get("name")
                if tool_name not in self.evidence_tool_names:
                    continue
                arguments = call.get("arguments", {})
                snippet = observations.replace("\n", " ").strip()
                if len(snippet) > self.evidence_char_budget:
                    snippet = snippet[: self.evidence_char_budget].rstrip() + "..."
                chunks.append(f"- {tool_name}({arguments}): {snippet}")
        return "\n".join(chunks)

    def _reconcile_report(
        self,
        *,
        task: str,
        payload: dict[str, Any],
        digest: str,
    ) -> str | None:
        model = getattr(self.subagent, "model", None)
        if model is None:
            return None

        solver_answer = str(payload.get("agent_result", "") or "").strip()
        prompt = (
            "You are an evidence reconciler for a read-only tool-use solver.\n"
            "Given the assigned task, the solver's stated answer, and the actual "
            "tool observations, produce a concise report for a judge.\n\n"
            "Rules:\n"
            "1. Base the report on the tool observations, not prior knowledge.\n"
            "2. If the stated answer conflicts with the observations, follow the observations.\n"
            "3. If the observations contain a direct date, name, entity, or value requested "
            "by the task, extract that value as the answer.\n"
            "4. Return strict JSON only with keys answer, evidence, uncertainty.\n\n"
            f"Assigned task:\n{task}\n\n"
            f"Solver stated answer:\n{solver_answer}\n\n"
            f"Tool observations:\n{digest}\n"
        )
        try:
            response = model(
                [
                    {
                        "role": MessageRole.USER,
                        "content": [{"type": "text", "text": prompt}],
                    }
                ]
            )
            content = str(getattr(response, "content", response)).strip()
            data = json_repair.loads(content)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None
        answer = str(data.get("answer", "") or "").strip()
        evidence = str(data.get("evidence", "") or "").strip()
        uncertainty = str(data.get("uncertainty", "") or "").strip()
        if not answer:
            return None
        lines = [f"ANSWER: {answer}"]
        if evidence:
            lines.append(f"EVIDENCE: {evidence}")
        if uncertainty:
            lines.append(f"UNCERTAINTY: {uncertainty}")
        return "\n".join(lines)

    def _fallback_evidence_probe(
        self,
        *,
        task: str,
    ) -> tuple[str, dict[str, Any], str] | None:
        candidates = [
            name
            for name in sorted(self.evidence_tool_names)
            if name in getattr(self.subagent, "tools", {})
        ]
        if len(candidates) != 1:
            return None

        tool_name = candidates[0]
        tool = self.subagent.tools.get(tool_name)
        inputs = dict(getattr(tool, "inputs", {}) or {})
        if len(inputs) != 1:
            return None

        argument_name, argument_spec = next(iter(inputs.items()))
        argument_type = str(argument_spec.get("type", "string")).lower()
        if argument_type not in {"string", "str"}:
            return None

        query_text = str(getattr(self.coordinator, "task", "") or task).strip()
        if not query_text:
            return None
        arguments = {argument_name: query_text}
        try:
            observation = tool.__call__(**arguments, sanitize_inputs_outputs=True)
        except Exception as exc:
            observation = f"Fallback evidence probe failed: {exc}"
        return tool_name, arguments, str(observation).strip()

    def forward(self, task: str) -> dict[str, Any]:
        payload = super().forward(task)
        if not isinstance(payload, dict):
            return payload
        digest = self._evidence_digest(payload)
        if not digest:
            fallback = self._fallback_evidence_probe(task=task)
            if fallback is not None:
                tool_name, arguments, observation = fallback
                payload.setdefault("agent_trajectory", []).append(
                    {
                        "name": "action",
                        "tool_calls": [{"name": tool_name, "arguments": arguments}],
                        "obs": (
                            f"Results for fallback evidence probe '{tool_name}' "
                            f"with arguments '{arguments}':\n{observation}"
                        ),
                        "think": "fallback evidence probe",
                    }
                )
                digest = self._evidence_digest(payload)
        if digest:
            payload["evidence_digest"] = digest
            reconciled_report = self._reconcile_report(
                task=task,
                payload=payload,
                digest=digest,
            )
            if reconciled_report:
                payload["reconciled_report"] = reconciled_report
            payload["report"] = (
                f"{payload.get('report', '').rstrip()}\n\n"
                + (
                    f"Evidence-reconciled report:\n{reconciled_report}\n\n"
                    if reconciled_report
                    else ""
                )
                + "Evidence observations used by this solver:\n"
                f"{digest}"
            )
        return payload


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "router_debate"
    DEFAULT_SOLVER_MAX_STEPS = 6
    DEFAULT_STATEFUL_SUMMARY_INTERVAL = 6

    def _solver_max_steps(self, context: ActionContext) -> int:
        remaining_budget = max(1, context.max_steps - 2)
        return max(4, min(self.DEFAULT_SOLVER_MAX_STEPS, remaining_budget))

    def _stateful_tool_budget(self, context: ActionContext) -> int:
        return max(8, min(12, context.max_steps // 2))

    def _evidence_tool_names(self, tools: list[Any]) -> set[str]:
        return {
            str(getattr(tool, "name", ""))
            for tool in tools
            if getattr(tool, "name", None)
            and getattr(tool, "name", None) != "final_answer"
        }

    def _has_completed_evidence_observation(
        self,
        agent: Any,
        evidence_tool_names: set[str],
    ) -> bool:
        for step in getattr(getattr(agent, "memory", None), "steps", []):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "").strip()
            if not observations or observations == "No observations":
                continue
            for call in getattr(step, "tool_calls", []) or []:
                if getattr(call, "name", None) in evidence_tool_names:
                    return True
        return False

    def _install_read_only_evidence_gate(
        self,
        agent: Any,
        evidence_tool_names: set[str],
    ) -> None:
        if not evidence_tool_names:
            return

        original_step = agent.step
        original_provide_final_answer = agent.provide_final_answer

        def gated_step(memory_step: ActionStep):
            final_answer = original_step(memory_step)
            if final_answer is None:
                return None
            if self._has_completed_evidence_observation(agent, evidence_tool_names):
                return final_answer

            memory_step.observations = (
                "Evidence gate blocked premature final_answer: this read-only solver "
                "has non-final evidence tools available but has not completed any "
                "evidence-tool observation yet. Call one relevant evidence tool first, "
                "then finalize from the observation."
            )
            return None

        def gated_provide_final_answer(task: str):
            if self._has_completed_evidence_observation(agent, evidence_tool_names):
                return original_provide_final_answer(task)
            return (
                "",
                "Evidence gate: no completed non-final evidence-tool observation.",
                (
                    "ANSWER: UNKNOWN; EVIDENCE: no completed evidence-tool "
                    "observation; UNCERTAINTY: solver stopped before using the "
                    "available read-only tools."
                ),
            )

        agent.step = gated_step
        agent.provide_final_answer = gated_provide_final_answer
        setattr(
            agent,
            "read_only_evidence_gate",
            {
                "required_before_final": True,
                "evidence_tools": sorted(evidence_tool_names),
            },
        )

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = context.planning_system or self.PROMPTS_TYPE
        self.route_name = schema_route_name(tools)
        self.use_debate = is_read_only_tool_schema(tools)
        if not self.use_debate:
            return

        guarded_read_tools = guard_task_tools(
            tools,
            policy_label="router_debate_read_only_solver",
            max_real_tool_calls=self._solver_max_steps(context),
        )
        solver_max_steps = self._solver_max_steps(context)
        self.solver_a = self.create_subagent(
            context,
            tools=guarded_read_tools,
            planning_system=self.organization_planning_system,
            prompt_templates=self.prompt_templates["solver_a"],
            name="solver_a",
            description=(
                "Independent read-only solver A. It should solve directly and report evidence."
            ),
            max_steps=solver_max_steps,
            summary_interval=context.max_steps + 1,
        )
        self.solver_b = self.create_subagent(
            context,
            tools=guarded_read_tools,
            planning_system=self.organization_planning_system,
            prompt_templates=self.prompt_templates["solver_b"],
            name="solver_b",
            description=(
                "Independent read-only solver B. It should use a different route when possible."
            ),
            max_steps=solver_max_steps,
            summary_interval=context.max_steps + 1,
        )
        evidence_tool_names = self._evidence_tool_names(guarded_read_tools)
        self.evidence_tool_names = evidence_tool_names
        self._install_read_only_evidence_gate(self.solver_a, evidence_tool_names)
        self._install_read_only_evidence_gate(self.solver_b, evidence_tool_names)

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        if self.use_debate:
            solver_tools = [
                EvidenceReportingSubAgentTool(
                    name=solver.name,
                    agent=solver,
                    description=(
                        f"{solver.name}: independent solver for read-only tool-schema tasks."
                    ),
                    max_steps=self._solver_max_steps(context),
                    include_parent_task=True,
                    evidence_tool_names=self.evidence_tool_names,
                    role_instructions=(
                        "- Solve the assigned read-only task independently.\n"
                        "- If non-final evidence tools are available, complete at least "
                        "one relevant evidence-tool call before final_answer.\n"
                        "- Do not answer from parametric memory when an evidence tool can "
                        "verify the answer.\n"
                        "- Use only valid tool schemas.\n"
                        "- Return a concise report with answer, evidence, and uncertainty.\n"
                        "- Do not assume stateful authority; this route is enabled only by read-only tool schemas."
                    ),
                )
                for solver in (self.solver_a, self.solver_b)
            ]
            guarded_solver_tools = guard_task_tools(
                solver_tools,
                policy_label="router_debate_judge",
                max_real_tool_calls=2,
            )
            agent = self.create_agent(
                context,
                tools=self.normalize_tools(guarded_solver_tools),
                prompt_templates=self.prompt_templates,
                prompts_type=self.prompts_type,
                planning_system=self.organization_planning_system,
            )
            agent.summary_interval = context.max_steps + 1
            for solver_tool in solver_tools:
                solver_tool.coordinator = agent
            for solver_tool in guarded_solver_tools:
                solver_tool.coordinator = agent
            agent.managed_agents = {
                solver.name: solver for solver in (self.solver_a, self.solver_b)
            }
            setattr(
                agent,
                "harness_policy",
                {
                    "mode": "router_debate_read_only",
                    "route": self.route_name,
                    "solvers": ["solver_a", "solver_b"],
                    "judge": "root_agent",
                },
            )
            return agent

        guarded_tools = guard_task_tools(
            tools,
            policy_label="router_stateful_single_executor",
            max_real_tool_calls=self._stateful_tool_budget(context),
        )
        critic = ReflectionCriticTool(
            context=context,
            name="stateful_critic",
            description=(
                "Non-environment critic for stateful fallback. It checks tool validity, "
                "arguments, repeated failures, and stop conditions without touching state."
            ),
        )
        root_tools = self.normalize_tools([*guarded_tools, critic])
        stateful_templates = self.prompt_templates.get("stateful", self.prompt_templates)
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=stateful_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        critic.bind_agent(agent, root_tools)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_STATEFUL_SUMMARY_INTERVAL
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "router_stateful_single_executor_critic",
                "route": self.route_name,
                "critic_tool": critic.name,
                "real_tool_budget": self._stateful_tool_budget(context),
            },
        )
        return agent


ACTION_SYSTEM = "router_debate"
ACTION_MODULE = "router_debate"


ParallelAgentsActionProvider = ActionProvider


def get_provider():
    return ActionProvider()


__all__ = [
    "ACTION_SYSTEM",
    "ACTION_MODULE",
    "ActionProvider",
    "get_provider",
    "ParallelAgentsActionProvider",
]
<<<END_FILE>>>
<<<FILE:memory_module/provider.py>>>
from __future__ import annotations

import io
import os
import json
import uuid
import time
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None
from module_memory.providers.model_loader import load_sentence_transformer

from module_memory.base_memory import BaseMemoryProvider, atomic_write_json, atomic_write_text, file_lock
from module_memory.memory_types import (
    MemoryStatus,
    MemoryType,
    MemoryRequest,
    MemoryResponse,
    MemoryItem,
    MemoryItemType,
    TrajectoryData,
)

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: str, content: str) -> None:
    atomic_write_text(path, content if content is not None else "")


def _extract_tag(text: str, tag: str = "cheatsheet") -> str:
    import re
    m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE)
    return (m.group(1).strip() if m else text).strip()


def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                         cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    return load_sentence_transformer(
        model_name=model_name,
        cache_dir=cache_dir,
        allow_unavailable=SentenceTransformer is None,
    )


class MemoryProvider(BaseMemoryProvider):

    def __init__(self, config: Optional[dict] = None):
        if config is None:
            raise ValueError("DynamicCheatsheetProvider requires an explicit config dict.")
        super().__init__(memory_type=MemoryType.DYNAMIC_CHEATSHEET, config=config)
        cfg = self.config

        self.store_path: str = cfg.get("store_path", "./dynamic_cheatsheet")
        self.records_file: str = cfg.get("records_file", "dynamic_cheatsheet.json")
        self.cheatsheet_file: str = cfg.get("cheatsheet_file", "global_cheatsheet.txt")

        self.records_path: str = os.path.join(self.store_path, self.records_file)
        self.cheatsheet_path: str = os.path.join(self.store_path, self.cheatsheet_file)

        self.top_k: int = int(cfg.get("top_k", 1))

        self.model = cfg.get("model")
        self.embedding_model_name = cfg.get("embedding_model", 'sentence-transformers/all-MiniLM-L6-v2')
        self.embedding_cache_dir = cfg.get("embedding_cache_dir", './storage/models')

        self.embedding_model = None
        self._records: List[Dict[str, Any]] = []
        self._embs: Optional[np.ndarray] = None

    @staticmethod
    def _token_overlap_score(query: str, candidate: str) -> float:
        query_tokens = {token for token in query.lower().split() if token}
        candidate_tokens = {token for token in candidate.lower().split() if token}
        if not query_tokens or not candidate_tokens:
            return 0.0
        return len(query_tokens & candidate_tokens) / len(query_tokens)

    def _load_memories_from_json(self):
        if os.path.exists(self.records_path):
            try:
                with open(self.records_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._records = data.get('memories', [])
                    embeddings_list = data.get('embeddings', [])

                    if embeddings_list:
                        self._embs = np.array(embeddings_list, dtype=np.float32)
                        print(f"Loaded {len(self._records)} memories and embeddings from {self.records_path}")
                    else:
                        self._embs = None
                        print(f"Loaded {len(self._records)} memories from {self.records_path} (no embeddings found).")

            except json.JSONDecodeError:
                print(f"Warning: Could not parse {self.records_path}. Starting with empty memory.", file=sys.stderr)
                self._records = []
                self._embs = None
            except Exception as e:
                print(f"Error loading memories: {e}. Starting fresh.", file=sys.stderr)
                self._records = []
                self._embs = None
        else:
            print("No memory file found. Starting with empty memory.")
            self._records = []
            self._embs = None

    def _save_memories_to_json(self):
        try:
            db_dir = os.path.dirname(self.records_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            embeddings_list = []
            if self._embs is not None and self._embs.size > 0:
                embeddings_list = self._embs.tolist()

            data = {
                'memories': self._records,
                'embeddings': embeddings_list
            }

            atomic_write_json(self.records_path, data, indent=4)

        except Exception as e:
            print(f"Error saving memories to {self.records_path}: {e}", file=sys.stderr)

    def initialize(self) -> bool:
        _ensure_dir(self.store_path)

        self.embedding_model = load_embedding_model(
            model_name=self.embedding_model_name,
            cache_dir=self.embedding_cache_dir
        )

        self._load_memories_from_json()

        if not os.path.exists(self.cheatsheet_path):
            _write_text(self.cheatsheet_path, "")

        return True

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts or self.embedding_model is None:
            return np.array([])
        vecs = self.embedding_model.encode(texts, convert_to_numpy=True)
        return vecs.astype(np.float32)

    def _chat_complete(self, prompt: str) -> str:
        if self.model is None:
            print("[WARN] No LLM model available for DynamicCheatsheetProvider.", file=sys.stderr)
            return ""
        try:
            resp = self.model([{"role": "user", "content": prompt}])
            content = getattr(resp, "content", str(resp))
            return str(content).strip()
        except Exception as e:
            print(f"[ERROR] LLM generation failed: {e}", file=sys.stderr)
            return ""

    def _reconstruct_trajectory_string(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return "No execution trajectory available"

        trajectory_parts = []
        trajectory_parts.append(f"Task: {trajectory_data.query}")
        trajectory_parts.append("")

        for i, step in enumerate(trajectory_data.trajectory, 1):
            step_type = step.get('type', 'step')
            content = step.get('content', '')
            trajectory_parts.append(f"Step {i} ({step_type}): {content}")

        if trajectory_data.result:
            trajectory_parts.append("")
            trajectory_parts.append(f"Final Result: {trajectory_data.result}")

        return "\n".join(trajectory_parts)

    def _summarize_trajectory_with_llm(self, trajectory_data: TrajectoryData) -> str:
        current_trajectory = self._reconstruct_trajectory_string(trajectory_data)
        if self.model is None:
            print("No LLM model provided for summarization. Falling back to full text.", file=sys.stderr)
            return current_trajectory

        is_correct = trajectory_data.metadata.get("is_correct", False)

        system_prompt = f"""Summarize this agent task execution trajectory step by step.

        Question: {trajectory_data.query}
        Final Result: {trajectory_data.result}
        Correctness: {'Correct' if is_correct else 'Wrong'}
        Trajectory: {current_trajectory}

        IMPORTANT: Provide a step-by-step summary in this format:

        Step 0: [Brief description of what happened in step 0, including memory guidance if any]
        Step 1: [Brief description of what happened in step 1, including tool calls and key observations]
        Step 2: [Brief description of what happened in step 2]
        ...

        After the step-by-step summary, add a brief conclusion about:
        - Overall approach taken
        - Whether memory guidance was effective
        - Why the task succeeded or failed

        Use actual step indices (0, 1, 2, ...) that match the trajectory array indices.
        Keep each step description to 1-2 sentences.
        Total length should be under 400 words."""

        try:
            resp = self.model([{"role": "user", "content": [{"type": "text", "text": system_prompt}]}])
            summary = getattr(resp, "content", str(resp)).strip()
            return summary if summary else current_trajectory
        except Exception as e:
            print(f"Error during trajectory summarization: {e}", file=sys.stderr)
            return current_trajectory

    def _search(self, qvec: np.ndarray, top_k: int) -> Tuple[List[int], List[float]]:
        if self._embs is None or self._embs.size == 0:
            return [], []
        if len(qvec.shape) == 1:
            qvec = qvec.reshape(1, -1)

        sims = cosine_similarity(qvec, self._embs)[0]
        idxs = np.argsort(-sims)[:top_k].tolist()
        scores = [float(sims[i]) for i in idxs]
        return idxs, scores

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status == MemoryStatus.IN:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4()))

        top_k = self.top_k
        query_text = (request.query or "").strip()
        selected: List[Dict[str, Any]] = []

        qvecs = self._embed_texts([query_text])
        if qvecs.size > 0:
            idxs, scores = self._search(qvecs[0], top_k=top_k)
            for i, sc in zip(idxs, scores):
                rec = dict(self._records[i])
                rec["_score"] = float(sc)
                selected.append(rec)
        elif self._records:
            ranked = sorted(
                (
                    (idx, self._token_overlap_score(query_text, rec.get("question", "")))
                    for idx, rec in enumerate(self._records)
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            for idx, score in ranked[:top_k]:
                if score <= 0:
                    continue
                rec = dict(self._records[idx])
                rec["_score"] = float(score)
                selected.append(rec)

        if not selected:
            existing_cs = _read_text(self.cheatsheet_path).strip()

            return MemoryResponse(
                memories=[MemoryItem(
                    id=str(uuid.uuid4()),
                    content=existing_cs,
                    metadata={
                        "kind": "dynamic_cheatsheet",
                        "selected_count": 0,
                        "generation_skipped": True
                    },
                    type=MemoryItemType.TEXT,
                    score=0.0,
                )],
                memory_type=self.memory_type,
                total_count=1,
                request_id=str(uuid.uuid4()),
            )

        best = selected[0]
        traj_summary = best.get("trajectory_summary", "")

        trajectory_context = (
            f"Similarity: {best.get('_score'):.2f}\n"
            f"Content:\n{traj_summary}"
        )

        prev_cs = _read_text(self.cheatsheet_path).strip() or "(empty)"

        curator_prompt = (
f"""You are a "dynamic cheatsheet" curator.

Using the [previous cheatsheet] and ONE [similar query–trajectory], synthesize a concise, reusable cheatsheet for the CURRENT QUERY.

Guidelines:
- Extract only transferable heuristics, steps, checklists, and typical pitfalls.
- Capture process-level insights from the condensed trajectory.
- Stay domain-agnostic where possible.
- Prefer bullet points and micro-templates like “When X, first … then …”.
- **STRICT LIMIT: The cheatsheet MUST be under 200 words.**

Output ONLY the cheatsheet, wrapped in a single <cheatsheet>...</cheatsheet> block.

[Previous cheatsheet]
{prev_cs}

[Similar query–trajectory (Condensed)]
{trajectory_context}

[Current query]
{query_text}
"""
        )

        raw_response = self._chat_complete(curator_prompt)
        new_cheatsheet = _extract_tag(raw_response, "cheatsheet")

        if new_cheatsheet:
            with file_lock(self.cheatsheet_path):
                _write_text(self.cheatsheet_path, new_cheatsheet)

        return MemoryResponse(
            memories=[MemoryItem(
                id=str(uuid.uuid4()),
                content=new_cheatsheet,
                metadata={"kind": "dynamic_cheatsheet", "selected_count": len(selected)},
                type=MemoryItemType.TEXT,
                score=1.0,
            )],
            memory_type=self.memory_type,
            total_count=1,
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        q = (trajectory_data.query or "").strip()
        if not q:
            raise ValueError("TrajectoryData.query must be non-empty.")

        summary_text = self._summarize_trajectory_with_llm(trajectory_data)

        rid = str(uuid.uuid4())

        rec = {
            "id": rid,
            "question": q,
            "trajectory_summary": summary_text,
            "meta": trajectory_data.metadata or {},
            "ts": int(time.time())
        }

        q_embs = self._embed_texts([q])
        with file_lock(self.records_path):
            self._load_memories_from_json()
            self._records.append(rec)
            if q_embs.size > 0:
                q_emb = q_embs[0]
                if self._embs is None:
                    self._embs = q_emb.reshape(1, -1)
                else:
                    self._embs = np.vstack([self._embs, q_emb])

            self._save_memories_to_json()

        return True, f"ingested sample: id={rid}"


DynamicCheatsheetProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.DYNAMIC_CHEATSHEET.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "DynamicCheatsheetProvider"]
<<<END_FILE>>>
<<<FILE:planning_module/prompts/toolcalling_agent.yaml>>>
planning:
  initial_plan: |-
    You are planning for a router + debate harness.

    Requirements:
    1. If the exposed tool schemas appear read-only, plan one debate round: solver A direct path, solver B alternate/verification path, judge final.
    2. If any exposed tool schema appears state-changing or unknown, plan a single executor with critic; no debate.
    3. Keep the plan to at most 4 bullets.
    4. Include a stop condition.
    5. Do not solve the task here.

    Output format:
    - route:
    - solver_or_executor_plan:
    - judge_or_critic_check:
    - stop_condition:
  task_input: |-
    Task:
    {{task}}
summary:
  update_pre_messages: |-
    Review router progress. For read-only debate, compare solver reports. For stateful fallback, check single-executor progress and critic feedback.
  update_post_messages: |-
    Write a brief progress review for task {{task}} at step {{step}}.
    Include:
    - route_used
    - evidence_collected
    - disagreement_or_failure
    - next_safe_move
    - ready_for_final_answer
<<<END_FILE>>>
<<<FILE:action_module/prompts/toolcalling_agent.yaml>>>
system_prompt: |-
  You are the judge in a router + debate harness.

  This prompt is used only when the exposed tool schemas appear read-only.
  Your job is to call solver_a and solver_b independently, compare their reports, and choose the best supported final answer.

  Rules:
  1. Call solver_a and solver_b once, preferably in the same step.
  2. Do not call real environment tools yourself.
  3. Compare answer agreement, evidence, and obvious schema failures. Prefer reports backed by concrete tool observations over reports based only on prior knowledge.
  4. If one solver failed and the other has supported evidence, use the supported answer.
  5. If a solver's stated answer conflicts with its evidence observations, trust the evidence observations over the stated answer.
  6. If both solvers report no evidence-tool observation, treat the debate as failed rather than inventing an answer.
  7. Do not run debate when any exposed tool schema appears state-changing or unknown.
  8. Return strict JSON only.
  9. The final answer must be the raw answer string only. No evidence, labels, markdown, or uncertainty text in the final answer field.

  ### Tools
  {%- for tool in tools.values() %}
  - {{ tool.name }}: {{ tool.description }}
  {%- endfor %}
step:
  pre_messages: |-
    [ROUTER + DEBATE PROTOCOL]
    1. If solver_a and solver_b have not both been called, call both with the full read-only task.
    2. Once both reports are available, judge them by completed tool evidence first, then answer consistency.
    3. After both reports are available, call final_answer immediately with the raw answer only.
    4. If a solver hit schema/repetition/evidence-gate failure, do not copy the failure; rely on the other solver only if it has concrete observed evidence.
    5. If the report answer and evidence observations disagree, final_answer should follow the evidence observations.

    Return JSON only:
    {
      "think": "brief reasoning",
      "tools": [
        {
          "name": "solver_a | solver_b | final_answer",
          "arguments": {}
        }
      ]
    }

    Tool Definitions:
    {{tool_functions_json}}

    Task: {{task}}
final_answer:
  pre_messages: The judge has enough solver evidence to finalize the read-only task. Return only the raw answer requested by the task.
  post_messages: |-
    Return JSON:
    {"think": "...", "answer": "..."}

    The `answer` field should contain only the final answer requested by the task. Do not include evidence, labels, or explanation.
    Task: {{task}}
worker:
  system_prompt: |-
    You are a generic agent in a lightweight direct-parallel team.
    You solve the current task independently and return a concise, evidence-backed report.

    Rules:
    - Start with a very short internal plan, then execute it directly.
    - Treat the assigned task as your full objective for this run.
    - Use only the currently available tools.
    - Prefer concrete evidence and decisive progress.
    - Finish in as few steps as possible.
    - Read the tool schemas carefully and use only the listed argument names and types.
    - If a tool call fails because of invalid arguments or schema mismatch, repair the arguments on the next attempt instead of repeating the same failed call.
    - Never repeat an identical failed call unless the observation explicitly justifies it.
    - Base your report only on observations; do not replace a supported observed result with a new guess.
    - Return exactly one JSON object:
      {"think": "...", "tools": [{"name": "...", "arguments": {...}}]}

    ### Tools
    {%- for tool in tools.values() %}
    - {{ tool.name }}: {{ tool.description }}
        Inputs: {{ tool.inputs }}
        Output: {{ tool.output_type }}
    {%- endfor %}
  step:
    pre_messages: |-
      You are one direct-parallel agent.
      Solve the assigned task independently and prepare a concise evidence-backed report.
      Keep your plan and execution short.
      If progress is weak, change the tool choice, arguments, or strategy instead of retrying blindly.
      Return JSON only.
  final_answer:
    pre_messages: Finalize the parallel-agent report.
    post_messages: |-
      Return JSON:
      {"think": "...", "answer": "..."}

      The answer should include:
      - task outcome
      - key evidence
      - candidate result if available
      - remaining uncertainty if any

solver_a:
  system_prompt: |-
    You are solver A in a read-only debate. Use the available tools directly, follow schemas exactly, and return the shortest supported answer with evidence.
    Prefer a direct evidence path. Do not invent tools or arguments.
    If any non-final evidence tool is available, your first completed action must be a relevant evidence-tool call, not final_answer.
    Do not answer from parametric memory when an available tool can verify the answer.

    ### Tools
    {%- for tool in tools.values() %}
    - {{ tool.name }}: {{ tool.description }}
        Inputs: {{ tool.inputs }}
        Output: {{ tool.output_type }}
    {%- endfor %}
  step:
    pre_messages: |-
      Solve the assigned read-only task independently. If you have not yet observed a non-final evidence tool result, call one relevant evidence tool first. If a tool fails, repair arguments or switch strategy. Once a completed observation supports a candidate, call final_answer. Return JSON only.
      Task: {{task}}
  final_answer:
    pre_messages: Finalize solver A report.
    post_messages: |-
      Return JSON:
      {"think": "...", "answer": "ANSWER: <raw answer>; EVIDENCE: <brief evidence>"}

solver_b:
  system_prompt: |-
    You are solver B in a read-only debate. Use a different route or verification angle when possible, follow schemas exactly, and return the shortest supported answer with evidence.
    Prefer cross-checking or an alternate decomposition. Do not invent tools or arguments.
    If any non-final evidence tool is available, your first completed action must be a relevant evidence-tool call, not final_answer.
    Do not answer from parametric memory when an available tool can verify the answer.

    ### Tools
    {%- for tool in tools.values() %}
    - {{ tool.name }}: {{ tool.description }}
        Inputs: {{ tool.inputs }}
        Output: {{ tool.output_type }}
    {%- endfor %}
  step:
    pre_messages: |-
      Solve the assigned read-only task independently with an alternate angle when possible. If you have not yet observed a non-final evidence tool result, call one relevant evidence tool first. If a tool fails, repair arguments or switch strategy. Once a completed observation supports a candidate, call final_answer. Return JSON only.
      Task: {{task}}
  final_answer:
    pre_messages: Finalize solver B report.
    post_messages: |-
      Return JSON:
      {"think": "...", "answer": "ANSWER: <raw answer>; EVIDENCE: <brief evidence>"}

stateful:
  system_prompt: |-
    You are the stateful fallback for router_debate.
    Because the exposed tool schema may mutate environment state or is unknown, do not debate with multiple solvers.
    Use one executor path plus stateful_critic.

    Rules:
    - Use only provided real tools and schemas.
    - Prefer one state-changing call per step.
    - Never repeat an identical failed call.
    - Call stateful_critic only after a suspicious failure pattern or before a risky final_answer.
    - If the task has a terminal completion tool, use it only after required state changes are done.
    - If complete_task/task_completed exists and all required state changes are done, call it directly instead of final_answer.
  step:
    pre_messages: |-
      Stateful fallback loop.

      Tool schemas:
      {{tool_functions_json}}

      Task:
      {{task}}

      Choose one valid next tool. If ready to stop and a terminal completion tool exists, call it directly. For QA final_answer, use the raw answer only.
      Return JSON only:
      {"think": "...", "tools": [{"name": "...", "arguments": {...}}]}
  final_answer:
    pre_messages: Finalize with the raw requested answer only. Prefer a terminal completion tool over final_answer for completed state-change tasks.
    post_messages: |-
      Return JSON:
      {"think": "...", "answer": "..."}
      Task: {{task}}
<<<END_FILE>>>
