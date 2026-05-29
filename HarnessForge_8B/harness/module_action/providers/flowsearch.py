from __future__ import annotations

from typing import Any

from module_action.base_action import ActionContext, BaseActionProvider


class FlowsearchActionProvider(BaseActionProvider):
    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return [context.executor_tool, context.refine_tool]

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.resolve_prompts_type(context)
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = context.planning_system
        self.task_tools = self.get_task_tool_map(context, include_reasoning=True)

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
        agent.tools.update(self.task_tools)
        return agent
