from __future__ import annotations

from typing import Any

from module_action.base_action import ActionContext, BaseActionProvider
from module_action.tools import load_bench_tools


class ActionProvider(BaseActionProvider):
    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return load_bench_tools(
            bench_type,
            db_path=context.db_path,
            context=context,
        )

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

ACTION_SYSTEM = 'single_react'
ACTION_MODULE = 'single_react'

SingleReactActionProvider = ActionProvider

def get_provider():
    return ActionProvider()

__all__ = ['ACTION_SYSTEM', 'ACTION_MODULE', 'ActionProvider', 'get_provider', 'SingleReactActionProvider']
