from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_HARNESS_ROOT = PROJECT_ROOT / "harness_factory" / "rounds" / "round_00_base"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "round1_examples"
MANIFEST_NAME = "manifest.json"
COMBINED_PROMPT_NAME = "prompt_examples.md"
DEFAULT_HARNESS_NAMES = tuple(f"harness{i}" for i in range(1, 8))
INCLUDE_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".txt"}
SKIP_DIRS = {"__pycache__"}
BUILDER_CONSTANTS = (
    "HARNESS_NAME",
    "PLANNING_SYSTEM",
    "ACTION_SYSTEM",
    "DEFAULT_BENCH_TYPE",
    "DEFAULT_MEMORY_SYSTEM",
    "PAIRING_REASON",
)


class LiteralString(str):
    """Marker string so YAML uses literal block style for multiline strings."""


class LiteralDumper(yaml.SafeDumper):
    """Safe YAML dumper with literal-block support for multiline strings."""


def _literal_presenter(dumper: yaml.SafeDumper, data: LiteralString) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


LiteralDumper.add_representer(LiteralString, _literal_presenter)


def _literalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _literalize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_literalize(item) for item in value]
    if isinstance(value, str) and "\n" in value:
        return LiteralString(value.rstrip("\n"))
    return value


def _read_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8-sig")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n"))


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


def _normalize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_payload(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_normalize_payload(item) for item in value]
    if isinstance(value, str):
        return _normalize_text(value)
    return value


def _extract_builder_metadata(builder_path: Path) -> dict[str, Any]:
    source = _read_text(builder_path)
    tree = ast.parse(source, filename=str(builder_path))

    metadata: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name not in BUILDER_CONSTANTS:
            continue
        try:
            metadata[name.lower()] = ast.literal_eval(node.value)
        except Exception:
            continue
    return metadata


def _extract_provider_constant(path: Path, constant_name: str) -> Any | None:
    if not path.exists():
        return None
    source = _read_text(path)
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != constant_name:
            continue
        try:
            return ast.literal_eval(node.value)
        except Exception:
            pass
        value = node.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr == 'value'
            and isinstance(value.value, ast.Attribute)
            and isinstance(value.value.value, ast.Name)
            and value.value.value.id == 'MemoryType'
        ):
            return value.value.attr.lower()
        if (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == 'MemoryType'
        ):
            return value.attr.lower()
    match = re.search(rf"{constant_name}\\s*=\\s*['\"]([^'\"]+)['\"]", source)
    if match:
        return match.group(1)
    memory_match = re.search(rf'{constant_name}\s*=\s*MemoryType\.([A-Z_]+)\.value', source)
    if memory_match:
        return memory_match.group(1).lower()
    return None


def _populate_missing_metadata(metadata: dict[str, Any], harness_dir: Path) -> dict[str, Any]:
    enriched = dict(metadata)
    enriched.setdefault('harness_name', harness_dir.name)
    if 'planning_system' not in enriched:
        planning_system = _extract_provider_constant(harness_dir / 'planning_module' / 'provider.py', 'PLANNING_SYSTEM')
        if planning_system is not None:
            enriched['planning_system'] = planning_system
    if 'action_system' not in enriched:
        action_system = _extract_provider_constant(harness_dir / 'action_module' / 'provider.py', 'ACTION_SYSTEM')
        if action_system is not None:
            enriched['action_system'] = action_system
    if 'default_memory_system' not in enriched:
        memory_system = _extract_provider_constant(harness_dir / 'memory_module' / 'provider.py', 'MEMORY_SYSTEM')
        if memory_system is not None:
            enriched['default_memory_system'] = memory_system
    return enriched


def _file_group(rel_path: str) -> tuple[int, str]:
    normalized = rel_path.replace("\\", "/")
    if normalized == "builder.py":
        return (0, normalized)
    if normalized == "Description.md":
        return (1, normalized)
    if normalized == "report.md":
        return (2, normalized)
    if normalized == "__init__.py":
        return (3, normalized)
    if normalized.startswith("planning_module/"):
        return (4, normalized)
    if normalized.startswith("action_module/"):
        return (5, normalized)
    if normalized.startswith("memory_module/"):
        return (6, normalized)
    return (7, normalized)


