from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_HARNESS_PACKAGES = ("harness_factory", "harness")
PACKAGE_ROOT_ENV = "HARNESS_PACKAGE_ROOT"



def get_project_root() -> Path:
    return Path(__file__).resolve().parent



def _normalize_package_name(value: str | None) -> str:
    if value is None:
        return DEFAULT_HARNESS_PACKAGES[0]
    package_name = str(value).strip().strip(".")
    return package_name or DEFAULT_HARNESS_PACKAGES[0]



def _package_path(package_name: str) -> Path:
    return Path(*package_name.split("."))



def _resolve_package_root(package_name: str, package_root: str | os.PathLike[str] | None = None) -> Path:
    package_rel = _package_path(package_name)
    candidates: list[Path] = []

    if package_root:
        hint = Path(package_root).resolve()
        candidates.append((hint / package_rel).resolve())
        if hint.name == package_rel.name:
            candidates.append(hint)

    candidates.append((get_project_root() / package_rel).resolve())

    for candidate in candidates:
        if candidate.exists():
            return candidate

    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        f"Configured harness package '{package_name}' was not found. Searched: {searched}"
    )



def get_active_harness_package() -> str:
    configured = os.environ.get("HARNESS_PACKAGE")
    if configured:
        return _normalize_package_name(configured)

    project_root = get_project_root()
    for package_name in DEFAULT_HARNESS_PACKAGES:
        harness_root = project_root.joinpath(*package_name.split(".")).resolve()
        if harness_root.exists():
            return package_name
    return DEFAULT_HARNESS_PACKAGES[0]



def get_active_harness_root() -> Path:
    package_name = get_active_harness_package()
    package_root = os.environ.get(PACKAGE_ROOT_ENV)
    return _resolve_package_root(package_name, package_root)



def _prepend_path(path: Path) -> None:
    path_str = str(path.resolve())
    while path_str in sys.path:
        sys.path.remove(path_str)
    sys.path.insert(0, path_str)



def ensure_harness_on_path() -> Path:
    active_root = get_active_harness_root()

    # Keep legacy shared modules importable via top-level names like module_memory.*
    ordered_roots: list[Path] = [active_root]
    for package_name in DEFAULT_HARNESS_PACKAGES:
        candidate = (get_project_root() / _package_path(package_name)).resolve()
        if candidate.exists() and candidate != active_root:
            ordered_roots.append(candidate)

    for root in reversed(ordered_roots):
        _prepend_path(root)

    # Make the active package importable as <package_name>.<bundle_name>
    _prepend_path(active_root.parent)
    importlib.invalidate_caches()
    return active_root



def activate_harness_package(
    package_name: str,
    package_root: str | os.PathLike[str] | None = None,
) -> Path:
    normalized = _normalize_package_name(package_name)
    os.environ["HARNESS_PACKAGE"] = normalized
    if package_root is not None:
        os.environ[PACKAGE_ROOT_ENV] = str(Path(package_root).resolve())
    else:
        os.environ.pop(PACKAGE_ROOT_ENV, None)
    return ensure_harness_on_path()



ACTIVE_HARNESS_ROOT = ensure_harness_on_path()



def _import_first_available(module_names: list[str]):
    ensure_harness_on_path()
    last_error = None
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ModuleNotFoundError("No import candidates were provided.")



def get_harness_module_name(harness_name: str) -> str:
    return f"{get_active_harness_package()}.{harness_name}"



def import_harness_module(harness_name: str):
    ensure_harness_on_path()
    return importlib.import_module(get_harness_module_name(harness_name))



def get_harness_memory_package_name(harness_name: str) -> str:
    return f"{get_harness_module_name(harness_name)}.memory_module"



def get_memory_factory_module(harness_name: str | None = None):
    candidates: list[str] = []
    if harness_name:
        candidates.append(f"{get_harness_memory_package_name(harness_name)}.factory")
    candidates.extend(["module_memory.factory", "harness.module_memory.factory"])
    return _import_first_available(candidates)



def get_memory_types_module(
    *,
    memory_provider: Any | None = None,
    harness_name: str | None = None,
):
    candidates: list[str] = []
    if memory_provider is not None:
        provider_module_name = type(memory_provider).__module__
        package_name = provider_module_name.rsplit(".", 1)[0]
        candidates.append(f"{package_name}.memory_types")
    if harness_name:
        candidates.append(f"{get_harness_memory_package_name(harness_name)}.memory_types")
    candidates.extend(["module_memory.memory_types", "harness.module_memory.memory_types"])
    return _import_first_available(candidates)



def build_memory_provider(
    *,
    memory_system: str | None,
    base_dir: Path,
    model: Any = None,
    write_only: bool | None = None,
    storage_namespace: str | None = None,
    storage_root: Path | None = None,
):
    factory_module = get_memory_factory_module(storage_namespace)
    return factory_module.build_memory_provider(
        memory_system=memory_system,
        base_dir=base_dir,
        model=model,
        write_only=write_only,
        storage_namespace=storage_namespace,
        storage_root=storage_root,
    )
