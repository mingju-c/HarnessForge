"""Central registry for planning modules and prompt template loaders."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml


PLANNING_REGISTRY: dict[str, tuple[str, str]] = {
    "flash_searcher": ("flash_searcher", "FlashSearcherPlanning"),
    "bird_sql": ("bird_sql", "BirdSQLPlanning"),
    "oagent": ("oagent", "OAgentPlanning"),
    "joy_agent": ("joy_agent", "JoyAgentPlanning"),
    "owl": ("owl", "OwlPlanning"),
    "co-sight": ("co_sight", "CosightPlanning"),
    "co_sight": ("co_sight", "CosightPlanning"),
    "flowsearch": ("flowsearch", "FlowSearcherPlanning"),
    "agentorchestra": ("agentorchestra", "AgentOrchestraPlanning"),
    "planner": ("planner", "PlannerPlanning"),
}


MODULE_ROOT = Path(__file__).resolve().parent
ACTION_MODULE_ROOT = MODULE_ROOT.parent / "module_action"
PLANNING_PACKAGE = f"{__package__}.planning"


def list_planning_systems() -> list[str]:
    """Return supported planning system names."""
    return sorted(PLANNING_REGISTRY.keys())


def resolve_planning_entry(planning_system: str) -> tuple[str, str]:
    """
    Resolve a planning system name to (module_name, class_name).

    Supports dynamic planner modules generated with `planner_*`.
    """
    if planning_system in PLANNING_REGISTRY:
        return PLANNING_REGISTRY[planning_system]
    if planning_system.startswith("planner_"):
        return planning_system, "PlannerPlanning"
    raise ValueError(
        f"Unknown planning system: {planning_system}. "
        f"Available options: {list_planning_systems()}"
    )


def get_planning_class(planning_system: str) -> type[Any]:
    """Import and return the planning class for a given planning system."""
    module_name, class_name = resolve_planning_entry(planning_system)
    planning_module = importlib.import_module(f"{PLANNING_PACKAGE}.{module_name}")
    planning_class = getattr(planning_module, class_name, None)
    if planning_class is None:
        raise ValueError(
            f"Planning class not found: {class_name} in {PLANNING_PACKAGE}.{module_name}"
        )
    return planning_class


def _candidate_module_roots(
    project_root: Path | None,
    default_root: Path,
    module_name: str,
) -> list[Path]:
    roots: list[Path] = []
    if project_root is not None:
        project_root = project_root.resolve()
        alternate_name = {
            "module_planning": "planning_module",
            "module_action": "action_module",
            "module_memory": "memory_module",
        }.get(module_name)
        roots.extend(
            [
                project_root / module_name,
                project_root / "harness" / module_name,
            ]
        )
        if alternate_name is not None:
            roots.extend(
                [
                    project_root / alternate_name,
                    project_root / "harness" / alternate_name,
                ]
            )
    roots.append(default_root)
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        root_str = str(root)
        if root_str in seen:
            continue
        seen.add(root_str)
        deduped.append(root)
    return deduped


def _candidate_prompt_names(prompts_type: str) -> list[str]:
    candidates = [prompts_type]
    if "_" in prompts_type:
        candidates.append(prompts_type.replace("_", "-"))
    if "-" in prompts_type:
        candidates.append(prompts_type.replace("-", "_"))
    return list(dict.fromkeys(candidates))


def _resolve_prompt_path(
    module_roots: list[Path],
    prompts_type: str,
    *,
    required: bool,
) -> Path | None:
    """Resolve a prompt template path from prompts_type."""
    candidates = _candidate_prompt_names(prompts_type)

    searched_paths: list[Path] = []
    for module_root in module_roots:
        flat_path = module_root / "prompts" / "toolcalling_agent.yaml"
        searched_paths.append(flat_path)
        if flat_path.exists():
            return flat_path

        for candidate in candidates:
            candidate_path = module_root / "prompts" / candidate / "toolcalling_agent.yaml"
            searched_paths.append(candidate_path)
            if candidate_path.exists():
                return candidate_path

    if required:
        raise FileNotFoundError(
            f"No prompt file found for prompts_type '{prompts_type}'. "
            f"Searched: {', '.join(str(path) for path in searched_paths)}"
        )
    return None


def resolve_prompt_path(project_root: Path | None, prompts_type: str) -> Path:
    """Resolve the planning-side prompt template path for a prompts_type."""
    return _resolve_prompt_path(
        _candidate_module_roots(project_root, MODULE_ROOT, "module_planning"),
        prompts_type,
        required=True,
    )


def resolve_action_prompt_path(project_root: Path | None, prompts_type: str) -> Path | None:
    """Resolve the action-side prompt template path for a prompts_type if it exists."""
    return _resolve_prompt_path(
        _candidate_module_roots(project_root, ACTION_MODULE_ROOT, "module_action"),
        prompts_type,
        required=False,
    )


def _load_prompt_file(prompt_path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Prompt file is not a mapping: {prompt_path}")
    return loaded


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(base_value, value)
        else:
            merged[key] = value
    return merged


def _strip_prompt_sections(
    payload: Any,
    blocked_keys: set[str] | None = None,
) -> Any:
    if blocked_keys is None:
        blocked_keys = {"planning", "summary"}

    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if key in blocked_keys:
                continue
            cleaned[key] = _strip_prompt_sections(value, blocked_keys)
        return cleaned

    if isinstance(payload, list):
        return [_strip_prompt_sections(item, blocked_keys) for item in payload]

    return payload


def merge_prompt_templates(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    return _deep_merge_dicts(base, override)


def load_planning_prompt_templates(
    project_root: Path | None,
    prompts_type: str,
) -> dict[str, Any]:
    planning_prompt_path = resolve_prompt_path(
        project_root=project_root,
        prompts_type=prompts_type,
    )
    return _load_prompt_file(planning_prompt_path)


def load_action_prompt_templates(
    project_root: Path | None,
    prompts_type: str,
) -> dict[str, Any]:
    action_prompt_path = resolve_action_prompt_path(
        project_root=project_root,
        prompts_type=prompts_type,
    )
    if action_prompt_path is None:
        return {}
    return _strip_prompt_sections(_load_prompt_file(action_prompt_path))


def load_prompt_templates(project_root: Path | None, prompts_type: str) -> dict[str, Any]:
    """
    Load prompt templates YAML for a prompts package.

    Planning-side prompts provide the planning/summarization prompts, while
    action-side prompts provide runtime execution/orchestration prompts. When
    both exist, action-side keys override planning-side keys.
    """
    planning_prompts = load_planning_prompt_templates(
        project_root=project_root,
        prompts_type=prompts_type,
    )
    action_prompts = load_action_prompt_templates(
        project_root=project_root,
        prompts_type=prompts_type,
    )
    return merge_prompt_templates(planning_prompts, action_prompts)