def _collect_source_files(harness_dir: Path) -> dict[str, str]:
    source_files: dict[str, str] = {}
    for path in harness_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in INCLUDE_SUFFIXES:
            continue
        rel_path = path.relative_to(harness_dir).as_posix()
        source_files[rel_path] = _read_text(path)

    return {
        rel_path: source_files[rel_path]
        for rel_path in sorted(source_files, key=_file_group)
    }


def _load_metrics(metrics_path: Path) -> dict[str, Any]:
    if not metrics_path.exists():
        return {}
    return json.loads(metrics_path.read_text(encoding="utf-8"))


def _render_metric_lines(metrics: dict[str, Any]) -> list[str]:
    if not metrics:
        return ["- Metrics: unavailable"]

    ordered_fields = [
        ("num_tasks", "Evaluated tasks"),
        ("answer_correct", "Exact accuracy"),
        ("has_valid_answer", "Valid answer rate"),
        ("path_score", "Average path score"),
        ("average_actions", "Average actions"),
        ("average_tool_calls", "Average tool calls"),
        ("tokens_avg", "Average total tokens"),
        ("runtime_avg_sec", "Average runtime (sec)"),
    ]
    lines: list[str] = []
    for key, label in ordered_fields:
        if key not in metrics:
            continue
        value = metrics[key]
        if isinstance(value, float) and key in {"answer_correct", "has_valid_answer"}:
            rendered = f"{value * 100:.2f}%"
        elif isinstance(value, float) and key == "path_score":
            rendered = f"{value:.4f}"
        else:
            rendered = str(value)
        lines.append(f"- {label}: {rendered}")
    if "source_result_file" in metrics:
        lines.append(f"- Source result file: {metrics['source_result_file']}")
    elif "result_source" in metrics:
        lines.append(f"- Source result file: {metrics['result_source']}")
    return lines or ["- Metrics: unavailable"]


def _select_prompt_files(file_order: list[str], source_files: dict[str, str]) -> list[str]:
    preferred: list[str] = [
        "builder.py",
        "Description.md",
        "__init__.py",
        "planning_module/provider.py",
        "action_module/provider.py",
        "memory_module/provider.py",
    ]
    preferred.extend(
        path
        for path in file_order
        if path.startswith("planning_module/prompts/") and path.endswith((".yaml", ".yml"))
    )
    preferred.extend(
        path
        for path in file_order
        if path.startswith("action_module/prompts/") and path.endswith((".yaml", ".yml"))
    )
    preferred.extend(
        path
        for path in file_order
        if path.startswith("memory_module/") and path.endswith(".py") and path != "memory_module/provider.py"
    )
    return list(dict.fromkeys(path for path in preferred if path in source_files))


def _render_prompt_ready_example(
    *,
    harness_name: str,
    payload: dict[str, Any],
) -> str:
    metadata = payload.get("metadata", {})
    metrics = payload.get("profile_metrics", {})
    report_markdown = str(payload.get("profile_report_markdown") or "").strip()
    description_markdown = str(payload.get("description_markdown") or "").strip()
    source_files = payload.get("source_files", {})
    file_order = payload.get("file_order", [])
    selected_files = _select_prompt_files(file_order, source_files)

    lines = [
        f"## Example Harness: {harness_name}",
        "",
        "### Harness Identity",
        f"- Planning system: {metadata.get('planning_system', 'unknown')}",
        f"- Action system: {metadata.get('action_system', 'unknown')}",
        f"- Default memory system: {metadata.get('default_memory_system', 'unknown')}",
        f"- Default bench type: {metadata.get('default_bench_type')}",
        f"- Pairing reason: {metadata.get('pairing_reason', 'unknown')}",
        "",
        "### Description",
        description_markdown or "No description available.",
        "",
        "### Performance Snapshot",
        *_render_metric_lines(metrics),
        "",
        "### Performance Report",
        report_markdown or "No report available.",
        "",
        "### Bundle Files",
    ]

    for rel_path in selected_files:
        lines.append(f"<<<FILE:{rel_path}>>>")
        lines.append(str(source_files[rel_path]).rstrip())
        lines.append("<<<END_FILE>>>")

    return "\n".join(lines).strip()


