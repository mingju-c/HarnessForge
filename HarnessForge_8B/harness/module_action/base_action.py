from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

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


class BaseActionProvider:
    def __init__(self) -> None:
        self.reset_state()

    def reset_state(self) -> None:
        self.prompt_templates: Any = None
        self.prompts_type: str | None = None
        self.organization_planning_system: str | None = None

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
            prompt_templates=prompt_templates,
            memory_provider=context.memory_provider,
            project_root=context.project_root,
            **kwargs,
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
