from __future__ import annotations

import json
import shutil
from collections import OrderedDict
from pathlib import Path
from textwrap import dedent
from typing import Any

import yaml


HARNESS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = HARNESS_ROOT.parent
ACTION_PROVIDER_ROOT = HARNESS_ROOT / "module_action" / "providers"
ACTION_PROMPT_ROOT = HARNESS_ROOT / "module_action" / "prompts"
PLANNING_MODULE_ROOT = HARNESS_ROOT / "module_planning" / "planning"
PLANNING_PROMPT_ROOT = HARNESS_ROOT / "module_planning" / "prompts"
DEFAULT_MEMORY_SYSTEM = "lightweight_memory"
DEFAULT_BENCH_TYPE = "bird"


def _load_registry_names() -> tuple[OrderedDict[str, tuple[str, str]], OrderedDict[str, tuple[str, str]]]:
    from module_action.registry import ACTION_REGISTRY
    from module_planning.registry import PLANNING_REGISTRY

    return OrderedDict(PLANNING_REGISTRY), OrderedDict(ACTION_REGISTRY)


def _canonical_system_name(
    registry: OrderedDict[str, tuple[str, str]],
    module_name: str,
) -> str:
    if module_name in registry:
        return module_name
    for system_name, (registered_module_name, _) in registry.items():
        if registered_module_name == module_name:
            return system_name
    raise ValueError(f"No canonical system name found for module '{module_name}'")


def _module_exists(module_root: Path, module_name: str) -> bool:
    return (module_root / f"{module_name}.py").exists()


def _prompt_dir(prompt_root: Path, prompt_key: str) -> Path | None:
    direct = prompt_root / prompt_key
    if direct.exists():
        return direct
    dashed = prompt_root / prompt_key.replace("_", "-")
    if dashed.exists():
        return dashed
    underscored = prompt_root / prompt_key.replace("-", "_")
    if underscored.exists():
        return underscored
    return None


def _copy_prompt_dir(src_dir: Path | None, dst_root: Path) -> None:
    if src_dir is None or not src_dir.exists():
        return
    dst_dir = dst_root / src_dir.name
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)


def _load_single_react_prompt_templates() -> dict[str, Any]:
    from module_action.providers.single_react import SINGLE_REACT_PROMPT_TEMPLATES

    return SINGLE_REACT_PROMPT_TEMPLATES


def _dedupe_planning_registry(
    planning_registry: OrderedDict[str, tuple[str, str]],
) -> list[dict[str, str]]:
    seen_modules: set[str] = set()
    planning_entries: list[dict[str, str]] = []
    for system_name, (module_name, class_name) in planning_registry.items():
        if module_name in seen_modules:
            continue
        seen_modules.add(module_name)
        planning_entries.append(
            {
                "planning_system": _canonical_system_name(planning_registry, module_name),
                "planning_module": module_name,
                "planning_class": class_name,
            }
        )
    return planning_entries


def _resolve_action_for_planning(
    planning_module: str,
    action_registry: OrderedDict[str, tuple[str, str]],
) -> tuple[str, str, str]:
    if _module_exists(ACTION_PROVIDER_ROOT, planning_module):
        action_system = _canonical_system_name(action_registry, planning_module)
        return action_system, planning_module, "matched_same_name"
    return "single_react", "single_react", "fallback_single_react"


def _is_supported_planning(entry: dict[str, str]) -> bool:
    return _module_exists(PLANNING_MODULE_ROOT, entry["planning_module"])


def _build_bundle_specs() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    planning_registry, action_registry = _load_registry_names()
    bundle_specs: list[dict[str, str]] = []
    skipped_specs: list[dict[str, str]] = []

    for planning_entry in _dedupe_planning_registry(planning_registry):
        planning_system = planning_entry["planning_system"]
        planning_module = planning_entry["planning_module"]
        if not _is_supported_planning(planning_entry):
            skipped_specs.append(
                {
                    **planning_entry,
                    "reason": "planning_module_missing",
                }
            )
            continue

        action_system, action_module, pairing_reason = _resolve_action_for_planning(
            planning_module,
            action_registry,
        )
        bundle_specs.append(
            {
                **planning_entry,
                "action_system": action_system,
                "action_module": action_module,
                "pairing_reason": pairing_reason,
                "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
                "default_bench_type": DEFAULT_BENCH_TYPE,
            }
        )

    return bundle_specs, skipped_specs