def _build_example_payload(harness_dir: Path) -> dict[str, Any]:
    builder_path = harness_dir / "builder.py"
    if not builder_path.exists():
        raise FileNotFoundError(f"Missing builder.py in harness bundle: {harness_dir}")

    metadata = _populate_missing_metadata(_extract_builder_metadata(builder_path), harness_dir)
    metadata["source_root"] = harness_dir.as_posix()

    description_path = harness_dir / "Description.md"
    metrics_path = harness_dir / "metrics.json"
    report_path = harness_dir / "report.md"
    description_markdown = _read_text(description_path) if description_path.exists() else ""
    report_markdown = _read_text(report_path) if report_path.exists() else ""
    profile_metrics = _load_metrics(metrics_path)
    source_files = _collect_source_files(harness_dir)

    payload = {
        "metadata": metadata,
        "artifact_paths": {
            "harness_root": harness_dir.as_posix(),
            "description_path": description_path.as_posix() if description_path.exists() else None,
            "report_path": report_path.as_posix() if report_path.exists() else None,
            "metrics_path": metrics_path.as_posix() if metrics_path.exists() else None,
        },
        "description_markdown": description_markdown,
        "profile_metrics": profile_metrics,
        "profile_report_markdown": report_markdown,
        "file_order": list(source_files.keys()),
        "source_files": source_files,
    }
    payload["prompt_ready_example"] = _render_prompt_ready_example(
        harness_name=harness_dir.name,
        payload=payload,
    )
    return _literalize(payload)


