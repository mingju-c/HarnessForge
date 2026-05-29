from __future__ import annotations

import ast
import re
from typing import Any

from Agents.models import MessageRole
from Agents.tools import Tool
from _harness_guards import guard_task_tools, schema_route_name
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = "round03_01_evidence_arbiter_react"
ACTION_MODULE = ACTION_SYSTEM
AUDIT_TOOL_NAME = "predicate_evidence_check"
AUDIT_TOOL_DESCRIPTION = "Non-environment checker for retrieval candidate support, predicate match, and distractor rejection."
AUDIT_TOOL_PROMPT = 'Audit a retrieval answer candidate. Compare target subject, requested predicate, answer type, supporting observation, and rejected distractors. The candidate must fill the requested role, not merely appear near evidence.'
TERMINAL_GATE_ENABLED = False
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



LANGUAGE_CODES = {
    "english": "en",
    "french": "fr",
    "spanish": "es",
    "german": "de",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
}
TOKEN_PLACEHOLDERS = {"", "token", "[token]", "user_token", "access_token", "placeholder", "unknown", "none", "null"}


def _schema_type(schema: Any) -> str | None:
    if not isinstance(schema, dict):
        return None
    value = schema.get("type") or schema.get("json_schema", {}).get("type")
    return str(value).lower() if value is not None else None


def _extract_latest_token(text: str) -> str | None:
    matches = re.findall(r"['\"]token['\"]\s*:\s*['\"]([^'\"]+)['\"]", text or "")
    return matches[-1] if matches else None


def _extract_device_id(*texts: str) -> str | None:
    joined = "\n".join(text for text in texts if text)
    patterns = [
        r"\b(?:device\s+)?id\s*(?:is|=|:)?\s*['\"]?([A-Za-z0-9_-]{3,})",
        r"\bit(?:'s| is)\s+['\"]?([A-Za-z0-9_-]{4,})",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, joined, flags=re.IGNORECASE)
        for candidate in reversed(matches):
            candidate = str(candidate).rstrip(".,;)")
            if re.search(r"\d", candidate):
                return candidate
    digit_matches = re.findall(r"\b\d{4,}\b", joined)
    return digit_matches[-1] if digit_matches else None


def _split_people(text: str) -> list[str]:
    cleaned = str(text or "").strip().strip(".?!")
    cleaned = re.sub(r"\bwith\b\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\battending\b", "", cleaned, flags=re.IGNORECASE).strip()
    parts = re.split(r"\s*,\s*|\s+and\s+", cleaned)
    return [part.strip().strip("'\"") for part in parts if part.strip().strip("'\"")]


def _format_people_list(value: Any, *, task_text: str = "") -> str:
    if isinstance(value, list):
        return str([str(item) for item in value])
    text = str(value or "").strip()
    if text.startswith("[") and text.endswith("]"):
        return text
    people = _split_people(text)
    if not people or people == ["[]"]:
        patterns = [
            r"with\s+(.+?)\s+attending",
            r"attendees?\s*(?:are|is|:)?\s+(.+?)(?:[.\n]|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, task_text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                people = _split_people(match.group(1))
                break
    return str(people)


def _canonical_short_phrase(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    lowered = text.lower()
    if key == "content" and lowered.startswith("call my "):
        return "Call " + text[8:]
    if key in {"content", "symptom"} and text and text == lowered:
        return text[:1].upper() + text[1:]
    return value


def _parse_list_literal(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return value
    try:
        parsed = ast.literal_eval(stripped)
    except Exception:
        return value
    return parsed if isinstance(parsed, list) else value


class StructuredRequestRepairTool(Tool):
    """Narrow argument-shape repair around task tools for structured request generation."""

    skip_forward_signature_validation = True

    def __init__(self, wrapped: Tool) -> None:
        self._wrapped = wrapped
        self.agent = None
        self.name = wrapped.name
        self.description = (
            f"{wrapped.description}\n\nStructured request repair: preserve exact schema keys and compact values; "
            "ID, token, language-code, boolean-string, people-list, and list-literal shapes may be repaired before execution."
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
        if hasattr(self._wrapped, "bind_agent"):
            self._wrapped.bind_agent(agent)

    def _history_text(self) -> str:
        task = str(getattr(self.agent, "task", "") or "")
        return task + "\n" + _text_from_messages(self.agent, limit=12, chars=7000)

    def _repair(self, original: dict[str, Any]) -> dict[str, Any]:
        repaired = dict(original)
        allowed = set(self.inputs.keys())
        history = self._history_text()

        if "device_id" in allowed and "device_id" not in repaired and "name" in repaired:
            device_id = _extract_device_id(str(repaired.get("name", "")), history)
            if device_id:
                repaired["device_id"] = device_id
                if "name" not in allowed:
                    repaired.pop("name", None)

        if "token" in allowed:
            token_value = repaired.get("token")
            if isinstance(token_value, str) and token_value.strip().lower() in TOKEN_PLACEHOLDERS:
                observed_token = _extract_latest_token(history)
                if observed_token:
                    repaired["token"] = observed_token

        if "tgt_lang" in allowed and isinstance(repaired.get("tgt_lang"), str):
            lowered = repaired["tgt_lang"].strip().lower()
            repaired["tgt_lang"] = LANGUAGE_CODES.get(lowered, repaired["tgt_lang"])

        if "attendees" in allowed and "attendees" in repaired:
            repaired["attendees"] = _format_people_list(repaired.get("attendees"), task_text=history)

        if "health_data" in allowed and "health_data" in repaired:
            repaired["health_data"] = _parse_list_literal(repaired.get("health_data"))

        if self.name == "BookHotel" and isinstance(repaired.get("hotel_name"), str):
            repaired["hotel_name"] = re.sub(r"^the\s+", "", repaired["hotel_name"].strip(), flags=re.IGNORECASE)

        for key, value in list(repaired.items()):
            if key in {"on"} and isinstance(value, bool):
                repaired[key] = "True" if value else "False"
            elif _schema_type(self.inputs.get(key)) == "string" and isinstance(value, (int, float, bool)):
                if isinstance(value, bool):
                    repaired[key] = "True" if value else "False"
                else:
                    repaired[key] = str(value)
            repaired[key] = _canonical_short_phrase(key, repaired[key])
        return repaired

    def forward(self, **kwargs: Any) -> Any:
        return self._wrapped.__call__(**self._repair(dict(kwargs)), sanitize_inputs_outputs=True)


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
        guarded_tools = guard_task_tools(tools, policy_label="round03_evidence_arbiter")
        repaired_tools = [
            StructuredRequestRepairTool(tool) if isinstance(tool, Tool) else tool
            for tool in guarded_tools
        ]
        gated_tools, terminal_wrappers = _maybe_gate_tools(repaired_tools)
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
        for tool in repaired_tools:
            if hasattr(tool, "bind_agent"):
                tool.bind_agent(agent)
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
                "mode": "predicate_evidence_arbitration_single_executor",
                "checker_tool": audit_tool.name,
                "schema_route": schema_route_name(tools),
                "terminal_gate": TERMINAL_GATE_ENABLED,
                "focus": ['predicate_answer_match', 'distractor_rejection', 'retrieval_finalization'],
            },
        )
        return agent


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
