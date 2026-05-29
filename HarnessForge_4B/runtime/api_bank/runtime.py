from __future__ import annotations

import json
import os
import importlib.util
import inspect
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from Agents.tools import Tool


_JSON_TYPE_MAP = {
    "str": "string",
    "string": "string",
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "list": "array",
    "array": "array",
    "dict": "object",
    "object": "object",
}


def extract_api_descriptions(sample: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract API-Bank tool descriptions embedded as JSON lines in a sample."""
    if not isinstance(sample, dict):
        return []

    text_parts = [
        str(sample.get("instruction", "") or ""),
        str(sample.get("input", "") or ""),
    ]
    tools: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    candidate_names: list[str] = []

    for text in text_parts:
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{") or not line.endswith("}"):
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            tool_spec = _normalize_api_description(payload)
            name = tool_spec.get("name")
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            tools.append(tool_spec)
            candidate_names.append(str(name))

    for api_call in sample.get("api_calls") or []:
        if not isinstance(api_call, dict):
            continue
        name = str(api_call.get("api_name") or api_call.get("name") or "").strip()
        if name and name not in candidate_names:
            candidate_names.append(name)

    executor = get_api_bank_executor()
    real_tools: list[dict[str, Any]] = []
    real_seen: set[str] = set()
    for name in candidate_names:
        spec = executor.get_tool_spec(name) if executor is not None else None
        if spec and spec.get("name") not in real_seen:
            real_tools.append(spec)
            real_seen.add(str(spec.get("name")))
    if real_tools:
        for tool in tools:
            name = str(tool.get("name") or "")
            if name and name not in real_seen:
                real_tools.append(tool)
        return real_tools

    if not tools:
        for api_call in sample.get("api_calls") or []:
            if not isinstance(api_call, dict):
                continue
            name = str(api_call.get("api_name") or api_call.get("name") or "").strip()
            if not name or name in seen_names:
                continue
            raw_args = api_call.get("param_dict") or api_call.get("input") or {}
            input_parameters = {
                str(key): {
                    "type": _infer_json_type(value),
                    "description": f"Input parameter '{key}'.",
                }
                for key, value in (raw_args.items() if isinstance(raw_args, dict) else [])
            }
            tools.append(
                {
                    "name": name,
                    "description": f"API-Bank API {name}.",
                    "input_parameters": input_parameters,
                    "output_parameters": {},
                }
            )
            seen_names.add(name)

    return tools


def build_api_bank_tools(sample: dict[str, Any] | None) -> list[Tool]:
    specs = extract_api_descriptions(sample)
    executor = get_api_bank_executor()
    tools: list[Tool] = []
    for spec in specs:
        name = str(spec.get("name") or "").strip()
        if executor is not None and executor.has_tool(name):
            tools.append(APIBankExecutableTool(spec, executor))
        else:
            tools.append(APIBankMockTool(spec))
    return tools


def load_deepagent_api_bank_level1(data_dir: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Load DeepAgent's default API-Bank level-1-given-desc-e2e directory."""
    root = Path(data_dir).expanduser()
    rows: list[dict[str, Any]] = []
    # Match DeepAgent's APIBankDataLoader.load_level1_data(), which iterates
    # over os.listdir(data_dir) instead of lexicographically sorting files.
    for file_name in os.listdir(root):
        if not file_name.endswith(".jsonl"):
            continue
        file_path = root / file_name
        chat_history: list[dict[str, Any]] = []
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    chat_history.append(json.loads(line))
        api_calls = [
            {
                "api_name": turn.get("api_name"),
                "param_dict": turn.get("param_dict") or {},
                "result": turn.get("result"),
            }
            for turn in chat_history
            if isinstance(turn, dict) and turn.get("role") == "API"
        ]
        rows.append(
            {
                "file": file_path.name,
                "chat_history": chat_history,
                "api_calls": api_calls,
                "_api_bank_format": "deepagent_level1",
            }
        )
    return rows


def format_deepagent_dialogue(chat_history: list[dict[str, Any]]) -> str:
    """Format dialogue exactly like DeepAgent: up to and including last User turn."""
    last_user_idx = -1
    for idx, turn in enumerate(chat_history):
        if isinstance(turn, dict) and turn.get("role") == "User":
            last_user_idx = idx
    dialogue_turns = chat_history[: last_user_idx + 1] if last_user_idx != -1 else chat_history
    lines = []
    for turn in dialogue_turns:
        if not isinstance(turn, dict) or turn.get("role") == "API":
            continue
        role = turn.get("role", "User")
        text = turn.get("text", "")
        lines.append(f"{role}: {text}")
    return "\n".join(lines).strip()


def format_expected_api_requests(api_calls: list[dict[str, Any]]) -> str:
    rendered = []
    for api_call in api_calls:
        if not isinstance(api_call, dict):
            continue
        name = str(api_call.get("api_name") or api_call.get("name") or "").strip()
        args = api_call.get("param_dict") or api_call.get("input") or {}
        if not name:
            continue
        arg_text = ", ".join(f"{key}={_quote_api_value(value)}" for key, value in args.items()) if isinstance(args, dict) else ""
        rendered.append(f"{name}({arg_text})")
    return "API-Request: [" + ", ".join(rendered) + "]"


def _infer_json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _quote_api_value(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)
    return repr(str(value))


def _normalize_api_description(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or payload.get("apiCode") or "").strip()
    description = str(payload.get("description") or "").strip()
    raw_inputs = payload.get("input_parameters") or payload.get("parameters") or {}
    raw_outputs = payload.get("output_parameters") or payload.get("response") or {}

    return {
        "name": name,
        "description": description or f"API-Bank API {name}.",
        "input_parameters": raw_inputs if isinstance(raw_inputs, dict) else {},
        "output_parameters": raw_outputs if isinstance(raw_outputs, dict) else {},
    }


def _default_api_bank_root() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        project_root / "eval_bench" / "api-bank",
        project_root / "DeepAgent" / "data" / "API-Bank",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _default_apis_dir() -> Path:
    return Path(os.environ.get("API_BANK_APIS_DIR") or _default_api_bank_root() / "apis").expanduser()


def _default_database_dir() -> Path:
    return Path(os.environ.get("API_BANK_DATABASE_DIR") or _default_api_bank_root() / "init_database").expanduser()


_EXECUTOR_CACHE: dict[tuple[str, str], "APIBankRealExecutor"] = {}


def get_api_bank_executor(
    apis_dir: str | os.PathLike[str] | None = None,
    database_dir: str | os.PathLike[str] | None = None,
) -> "APIBankRealExecutor | None":
    apis_path = Path(apis_dir).expanduser() if apis_dir is not None else _default_apis_dir()
    database_path = Path(database_dir).expanduser() if database_dir is not None else _default_database_dir()
    if not apis_path.is_dir():
        return None
    key = (str(apis_path.resolve()), str(database_path.resolve()) if database_path.exists() else "")
    executor = _EXECUTOR_CACHE.get(key)
    if executor is None:
        executor = APIBankRealExecutor(apis_path, database_path)
        _EXECUTOR_CACHE[key] = executor
    return executor


class APIBankRealExecutor:
    def __init__(self, apis_dir: Path, database_dir: Path) -> None:
        self.apis_dir = apis_dir
        self.database_dir = database_dir
        self.init_databases = self._load_databases(database_dir)
        self.tool_classes: dict[str, type] = {}
        self.tool_specs: dict[str, dict[str, Any]] = {}
        self._load_tool_classes()
        self.token_checker = self._init_token_checker()

    def _load_databases(self, database_dir: Path) -> dict[str, Any]:
        databases: dict[str, Any] = {}
        if not database_dir.is_dir():
            return databases
        for file_path in database_dir.glob("*.json"):
            try:
                with file_path.open("r", encoding="utf-8") as handle:
                    databases[file_path.stem] = json.load(handle)
            except Exception:
                continue
        return databases

    def _load_tool_classes(self) -> None:
        apis_dir_str = str(self.apis_dir.resolve())
        if apis_dir_str not in sys.path:
            sys.path.insert(0, apis_dir_str)
        for file_path in sorted(self.apis_dir.glob("*.py")):
            if file_path.name in {"__init__.py", "api.py", "tool_search.py"}:
                continue
            try:
                module_name = f"mate_api_bank_{file_path.stem}_{abs(hash(str(file_path.resolve())))}"
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception:
                continue
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not (
                    isinstance(attr, type)
                    and hasattr(attr, "description")
                    and hasattr(attr, "input_parameters")
                    and hasattr(attr, "output_parameters")
                    and hasattr(attr, "call")
                ):
                    continue
                self.tool_classes[attr_name] = attr
                self.tool_specs[attr_name] = {
                    "name": attr_name,
                    "description": str(getattr(attr, "description", "") or f"API-Bank API {attr_name}."),
                    "input_parameters": getattr(attr, "input_parameters", {}) or {},
                    "output_parameters": getattr(attr, "output_parameters", {}) or {},
                }

    def _init_token_checker(self) -> Any:
        check_cls = self.tool_classes.get("CheckToken")
        if check_cls is None:
            return None
        try:
            return self._instantiate_tool(check_cls)
        except Exception:
            return None

    def has_tool(self, name: str) -> bool:
        return bool(name and name in self.tool_classes)

    def get_tool_spec(self, name: str) -> dict[str, Any] | None:
        spec = self.tool_specs.get(name)
        return deepcopy(spec) if spec else None

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool_class = self.tool_classes.get(tool_name)
        if tool_class is None:
            return {
                "api_name": tool_name,
                "input": arguments,
                "output": None,
                "exception": f"Tool '{tool_name}' not found",
            }
        try:
            tool_instance = self._instantiate_tool(tool_class)
            return tool_instance.call(**arguments)
        except Exception as exc:
            return {
                "api_name": tool_name,
                "input": arguments,
                "output": None,
                "exception": str(exc),
            }

    def _instantiate_tool(self, tool_class: type) -> Any:
        init_kwargs: dict[str, Any] = {}
        init_args: list[Any] = []
        database_name = getattr(tool_class, "database_name", None)
        database = self.init_databases.get(database_name) if database_name else None
        try:
            signature = inspect.signature(tool_class.__init__)
        except Exception:
            signature = None

        if database is not None:
            if signature and "init_database" in signature.parameters:
                init_kwargs["init_database"] = database
            else:
                init_args.append(database)

        needs_token = False
        input_parameters = getattr(tool_class, "input_parameters", {}) or {}
        if isinstance(input_parameters, dict):
            needs_token = "token" in input_parameters
        token_checker = getattr(self, "token_checker", None)
        if needs_token and token_checker is not None and tool_class.__name__ != "CheckToken":
            if signature and "token_checker" in signature.parameters:
                init_kwargs["token_checker"] = token_checker
            else:
                init_args.append(token_checker)

        return tool_class(*init_args, **init_kwargs)


def _build_tool_inputs(input_parameters: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inputs: dict[str, dict[str, Any]] = {}
    for param_name, raw_info in input_parameters.items():
        info = deepcopy(raw_info) if isinstance(raw_info, dict) else {}
        raw_type = str(info.get("type", "string")).strip()
        raw_type_lower = raw_type.lower()
        mapped_type = "any" if raw_type_lower.startswith("union") else _JSON_TYPE_MAP.get(raw_type_lower, "string")
        entry = {
            "type": mapped_type,
            "description": str(info.get("description", "") or f"Input parameter '{param_name}'."),
        }
        if mapped_type == "array":
            entry["items"] = {"type": "string"}
        if not bool(info.get("required", True)):
            entry["nullable"] = True
        inputs[str(param_name)] = entry
    return inputs


class APIBankMockTool(Tool):
    skip_forward_signature_validation = True
    output_type = "any"

    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__()
        self.name = str(spec.get("name", "")).strip()
        if not self.name:
            raise ValueError("API-Bank tool spec is missing a valid name.")
        self.description = str(spec.get("description", "") or f"API-Bank API {self.name}.")
        self.inputs = _build_tool_inputs(spec.get("input_parameters", {}) or {})
        self.output_parameters = spec.get("output_parameters", {}) or {}

    def forward(self, **kwargs):
        return {
            "api_name": self.name,
            "input": kwargs,
            "output": {
                "status": "called",
                "output_parameters": self.output_parameters,
            },
            "exception": None,
        }


class APIBankExecutableTool(Tool):
    skip_forward_signature_validation = True
    output_type = "any"

    def __init__(self, spec: dict[str, Any], executor: APIBankRealExecutor) -> None:
        super().__init__()
        self.name = str(spec.get("name", "")).strip()
        if not self.name:
            raise ValueError("API-Bank tool spec is missing a valid name.")
        self.description = str(spec.get("description", "") or f"API-Bank API {self.name}.")
        self.inputs = _build_tool_inputs(spec.get("input_parameters", {}) or {})
        self.executor = executor

    def forward(self, **kwargs):
        return self.executor.execute(self.name, kwargs)
