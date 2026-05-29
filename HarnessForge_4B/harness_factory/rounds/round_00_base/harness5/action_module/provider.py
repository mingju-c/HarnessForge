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

