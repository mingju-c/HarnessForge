"""Factory helpers for building memory providers."""

from __future__ import annotations

import importlib
import harness_runtime
from pathlib import Path
from typing import Any

from .base_memory import WriteOnlyMemoryProvider
from .config import get_memory_config
from .memory_types import MemoryType, PROVIDER_MAPPING


PROVIDER_PACKAGE = f"{__package__}.providers"
SHARED_MODEL_CACHE_KEYS = {"model_cache_dir", "embedding_model_cache", "embedding_cache_dir"}
NON_NAMESPACED_STORAGE_KEYS = SHARED_MODEL_CACHE_KEYS


def resolve_relative_paths(value: Any, base_dir: Path) -> Any:
    """Resolve config values like './x' or '.\\x' to absolute paths."""
    if isinstance(value, dict):
        return {k: resolve_relative_paths(v, base_dir) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_relative_paths(v, base_dir) for v in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("./") or stripped.startswith(".\\"):
            return str((base_dir / stripped[2:]).resolve())
    return value


def rebase_storage_paths(
    value: Any,
    *,
    default_storage_root: Path,
    storage_root: Path | None,
    key: str | None = None,
) -> Any:
    if storage_root is None:
        return value

    if isinstance(value, dict):
        return {
            key: rebase_storage_paths(
                child_value,
                default_storage_root=default_storage_root,
                storage_root=storage_root,
                key=key,
            )
            for key, child_value in value.items()
        }
    if isinstance(value, list):
        return [
            rebase_storage_paths(
                item,
                default_storage_root=default_storage_root,
                storage_root=storage_root,
                key=key,
            )
            for item in value
        ]
    if not isinstance(value, str) or key in SHARED_MODEL_CACHE_KEYS:
        return value

    try:
        resolved_path = Path(value).resolve(strict=False)
        relative_path = resolved_path.relative_to(default_storage_root)
    except Exception:
        return value
    return str((storage_root / relative_path).resolve())


def apply_storage_namespace(
    value: Any,
    *,
    storage_root: Path,
    namespace: str | None,
    key: str | None = None,
) -> Any:
    if not namespace:
        return value

    if isinstance(value, dict):
        return {
            child_key: apply_storage_namespace(
                child_value,
                storage_root=storage_root,
                namespace=namespace,
                key=child_key,
            )
            for child_key, child_value in value.items()
        }

    if isinstance(value, list):
        return [
            apply_storage_namespace(
                item,
                storage_root=storage_root,
                namespace=namespace,
                key=key,
            )
            for item in value
        ]

    if not isinstance(value, str) or key in NON_NAMESPACED_STORAGE_KEYS:
        return value

    try:
        path_value = Path(value)
        resolved_path = path_value.resolve(strict=False)
        relative_path = resolved_path.relative_to(storage_root)
    except Exception:
        return value

    return str((storage_root / namespace / relative_path).resolve())


def build_memory_provider(
    memory_system: str | None,
    base_dir: Path,
    model: Any = None,
    write_only: bool | None = None,
    storage_namespace: str | None = None,
    storage_root: Path | None = None,
) -> Any:
    """Build and initialize a memory provider by memory system name."""
    if not memory_system:
        return None

    normalized = memory_system.strip().lower()
    default_storage_root = (base_dir / "storage").resolve()
    resolved_storage_root = storage_root.resolve() if storage_root is not None else default_storage_root
    storage_namespace = (
        str(storage_namespace).strip()
        if storage_namespace is not None and str(storage_namespace).strip()
        else None
    )

    provider_cls = None
    config_memory_type = None
    if storage_namespace:
        try:
            harness_memory_module = importlib.import_module(
                f"{harness_runtime.get_harness_memory_package_name(storage_namespace)}.provider"
            )
        except ModuleNotFoundError:
            harness_memory_module = None

        if harness_memory_module is not None:
            harness_memory_system = getattr(harness_memory_module, "MEMORY_SYSTEM", None)
            harness_provider_cls = getattr(harness_memory_module, "MemoryProvider", None)
            if (
                harness_memory_system is not None
                and harness_provider_cls is not None
                and str(harness_memory_system).strip().lower() == normalized
            ):
                provider_cls = harness_provider_cls
                config_memory_type = MemoryType.LIGHTWEIGHT_MEMORY

    if provider_cls is None:
        try:
            memory_type = MemoryType(normalized)
        except ValueError as exc:
            supported = ", ".join(sorted(mem.value for mem in MemoryType))
            raise ValueError(
                f"Unknown memory system: {memory_system}. Supported values: {supported}"
            ) from exc
        config_memory_type = memory_type
        provider_meta = PROVIDER_MAPPING.get(memory_type)
        if not provider_meta:
            raise ValueError(f"No provider mapping found for memory system: {memory_system}")
        class_name, module_name = provider_meta

        try:
            module = importlib.import_module(f"{PROVIDER_PACKAGE}.{module_name}")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"Failed to import memory provider module for '{memory_system}': "
                f"{PROVIDER_PACKAGE}.{module_name}. Missing dependency/module: {exc.name}"
            ) from exc

        provider_cls = getattr(module, class_name, None)
        if provider_cls is None:
            raise ValueError(
                f"Provider class not found: {class_name} in {PROVIDER_PACKAGE}.{module_name}"
            )

    provider_config = resolve_relative_paths(get_memory_config(config_memory_type), base_dir)
    provider_config = rebase_storage_paths(
        provider_config,
        default_storage_root=default_storage_root,
        storage_root=resolved_storage_root,
    )
    provider_config = apply_storage_namespace(
        provider_config,
        storage_root=resolved_storage_root,
        namespace=storage_namespace,
    )
    if model is not None:
        provider_config["model"] = model
    if write_only is None:
        write_only = bool(provider_config.get("write_only", False))
    else:
        write_only = bool(write_only)
    provider_config["write_only"] = write_only

    provider = provider_cls(config=provider_config)
    init_ok = provider.initialize()
    if init_ok is False:
        raise RuntimeError(f"Memory provider initialize() returned False: {memory_system}")
    if write_only:
        provider = WriteOnlyMemoryProvider(provider)
    return provider
