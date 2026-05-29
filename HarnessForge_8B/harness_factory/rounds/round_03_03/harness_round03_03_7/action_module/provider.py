from __future__ import annotations

from typing import Any

from Agents.models import MessageRole
from Agents.tools import Tool
from _harness_guards import guard_task_tools, is_read_only_tool_schema, schema_route_name
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = "round03_03_risk_routed_react"
ACTION_MODULE = ACTION_SYSTEM
POLICY_LABEL = "round03_03_risk_routed_minimalist"
CHECKER_NAME = "risk_snapshot_check"
CHECKER_TITLE = 'low-noise risk snapshot checker'
CHECKER_INSTRUCTION = 'Produce a tiny risk snapshot: no_risk, schema_risk, stateful_risk, evidence_risk, or raw_final_risk, plus the one next constraint if any.'
TERMINAL_GATE_ENABLED = False
SEQUENTIAL_MUTATIONS = True
FOCUS = ['risk_triggered_controls', 'fast_read_only_path', 'sparse_memory_cues', 'compact_snapshot_gate']

FAILURE_MARKERS = ('"success": false', "'success': false", "error for tool call", "schema advisory", "unknown tool", "invalid", "not found", "does not exist", "permission denied", "access denied", "repeated-failure advisory", "guard blocked")
READY_MARKERS = ("terminal_blockers: none", "terminal_blockers: no", "final_readiness: ready", "final_readiness: yes", "all rows closed", "no unresolved", "verdict: allow", "final_allowed: yes")
COMPLETION_NAMES = {"complete_task", "submit_task", "finish_task", "mark_task_complete"}


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        return "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return str(content)


def _recent_history(agent: Any, *, limit: int = 16, chars: int = 9000) -> str:
    if agent is None:
        return ""
    try:
        messages = agent.write_memory_to_messages(include_system_prompt=False)
    except Exception:
        messages = []
    chunks = []
    for message in messages[-limit:]:
        role = message.get("role", "")
        text = _message_text(message)
        if text:
            chunks.append(f"{role}: {text}")
    return "\n\n".join(chunks)[-chars:]


class TerminalGateTool(Tool):
    """Light wrapper that can block risky stateful completion calls."""

    skip_forward_signature_validation = True

    def __init__(self, wrapped: Tool, *, enabled: bool) -> None:
        self._wrapped = wrapped
        self._enabled = enabled
        self.agent = None
        self.name = wrapped.name
        self.description = getattr(wrapped, "description", "")
        if enabled and self._is_completion_name():
            self.description += "\n\nRound03_03 terminal gate: call this only when required rows are observation-closed and recent failures are repaired."
        self.inputs = dict(getattr(wrapped, "inputs", {}) or {})
        self.output_type = getattr(wrapped, "output_type", "string")
        for attr in ("terminal_tool", "is_terminal_observation", "terminal_answer"):
            if hasattr(wrapped, attr):
                setattr(self, attr, getattr(wrapped, attr))
        super().__init__()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def bind_agent(self, agent: Any) -> None:
        self.agent = agent

    def _is_completion_name(self) -> bool:
        lowered = str(self.name or "").lower()
        return lowered in COMPLETION_NAMES or ("complete" in lowered and "task" in lowered)

    def _completion_blocker(self) -> str | None:
        if not self._enabled or not self._is_completion_name():
            return None
        history = _recent_history(self.agent, limit=18, chars=10000).lower()
        if not history:
            return None
        has_failure = any(marker in history for marker in FAILURE_MARKERS)
        has_ready = any(marker in history for marker in READY_MARKERS)
        if has_failure and not has_ready:
            return "Terminal gate advisory: completion was not executed because recent history contains failed, invalid, or repeated calls without a later ready marker. Repair or close the affected row, then complete only when observations support readiness."
        return None

    def forward(self, **kwargs: Any) -> Any:
        blocker = self._completion_blocker()
        if blocker is not None:
            return blocker
        return self._wrapped.__call__(**kwargs, sanitize_inputs_outputs=True)


class RiskRoutedSnapshotTool(Tool):
    name = CHECKER_NAME
    description = "Rare non-environment checker for risk routed minimalist. It returns constraints, not evidence."
    inputs = {"draft": {"type": "string", "description": "Candidate next action, status update, answer, or completion claim to inspect."}}
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
            self.allowed_tool_names = [getattr(tool, "name", "") for tool in tools if getattr(tool, "name", "") and getattr(tool, "name", "") != self.name]

    def forward(self, draft: str) -> str:
        cleaned = str(draft or "").strip()
        if self._throttle_exact_repeats and cleaned and cleaned == self._last_draft:
            return "verdict: throttle\nblocker: checker was called on the same draft without new observations\nrequired_next_move: take a real schema-listed action, repair the open row, or finalize from observed evidence\nfinal_allowed: no\nevidence_limit: checker text is not environment evidence"
        self._last_draft = cleaned
        prompt = (
            f"You are a rare non-environment {CHECKER_TITLE}. {CHECKER_INSTRUCTION} Checker output must constrain the next action and must never count as environment evidence."
            + "\n\nAllowed non-checker tools: " + str(self.allowed_tool_names)
            + "\n\nRecent trajectory:\n" + _recent_history(self.agent)
            + "\n\nDraft to inspect:\n" + cleaned
            + "\n\nReturn concise text with exactly these fields: verdict, blocker, required_next_move, final_allowed, evidence_limit."
        )
        try:
            response = self.model([{"role": MessageRole.USER, "content": [{"type": "text", "text": prompt}]}])
            return str(getattr(response, "content", response)).strip()
        except Exception as exc:
            return f"verdict: caution\nblocker: checker model failed: {exc}\nrequired_next_move: rely on schema-listed tools and observed evidence\nfinal_allowed: only if observations already satisfy the task\nevidence_limit: checker failure is not evidence"


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
        guarded_tools = guard_task_tools(tools, policy_label=POLICY_LABEL)
        gated_tools = [TerminalGateTool(tool, enabled=TERMINAL_GATE_ENABLED) for tool in guarded_tools]
        checker = RiskRoutedSnapshotTool(context=context)
        root_tools = self.normalize_tools([*gated_tools, checker])
        agent = self.create_agent(context, tools=root_tools, prompt_templates=self.prompt_templates, prompts_type=self.prompts_type, planning_system=self.organization_planning_system)
        for tool in gated_tools:
            tool.bind_agent(agent)
        checker.bind_agent(agent, root_tools)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_SUMMARY_INTERVAL
        if SEQUENTIAL_MUTATIONS and not self.use_read_only_mode:
            agent.max_tool_calls_per_step = 1
        elif getattr(agent, "max_tool_calls_per_step", None) is None:
            agent.max_tool_calls_per_step = 2
        setattr(agent, "harness_policy", {"mode": "risk_routed_minimalist_single_executor", "checker_tool": checker.name, "policy_label": POLICY_LABEL, "focus": FOCUS, "route": self.route_name, "read_only_mode": self.use_read_only_mode, "terminal_gate_enabled": TERMINAL_GATE_ENABLED, "sequential_mutations": SEQUENTIAL_MUTATIONS})
        return agent


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
