from __future__ import annotations

from typing import Any

from _harness_guards import ReflectionCriticTool, guard_task_tools
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = "round01_ledger_react"
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

    def build_organization(self, context: ActionContext, tools: list[Any]):
        guarded_tools = guard_task_tools(tools, policy_label="round01_observation_ledger")
        checker = ReflectionCriticTool(
            context=context,
            name="ledger_preflight",
            description=(
                "Non-environment preflight checker. Use before final_answer or a terminal "
                "completion claim when there are multiple requirements; it checks observed "
                "successes, remaining work, schema validity, and repeated failures."
            ),
        )
        root_tools = self.normalize_tools([*guarded_tools, checker])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        checker.bind_agent(agent, root_tools)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_SUMMARY_INTERVAL
        if getattr(agent, "max_tool_calls_per_step", None) is None:
            agent.max_tool_calls_per_step = 2
        setattr(agent, "harness_policy", {"mode": "observation_ledger", "preflight_tool": checker.name})
        return agent


ACTION_SYSTEM = "round01_ledger_react"
ACTION_MODULE = ACTION_SYSTEM


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
