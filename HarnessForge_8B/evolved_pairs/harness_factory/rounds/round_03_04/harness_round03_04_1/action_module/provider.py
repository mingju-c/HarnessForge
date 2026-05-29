from __future__ import annotations

import re
from typing import Any

from Agents.models import MessageRole
from Agents.tools import Tool
from _harness_guards import guard_task_tools, is_read_only_tool_schema, schema_route_name
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = "round03_04_closure_ledger_react"
ACTION_MODULE = ACTION_SYSTEM
POLICY_LABEL = "round03_04_closure_ledger_guard"
CHECKER_NAME = "closure_ledger_check"
CHECKER_TITLE = "closure ledger readiness checker"
CHECKER_INSTRUCTION = 'Audit pending obligations, observed success rows, failed calls, mutable postconditions, and raw final readiness. Completion is allowed only when required rows are closed by observations or explicitly blocked by evidence.'
STATUS_CONTRACT = "CLOSURE_LEDGER_COMMIT"
SCHEMA_PREFLIGHT_ENABLED = True
TERMINAL_GATE_ENABLED = True
SEQUENTIAL_MUTATIONS = True
FOCUS = ['mutable_closure_ledger', 'schema_preflight', 'enforced_checker_blockers', 'raw_final_commit']

FAILURE_MARKERS = (
    '"success": false',
    "'success': false",
    "error for tool call",
    "schema advisory",
    "schema preflight blocked",
    "unknown tool",
    "invalid",
    "not found",
    "does not exist",
    "permission denied",
    "access denied",
    "repeated-failure advisory",
    "guard blocked",
    "terminal gate advisory",
)
READY_MARKERS = (
    "terminal_blockers: none",
    "terminal_blockers: no",
    "final_readiness: ready",
    "final_readiness: yes",
    "all rows closed",
    "no unresolved",
    "verdict: allow",
    "final_allowed: yes",
    "completion_ready: yes",
)
SUCCESS_MARKERS = (
    '"success": true',
    "'success': true",
    "successfully",
    "created",
    "updated",
    "deleted",
    "reserved",
    "completed",
    "status: success",
)
COMPLETION_NAMES = {"complete_task", "submit_task", "finish_task", "mark_task_complete"}
PLACEHOLDER_VALUES = {"", "unknown", "n/a", "none", "null", "todo", "tbd", "id", "user_id", "patient_id", "string", "value"}


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


def _schema_type(schema: Any) -> str | None:
    if not isinstance(schema, dict):
        return None
    value = schema.get("type") or schema.get("json_schema", {}).get("type")
    if isinstance(value, list):
        return next((str(item) for item in value if item != "null"), None)
    return str(value) if value is not None else None