def _next_harness_index(count: int) -> int:
    existing_indices: list[int] = []
    for path in HARNESS_ROOT.iterdir():
        if not path.is_dir():
            continue
        name = path.name
        if not name.startswith("harness"):
            continue
        suffix = name.removeprefix("harness")
        if suffix.isdigit():
            existing_indices.append(int(suffix))
    return (max(existing_indices) + 1) if existing_indices else 1


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _bundle_builder_source(bundle_name: str, spec: dict[str, str]) -> str:
    return dedent(
        f"""
        from __future__ import annotations

        from dataclasses import replace
        from pathlib import Path

        from Agents.agents import ToolCallingAgent
        from module_action.base_action import ActionContext
        from module_action.registry import get_action_provider


        HARNESS_NAME = "{bundle_name}"
        PLANNING_SYSTEM = "{spec["planning_system"]}"
        ACTION_SYSTEM = "{spec["action_system"]}"
        DEFAULT_BENCH_TYPE = "{spec["default_bench_type"]}"
        DEFAULT_MEMORY_SYSTEM = "{spec["recommended_memory_system"]}"
        PAIRING_REASON = "{spec["pairing_reason"]}"


        def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
            if tool is not None and hasattr(tool, "agent"):
                setattr(tool, "agent", agent)


        def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
            if getattr(agent, "planning_system", None) != "owl":
                return
            if not hasattr(agent, "web_memory") or agent.web_memory is None:
                agent.web_memory = []
            if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
                agent.reasoning_memory = []


        def prepare_context(context: ActionContext) -> ActionContext:
            bench_type = context.bench_type or DEFAULT_BENCH_TYPE
            if bench_type == "bird" and not context.db_path:
                raise ValueError(
                    f"{{HARNESS_NAME}} requires db_path when bench_type='bird'."
                )
            prompts_type = context.prompts_type or PLANNING_SYSTEM
            return replace(
                context,
                planning_system=PLANNING_SYSTEM,
                action_system=ACTION_SYSTEM,
                prompts_type=prompts_type,
                bench_type=bench_type,
                project_root=Path(__file__).resolve().parents[2],
            )


        def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
            prepared_context = prepare_context(context)
            action_provider = get_action_provider(prepared_context.action_system)
            agent = action_provider.build(prepared_context)

            setattr(agent, "planning_system", prepared_context.planning_system)
            setattr(agent, "action_system", prepared_context.action_system)
            setattr(agent, "harness_name", HARNESS_NAME)
            setattr(
                agent,
                "harness_metadata",
                {{
                    "planning_system": PLANNING_SYSTEM,
                    "action_system": ACTION_SYSTEM,
                    "default_bench_type": DEFAULT_BENCH_TYPE,
                    "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
                    "pairing_reason": PAIRING_REASON,
                }},
            )

            if prepared_context.vector_tool is not None:
                prepared_context.vector_tool.memory = agent.memory

            _bind_agent_reference(agent, prepared_context.process_tool)
            _bind_agent_reference(agent, prepared_context.end_process_tool)
            _bind_agent_reference(agent, prepared_context.delete_memory_tool)
            _bind_agent_reference(agent, prepared_context.executor_tool)
            _bind_agent_reference(agent, prepared_context.refine_tool)

            _ensure_owl_memory(agent)
            return agent
        """
    ).strip() + "\n"


def _bundle_init_source() -> str:
    return 'from .builder import build_agent_from_context\n\n__all__ = ["build_agent_from_context"]\n'


def _bundle_description(bundle_name: str, spec: dict[str, str]) -> str:
    return dedent(
        f"""
        Harness summary:
        - Planning: local planning behavior defined by this bundle.
        - Execution: local action behavior paired for this bundle.
        - Memory: bundle-recommended reusable memory backend.
        - Default bench: `{spec["default_bench_type"]}`

        Coordination pattern:
        - Reason: `{spec["pairing_reason"]}`
        - If a same-name action module exists, use it directly.
        - Otherwise fall back to `single_react`.

        Runtime notes:
        - Generated bundle: `{bundle_name}`
        - Builder enforces `bench_type={spec["default_bench_type"]}` by default unless the caller already supplies one.
        - For BIRD runs, `db_path` must exist in `ActionContext`.
        - The builder keeps the current `ActionContext` object flow and only normalizes planning/action pairing.
        """
    ).strip() + "\n"


