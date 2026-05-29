from __future__ import annotations

import ast
import inspect
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from copy import deepcopy
from typing import Any

from Agents.tools import Tool


TOOLHOP_MODE_CLOSED = "closed"
TOOLHOP_MODE_OPEN = "open"
TOOLHOP_TOOL_TIMEOUT_SECONDS = 10

_JSON_TYPE_MAP = {
    "string": "string",
    "boolean": "boolean",
    "integer": "integer",
    "number": "number",
    "array": "array",
    "object": "object",
    "null": "any",
}

_SANITIZED_MODULE_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


def _normalize_toolhop_mode(mode: str | None) -> str:
    normalized = str(mode or TOOLHOP_MODE_CLOSED).strip().lower()
    if normalized not in {TOOLHOP_MODE_CLOSED, TOOLHOP_MODE_OPEN}:
        raise ValueError(
            f"Unsupported ToolHop mode: {mode!r}. "
            f"Expected one of: {TOOLHOP_MODE_CLOSED}, {TOOLHOP_MODE_OPEN}."
        )
    return normalized


def _sanitize_function_block(source: str, index: int) -> Any:
    filename = f"<toolhop_function_{index}>"
    try:
        parsed = ast.parse(source, filename=filename, mode="exec")
    except SyntaxError:
        return compile(source, filename=filename, mode="exec")

    sanitized_body = []
    for node in parsed.body:
        if isinstance(node, _SANITIZED_MODULE_NODES):
            sanitized_body.append(node)
            continue
        if isinstance(node, ast.Assign) and _is_safe_literal_expression(node.value):
            sanitized_body.append(node)
            continue
        if isinstance(node, ast.AnnAssign) and node.value is not None and _is_safe_literal_expression(node.value):
            sanitized_body.append(node)
    if not sanitized_body:
        sanitized_body = parsed.body
    sanitized_module = ast.Module(body=sanitized_body, type_ignores=[])
    return compile(sanitized_module, filename=filename, mode="exec")


