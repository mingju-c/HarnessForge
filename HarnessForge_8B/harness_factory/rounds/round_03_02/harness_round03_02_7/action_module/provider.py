from __future__ import annotations

import json
import threading
from typing import Any

from Agents.models import MessageRole
from Agents.tools import Tool
from _harness_guards import guard_task_tools, schema_route_name
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = 'round03_02_milestone_gate_react'
ACTION_MODULE = ACTION_SYSTEM
CONTRACT_NAME = 'MILESTONE_GATE_DIRECT'
CHECKER_PROMPT = 'You are a non-environment milestone gate checker. Verify that the proposed next action respects the current milestone: bind identifiers/evidence, act or transform only with observed inputs, verify postconditions or relation support, then finalize.'
CHECKER_RETURN_FIELDS = 'Return concise text with fields: verdict, current_gate, missing_requirement, next_safe_move.'


def _json_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _looks_failed(observation: Any) -> bool:
    if isinstance(observation, dict):
        if observation.get("success") is False or "error" in observation:
            return True
    text = str(observation).lower()
    markers = (
        '"success": false',
        "'success': false",
        "error",
        "unknown tool",
        "invalid",
        "not found",
        "does not exist",
        "permission denied",
        "access denied",
        "failed",
        "guard blocked",
        "schema advisory",
    )
    return any(marker in text for marker in markers)


class RouteChangeState:
    def __init__(self) -> None:
        self.failed_calls: dict[tuple[str, str], int] = {}
        self.lock = threading.Lock()


class RouteChangeGuardedTool(Tool):
    """Blocks a third identical failed real call so the executor must change route."""

    skip_forward_signature_validation = True

    def __init__(self, wrapped: Tool, state: RouteChangeState, *, policy_label: str, block_after: int = 2) -> None:
        self._wrapped = wrapped
        self._state = state
        self._block_after = block_after
        self.name = wrapped.name
        self.description = (
            str(wrapped.description)
            + (chr(10) * 2)
            + f"Route-change policy ({policy_label}): after the same tool+arguments fail twice, "
            "this wrapper returns a blocked observation instead of executing the same failed call again. "
            "Use a changed schema-listed tool, changed arguments, changed entity/ID binding, or finalize from existing evidence."
        )
        self.inputs = dict(getattr(wrapped, "inputs", {}) or {})
        self.output_type = getattr(wrapped, "output_type", "string")
        for attr in ("terminal_tool", "is_terminal_observation", "terminal_answer"):
            if hasattr(wrapped, attr):
                setattr(self, attr, getattr(wrapped, attr))
        super().__init__()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def forward(self, **kwargs: Any) -> Any:
        key = (self.name, _json_key(kwargs))
        with self._state.lock:
            repeat_count = self._state.failed_calls.get(key, 0)
            if repeat_count >= self._block_after and not getattr(self._wrapped, "terminal_tool", False):
                return (
                    f"Route-change guard blocked {self.name}: identical tool+arguments already failed "
                    f"{repeat_count} times under {CONTRACT_NAME}. The call was not executed. "
                    "Choose a materially different schema-listed route, repair the missing precondition, "
                    "or finalize only if observations are sufficient."
                )
        observation = self._wrapped.__call__(**kwargs, sanitize_inputs_outputs=True)
        with self._state.lock:
            if _looks_failed(observation):
                self._state.failed_calls[key] = self._state.failed_calls.get(key, 0) + 1
            else:
                self._state.failed_calls.pop(key, None)
        return observation


def _with_route_change_guard(tools: list[Any], *, policy_label: str) -> list[Any]:
    state = RouteChangeState()
    guarded: list[Any] = []
    for tool in tools:
        if isinstance(tool, Tool):
            guarded.append(RouteChangeGuardedTool(tool, state, policy_label=policy_label))
        else:
            guarded.append(tool)
    return guarded


class MilestoneGateCheckTool(Tool):
    name = 'milestone_gate_check'
    description = 'Non-environment checker for bind-act-verify-final milestone gates.'
    inputs = {
        "draft": {"type": "string", "description": "Candidate next action, answer, completion claim, or repair route to inspect."}
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
                text = (chr(10)).join(str(item.get("text", "")) for item in content if isinstance(item, dict))
            else:
                text = str(content)
            if text:
                chunks.append(f"{role}: {text}")
        return (chr(10) * 2).join(chunks)[-8000:]

    def forward(self, draft: str) -> str:
        prompt = (chr(10) * 2).join([
            CHECKER_PROMPT,
            f"Contract: {CONTRACT_NAME}",
            "Recent trajectory:" + chr(10) + self._recent_history(),
            "Draft to inspect:" + chr(10) + str(draft),
            CHECKER_RETURN_FIELDS,
        ])
        try:
            response = self.model([
                {"role": MessageRole.USER, "content": [{"type": "text", "text": prompt}]}
            ])
            return str(getattr(response, "content", response)).strip()
        except Exception as exc:
            return (chr(10)).join([
                "verdict: caution",
                f"issue: checker model failed: {exc}",
                "next_safe_move: rely only on observed tool results; use a valid tool, changed repair route, or terminal tool when ready",
            ])


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
        route = schema_route_name(tools)
        guarded_tools = guard_task_tools(tools, policy_label='milestone_gate_direct')
        guarded_tools = _with_route_change_guard(guarded_tools, policy_label='milestone_gate_direct')
        checker = MilestoneGateCheckTool(context=context)
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
        setattr(
            agent,
            "harness_policy",
            {
                "mode": 'milestone_gate_direct',
                "contract": CONTRACT_NAME,
                "checker_tool": checker.name,
                "schema_route": route,
                "route_change_guard": "blocks_third_identical_failed_nonterminal_call",
            },
        )
        return agent


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
