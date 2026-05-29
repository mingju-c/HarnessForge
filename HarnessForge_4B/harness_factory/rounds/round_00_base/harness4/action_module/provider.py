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
