from __future__ import annotations

from typing import Any

from _harness_guards import ReflectionCriticTool, guard_task_tools, is_read_only_tool_schema, schema_route_name
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = "round01_mutability_react"
ACTION_MODULE = ACTION_SYSTEM


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    DEFAULT_SUMMARY_INTERVAL = 8

    def build_affordance(self, bench_type: str | None, context: ActionContext) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(self, context: ActionContext, tools: list[Any]) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = context.planning_system
        self.use_read_only_mode = is_read_only_tool_schema(tools)
        self.route_name = schema_route_name(tools)

    def build_organization(self, context: ActionContext, tools: list[Any]):
        guarded_tools = guard_task_tools(tools, policy_label=f"round01_{{self.route_name}}")
        critic = ReflectionCriticTool(
            context=context,
            name="route_critic",
            description=(
                "Non-environment route critic. It checks whether the current tool pattern "
                "should be treated as read-only evidence gathering or sequential mutable commit."
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
        agent.max_tool_calls_per_step = 2
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "mutability_aware_single_executor",
                "route": self.route_name,
                "read_only_mode": self.use_read_only_mode,
                "max_tool_calls_per_step": agent.max_tool_calls_per_step,
                "critic_tool": critic.name,
            },
        )
        return agent


ACTION_SYSTEM = "round01_mutability_react"
ACTION_MODULE = ACTION_SYSTEM


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
