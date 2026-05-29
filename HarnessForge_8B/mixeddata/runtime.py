from __future__ import annotations

import json
import os
import re
import sys
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from Agents.tools import Tool


_MIXED_VERL_ROOT = os.getenv("MIXED_VERL_ROOT")
DEFAULT_VERL_ROOT = Path(_MIXED_VERL_ROOT).expanduser() if _MIXED_VERL_ROOT else None
DEFAULT_SEARCHQA_DEVICE = os.getenv("MATE_MIXED_SEARCHQA_DEVICE", "cpu")

_JSON_TYPE_MAP = {
    "string": "string",
    "boolean": "boolean",
    "integer": "integer",
    "number": "number",
    "array": "array",
    "object": "object",
    "null": "any",
}


def _ensure_verl_path() -> None:
    if DEFAULT_VERL_ROOT is None:
        return
    verl_root = str(DEFAULT_VERL_ROOT)
    if verl_root and verl_root not in sys.path:
        sys.path.append(verl_root)


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{\"":
        return value
    try:
        return json.loads(stripped)
    except Exception:
        return value


def _as_dict(value: Any) -> dict[str, Any]:
    value = _maybe_json(value)
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    value = _maybe_json(value)
    return value if isinstance(value, list) else []


def _prompt_messages(sample: dict[str, Any] | None) -> list[dict[str, Any]]:
    prompt = (sample or {}).get("prompt", [])
    if hasattr(prompt, "tolist"):
        prompt = prompt.tolist()
    if not isinstance(prompt, list):
        return []
    return [item for item in prompt if isinstance(item, dict)]


def _prompt_text(sample: dict[str, Any] | None, role: str) -> str:
    for message in _prompt_messages(sample):
        if str(message.get("role") or "").lower() == role:
            content = message.get("content")
            if isinstance(content, str):
                return content
    return ""


def strip_tool_schema_section(system_content: str) -> str:
    marker = "Available tool schemas:"
    if marker not in system_content:
        return system_content.strip()
    return system_content.split(marker, 1)[0].strip()


def get_mixed_benchmark(sample: dict[str, Any] | None) -> str:
    if not isinstance(sample, dict):
        return "unknown"
    extra_info = _as_dict(sample.get("extra_info"))
    create_kwargs = get_mixed_create_kwargs(sample)
    for value in (
        sample.get("benchmark"),
        extra_info.get("benchmark"),
        create_kwargs.get("benchmark"),
        sample.get("data_source"),
    ):
        text = str(value or "").lower()
        if "envscaler" in text:
            return "envscaler"
        if "searchqa" in text:
            return "searchqa"
        if "toolhop" in text:
            return "toolhop"
    return "unknown"


def get_mixed_create_kwargs(sample: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(sample, dict):
        return {}
    extra_info = _as_dict(sample.get("extra_info"))
    tools_kwargs = _as_dict(extra_info.get("tools_kwargs"))
    mixed_call = _as_dict(tools_kwargs.get("mixed_call"))
    create_kwargs = _as_dict(mixed_call.get("create_kwargs"))
    return deepcopy(create_kwargs)


def extract_mixed_ground_truth(sample: dict[str, Any] | None) -> str:
    if not isinstance(sample, dict):
        return ""
    reward_model = _as_dict(sample.get("reward_model"))
    extra_info = _as_dict(sample.get("extra_info"))
    for value in (
        reward_model.get("ground_truth"),
        sample.get("answer"),
        extra_info.get("answer"),
        extra_info.get("golden_answers"),
    ):
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            return json.dumps(list(value), ensure_ascii=False)
        text = str(value).strip()
        if text:
            return text
    return ""


def extract_mixed_task(sample: dict[str, Any] | None) -> str:
    if not isinstance(sample, dict):
        return ""

    extra_info = _as_dict(sample.get("extra_info"))
    user_task = (
        str(sample.get("question") or "").strip()
        or str(extra_info.get("question") or "").strip()
        or _prompt_text(sample, "user").strip()
    )
    benchmark = get_mixed_benchmark(sample)
    if benchmark in {"toolhop", "searchqa"}:
        terminal_instruction = (
            f"{benchmark.upper()} terminal rule: this is a short-answer QA task. "
            "Use the available evidence tools only until a candidate answer is supported. "
            "Before reaching max_steps, call final_answer with only the raw answer value. "
            "Do not finish this task without calling final_answer."
        )
        return f"{terminal_instruction}\n\nTask:\n{user_task}".strip()

    if benchmark != "envscaler":
        return user_task

    envscaler_instruction = (
        "EnvScaler execution rule: use the task-specific tools to update the environment state. "
        "When all requested state changes are complete, call complete_task exactly once with "
        "answer set to 'Task Completed'. complete_task is the terminal action: after it succeeds, "
        "do not call complete_task again and do not call any other tool."
    )
    context = str(sample.get("mate_system_context") or "").strip()
    if not context:
        context = strip_tool_schema_section(_prompt_text(sample, "system"))
    if context:
        return f"{context}\n\n{envscaler_instruction}\n\nTask:\n{user_task}".strip()
    return f"{envscaler_instruction}\n\nTask:\n{user_task}".strip()


def _schema_to_tool_inputs(parameters: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    parameters = parameters if isinstance(parameters, dict) else {}
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    if not isinstance(properties, dict):
        return {}

    inputs: dict[str, dict[str, Any]] = {}
    for key, raw_spec in properties.items():
        spec = deepcopy(raw_spec) if isinstance(raw_spec, dict) else {}
        raw_type = spec.get("type", "any")
        nullable = bool(spec.get("nullable", False))
        if isinstance(raw_type, list):
            nullable = nullable or "null" in raw_type
            non_null_types = [item for item in raw_type if item != "null"]
            raw_type = non_null_types[0] if len(non_null_types) == 1 else "any"
        mapped_type = _JSON_TYPE_MAP.get(str(raw_type).strip().lower(), "any")
        if mapped_type == "any" and raw_type == "null":
            nullable = True
        spec["type"] = mapped_type
        spec["description"] = str(spec.get("description", "")).strip() or f"Input parameter '{key}'."
        if key not in required or nullable:
            spec["nullable"] = True
        inputs[str(key)] = spec
    return inputs


def _normalize_openai_tool_spec(raw_spec: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw_spec, dict):
        return None
    function = raw_spec.get("function") if raw_spec.get("type") == "function" else raw_spec
    if not isinstance(function, dict):
        return None
    name = str(function.get("name") or "").strip()
    if not name:
        return None
    parameters = _as_dict(function.get("parameters") or function.get("parameters_json"))
    return {
        "name": name,
        "description": str(function.get("description") or f"Tool '{name}'.").strip(),
        "parameters": parameters,
    }


def _decode_tool_schemas_from_system(system_content: str) -> list[dict[str, Any]]:
    marker = "Available tool schemas:"
    if marker in system_content:
        system_content = system_content.split(marker, 1)[1]
    start = system_content.find("[")
    if start < 0:
        return []
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(system_content[start:])
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [spec for spec in (_normalize_openai_tool_spec(item) for item in value) if spec]


def _sample_tool_schemas(sample: dict[str, Any]) -> list[dict[str, Any]]:
    raw_schemas = sample.get("tool_schemas")
    if isinstance(raw_schemas, list) and raw_schemas:
        return [spec for spec in (_normalize_openai_tool_spec(item) for item in raw_schemas) if spec]
    return _decode_tool_schemas_from_system(_prompt_text(sample, "system"))


def _toolhop_sample_from_create_kwargs(sample: dict[str, Any], create_kwargs: dict[str, Any]) -> dict[str, Any]:
    functions = [item for item in _as_list(create_kwargs.get("functions_json")) if isinstance(item, str)]
    tools_json = _as_list(create_kwargs.get("tools_json"))
    tools: dict[str, dict[str, Any]] = {}
    for index, raw_spec in enumerate(tools_json):
        spec = _normalize_openai_tool_spec(raw_spec)
        if not spec:
            continue
        key = str(raw_spec.get("subtask") or index) if isinstance(raw_spec, dict) else str(index)
        tools[key] = spec
    if not tools:
        for index, spec in enumerate(_sample_tool_schemas(sample)):
            if spec["name"] == "final_answer":
                continue
            tools[str(index)] = spec
    return {
        "question": str(sample.get("question") or _as_dict(sample.get("extra_info")).get("question") or ""),
        "answer": extract_mixed_ground_truth(sample),
        "functions": functions,
        "tools": tools,
    }


class SearchQASearchTool(Tool):
    name = "search"
    description = "Offline Wikipedia search over the AgentGym SearchQA retriever."
    inputs = {"query": {"type": "string", "description": "Search query."}}
    output_type = "string"

    def __init__(self, create_kwargs: dict[str, Any]):
        super().__init__()
        self.create_kwargs = deepcopy(create_kwargs)

    def forward(self, query: str) -> str:
        _ensure_verl_path()
        os.environ.setdefault("MIXED_SEARCHQA_DEVICE", DEFAULT_SEARCHQA_DEVICE)
        try:
            from .mixed_tool import _get_searchqa_retriever
        except Exception:
            from recipe.mixed_agent.mixed_tool import _get_searchqa_retriever

        retriever = _get_searchqa_retriever(self.create_kwargs)
        text = retriever.format_results(query=str(query).strip(), topk=self.create_kwargs.get("topk"))
        return f"<information>\n{text}\n</information>"


class EnvScalerState:
    def __init__(self, sample: dict[str, Any], create_kwargs: dict[str, Any]):
        self.sample = sample
        self.create_kwargs = deepcopy(create_kwargs)
        self.session = None
        self.lock = threading.Lock()
        self.done = False
        self.last_reward: float | None = None

    def _ensure_session(self):
        if self.session is not None:
            return self.session
        _ensure_verl_path()
        try:
            from .mixed_tool import EnvScalerSession, _load_env_items
        except Exception:
            from recipe.mixed_agent.mixed_tool import EnvScalerSession, _load_env_items

        envs_path = self.create_kwargs.get("envs_path")
        task_record = self.create_kwargs.get("task_record")
        if not isinstance(task_record, dict):
            task_record = _as_dict(self.create_kwargs.get("task_record_json"))
        if not envs_path or not isinstance(task_record, dict):
            raise ValueError("EnvScaler create_kwargs must include envs_path and task_record_json.")
        env_items = _load_env_items(envs_path)
        env_id = task_record["env_id"]
        if env_id not in env_items:
            raise ValueError(f"EnvScaler env_id '{env_id}' not found in {envs_path}.")
        self.session = EnvScalerSession(task_record=task_record, env_item=env_items[env_id])
        return self.session

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        with self.lock:
            session = self._ensure_session()
            observation, reward, done = session.call(name, arguments)
            if done:
                self.done = True
                self.last_reward = float(reward)
                extra_info = self.sample.setdefault("extra_info", {})
                reward_scores = extra_info.setdefault("rollout_reward_scores", {})
                reward_scores["envscaler_score"] = float(reward)
                reward_scores["envscaler_done"] = 1.0
            return str(observation)


class EnvScalerDynamicTool(Tool):
    skip_forward_signature_validation = True
    output_type = "string"

    def __init__(self, spec: dict[str, Any], state: EnvScalerState):
        super().__init__()
        self.name = spec["name"]
        self.description = spec.get("description") or f"EnvScaler tool '{self.name}'."
        self.terminal_tool = self.name == "complete_task"
        if self.terminal_tool:
            self.description = (
                f"{self.description} This is the terminal EnvScaler action. "
                "Call it exactly once after all requested state changes are complete; "
                "once it succeeds, the current task must stop immediately."
            )
        self.inputs = _schema_to_tool_inputs(spec.get("parameters"))
        self.state = state

    def forward(self, **kwargs):
        return self.state.call(self.name, kwargs)

    def is_terminal_observation(self, observation: Any) -> bool:
        return self.terminal_tool and self.state.done

    def terminal_answer(self, arguments: dict[str, Any], observation: Any) -> str:
        return "Task Completed"


def _build_envscaler_tools(sample: dict[str, Any], create_kwargs: dict[str, Any]) -> list[Tool]:
    schemas = _sample_tool_schemas(sample)
    state = EnvScalerState(sample, create_kwargs)
    tools: list[Tool] = []
    seen: set[str] = set()
    for spec in schemas:
        name = spec.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        tools.append(EnvScalerDynamicTool(spec, state))
    if "complete_task" not in seen:
        tools.append(
            EnvScalerDynamicTool(
                {
                    "name": "complete_task",
                    "description": "Finish an EnvScaler task after all required state changes have been made.",
                    "parameters": {
                        "type": "object",
                        "required": ["answer"],
                        "properties": {
                            "answer": {
                                "type": "string",
                                "description": "Must be exactly Task Completed.",
                            }
                        },
                    },
                },
                state,
            )
        )
    return tools


def build_mixeddata_tools(sample: dict[str, Any]) -> list[Tool]:
    benchmark = get_mixed_benchmark(sample)
    create_kwargs = get_mixed_create_kwargs(sample)

    if benchmark == "toolhop":
        from runtime.toolhop.runtime import build_toolhop_tools

        return build_toolhop_tools(_toolhop_sample_from_create_kwargs(sample, create_kwargs), mode="closed")
    if benchmark == "searchqa":
        return [SearchQASearchTool(create_kwargs)]
    if benchmark == "envscaler":
        return _build_envscaler_tools(sample, create_kwargs)
    raise ValueError(f"Unsupported MixedData benchmark: {benchmark}")
