from __future__ import annotations

from typing import Any

from Agents.models import MessageRole
from Agents.tools import Tool
from _harness_guards import guard_task_tools
from module_action.base_action import ActionContext, BaseActionProvider
from ..._regression_guidance import apply_round02_01_regression_fixes


ACTION_SYSTEM = "round02_01_raw_answer_react"
ACTION_MODULE = ACTION_SYSTEM


class RawAnswerBindingTool(Tool):
    name = "raw_answer_check"
    description = "Non-environment checker for exact final answer binding to decisive raw observations."
    inputs = {
        "draft": {"type": "string", "description": "Candidate next action, answer, or completion claim to inspect."}
    }
    output_type = "string"

    def __init__(self, *, context: ActionContext):
        self.model = context.model
        self.agent = None
        super().__init__()

    def bind_agent(self, agent: Any) -> None:
        self.agent = agent

    def _recent_history(self) -> str:
        if self.agent is None:
            return ""
        try:
            messages = self.agent.write_memory_to_messages(include_system_prompt=False)
        except Exception:
            messages = []
        chunks = []
        for message in messages[-14:]:
            role = message.get("role", "")
            content = message.get("content", "")
            if isinstance(content, list):
                text = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
            else:
                text = str(content)
            if text:
                chunks.append(f"{role}: {text}")
        return "\n\n".join(chunks)[-8000:]

    def forward(self, draft: str) -> str:
        prompt = (
            'You are a non-environment raw answer checker. Verify that the draft answer is the requested answer type, is supported by the decisive observation, and copies raw fields such as result, output, answer, value, date, count, id, name, or string exactly when no transformation is requested.'
            f"\n\nRecent trajectory:\n{self._recent_history()}\n\n"
            f"Draft to inspect:\n{draft}\n\n"
            "Return concise text with fields: verdict, decisive_observation, raw_field_to_copy, next_safe_move."
        )
        try:
            response = self.model([
                {"role": MessageRole.USER, "content": [{"type": "text", "text": prompt}]}
            ])
            return str(getattr(response, "content", response)).strip()
        except Exception as exc:
            return (
                "verdict: caution\n"
                f"evidence: checker model failed: {exc}\n"
                "missing_or_risk: rely only on observed tool results\n"
                "next_safe_move: use a valid tool if evidence is missing, otherwise finalize from observations"
            )


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    DEFAULT_SUMMARY_INTERVAL = 8

    def build_affordance(self, bench_type: str | None, context: ActionContext) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(self, context: ActionContext, tools: list[Any]) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = apply_round02_01_regression_fixes(
            self.load_prompt_templates(context, self.prompts_type),
            checker_name="raw_answer_check",
        )
        self.organization_planning_system = context.planning_system

    def build_organization(self, context: ActionContext, tools: list[Any]):
        guarded_tools = guard_task_tools(tools, policy_label="round02_raw_answer")
        checker = RawAnswerBindingTool(context=context)
        root_tools = self.normalize_tools([*guarded_tools, checker])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        checker.bind_agent(agent)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_SUMMARY_INTERVAL
        if getattr(agent, "max_tool_calls_per_step", None) is None:
            agent.max_tool_calls_per_step = 2
        setattr(agent, "harness_policy", {"mode": "raw_answer_binding", "checker_tool": checker.name})
        return agent


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