def _is_optional_schema(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    description = str(schema.get("description", "")).lower()
    return bool(
        schema.get("optional")
        or schema.get("nullable")
        or "default" in schema
        or "optional" in description
    )


def _enum_values(schema: Any) -> list[Any]:
    if not isinstance(schema, dict):
        return []
    for key in ("enum", "choices", "allowed_values"):
        values = schema.get(key)
        if isinstance(values, (list, tuple, set)):
            return list(values)
    return []


def _object_properties(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties") or schema.get("fields") or schema.get("schema", {}).get("properties")
    return dict(props) if isinstance(props, dict) else {}


def _required_from_schema(inputs: dict[str, Any]) -> set[str]:
    explicit = inputs.get("required")
    if isinstance(explicit, (list, tuple, set)):
        return {str(item) for item in explicit}
    required = set()
    for key, schema in inputs.items():
        if key == "required":
            continue
        if isinstance(schema, dict) and (schema.get("required") is True or not _is_optional_schema(schema)):
            required.add(key)
    return required


def _validate_value(key_path: str, schema: Any, value: Any) -> list[str]:
    errors: list[str] = []
    expected_type = _schema_type(schema)
    enum_values = _enum_values(schema)
    if enum_values and value not in enum_values:
        string_values = {str(item) for item in enum_values}
        if str(value) not in string_values:
            errors.append(f"invalid enum at {key_path}={value!r}; allowed={list(enum_values)!r}")
    if expected_type == "object":
        if not isinstance(value, dict):
            errors.append(f"expected object at {key_path}, got {type(value).__name__}")
            return errors
        props = _object_properties(schema)
        required = schema.get("required")
        if not isinstance(required, (list, tuple, set)):
            required = [name for name, child in props.items() if isinstance(child, dict) and child.get("required") is True]
        for child_key in required:
            if child_key not in value or value.get(child_key) in (None, ""):
                errors.append(f"missing nested required field {key_path}.{child_key}")
        for child_key, child_value in value.items():
            child_schema = props.get(child_key)
            if child_schema is not None:
                errors.extend(_validate_value(f"{key_path}.{child_key}", child_schema, child_value))
    elif expected_type == "array":
        if not isinstance(value, list):
            errors.append(f"expected array at {key_path}, got {type(value).__name__}")
        else:
            item_schema = schema.get("items") if isinstance(schema, dict) else None
            if item_schema is not None:
                for index, item in enumerate(value[:5]):
                    errors.extend(_validate_value(f"{key_path}[{index}]", item_schema, item))
    return errors


class SchemaPreflightTool(Tool):
    """Local hard preflight layered over the shared soft guard."""

    skip_forward_signature_validation = True

    def __init__(self, wrapped: Tool, *, enabled: bool, terminal_gate_enabled: bool) -> None:
        self._wrapped = wrapped
        self._enabled = enabled
        self._terminal_gate_enabled = terminal_gate_enabled
        self.agent = None
        self.name = wrapped.name
        self.description = getattr(wrapped, "description", "")
        if enabled:
            self.description += (
                "\n\nRound03_04 schema preflight: calls are checked for exact keys, "
                "required fields, nested object requirements, enum values, and placeholder IDs before execution."
            )
        if terminal_gate_enabled and self._is_completion_tool():
            self.description += (
                "\n\nRound03_04 terminal gate: call only when observation-backed rows are closed and recent failures are repaired."
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

    def _is_completion_tool(self) -> bool:
        lowered = str(self.name or "").lower()
        return lowered in COMPLETION_NAMES or ("complete" in lowered and "task" in lowered)

    def _prepare_arguments(self, original: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
        repair = getattr(self._wrapped, "_repair_argument_keys", None)
        if callable(repair):
            arguments, extra_keys, mapped_keys = repair(original)
        else:
            allowed = set(self.inputs.keys())
            arguments = {key: value for key, value in original.items() if key in allowed}
            extra_keys = sorted(set(original.keys()) - allowed)
            mapped_keys = []
        unmapped_extra = [
            key for key in extra_keys
            if not any(str(mapping).startswith(f"{key}->") for mapping in mapped_keys)
        ]
        for key, schema in self.inputs.items():
            if key in arguments and _schema_type(schema) == "array" and not isinstance(arguments[key], list):
                arguments[key] = [arguments[key]]
        return arguments, extra_keys, mapped_keys, unmapped_extra

    def _schema_errors(self, arguments: dict[str, Any], unmapped_extra: list[str]) -> list[str]:
        if not self._enabled:
            return []
        errors: list[str] = []
        allowed_keys = sorted(key for key in self.inputs.keys() if key != "required")
        if unmapped_extra:
            errors.append(f"unknown argument keys {unmapped_extra!r}; allowed={allowed_keys!r}")
        required = _required_from_schema(self.inputs)
        for key in sorted(required):
            if key not in arguments or arguments.get(key) in (None, ""):
                errors.append(f"missing required argument {key!r}")
        for key, value in arguments.items():
            schema = self.inputs.get(key)
            if schema is None:
                continue
            errors.extend(_validate_value(key, schema, value))
            if isinstance(value, str) and value.strip().lower() in PLACEHOLDER_VALUES and re.search(r"(^|_)(id|ids|uuid|code|name|email)$", key.lower()):
                errors.append(f"placeholder-like value for {key!r}; bind a real observed value before calling")
        return errors

    def _terminal_blocker(self) -> str | None:
        if not self._terminal_gate_enabled or not self._is_completion_tool():
            return None
        history = _recent_history(self.agent, limit=18, chars=10000).lower()
        if not history:
            return None
        has_failure = any(marker in history for marker in FAILURE_MARKERS)
        has_ready = any(marker in history for marker in READY_MARKERS)
        last_failure = max([history.rfind(marker) for marker in FAILURE_MARKERS if marker in history] or [-1])
        tail = history[last_failure:] if last_failure >= 0 else ""
        repaired_after_failure = any(marker in tail for marker in SUCCESS_MARKERS)
        if has_failure and not has_ready and not repaired_after_failure:
            return (
                "Terminal gate advisory: completion was not executed because recent history contains failed, invalid, "
                "or repeated calls without a later ready marker or repair success. Close the affected row with observation, "
                "repair the blocker, or state an evidence-backed impossibility before completing."
            )
        return None

    def forward(self, **kwargs: Any) -> Any:
        original_arguments = dict(kwargs)
        arguments, extra_keys, mapped_keys, unmapped_extra = self._prepare_arguments(original_arguments)
        errors = self._schema_errors(arguments, unmapped_extra)
        if errors:
            return (
                f"Schema preflight blocked {self.name} before environment execution. "
                f"failure_class: schema_mismatch; errors: {errors}; supplied_keys: {sorted(original_arguments.keys())}; "
                f"mapped_keys: {mapped_keys or []}; allowed_schema_keys: {sorted(key for key in self.inputs.keys() if key != 'required')}. "
                "Repair by using exact schema keys, binding required IDs from observations, satisfying nested fields, or choosing a valid enum."
            )
        blocker = self._terminal_blocker()
        if blocker is not None:
            return blocker
        return self._wrapped.__call__(**arguments, sanitize_inputs_outputs=True)


class ContractCheckTool(Tool):
    name = CHECKER_NAME
    description = "Rare non-environment checker for the harness status contract. It returns constraints, not evidence."
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
            self.allowed_tool_names = [
                getattr(tool, "name", "")
                for tool in tools
                if getattr(tool, "name", "") and getattr(tool, "name", "") != self.name
            ]

    def forward(self, draft: str) -> str:
        cleaned = str(draft or "").strip()
        if self._throttle_exact_repeats and cleaned and cleaned == self._last_draft:
            return (
                "verdict: throttle\n"
                "blocker: checker was called on the same draft without new observations\n"
                "required_observation: none yet\n"
                "allowed_next_action: take a real schema-listed action, repair the open row, or finalize from observed evidence\n"
                "final_allowed: no\n"
                "evidence_limit: checker text is not environment evidence"
            )
        self._last_draft = cleaned
        prompt = (
            f"You are a rare non-environment {CHECKER_TITLE} for {STATUS_CONTRACT}. {CHECKER_INSTRUCTION} "
            "Checker output must constrain the next action and must never count as environment evidence."
            + "\n\nAllowed non-checker tools: " + str(self.allowed_tool_names)
            + "\n\nRecent trajectory:\n" + _recent_history(self.agent)
            + "\n\nDraft to inspect:\n" + cleaned
            + "\n\nReturn concise text with exactly these fields: verdict, blocker, required_observation, allowed_next_action, final_allowed, evidence_limit."
        )
        try:
            response = self.model([{"role": MessageRole.USER, "content": [{"type": "text", "text": prompt}]}])
            return str(getattr(response, "content", response)).strip()
        except Exception as exc:
            return (
                f"verdict: caution\n"
                f"blocker: checker model failed: {exc}\n"
                "required_observation: rely on schema-listed tools and observed evidence\n"
                "allowed_next_action: use a valid tool if evidence is missing, otherwise finalize from observations\n"
                "final_allowed: only if observations already satisfy the task\n"
                "evidence_limit: checker failure is not evidence"
            )


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    DEFAULT_SUMMARY_INTERVAL = 6

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
        preflight_tools = [
            SchemaPreflightTool(tool, enabled=SCHEMA_PREFLIGHT_ENABLED, terminal_gate_enabled=TERMINAL_GATE_ENABLED)
            if isinstance(tool, Tool)
            else tool
            for tool in guarded_tools
        ]
        checker = ContractCheckTool(context=context)
        root_tools = self.normalize_tools([*preflight_tools, checker])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        for tool in preflight_tools:
            if hasattr(tool, "bind_agent"):
                tool.bind_agent(agent)
        checker.bind_agent(agent, root_tools)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_SUMMARY_INTERVAL
        if SEQUENTIAL_MUTATIONS and not self.use_read_only_mode:
            agent.max_tool_calls_per_step = 1
        elif getattr(agent, "max_tool_calls_per_step", None) is None:
            agent.max_tool_calls_per_step = 2
        setattr(
            agent,
            "harness_policy",
            {
                "mode": f"{STATUS_CONTRACT.lower()}_single_executor",
                "checker_tool": checker.name,
                "policy_label": POLICY_LABEL,
                "focus": FOCUS,
                "route": self.route_name,
                "read_only_mode": self.use_read_only_mode,
                "schema_preflight_enabled": SCHEMA_PREFLIGHT_ENABLED,
                "terminal_gate_enabled": TERMINAL_GATE_ENABLED,
                "sequential_mutations": SEQUENTIAL_MUTATIONS,
            },
        )
        return agent


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider"]
