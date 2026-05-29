from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

try:
    from FlashOAgents import OpenAIServerModel
except ModuleNotFoundError:
    from Agents.models import OpenAIServerModel


DEFAULT_LOCAL_API_KEY = "local-llm"
SUPPORTED_BACKENDS = {"api", "local"}


@dataclass(frozen=True)
class LLMConfig:
    model: str
    backend: str
    api_key: Optional[str]
    api_base: Optional[str]


def _normalize_optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def get_default_model_name(default: str = "gpt-4.1-mini") -> str:
    return (
        _normalize_optional_string(os.environ.get("PLANNING_MODEL"))
        or _normalize_optional_string(os.environ.get("EXECUTE_MODEL"))
        or default
    )


def normalize_backend(value: Any) -> str:
    normalized = (_normalize_optional_string(value) or "api").lower()
    aliases = {
        "api": "api",
        "openai": "api",
        "remote": "api",
        "local": "local",
        "local_server": "local",
        "localhost": "local",
    }
    resolved = aliases.get(normalized)
    if resolved is None:
        supported = ", ".join(sorted(SUPPORTED_BACKENDS))
        raise ValueError(
            f"Unsupported model backend: {value!r}. Expected one of: {supported}."
        )
    return resolved


def resolve_llm_config(
    model: Any,
    *,
    backend: Any = None,
    api_key: Any = None,
    api_base: Any = None,
) -> LLMConfig:
    model_name = _normalize_optional_string(model)
    if model_name is None:
        raise ValueError("Model name is required.")

    resolved_backend = normalize_backend(
        backend
        or os.environ.get("MODEL_BACKEND")
        or os.environ.get("LLM_BACKEND")
        or "api"
    )

    resolved_api_key = (
        _normalize_optional_string(api_key)
        or _normalize_optional_string(os.environ.get("OPENAI_API_KEY"))
    )
    resolved_api_base = (
        _normalize_optional_string(api_base)
        or _normalize_optional_string(os.environ.get("OPENAI_BASE_URL"))
        or _normalize_optional_string(os.environ.get("OPENAI_API_BASE"))
    )

    if resolved_backend == "api":
        if resolved_api_key is None:
            raise ValueError(
                "OPENAI_API_KEY is required when --model-backend=api."
            )
    else:
        if resolved_api_base is None:
            raise ValueError(
                "A local OpenAI-compatible endpoint is required when "
                "--model-backend=local. Set --api-base or OPENAI_BASE_URL/OPENAI_API_BASE."
            )
        if resolved_api_key is None:
            resolved_api_key = (
                _normalize_optional_string(os.environ.get("LOCAL_LLM_API_KEY"))
                or DEFAULT_LOCAL_API_KEY
            )

    return LLMConfig(
        model=model_name,
        backend=resolved_backend,
        api_key=resolved_api_key,
        api_base=resolved_api_base,
    )


def create_chat_model(config: LLMConfig, **kwargs):
    init_kwargs = {key: value for key, value in kwargs.items() if value is not None}
    return OpenAIServerModel(
        model_id=config.model,
        api_key=config.api_key,
        api_base=config.api_base,
        **init_kwargs,
    )
