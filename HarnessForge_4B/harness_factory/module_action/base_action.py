from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from Agents.tools import Tool
from Agents.utils import make_json_serializable

if TYPE_CHECKING:
    from Agents.agents import ToolCallingAgent


@dataclass
class ActionContext:
    model: Any
    summary_interval: int | None
    prompts_type: str | None
    max_steps: int
    planning_system: str
    action_system: str
    memory_provider: Any = None
    project_root: Path | None = None
    bench_type: str | None = None
    db_path: str | None = None
    kwargs: dict[str, Any] = field(default_factory=dict)
    bench_tools: list[Any] = field(default_factory=list)
    strict_bench_tools: bool = False
    toolhop_sample: dict[str, Any] | None = None
    toolhop_mode: str | None = None
    toolhop_functions: list[str] = field(default_factory=list)
    toolhop_tool_specs: list[dict[str, Any]] = field(default_factory=list)
    web_tool: Any = None
    crawl_tool: Any = None
    vector_tool: Any = None
    reasoning_tool: Any = None
    process_tool: Any = None
    end_process_tool: Any = None
    delete_memory_tool: Any = None
    expert_parallel_tool: Any = None
    camv_tool: Any = None
    executor_tool: Any = None
    refine_tool: Any = None


class ActionProvider(Protocol):
    def build(self, context: ActionContext) -> "ToolCallingAgent":
        ...


