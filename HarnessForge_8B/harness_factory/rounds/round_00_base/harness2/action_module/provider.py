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
