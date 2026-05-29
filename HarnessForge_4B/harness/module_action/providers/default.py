from __future__ import annotations

from typing import Any

from module_action.base_action import ActionContext, BaseActionProvider


class DefaultActionProvider(BaseActionProvider):
    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        primary_tools = self.get_primary_task_tools(context, include_reasoning=True)
        if getattr(context, "strict_bench_tools", False) and getattr(context, "bench_tools", None):
            return primary_tools
        return primary_tools + [
            context.vector_tool,
            context.process_tool,
            context.end_process_tool,
            context.delete_memory_tool,
        ]

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.resolve_prompts_type(context)
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