def _is_safe_literal_expression(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_safe_literal_expression(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            _is_safe_literal_expression(key) and _is_safe_literal_expression(value)
            for key, value in zip(node.keys, node.values)
            if key is not None
        )
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _is_safe_literal_expression(node.operand)
    return False


def _build_tool_inputs(parameters: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    parameters = parameters if isinstance(parameters, dict) else {}
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    tool_inputs: dict[str, dict[str, Any]] = {}

    if not isinstance(properties, dict):
        return tool_inputs

    for key, raw_spec in properties.items():
        spec = deepcopy(raw_spec) if isinstance(raw_spec, dict) else {}
        raw_type = spec.get("type", "any")
        nullable = bool(spec.get("nullable", False))

        if isinstance(raw_type, list):
            nullable = nullable or ("null" in raw_type)
            non_null_types = [value for value in raw_type if value != "null"]
            raw_type = non_null_types[0] if len(non_null_types) == 1 else "any"

        mapped_type = _JSON_TYPE_MAP.get(str(raw_type).strip().lower(), "any")
        if mapped_type == "any" and raw_type == "null":
            nullable = True

        entry = spec
        entry["type"] = mapped_type
        entry["description"] = str(entry.get("description", "")).strip() or f"Input parameter '{key}'."
        if key not in required or nullable:
            entry["nullable"] = True
        tool_inputs[str(key)] = entry

    return tool_inputs


def _coerce_function_arguments(function: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Align noisy ToolHop JSON-schema arguments with the executed Python signature."""
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return arguments

    parameters = signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()):
        return arguments

    accepted = {
        name
        for name, param in parameters.items()
        if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    if not accepted:
        return {}

    coerced = {key: value for key, value in arguments.items() if key in accepted}
    missing_required = [
        name
        for name, param in parameters.items()
        if name in accepted and param.default is inspect.Parameter.empty and name not in coerced
    ]
    if not missing_required:
        return coerced

    alias_groups = {
        "input": ("input_string", "string", "text", "name", "full_name", "value"),
        "input_string": ("input", "string", "text", "value"),
        "strings": ("input", "inputs", "items", "values", "names", "words"),
        "items": ("input", "inputs", "strings", "values", "names"),
        "values": ("input", "inputs", "strings", "items", "names"),
        "start_date": ("input_date", "base_date", "date"),
        "input_date": ("start_date", "base_date", "date"),
        "base_date": ("start_date", "input_date", "date"),
        "amount": ("days", "duration", "interval", "value"),
        "duration": ("amount", "days", "interval", "value"),
    }
    reverse_aliases: dict[str, set[str]] = {}
    for canonical, aliases in alias_groups.items():
        reverse_aliases.setdefault(canonical, set()).update(aliases)
        for alias in aliases:
            reverse_aliases.setdefault(alias, set()).add(canonical)
            reverse_aliases[alias].update(value for value in aliases if value != alias)

    for name in list(missing_required):
        for alias in reverse_aliases.get(name, set()):
            if alias in arguments:
                coerced[name] = arguments[alias]
                break

    missing_required = [name for name in missing_required if name not in coerced]
    if missing_required and len(arguments) == 1:
        sole_value = next(iter(arguments.values()))
        if isinstance(sole_value, dict):
            for name in list(missing_required):
                if name in sole_value:
                    coerced[name] = sole_value[name]
                    continue
                for alias in reverse_aliases.get(name, set()):
                    if alias in sole_value:
                        coerced[name] = sole_value[alias]
                        break
            missing_required = [name for name in missing_required if name not in coerced]

        if missing_required:
            if len(missing_required) == 1 and not isinstance(sole_value, dict):
                coerced[missing_required[0]] = sole_value
            elif isinstance(sole_value, (list, tuple)) and len(sole_value) >= len(missing_required):
                for name, value in zip(missing_required, sole_value):
                    coerced[name] = value

    return coerced


class ToolHopExecutionScope:
    def __init__(self, functions: list[str], timeout_seconds: int = TOOLHOP_TOOL_TIMEOUT_SECONDS):
        if not isinstance(functions, list) or not all(isinstance(item, str) for item in functions):
            raise TypeError("ToolHop functions must be a list of Python source strings.")
        self.functions = list(functions)
        self.timeout_seconds = timeout_seconds
        self.scope: dict[str, Any] = {"__builtins__": __builtins__}
        self._compile_functions()

    def _compile_functions(self) -> None:
        for index, function_source in enumerate(self.functions):
            code_object = _sanitize_function_block(function_source, index=index)
            exec(code_object, self.scope)

    def call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("ToolHop tool name must be a non-empty string.")
        if tool_name not in self.scope:
            raise KeyError(f"ToolHop tool '{tool_name}' is not defined in the current sample scope.")

        arguments = arguments if isinstance(arguments, dict) else {}
        function = self.scope[tool_name]
        arguments = _coerce_function_arguments(function, arguments)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(function, **arguments)
            try:
                return future.result(timeout=self.timeout_seconds)
            except FuturesTimeoutError as exc:
                raise TimeoutError(
                    f"ToolHop tool '{tool_name}' timed out after {self.timeout_seconds} seconds."
                ) from exc


class ToolHopSampleTool(Tool):
    skip_forward_signature_validation = True
    output_type = "any"

    def __init__(
        self,
        tool_spec: dict[str, Any],
        executor: ToolHopExecutionScope,
        *,
        subtask_hint: str | None = None,
    ) -> None:
        super().__init__()
        if not isinstance(tool_spec, dict):
            raise TypeError("ToolHop tool_spec must be a dictionary.")

        self.name = str(tool_spec.get("name", "")).strip()
        if not self.name:
            raise ValueError("ToolHop tool_spec is missing a valid tool name.")

        description = str(tool_spec.get("description", "")).strip()
        if subtask_hint:
            description = f"{description} Relevant subtask: {subtask_hint}".strip()
        self.description = description or f"ToolHop tool '{self.name}'."
        self.inputs = _build_tool_inputs(tool_spec.get("parameters"))
        self.executor = executor

    def forward(self, **kwargs):
        return self.executor.call(self.name, kwargs)


def build_toolhop_tools(
    sample: dict[str, Any],
    *,
    mode: str | None = TOOLHOP_MODE_CLOSED,
) -> list[Tool]:
    normalized_mode = _normalize_toolhop_mode(mode)
    if normalized_mode == TOOLHOP_MODE_OPEN:
        raise NotImplementedError(
            "ToolHop open-set mode is reserved in the CLI, but retrieval/index integration is not implemented yet."
        )

    if not isinstance(sample, dict):
        raise TypeError("ToolHop sample must be a dictionary.")

    functions = sample.get("functions")
    tools = sample.get("tools")
    if not isinstance(functions, list) or not functions:
        raise ValueError("ToolHop closed-set mode requires sample['functions'].")
    if not isinstance(tools, dict) or not tools:
        raise ValueError("ToolHop closed-set mode requires sample['tools'].")

    executor = ToolHopExecutionScope(functions)
    loaded_tools: list[Tool] = []
    for subtask_hint, tool_spec in tools.items():
        if not isinstance(tool_spec, dict):
            continue
        loaded_tools.append(
            ToolHopSampleTool(
                tool_spec,
                executor,
                subtask_hint=str(subtask_hint).strip() or None,
            )
        )
    return loaded_tools
