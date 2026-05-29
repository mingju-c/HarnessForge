from __future__ import annotations

from typing import Any

from Agents.models import MessageRole
from Agents.tools import Tool
from _harness_guards import guard_task_tools, schema_route_name
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = "round03_01_hybrid_verifier_react"
ACTION_MODULE = ACTION_SYSTEM
AUDIT_TOOL_NAME = "hybrid_status_verifier"
AUDIT_TOOL_DESCRIPTION = "Rare non-environment verifier for terminal readiness, repair constraints, slot closure, evidence support, and raw final form."
AUDIT_TOOL_PROMPT = 'Audit only the current high-risk boundary: terminal readiness, repeated failure repair, slot closure, evidence support, or raw final form. Return no_blocker or one concrete next_action_constraint.'
TERMINAL_GATE_ENABLED = True
THROTTLE_REPEATED_AUDITS = True


def _text_from_messages(agent: Any, *, limit: int = 14, chars: int = 8000) -> str:
    if agent is None:
        return ""
    try:
        messages = agent.write_memory_to_messages(include_system_prompt=False)
    except Exception:
        messages = []
    chunks = []
    for message in messages[-limit:]:
        role = message.get("role", "")
        content = message.get("content", "")
        if isinstance(content, list):
            text = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        else:
            text = str(content)
        if text:
            chunks.append(f"{role}: {text}")
    return "\n\n".join(chunks)[-chars:]


class Round0301AuditTool(Tool):
    name = AUDIT_TOOL_NAME
    description = AUDIT_TOOL_DESCRIPTION
    inputs = {
        "draft": {
            "type": "string",
            "description": "Candidate next action, status packet, answer, or completion claim to inspect.",
        }
    }
    output_type = "string"

    def __init__(self, *, context: ActionContext):
        self.model = context.model
        self.agent = None
        self.allowed_tool_names: list[str] = []
        self._last_draft: str | None = None
        super().__init__()

    def bind_agent(self, agent: Any, tools: list[Any] | None = None) -> None:
        self.agent = agent
        if tools is not None:
            self.allowed_tool_names = [
                getattr(tool, "name", "")
                for tool in tools
                if getattr(tool, "name", "") and getattr(tool, "name", "") != self.name
            ]

    def forward(self, draft: str) -> str:
        cleaned = str(draft or "").strip()
        if THROTTLE_REPEATED_AUDITS and cleaned and cleaned == self._last_draft:
            return (
                "verdict: throttle\n"
                "evidence: same audit draft repeated without new tool evidence\n"
                "missing_or_risk: checker-loop risk\n"
                "next_safe_move: take one real schema-listed action, or finalize only from decisive observations"
            )
        self._last_draft = cleaned
        prompt = (
            AUDIT_TOOL_PROMPT
            + "\n\nAllowed non-audit tools: " + str(self.allowed_tool_names)
            + "\n\nRecent trajectory:\n" + _text_from_messages(self.agent)
            + "\n\nDraft to inspect:\n" + cleaned
            + "\n\nReturn concise fields: verdict, evidence, missing_or_risk, next_safe_move."
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


class SoftTerminalGateTool(Tool):
    skip_forward_signature_validation = True

    def __init__(self, wrapped: Tool) -> None:
        self._wrapped = wrapped
        self.agent = None
        self.name = wrapped.name
        self.description = (
            f"{wrapped.description}\n\nRound03 terminal gate: complete only when "
            "required state rows are observed successful or explicitly evidence-blocked."
        )
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

    def _should_block(self) -> bool:
        if not TERMINAL_GATE_ENABLED:
            return False
        lowered_name = str(self.name).lower()
        if "complete" not in lowered_name:
            return False
        history = _text_from_messages(self.agent, limit=10, chars=5000).lower()
        failure_markers = (
            "success': false",
            '"success": false',
            "permission denied",
            "access denied",
            "not found",
            "does not exist",
            "unknown tool",
            "invalid",
            "error for tool call",
            "guard blocked",
            "schema advisory",
            "repeated-failure advisory",
        )
        success_markers = ("success': true", '"success": true', "successfully", "completed", "updated", "created", "added")
        last_failure = max((history.rfind(marker) for marker in failure_markers), default=-1)
        last_success = max((history.rfind(marker) for marker in success_markers), default=-1)
        waiver_markers = ("all required", "all rows", "remaining: none", "no remaining", "final_readiness: ready")
        has_waiver = any(marker in history[-1800:] for marker in waiver_markers)
        return last_failure > last_success and not has_waiver

    def forward(self, **kwargs: Any) -> Any:
        if self._should_block():
            return (
                "Terminal-readiness gate: complete_task was not executed because the recent trajectory "
                "contains an unrepaired failed or schema-invalid required row. Repair the row, choose an "
                "alternate listed mutator, or record an evidence-backed blocker before completing."
            )
        return self._wrapped.__call__(**kwargs, sanitize_inputs_outputs=True)


def _maybe_gate_tools(tools: list[Any]) -> tuple[list[Any], list[SoftTerminalGateTool]]:
    if not TERMINAL_GATE_ENABLED:
        return tools, []
    gated: list[Any] = []
    wrappers: list[SoftTerminalGateTool] = []
    for tool in tools:
        name = str(getattr(tool, "name", "") or "").lower()
        if "complete" in name and isinstance(tool, Tool):
            wrapper = SoftTerminalGateTool(tool)
            gated.append(wrapper)
            wrappers.append(wrapper)
        else:
            gated.append(tool)
    return gated, wrappers


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
        guarded_tools = guard_task_tools(tools, policy_label="round03_hybrid_verifier")
        gated_tools, terminal_wrappers = _maybe_gate_tools(guarded_tools)
        audit_tool = Round0301AuditTool(context=context)
        root_tools = self.normalize_tools([*gated_tools, audit_tool])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        audit_tool.bind_agent(agent, root_tools)
        for wrapper in terminal_wrappers:
            wrapper.bind_agent(agent)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_SUMMARY_INTERVAL
        if getattr(agent, "max_tool_calls_per_step", None) is None:
            agent.max_tool_calls_per_step = 2
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "hybrid_status_verifier_single_executor",
                "checker_tool": audit_tool.name,
                "schema_route": schema_route_name(tools),
                "terminal_gate": TERMINAL_GATE_ENABLED,
                "focus": ['hybrid_status_packet', 'rare_verifier', 'terminal_and_final_commit'],
            },
        )
        return agent


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
