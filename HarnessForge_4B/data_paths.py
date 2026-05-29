from __future__ import annotations

import os
from pathlib import Path


AEVOLVE_DATA_ROOT_ENV = "AEVOLVE_DATA_ROOT"


def _iter_default_shared_data_candidates(project_root: Path) -> list[Path]:
    workspace_root = project_root.parent
    workspace_parent = workspace_root.parent
    workspace_name = workspace_root.name

    sibling_names: list[str] = []
    for suffix in ("_new", "-new"):
        if workspace_name.endswith(suffix):
            sibling_name = workspace_name[: -len(suffix)].strip()
            if sibling_name:
                sibling_names.append(sibling_name)

    candidates: list[Path] = []
    seen: set[str] = set()
    for sibling_name in sibling_names:
        candidate = (workspace_parent / sibling_name / project_root.name / "data").resolve()
        key = candidate.as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def resolve_project_data_root(project_root: Path) -> Path:
    project_root = Path(project_root).resolve()

    env_value = str(os.environ.get(AEVOLVE_DATA_ROOT_ENV, "")).strip()
    if env_value:
        candidate = Path(env_value).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        return candidate.resolve()

    local_data_root = (project_root / "data").resolve()
    if local_data_root.exists():
        return local_data_root

    for candidate in _iter_default_shared_data_candidates(project_root):
        if candidate.exists():
            return candidate

    return local_data_root
