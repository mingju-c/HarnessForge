from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from Agents.tools import Tool


TAUBENCH_DOMAINS = {"retail", "airline"}
TAUBENCH_SPLITS = {
    "retail": {"train", "dev", "test"},
    "airline": {"test"},
}

TAUBENCH_RESPOND_TOOL = "respond"

_JSON_TYPE_MAP = {
    "string": "string",
    "boolean": "boolean",
    "integer": "integer",
    "number": "number",
    "array": "array",
    "object": "object",
    "null": "any",
}


def _candidate_taubench_roots(project_root: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    env_root = os.getenv("TAU_BENCH_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())

    if project_root is not None:
        project_root = Path(project_root).resolve()
        candidates.extend(
            [
                project_root.parent / "Bench" / "tau-bench",
                project_root.parent.parent / "Bench" / "tau-bench",
                project_root / "Bench" / "tau-bench",
            ]
        )

    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[4] / "Bench" / "tau-bench",
            here.parents[3] / "Bench" / "tau-bench",
        ]
    )
    return candidates


def ensure_taubench_importable(project_root: Path | None = None) -> None:
    try:
        import tau_bench  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    for candidate in _candidate_taubench_roots(project_root):
        if (candidate / "tau_bench").is_dir():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            try:
                import tau_bench  # noqa: F401

                return
            except ModuleNotFoundError:
                continue

    raise ModuleNotFoundError(
        "Could not import tau_bench. Install it with `python3 -m pip install -e "
        "<TAU_BENCH_ROOT>` or set TAU_BENCH_ROOT."
    )


def _validate_domain_split(domain: str, split: str) -> tuple[str, str]:
    domain = str(domain).strip().lower()
    split = str(split).strip().lower()
    if domain not in TAUBENCH_DOMAINS:
        raise ValueError(f"Unsupported tau-bench domain: {domain!r}")
    if split not in TAUBENCH_SPLITS[domain]:
        supported = ", ".join(sorted(TAUBENCH_SPLITS[domain]))
        raise ValueError(
            f"Unsupported tau-bench split {split!r} for {domain}. Supported: {supported}."
        )
    return domain, split


def _load_task_list(domain: str, split: str) -> list[Any]:
    ensure_taubench_importable()
    domain, split = _validate_domain_split(domain, split)
    if domain == "retail":
        if split == "test":
            from tau_bench.envs.retail.tasks_test import TASKS_TEST as tasks
        elif split == "train":
            from tau_bench.envs.retail.tasks_train import TASKS_TRAIN as tasks
        elif split == "dev":
            from tau_bench.envs.retail.tasks_dev import TASKS_DEV as tasks
        else:
            raise ValueError(f"Unknown retail split: {split}")
        return list(tasks)

    if domain == "airline":
        from tau_bench.envs.airline.tasks_test import TASKS as tasks

        return list(tasks)

    raise ValueError(f"Unsupported tau-bench domain: {domain}")


def load_taubench_items(domain: str, split: str) -> list[dict[str, Any]]:
    domain, split = _validate_domain_split(domain, split)
    tasks = _load_task_list(domain, split)
    return [
        {
            "task_id": index,
            "_global_index": index + 1,
            "taubench_domain": domain,
            "taubench_split": split,
            "question": f"tau-bench {domain}/{split} task {index}",
        }
        for index, _task in enumerate(tasks)
    ]


def parse_taubench_uri(uri: str) -> tuple[str, str]:
    raw = str(uri).strip()
    if raw.startswith("taubench://"):
        raw = raw[len("taubench://") :]
    parts = [part for part in raw.replace(":", "/").split("/") if part]
    if len(parts) != 2:
        raise ValueError(
            f"Invalid tau-bench selector {uri!r}. Expected taubench://<domain>/<split>."
        )
    return _validate_domain_split(parts[0], parts[1])


def _make_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _make_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_make_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _make_jsonable(value.model_dump())
    return str(value)


