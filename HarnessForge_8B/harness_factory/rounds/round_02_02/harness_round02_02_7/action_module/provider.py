from __future__ import annotations

from typing import Any

from Agents.models import MessageRole
from Agents.tools import Tool
from _harness_guards import guard_task_tools
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = "round02_02_verifier_contract_react"
ACTION_MODULE = ACTION_SYSTEM


class VerifierContractTool(Tool):
    name = "verifier_contract_check"
    description = "Rare non-environment verifier whose output must become a next-action constraint or finalization block."
    inputs = {
        "draft": {"type": "string", "description": "Candidate next action, status update, answer, or completion claim to inspect."}
    }
    output_type = "string"

    def __init__(self, *, context: ActionContext):
        self.model = context.model
        self.agent = None
        self.allowed_tool_names: list[str] = []
        self._last_draft: str | None = None
        self._throttle_exact_repeats = True
        super().__init__()

    def bind_agent(self, agent: Any, tools: list[Any] | None = None) -> None:
        self.agent = agent
        if tools is not None:
            self.allowed_tool_names = [
                getattr(tool, "name", "")
                for tool in tools
                if getattr(tool, "name", "") and getattr(tool, "name", "") != self.name
            ]

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
        cleaned = str(draft or "").strip()
        if self._throttle_exact_repeats and cleaned and cleaned == self._last_draft:
            return (
                "verdict: throttle\n"
                "evidence: this verifier was called on the same draft without new evidence\n"
                "missing_or_risk: checker loop risk\n"
                "next_safe_move: take a real schema-listed action, finalize from observed evidence, or state evidence-backed impossibility"
            )
        self._last_draft = cleaned
        prompt = (
            "You are a rare non-environment verifier. Audit only terminal readiness, repeated failure repair, candidate support, or raw final form. Your output must name one concrete next_action_constraint or say no_blocker."
            + "\n\nAllowed non-checker tools: " + str(self.allowed_tool_names)
            + "\n\nRecent trajectory:\n" + self._recent_history()
            + "\n\nDraft to inspect:\n" + cleaned
            + "\n\nReturn concise text with fields: verdict, evidence, missing_or_risk, next_safe_move."
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
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = context.planning_system


    def build_organization(self, context: ActionContext, tools: list[Any]):
        guarded_tools = guard_task_tools(tools, policy_label="round02_02_verifier_contract")
        checker = VerifierContractTool(context=context)
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
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "verifier_contract_single_executor",
                "checker_tool": checker.name,
                "policy_label": "round02_02_verifier_contract",
                "focus": ['rare_action_binding_verifier', 'checker_loop_throttle', 'next_action_constraints'],

            },
        )
        return agent


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
