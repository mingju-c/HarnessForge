from __future__ import annotations

import json
import re
import threading
from typing import Any

from Agents.models import MessageRole
from Agents.tools import Tool

from module_action.base_action import ActionContext


def _json_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _text_from_message(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return str(content)


def _looks_like_failed_observation(observation: Any) -> bool:
    if isinstance(observation, dict):
        success_value = observation.get("success")
        if success_value is False:
            return True
        if "error" in observation:
            return True
    text = str(observation).lower()
    failure_markers = [
        '"success": false',
        "'success': false",
        "error",
        "unknown tool",
        "invalid",
        "not found",
        "does not exist",
        "permission denied",
        "access denied",
        "cannot ",
        "failed",
        "reached max steps",
        "guard budget reached",
        "guard blocked",
    ]
    return any(marker in text for marker in failure_markers)


def _with_repeated_failure_advisory(observation: Any, *, tool_name: str, repeat_count: int) -> Any:
    advisory = (
        f"Repeated-failure advisory for {tool_name}: this exact real tool call has "
        f"failed {repeat_count} times. The call was still executed; do not repeat "
        "the identical tool+arguments again unless a later successful observation changes "
        "state or preconditions. Choose a different schema-listed tool, repaired "
        "arguments, or an alternate strategy that reaches the same goal."
    )
    if isinstance(observation, dict):
        updated = dict(observation)
        existing = updated.get("guard_advisory")
        updated["guard_advisory"] = f"{existing}\n{advisory}" if existing else advisory
        return updated
    return f"{observation}\n{advisory}"


class GuardState:
    def __init__(self, *, max_real_tool_calls: int | None = None) -> None:
        self.max_real_tool_calls = max_real_tool_calls
        self.real_tool_calls = 0
        self.failed_calls: dict[tuple[str, str], int] = {}
        self.lock = threading.Lock()

    def call_key(self, tool_name: str, arguments: Any) -> tuple[str, str]:
        return (tool_name, _json_key(arguments))


class GuardedTool(Tool):
    """Soft schema/retry helper around an existing task tool."""

    skip_forward_signature_validation = True

    def __init__(
        self,
        wrapped: Tool,
        state: GuardState,
        *,
        policy_label: str,
    ) -> None:
        self._wrapped = wrapped
        self._state = state
        self._policy_label = policy_label
        self.name = wrapped.name
        self.description = (
            f"{wrapped.description}\n\n"
            f"Guard policy ({policy_label}): use exact schema keys from the available "
            "tool list. Previous failures are advisory only; if a later observation "
            "changes preconditions, retrying the same real tool call is allowed."
        )
        self.inputs = dict(getattr(wrapped, "inputs", {}) or {})
        self.output_type = getattr(wrapped, "output_type", "string")
        for attr in ("terminal_tool", "is_terminal_observation", "terminal_answer"):
            if hasattr(wrapped, attr):
                setattr(self, attr, getattr(wrapped, attr))
        super().__init__()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def _coerce_argument(self, key: str, value: Any) -> Any:
        schema = self.inputs.get(key, {}) if isinstance(self.inputs, dict) else {}
        if schema.get("type") == "array" and not isinstance(value, list):
            return [value]
        return value

    def _repair_argument_keys(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
        allowed_keys = set(self.inputs.keys())
        repaired = {key: value for key, value in arguments.items() if key in allowed_keys}
        extra_keys = sorted(set(arguments.keys()) - allowed_keys)
        mapped: list[str] = []

        alias_candidates = {
            "account_status": ("new_status", "status"),
            "action": ("action_performed",),
            "author_name": ("name", "full_name", "person_name"),
            "book_title": ("title", "book_name"),
            "condition": ("new_condition",),
            "attribute": ("information_types",),
            "birth_date": ("date_of_birth", "input_date"),
            "contact_email": ("contact_info", "email"),
            "date": ("input_date", "event_date", "scheduled_date"),
            "dob": ("date_of_birth",),
            "folder_name": ("name",),
            "input": ("query", "text", "full_name", "draft", "characters"),
            "input_string": ("input", "text", "query"),
            "months_before": ("value",),
            "name": ("full_name", "person_name", "individual_name", "patient_name", "organization_name"),
            "moderation_status": ("new_status", "status"),
            "new_location": ("location_id", "new_location_id"),
            "new_status": ("status", "account_status"),
            "parent_folder": ("parent_folder_id",),
            "party_name": ("organization_name", "names"),
            "patient_name": ("name",),
            "person": ("person_name", "individual_name", "full_name", "name"),
            "political_party": ("organization_name", "names"),
            "phone_number": ("contact_phone_number", "phone"),
            "query": ("search_query", "question", "input", "draft"),
            "relation": ("relationship", "relationship_type"),
            "relationship_type": ("relationship",),
            "status": ("new_status", "account_status"),
            "user_name": ("name",),
        }

        for key in extra_keys:
            value = arguments.get(key)
            candidates = alias_candidates.get(key, ())
            if len(arguments) == 1 and len(allowed_keys) == 1:
                candidates = tuple(allowed_keys)
            for candidate in candidates:
                if candidate in allowed_keys and candidate not in repaired:
                    repaired[candidate] = self._coerce_argument(candidate, value)
                    mapped.append(f"{key}->{candidate}")
                    break

        return repaired, extra_keys, mapped

    def forward(self, **kwargs: Any) -> Any:
        original_arguments = dict(kwargs)
        arguments, extra_keys, mapped_keys = self._repair_argument_keys(original_arguments)
        if extra_keys and not arguments:
            return (
                f"Schema advisory for {self.name}: supplied argument keys {extra_keys} "
                f"do not match this tool schema. Allowed keys: {sorted(self.inputs.keys())}. "
                "The call was not executed; reissue the call with exact keys from the "
                "available tool schemas."
            )

        key = self._state.call_key(self.name, arguments)
        with self._state.lock:
            if (
                self._state.max_real_tool_calls is not None
                and self._state.real_tool_calls >= self._state.max_real_tool_calls
                and not getattr(self._wrapped, "terminal_tool", False)
            ):
                return (
                    "Tool-call budget advisory: the non-terminal tool-call budget for "
                    "this helper has been reached. Finalize only if observations are "
                    "sufficient; otherwise use a different valid strategy."
                )
            self._state.real_tool_calls += 1

        try:
            observation = self._wrapped.__call__(**arguments, sanitize_inputs_outputs=True)
        except TypeError as exc:
            if mapped_keys or extra_keys:
                return (
                    f"Schema advisory for {self.name}: supplied keys {extra_keys} were "
                    f"mapped as {mapped_keys or 'none'}, but the repaired call still did "
                    f"not satisfy the schema: {exc}. Allowed keys: {sorted(self.inputs.keys())}."
                )
            raise
        if _looks_like_failed_observation(observation):
            with self._state.lock:
                repeat_count = self._state.failed_calls.get(key, 0) + 1
                self._state.failed_calls[key] = repeat_count
            if repeat_count >= 2:
                observation = _with_repeated_failure_advisory(
                    observation, tool_name=self.name, repeat_count=repeat_count
                )
        else:
            with self._state.lock:
                self._state.failed_calls.pop(key, None)
        return observation


class ReflectionCriticTool(Tool):
    """Non-environment critic. It reads the trajectory and schema, then returns a checklist."""

    name = "critic_reflect"
    description = (
        "Review the current trajectory before continuing or finalizing. This critic "
        "does not call or modify the external environment."
    )
    inputs = {
        "draft": {
            "type": "string",
            "description": "The proposed next action or final answer to audit.",
        }
    }
    output_type = "string"

    def __init__(
        self,
        *,
        context: ActionContext,
        name: str = "critic_reflect",
        description: str | None = None,
    ) -> None:
        self.name = name
        if description is not None:
            self.description = description
        self.model = context.model
        self.agent = None
        self.allowed_tool_names: list[str] = []
        super().__init__()

    def bind_agent(self, agent: Any, tools: list[Any]) -> None:
        self.agent = agent
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
        for msg in messages[-12:]:
            role = msg.get("role", "")
            text = _text_from_message(msg)
            if text:
                chunks.append(f"{role}: {text}")
        return "\n\n".join(chunks)[-7000:]

    def forward(self, draft: str) -> str:
        history = self._recent_history()
        prompt = (
            "You are a tool-use critic. You do not operate the environment.\n"
            "Check only these issues:\n"
            "1. Whether the proposed tool exists in the allowed tool list.\n"
            "2. Whether arguments appear schema-consistent.\n"
            "3. Whether the trajectory repeats an identical failed call.\n"
            "4. Whether the agent should stop and finalize.\n\n"
            f"Allowed non-critic tools: {self.allowed_tool_names}\n\n"
            f"Recent trajectory:\n{history}\n\n"
            f"Draft to audit:\n{draft}\n\n"
            "Return concise text with fields: verdict, issue, next_safe_move."
        )
        try:
            response = self.model(
                [
                    {
                        "role": MessageRole.USER,
                        "content": [{"type": "text", "text": prompt}],
                    }
                ]
            )
            return str(getattr(response, "content", response)).strip()
        except Exception as exc:
            return (
                "verdict: caution\n"
                f"issue: critic model call failed: {exc}\n"
                "next_safe_move: use only allowed tools, avoid repeated failed calls, "
                "and finalize if the evidence is sufficient."
            )


def guard_task_tools(
    tools: list[Any],
    *,
    policy_label: str,
    max_real_tool_calls: int | None = None,
) -> list[Any]:
    state = GuardState(max_real_tool_calls=max_real_tool_calls)
    guarded: list[Any] = []
    for tool in tools:
        if not isinstance(tool, Tool):
            guarded.append(tool)
            continue
        guarded.append(GuardedTool(tool, state, policy_label=policy_label))
    return guarded


STATEFUL_TOOL_PATTERNS = [
    r"\badd\b",
    r"\bact\b",
    r"\bauthenticate\b",
    r"\bbuy\b",
    r"\bcancel\b",
    r"\bclick\b",
    r"\bcomplete\b",
    r"\bcreate\b",
    r"\bdelete\b",
    r"\bedit\b",
    r"\bfulfill\w*\b",
    r"\blogin\b",
    r"\blogout\b",
    r"\bmark\b",
    r"\bmutate\b",
    r"\border\b",
    r"\bpatch\b",
    r"\bpay\b",
    r"\bpost\b",
    r"\bput\b",
    r"\bremove\b",
    r"\breserve\b",
    r"\bset\b",
    r"\bship\w*\b",
    r"\bsubmit\b",
    r"\btransfer\b",
    r"\bupdate\b",
    r"\bwrite\b",
]

READ_ONLY_TOOL_PATTERNS = [
    r"\bauthor_lookup\b",
    r"\bcalculate\w*\b",
    r"\bcheck\b",
    r"\bcount\w*\b",
    r"\bcrawl\b",
    r"\bdescribe\b",
    r"\bfilter\b",
    r"\bfetch\b",
    r"\bfind\b",
    r"\bget\b",
    r"\binfo\b",
    r"\binformation\b",
    r"\bis\b",
    r"\bletter_counter\b",
    r"\blist\b",
    r"\blookup\b",
    r"\bprovide\b",
    r"\bquery\b",
    r"\bread\b",
    r"\breasoning\b",
    r"\bresolve\b",
    r"\bretrieve\b",
    r"\bretriever\b",
    r"\breturn\b",
    r"\bsearch\b",
    r"\bvalidate\b",
]


def _tool_words(tool: Any) -> str:
    name = str(getattr(tool, "name", "") or "").lower().replace("_", " ")
    description = str(getattr(tool, "description", "") or "").lower()
    return f"{name} {description}"


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def schema_route_name(tools: list[Any]) -> str:
    return "schema_read_only" if is_read_only_tool_schema(tools) else "schema_stateful_or_unknown"


def is_read_only_tool_schema(tools: list[Any]) -> bool:
    """Infer routing from exposed tool schemas only; never from dataset labels."""
    real_tools = [
        tool
        for tool in tools
        if getattr(tool, "name", None)
        and getattr(tool, "name", None) not in {"final_answer"}
    ]
    if not real_tools:
        return False

    for tool in real_tools:
        text = _tool_words(tool)
        if _matches_any(STATEFUL_TOOL_PATTERNS, text):
            return False
        if not _matches_any(READ_ONLY_TOOL_PATTERNS, text):
            return False
    return True