def _build_manifest_entry(
    *,
    harness_dir: Path,
    payload: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    metrics = payload.get("profile_metrics", {})
    output_path = output_dir / f"{harness_dir.name}.yaml"
    return {
        "harness_name": harness_dir.name,
        "output_path": output_path.as_posix(),
        "planning_system": payload["metadata"].get("planning_system"),
        "action_system": payload["metadata"].get("action_system"),
        "default_memory_system": payload["metadata"].get("default_memory_system"),
        "exact_accuracy": metrics.get("answer_correct"),
        "path_score": metrics.get("path_score"),
        "tokens_avg": metrics.get("tokens_avg"),
        "report_path": payload["artifact_paths"].get("report_path"),
        "metrics_path": payload["artifact_paths"].get("metrics_path"),
        "file_count": len(payload["file_order"]),
    }


def _iter_harness_dirs(
    *,
    harness_root: Path,
    selected_names: list[str] | None = None,
) -> list[Path]:
    if selected_names:
        names = list(dict.fromkeys(selected_names))
        harness_dirs = [harness_root / name for name in names]
        missing = [path.name for path in harness_dirs if not path.is_dir()]
        if missing:
            missing_text = ", ".join(missing)
            raise FileNotFoundError(f"Missing harness directories: {missing_text}")
        return harness_dirs

    harness_dirs = [
        path
        for path in harness_root.iterdir()
        if path.is_dir() and path.name.startswith("harness")
    ]
    return sorted(harness_dirs, key=lambda path: path.name)


def build_examples(
    *,
    harness_root: Path = DEFAULT_HARNESS_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    selected_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    combined_blocks: list[str] = []

    for harness_dir in _iter_harness_dirs(
        harness_root=harness_root,
        selected_names=selected_names,
    ):
        payload = _build_example_payload(harness_dir)
        output_path = output_dir / f"{harness_dir.name}.yaml"
        rendered_yaml = yaml.dump(
            payload,
            Dumper=LiteralDumper,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=100000,
            indent=2,
        )
        output_path.write_text(rendered_yaml, encoding="utf-8")
        entry = _build_manifest_entry(
            harness_dir=harness_dir,
            payload=payload,
            output_dir=output_dir,
        )
        entries.append(entry)
        combined_blocks.append(str(payload["prompt_ready_example"]).rstrip())

    manifest_path = output_dir / MANIFEST_NAME
    manifest_payload = {
        "examples": entries,
        "combined_prompt_path": (output_dir / COMBINED_PROMPT_NAME).as_posix(),
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / COMBINED_PROMPT_NAME).write_text(
        "\n\n".join(combined_blocks).rstrip() + "\n",
        encoding="utf-8",
    )
    return entries


def validate_examples(
    *,
    harness_root: Path = DEFAULT_HARNESS_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    selected_names: list[str] | None = None,
) -> dict[str, Any]:
    harness_dirs = _iter_harness_dirs(
        harness_root=harness_root,
        selected_names=selected_names,
    )
    issues: list[dict[str, Any]] = []

    expected_names = {path.name for path in harness_dirs}
    actual_example_names = {
        path.stem
        for path in output_dir.glob("*.yaml")
        if path.is_file() and path.name != MANIFEST_NAME
    }

    missing_examples = sorted(expected_names - actual_example_names)
    extra_examples = sorted(actual_example_names - expected_names)
    if missing_examples or extra_examples:
        issues.append(
            {
                "type": "example_file_set_mismatch",
                "missing_examples": missing_examples,
                "extra_examples": extra_examples,
            }
        )

    expected_entries: list[dict[str, Any]] = []
    combined_blocks: list[str] = []
    for harness_dir in harness_dirs:
        expected_payload = _normalize_payload(_build_example_payload(harness_dir))
        expected_entry = _build_manifest_entry(
            harness_dir=harness_dir,
            payload=expected_payload,
            output_dir=output_dir,
        )
        expected_entries.append(expected_entry)
        combined_blocks.append(str(expected_payload["prompt_ready_example"]).rstrip())

        example_path = output_dir / f"{harness_dir.name}.yaml"
        if not example_path.exists():
            continue

        actual_payload = _normalize_payload(yaml.safe_load(_read_text(example_path)))
        if actual_payload == expected_payload:
            continue

        expected_source_files = expected_payload.get("source_files", {})
        actual_source_files = actual_payload.get("source_files", {})
        changed_files = sorted(
            rel_path
            for rel_path in set(expected_source_files) | set(actual_source_files)
            if expected_source_files.get(rel_path) != actual_source_files.get(rel_path)
        )
        issues.append(
            {
                "type": "payload_mismatch",
                "harness_name": harness_dir.name,
                "changed_files": changed_files,
            }
        )

    manifest_path = output_dir / MANIFEST_NAME
    expected_manifest = {
        "examples": expected_entries,
        "combined_prompt_path": (output_dir / COMBINED_PROMPT_NAME).as_posix(),
    }
    if not manifest_path.exists():
        issues.append({"type": "missing_manifest", "path": manifest_path.as_posix()})
    else:
        actual_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if actual_manifest != expected_manifest:
            issues.append({"type": "manifest_mismatch", "path": manifest_path.as_posix()})

    combined_prompt_path = output_dir / COMBINED_PROMPT_NAME
    expected_combined_prompt = "\n\n".join(combined_blocks).rstrip()
    if not combined_prompt_path.exists():
        issues.append({"type": "missing_combined_prompt", "path": combined_prompt_path.as_posix()})
    else:
        actual_combined_prompt = _read_text(combined_prompt_path)
        if _normalize_text(actual_combined_prompt) != expected_combined_prompt:
            issues.append(
                {
                    "type": "combined_prompt_mismatch",
                    "path": combined_prompt_path.as_posix(),
                }
            )

    return {
        "harness_root": harness_root.as_posix(),
        "output_dir": output_dir.as_posix(),
        "selected_names": selected_names or [path.name for path in harness_dirs],
        "issue_count": len(issues),
        "issues": issues,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build prompt-ready round examples from harness bundles, including code, "
            "Description.md, report.md, and metrics.json."
        )
    )
    parser.add_argument(
        "--harness-root",
        type=Path,
        default=DEFAULT_HARNESS_ROOT,
        help="Root directory containing harness bundles.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for YAML examples and combined prompt text.",
    )
    parser.add_argument(
        "--harness",
        action="append",
        default=None,
        help="Specific harness name to include. Repeat for multiple names. Defaults to harness1..harness7.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Validate existing examples against harness bundles without rebuilding them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected_names = args.harness or list(DEFAULT_HARNESS_NAMES)
    harness_root = args.harness_root.resolve()
    output_dir = args.output_dir.resolve()

    if args.verify_only:
        result = validate_examples(
            harness_root=harness_root,
            output_dir=output_dir,
            selected_names=selected_names,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        raise SystemExit(1 if result["issue_count"] else 0)

    entries = build_examples(
        harness_root=harness_root,
        output_dir=output_dir,
        selected_names=selected_names,
    )
    print(
        json.dumps(
            {
                "output_dir": output_dir.as_posix(),
                "manifest_path": (output_dir / MANIFEST_NAME).as_posix(),
                "combined_prompt_path": (output_dir / COMBINED_PROMPT_NAME).as_posix(),
                "example_count": len(entries),
                "harnesses": [entry["harness_name"] for entry in entries],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
