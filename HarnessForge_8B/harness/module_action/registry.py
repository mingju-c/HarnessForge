"""Central registry for action providers."""

from __future__ import annotations

import importlib

from .base_action import ActionProvider


ACTION_REGISTRY: dict[str, tuple[str, str]] = {
    "default": ("default", "DefaultActionProvider"),
    "flash_searcher": ("default", "DefaultActionProvider"),
    "single_react": ("single_react", "SingleReactActionProvider"),
    "bird_sql": ("single_react", "SingleReactActionProvider"),
    "bird_sql_flashsearcher": ("single_react", "SingleReactActionProvider"),
    "oagent": ("default", "DefaultActionProvider"),
    "owl": ("default", "DefaultActionProvider"),
    "planner": ("default", "DefaultActionProvider"),
    "joy_agent": ("joy_agent", "JoyAgentActionProvider"),
    "co-sight": ("co_sight", "CosightActionProvider"),
    "co_sight": ("co_sight", "CosightActionProvider"),
    "flowsearch": ("flowsearch", "FlowsearchActionProvider"),
    "agentorchestra": ("agentorchestra", "AgentOrchestraActionProvider"),
}


PROVIDER_PACKAGE = f"{__package__}.providers"


def list_action_systems() -> list[str]:
    return sorted(ACTION_REGISTRY.keys())


def resolve_action_entry(action_system: str) -> tuple[str, str]:
    if action_system in ACTION_REGISTRY:
        return ACTION_REGISTRY[action_system]
    if action_system.startswith("planner_"):
        return ACTION_REGISTRY["default"]
    raise ValueError(
        f"Unknown action system: {action_system}. "
        f"Available options: {list_action_systems()}"
    )


def get_action_provider(action_system: str) -> ActionProvider:
    module_name, class_name = resolve_action_entry(action_system)
    provider_module = importlib.import_module(f"{PROVIDER_PACKAGE}.{module_name}")
    provider_class = getattr(provider_module, class_name, None)
    if provider_class is None:
        raise ValueError(
            f"Action provider not found: {class_name} in {PROVIDER_PACKAGE}.{module_name}"
        )
    return provider_class()