def _format_subagent_result(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    serializable = make_json_serializable(result)
    if isinstance(serializable, (dict, list)):
        try:
            return json.dumps(serializable, ensure_ascii=False)
        except Exception:
            return str(serializable).strip()
    return str(serializable).strip()


def _serialize_subagent_memory(agent: "ToolCallingAgent") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in getattr(getattr(agent, "memory", None), "steps", []):
        if hasattr(step, "dict"):
            rows.append(step.dict())
        else:
            rows.append({"repr": str(step)})
    return rows


def _capture_subagent_trajectory(agent: "ToolCallingAgent") -> list[dict[str, Any]]:
    from Agents.memory import ActionStep, PlanningStep, SummaryStep, TaskStep

    trajectory: list[dict[str, Any]] = []
    for step in getattr(getattr(agent, "memory", None), "steps", []):
        if isinstance(step, TaskStep):
            continue
        if isinstance(step, PlanningStep):
            trajectory.append(
                {
                    "name": "plan",
                    "value": step.plan,
                    "think": step.plan_think,
                    "cot_think": step.plan_reasoning,
                    "memory_guidance": getattr(step, "memory_guidance", None),
                }
            )
            continue
        if isinstance(step, SummaryStep):
            trajectory.append(
                {
                    "name": "summary",
                    "value": step.summary,
                    "cot_think": step.summary_reasoning,
                }
            )
            continue
        if isinstance(step, ActionStep):
            safe_tool_calls = step.tool_calls if step.tool_calls is not None else []
            trajectory.append(
                {
                    "name": "action",
                    "tool_calls": [tool_call.dict() for tool_call in safe_tool_calls],
                    "obs": step.observations,
                    "think": step.action_think,
                    "cot_think": step.action_reasoning,
                    "memory_guidance": getattr(step, "memory_guidance", None),
                    "subagent_trajectories": getattr(step, "subagent_trajectories", None),
                }
            )
            continue
        trajectory.append({"name": type(step).__name__, "value": str(step)})
    return trajectory


def _build_subagent_payload(
    *,
    worker_name: str,
    assigned_task: str,
    assignment_text: str,
    agent: "ToolCallingAgent",
    result: Any = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    report_body = (
        _format_subagent_result(result) if error is None else f"Error: {error}"
    )
    return {
        "worker_name": worker_name,
        "assigned_task": assigned_task.strip(),
        "assignment_text": assignment_text,
        "agent_result": make_json_serializable(result),
        "error": None if error is None else str(error),
        "report": f"{worker_name} report:\n{report_body}",
        "agent_trajectory": _capture_subagent_trajectory(agent),
        "trajectory": _serialize_subagent_memory(agent),
    }


class SubAgentTool(Tool):
    output_type = "string"
    inputs = {
        "task": {
            "type": "string",
            "description": "Focused task or subtask for this sub-agent.",
        }
    }

    def __init__(
        self,
        *,
        name: str,
        description: str,
        agent: "ToolCallingAgent",
        max_steps: int | None = None,
        include_parent_task: bool = True,
        role_instructions: str | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.subagent = agent
        self.coordinator = None
        self.max_steps = max_steps
        self.include_parent_task = include_parent_task
        self.role_instructions = role_instructions or ""
        super().__init__()

    def forward(self, task: str) -> dict[str, Any]:
        assignment_parts = []
        coordinator_task = getattr(self.coordinator, "task", "")
        if self.include_parent_task and coordinator_task:
            assignment_parts.extend(
                [
                    "Original top-level task:",
                    str(coordinator_task).strip(),
                    "",
                ]
            )
        assignment_parts.extend(["Assigned task:", task.strip()])
        if self.role_instructions:
            assignment_parts.extend(
                ["", "Execution requirements:", self.role_instructions.strip()]
            )

        assignment_text = "\n".join(
            part for part in assignment_parts if part is not None
        )
        if self.max_steps is not None:
            self.subagent.max_steps = self.max_steps
        self.subagent.memory.reset()

        try:
            answer = self.subagent.run(assignment_text, reset=True)
            return _build_subagent_payload(
                worker_name=self.name,
                assigned_task=task,
                assignment_text=assignment_text,
                agent=self.subagent,
                result=answer,
            )
        except Exception as exc:
            return _build_subagent_payload(
                worker_name=self.name,
                assigned_task=task,
                assignment_text=assignment_text,
                agent=self.subagent,
                error=exc,
            )


class BaseActionProvider:
    def __init__(self) -> None:
        self.reset_state()

    def reset_state(self) -> None:
        self.prompt_templates: Any = None
        self.prompts_type: str | None = None
        self.organization_planning_system: str | None = None
        self._subagent_memory_provider: Any = None

    def resolve_prompts_type(self, context: ActionContext) -> str:
        return context.prompts_type or context.action_system or context.planning_system

    def load_prompt_templates(self, context: ActionContext, prompts_type: str) -> Any:
        from module_planning.registry import load_action_prompt_templates

        return load_action_prompt_templates(
            project_root=context.project_root,
            prompts_type=prompts_type,
        )

    def normalize_tools(self, tools: list[Any]) -> list[Any]:
        normalized: list[Any] = []
        seen_names: set[Any] = set()
        for tool in tools:
            if tool is None:
                continue
            tool_name = getattr(tool, "name", None) or id(tool)
            if tool_name in seen_names:
                continue
            seen_names.add(tool_name)
            normalized.append(tool)
        return normalized

    def get_primary_task_tools(
        self,
        context: ActionContext,
        *,
        include_reasoning: bool = True,
    ) -> list[Any]:
        from module_action.tools import load_bench_tools

        bench_tools = list(getattr(context, "bench_tools", None) or [])
        if not bench_tools:
            bench_tools = load_bench_tools(
                context.bench_type,
                db_path=context.db_path,
                context=context,
            )
        if bench_tools:
            tools = list(bench_tools)
        else:
            tools = [context.web_tool, context.crawl_tool]

        strict_bench = bool(getattr(context, "strict_bench_tools", False) and bench_tools)
        if include_reasoning and context.reasoning_tool is not None and not strict_bench:
            tools.append(context.reasoning_tool)

        return self.normalize_tools(tools)

    def get_task_tool_map(
        self,
        context: ActionContext,
        *,
        include_reasoning: bool = True,
    ) -> dict[str, Any]:
        return {
            getattr(tool, "name"): tool
            for tool in self.get_primary_task_tools(
                context,
                include_reasoning=include_reasoning,
            )
            if getattr(tool, "name", None)
        }

    def create_agent(
        self,
        context: ActionContext,
        *,
        tools: list[Any],
        prompt_templates: Any = None,
        prompts_type: str | None = None,
        planning_system: str | None = None,
        **kwargs: Any,
    ) -> "ToolCallingAgent":
        from Agents.agents import ToolCallingAgent

        return ToolCallingAgent(
            model=context.model,
            tools=tools,
            summary_interval=context.summary_interval,
            max_steps=context.max_steps,
            prompts_type=prompts_type or self.resolve_prompts_type(context),
            planning_system=planning_system or context.planning_system,
            planning_class=context.kwargs.get("planning_class"),
            max_tool_calls_per_step=context.kwargs.get("max_tool_calls_per_step"),
            prompt_templates=prompt_templates,
            memory_provider=context.memory_provider,
            project_root=context.project_root,
            **kwargs,
        )

    def get_subagent_memory_provider(self, context: ActionContext) -> Any:
        if context.memory_provider is None:
            return None
        if self._subagent_memory_provider is None:
            from module_memory.base_memory import ReadOnlyMemoryProvider

            self._subagent_memory_provider = ReadOnlyMemoryProvider(
                context.memory_provider
            )
        return self._subagent_memory_provider

    def create_subagent(
        self,
        context: ActionContext,
        *,
        tools: list[Any],
        prompt_templates: Any = None,
        prompts_type: str | None = None,
        planning_system: str | None = None,
        summary_interval: int | None = None,
        max_steps: int | None = None,
        planning_class: Any = None,
        **kwargs: Any,
    ) -> "ToolCallingAgent":
        from Agents.agents import ToolCallingAgent

        return ToolCallingAgent(
            model=context.model,
            tools=tools,
            summary_interval=(
                context.summary_interval if summary_interval is None else summary_interval
            ),
            max_steps=context.max_steps if max_steps is None else max_steps,
            prompts_type=prompts_type or self.resolve_prompts_type(context),
            planning_system=planning_system or context.planning_system,
            planning_class=(
                context.kwargs.get("planning_class")
                if planning_class is None
                else planning_class
            ),
            max_tool_calls_per_step=context.kwargs.get("max_tool_calls_per_step"),
            prompt_templates=prompt_templates,
            memory_provider=self.get_subagent_memory_provider(context),
            project_root=context.project_root,
            **kwargs,
        )

    def create_subagent_tool(
        self,
        *,
        agent: "ToolCallingAgent",
        description: str,
        max_steps: int | None = None,
        include_parent_task: bool = True,
        role_instructions: str | None = None,
    ) -> Tool:
        return SubAgentTool(
            name=agent.name,
            description=description,
            agent=agent,
            max_steps=max_steps,
            include_parent_task=include_parent_task,
            role_instructions=role_instructions,
        )

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        raise NotImplementedError

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        raise NotImplementedError

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> "ToolCallingAgent":
        raise NotImplementedError

    def build(self, context: ActionContext) -> "ToolCallingAgent":
        self.reset_state()
        tools = self.normalize_tools(self.build_affordance(context.bench_type, context))
        self.build_specification(context, tools)
        agent = self.build_organization(context, tools)
        if agent is None:
            raise ValueError(
                f"{self.__class__.__name__}.build_organization() must return a ToolCallingAgent."
            )
        return agent