def _action_provider_wrapper_source(spec: dict[str, str]) -> str:
    return dedent(
        f"""
        from module_action.registry import get_action_provider


        ACTION_SYSTEM = "{spec["action_system"]}"
        ACTION_MODULE = "{spec["action_module"]}"


        def get_provider():
            return get_action_provider(ACTION_SYSTEM)
        """
    ).strip() + "\n"


def _planning_wrapper_source(spec: dict[str, str]) -> str:
    return dedent(
        f"""
        from module_planning.registry import get_planning_class


        PLANNING_SYSTEM = "{spec["planning_system"]}"
        PLANNING_MODULE = "{spec["planning_module"]}"
        PlanningClass = get_planning_class(PLANNING_SYSTEM)


        __all__ = ["PLANNING_SYSTEM", "PLANNING_MODULE", "PlanningClass"]
        """
    ).strip() + "\n"


def _planning_module_init_source(spec: dict[str, str]) -> str:
    module_name = spec["planning_module"]
    return f"from .{module_name} import PLANNING_MODULE, PLANNING_SYSTEM, PlanningClass\n\n__all__ = [\"PLANNING_SYSTEM\", \"PLANNING_MODULE\", \"PlanningClass\"]\n"


def _memory_wrapper_source() -> str:
    return dedent(
        """
        from module_memory.providers.lightweight_memory_provider import LightweightMemoryProvider


        MEMORY_SYSTEM = "lightweight_memory"


        __all__ = ["MEMORY_SYSTEM", "LightweightMemoryProvider"]
        """
    ).strip() + "\n"


def _create_bundle(bundle_name: str, spec: dict[str, str]) -> dict[str, str]:
    bundle_root = HARNESS_ROOT / bundle_name
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    _write_text(bundle_root / "__init__.py", _bundle_init_source())
    _write_text(bundle_root / "builder.py", _bundle_builder_source(bundle_name, spec))
    _write_text(bundle_root / "Description.md", _bundle_description(bundle_name, spec))

    action_module_root = bundle_root / "action_module"
    _write_text(action_module_root / "__init__.py", 'from .provider import ACTION_MODULE, ACTION_SYSTEM, get_provider\n\n__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "get_provider"]\n')
    _write_text(action_module_root / "provider.py", _action_provider_wrapper_source(spec))

    planning_module_root = bundle_root / "planning_module"
    _write_text(planning_module_root / "__init__.py", _planning_module_init_source(spec))
    _write_text(
        planning_module_root / f'{spec["planning_module"]}.py',
        _planning_wrapper_source(spec),
    )

    memory_module_root = bundle_root / "memory_module"
    _write_text(memory_module_root / "__init__.py", 'from .lightweight_memory_provider import MEMORY_SYSTEM, LightweightMemoryProvider\n\n__all__ = ["MEMORY_SYSTEM", "LightweightMemoryProvider"]\n')
    _write_text(memory_module_root / "lightweight_memory_provider.py", _memory_wrapper_source())

    planning_prompt_src = _prompt_dir(PLANNING_PROMPT_ROOT, spec["planning_system"])
    _copy_prompt_dir(planning_prompt_src, planning_module_root / "prompts")

    if spec["action_system"] == "single_react":
        _write_yaml(
            action_module_root / "prompts" / "single_react" / "toolcalling_agent.yaml",
            _load_single_react_prompt_templates(),
        )
    else:
        action_prompt_src = _prompt_dir(ACTION_PROMPT_ROOT, spec["action_system"])
        _copy_prompt_dir(action_prompt_src, action_module_root / "prompts")

    return {
        "bundle_name": bundle_name,
        **spec,
    }


def main() -> None:
    bundle_specs, skipped_specs = _build_bundle_specs()
    start_index = _next_harness_index(len(bundle_specs))

    generated_specs: list[dict[str, str]] = []
    for offset, spec in enumerate(bundle_specs):
        bundle_name = f"harness{start_index + offset}"
        generated_specs.append(_create_bundle(bundle_name, spec))

    manifest = {
        "default_bench_type": DEFAULT_BENCH_TYPE,
        "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
        "generated": generated_specs,
        "skipped": skipped_specs,
    }
    _write_text(
        HARNESS_ROOT / "generated_harnesses.json",
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    )


if __name__ == "__main__":
    main()