@dataclass
class TauBenchSession:
    domain: str
    split: str
    task_id: int
    user_model: str
    user_provider: str
    user_strategy: str
    env: Any
    initial_observation: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    done: bool = False
    reward: float = 0.0
    info: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def step(self, action_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        from tau_bench.types import Action

        with self.lock:
            if self.done:
                return {
                    "observation": "Episode already finished.",
                    "done": True,
                    "reward": self.reward,
                    "info": self.info,
                }

            response = self.env.step(Action(name=action_name, kwargs=kwargs or {}))
            self.done = bool(response.done)
            self.reward = float(response.reward or 0.0)
            self.info = _make_jsonable(response.info)
            event = {
                "action": action_name,
                "arguments": _make_jsonable(kwargs or {}),
                "observation": response.observation,
                "done": self.done,
                "reward": self.reward,
                "source": self.info.get("source") if isinstance(self.info, dict) else None,
            }
            self.events.append(event)
            return {
                "observation": response.observation,
                "done": self.done,
                "reward": self.reward,
                "info": self.info,
            }

    def terminal_payload(self) -> dict[str, Any]:
        return {
            "taubench_done": self.done,
            "taubench_reward": self.reward,
            "taubench_domain": self.domain,
            "taubench_split": self.split,
            "taubench_task_id": self.task_id,
            "taubench_user_model": self.user_model,
            "taubench_user_provider": self.user_provider,
            "taubench_user_strategy": self.user_strategy,
            "taubench_info": self.info,
            "taubench_events": self.events,
        }


def prepare_taubench_item(item: dict[str, Any], project_root: Path | None = None) -> TauBenchSession:
    ensure_taubench_importable(project_root)
    if not isinstance(item, dict):
        raise TypeError("tau-bench item must be a dictionary.")

    cached = item.get("_taubench_session")
    if isinstance(cached, TauBenchSession):
        return cached

    domain, split = _validate_domain_split(
        item.get("taubench_domain") or item.get("domain") or "retail",
        item.get("taubench_split") or item.get("split") or "test",
    )
    task_id = int(item.get("task_id", item.get("_global_index", 1) - 1))
    user_model = str(item.get("_taubench_user_model") or item.get("user_model") or "gpt-4o")
    user_provider = str(
        item.get("_taubench_user_model_provider")
        or item.get("user_model_provider")
        or "openai"
    )
    user_strategy = str(
        item.get("_taubench_user_strategy") or item.get("user_strategy") or "llm"
    )

    from tau_bench.envs import get_env

    env = get_env(
        domain,
        user_strategy=user_strategy,
        user_model=user_model,
        user_provider=user_provider,
        task_split=split,
        task_index=task_id,
    )
    reset_response = env.reset(task_index=task_id)
    session = TauBenchSession(
        domain=domain,
        split=split,
        task_id=task_id,
        user_model=user_model,
        user_provider=user_provider,
        user_strategy=user_strategy,
        env=env,
        initial_observation=reset_response.observation,
        info={"task": _make_jsonable(reset_response.info.task), "source": "user"},
    )
    item["_taubench_session"] = session
    return session


def _mate_inputs_from_json_schema(parameters: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    parameters = parameters if isinstance(parameters, dict) else {}
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    tool_inputs: dict[str, dict[str, Any]] = {}
    if not isinstance(properties, dict):
        return tool_inputs

    for key, raw_spec in properties.items():
        spec = dict(raw_spec) if isinstance(raw_spec, dict) else {}
        raw_type = spec.get("type", "any")
        nullable = bool(spec.get("nullable", False))
        if isinstance(raw_type, list):
            nullable = nullable or "null" in raw_type
            non_null_types = [value for value in raw_type if value != "null"]
            raw_type = non_null_types[0] if len(non_null_types) == 1 else "any"

        mapped_type = _JSON_TYPE_MAP.get(str(raw_type).strip().lower(), "any")
        if raw_type == "null":
            nullable = True
        spec["type"] = mapped_type
        spec["description"] = str(spec.get("description", "")).strip() or f"Input '{key}'."
        if key not in required or nullable:
            spec["nullable"] = True
        tool_inputs[str(key)] = spec
    return tool_inputs


class TauBenchEnvTool(Tool):
    skip_forward_signature_validation = True
    output_type = "any"
    terminal_tool = True

    def __init__(self, tool_info: dict[str, Any], session: TauBenchSession) -> None:
        function_info = tool_info.get("function", {}) if isinstance(tool_info, dict) else {}
        self.name = str(function_info.get("name", "")).strip()
        if not self.name:
            raise ValueError("tau-bench tool is missing function.name")
        self.description = str(function_info.get("description", "")).strip()
        self.inputs = _mate_inputs_from_json_schema(function_info.get("parameters"))
        self.session = session
        super().__init__()

    def forward(self, **kwargs: Any) -> dict[str, Any]:
        response = self.session.step(self.name, kwargs)
        return {
            "observation": response["observation"],
            "done": response["done"],
            "reward": response["reward"],
            "source": response["info"].get("source") if isinstance(response["info"], dict) else self.name,
        }

    def is_terminal_observation(self, observation: Any) -> bool:
        return _observation_done(observation)

    def terminal_answer(self, tool_arguments: Any, observation: Any) -> str:
        return json.dumps(self.session.terminal_payload(), ensure_ascii=False)


class TauBenchRespondTool(Tool):
    name = TAUBENCH_RESPOND_TOOL
    description = (
        "Send exactly one natural-language message to the simulated tau-bench user. "
        "Use this whenever you need to ask the user for information, ask for confirmation, "
        "or tell the user what you have done."
    )
    inputs = {
        "content": {
            "type": "string",
            "description": "The message to send to the simulated user.",
        }
    }
    output_type = "any"
    terminal_tool = True
    skip_forward_signature_validation = True

    def __init__(self, session: TauBenchSession) -> None:
        self.session = session
        super().__init__()

    def forward(self, content: str) -> dict[str, Any]:
        response = self.session.step(TAUBENCH_RESPOND_TOOL, {"content": content})
        return {
            "user_response": response["observation"],
            "done": response["done"],
            "reward": response["reward"],
        }

    def is_terminal_observation(self, observation: Any) -> bool:
        return _observation_done(observation)

    def terminal_answer(self, tool_arguments: Any, observation: Any) -> str:
        return json.dumps(self.session.terminal_payload(), ensure_ascii=False)


def _observation_done(observation: Any) -> bool:
    if isinstance(observation, dict):
        return bool(observation.get("done") or observation.get("taubench_done"))
    if isinstance(observation, str):
        try:
            data = json.loads(observation)
            if isinstance(data, dict):
                return bool(data.get("done") or data.get("taubench_done"))
        except Exception:
            return False
    return False


def build_taubench_tools(sample: dict[str, Any], context: Any = None) -> list[Tool]:
    project_root = getattr(context, "project_root", None) if context is not None else None
    session = prepare_taubench_item(sample, project_root=project_root)
    tools = [TauBenchEnvTool(tool_info, session) for tool_info in session.env.tools_info]
    tools.append(TauBenchRespondTool(session))
    return tools


def build_taubench_prompt(item: dict[str, Any], project_root: Path | None = None) -> str:
    session = prepare_taubench_item(item, project_root=project_root)
    wiki = str(getattr(session.env, "wiki", "")).strip()
    return f"""You are solving a tau-bench {session.domain} customer-service task.

Follow the domain policy below and interact with the simulated user until their goal is satisfied or policy requires transfer.

Important:
1. Use only one tool call per step. This environment is stateful.
2. Use `{TAUBENCH_RESPOND_TOOL}` to speak to the user. Do not call `final_answer` during the conversation.
3. Before consequential database updates, follow the policy and obtain explicit user confirmation when required.
4. Base decisions on tool observations, not guesses.
5. When a tool observation says the episode is done, stop; the benchmark reward is computed automatically.

Domain policy:
{wiki}

Conversation start:
User: {session.initial_observation}
"""
