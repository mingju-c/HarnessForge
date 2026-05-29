#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_REGISTRY_PATH = Path("registries/harness_pool.yaml")
REQUIRED_HARNESS_FILE = "builder.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sanitize_id(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("_") or "none"


def project_root_from_registry(registry_file: Path) -> Path:
    registry_file = registry_file.resolve()
    if registry_file.parent.name == "registries":
        return registry_file.parent.parent
    return Path.cwd().resolve()


def relpath(path: str | Path | None, root: Path) -> str | None:
    if path is None:
        return None
    raw = str(path).strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return str(candidate.resolve().relative_to(root.resolve()))
    except Exception:
        return str(candidate)


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "description": "Lightweight harness pool registry.",
            "updated_at": None,
            "harnesses": {},
        }
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Registry must be a YAML mapping: {path}")
    data.setdefault("schema_version", 1)
    data.setdefault("harnesses", {})
    return data


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    registry["updated_at"] = utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(registry, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def parse_builder_constants(builder_path: Path) -> dict[str, str]:
    text = builder_path.read_text(encoding="utf-8", errors="ignore")
    constants: dict[str, str] = {}
    for key in (
        "HARNESS_NAME",
        "PLANNING_SYSTEM",
        "ACTION_SYSTEM",
        "DEFAULT_MEMORY_SYSTEM",
        "PAIRING_REASON",
    ):
        match = re.search(rf"^\s*{key}\s*=\s*['\"]([^'\"]+)['\"]", text, flags=re.MULTILINE)
        if match:
            constants[key] = match.group(1)
    return constants


def generation_from_import_name(import_name: str) -> int:
    match = re.search(r"(?:^|\.)Round[_-]?(\d+)(?:\.|$)", import_name, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"_R(\d+)$", import_name, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0 if import_name == "base_harness" else -1


def discover_harnesses(project_root: Path, package: str) -> list[dict[str, Any]]:
    package_root = project_root.joinpath(*package.split("."))
    if not package_root.exists():
        raise FileNotFoundError(f"Harness package root not found: {package_root}")

    discovered: list[dict[str, Any]] = []
    for builder_path in sorted(package_root.glob(f"*/{REQUIRED_HARNESS_FILE}")):
        bundle_dir = builder_path.parent
        constants = parse_builder_constants(builder_path)
        import_name = bundle_dir.name
        discovered.append(harness_entry_from_path(project_root, package, import_name, bundle_dir, constants))

    for builder_path in sorted(package_root.glob(f"Round_*/*/{REQUIRED_HARNESS_FILE}")):
        bundle_dir = builder_path.parent
        round_dir = bundle_dir.parent.name
        constants = parse_builder_constants(builder_path)
        import_name = f"{round_dir}.{bundle_dir.name}"
        discovered.append(harness_entry_from_path(project_root, package, import_name, bundle_dir, constants))

    deduped: dict[str, dict[str, Any]] = {}
    for entry in discovered:
        deduped[entry["import_name"]] = entry
    return [deduped[name] for name in sorted(deduped)]


def harness_entry_from_path(
    project_root: Path,
    package: str,
    import_name: str,
    bundle_dir: Path,
    constants: dict[str, str],
) -> dict[str, Any]:
    planning = constants.get("PLANNING_SYSTEM")
    action = constants.get("ACTION_SYSTEM")
    memory = constants.get("DEFAULT_MEMORY_SYSTEM")
    topology = "direct_react"
    if action and any(token in action for token in ("verifier", "repair", "worker", "orchestra")):
        topology = "augmented_react"
    return {
        "import_name": import_name,
        "package": package,
        "path": relpath(bundle_dir, project_root),
        "generation": generation_from_import_name(import_name),
        "status": "active" if import_name == "base_harness" else "candidate",
        "default_memory": memory,
        "structure": {
            "planning": planning,
            "action": action,
            "topology": topology,
        },
        "pairing_reason": constants.get("PAIRING_REASON"),
    }


def merge_harness_entry(existing: dict[str, Any] | None, discovered: dict[str, Any]) -> dict[str, Any]:
    entry = dict(existing or {})
    runs = list(entry.get("runs") or [])
    latest = dict(entry.get("latest") or {})
    entry.update({key: value for key, value in discovered.items() if value is not None})
    entry["latest"] = latest
    entry["runs"] = runs
    return entry


def command_discover(args: argparse.Namespace) -> None:
    registry_file = args.registry_file.resolve()
    project_root = args.project_root.resolve() if args.project_root else project_root_from_registry(registry_file)
    registry = load_registry(registry_file)
    harnesses = registry.setdefault("harnesses", {})
    discovered = discover_harnesses(project_root, args.package)
    for entry in discovered:
        key = entry["import_name"]
        harnesses[key] = merge_harness_entry(harnesses.get(key), entry)
    save_registry(registry_file, registry)
    print(f"Discovered {len(discovered)} harness(s) into {registry_file}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def mean(values: list[Any]) -> float | None:
    numbers: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            numbers.append(number)
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    successful = sum(1 for row in rows if row.get("status") == "success")
    errors = sum(1 for row in rows if row.get("status") == "error")
    correctness_values = [
        row.get("answer_correct", row.get("api_call_correct"))
        for row in rows
        if row.get("answer_correct", row.get("api_call_correct")) is not None
    ]
    judgement_values = [
        1 if str(row.get("judgement", "")).strip().lower() == "correct" else 0
        for row in rows
        if str(row.get("judgement", "")).strip().lower() in {"correct", "incorrect"}
    ]
    accuracy = mean(correctness_values)
    if accuracy is None:
        accuracy = mean(judgement_values)

    elapsed_values = [row.get("metrics", {}).get("elapsed_time") for row in rows]
    token_values = [row.get("metrics", {}).get("total_tokens") for row in rows]
    prompt_token_values = [row.get("metrics", {}).get("prompt_tokens") for row in rows]
    completion_token_values = [row.get("metrics", {}).get("completion_tokens") for row in rows]
    api_call_values = [row.get("metrics", {}).get("api_calls") for row in rows]

    return {
        "total_tasks": total,
        "successful": successful,
        "errors": errors,
        "accuracy": accuracy,
        "valid_answer_rate": mean([row.get("has_valid_answer") for row in rows]),
        "path_score": mean([row.get("path_score") for row in rows]),
        "api_name_accuracy": mean([row.get("api_name_correct") for row in rows]),
        "api_args_accuracy": mean([row.get("api_args_correct") for row in rows]),
        "api_call_accuracy": mean([row.get("api_call_correct") for row in rows]),
        "restbench_path_rate": mean([row.get("restbench_path_rate") for row in rows]),
        "restbench_success_rate": mean([row.get("restbench_success") for row in rows]),
        "avg_actions": mean([row.get("toolhop_action_count", row.get("action_count")) for row in rows]),
        "avg_tool_calls": mean([row.get("tool_call_count") for row in rows]),
        "avg_elapsed_time": mean(elapsed_values),
        "avg_tokens": mean(token_values),
        "avg_prompt_tokens": mean(prompt_token_values),
        "avg_completion_tokens": mean(completion_token_values),
        "avg_api_calls": mean(api_call_values),
        "total_tokens": sum(float(value or 0) for value in token_values),
        "total_api_calls": sum(float(value or 0) for value in api_call_values),
    }


def clean_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in metrics.items():
        if value is None:
            continue
        if isinstance(value, float):
            cleaned[key] = round(value, 6)
        else:
            cleaned[key] = value
    return cleaned


def merge_summary_metrics(
    *,
    result_summary: dict[str, Any],
    benchmark_summary: dict[str, Any] | None = None,
    report_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = dict(result_summary)
    benchmark_summary = benchmark_summary or {}
    report_summary = report_summary or {}

    if "answer_correct" in benchmark_summary:
        metrics["accuracy"] = benchmark_summary.get("answer_correct")
    if "api_call_accuracy" in benchmark_summary:
        metrics["accuracy"] = benchmark_summary.get("api_call_accuracy")
    if "success_rate" in benchmark_summary:
        metrics["accuracy"] = benchmark_summary.get("success_rate")
    if "has_valid_answer" in benchmark_summary:
        metrics["valid_answer_rate"] = benchmark_summary.get("has_valid_answer")
    if "path_score" in benchmark_summary:
        metrics["path_score"] = benchmark_summary.get("path_score")
    if "path_rate" in benchmark_summary:
        metrics["path_score"] = benchmark_summary.get("path_rate")
    if "average_actions" in benchmark_summary:
        metrics["avg_actions"] = benchmark_summary.get("average_actions")
    if "average_tool_calls" in benchmark_summary:
        metrics["avg_tool_calls"] = benchmark_summary.get("average_tool_calls")

    if "accuracy" in report_summary and metrics.get("accuracy") is None:
        metrics["accuracy"] = report_summary.get("accuracy")
    for source_key, target_key in (
        ("avg_time_per_task", "avg_elapsed_time"),
        ("avg_tokens_per_task", "avg_tokens"),
        ("avg_prompt_tokens_per_task", "avg_prompt_tokens"),
        ("avg_completion_tokens_per_task", "avg_completion_tokens"),
        ("total_tokens", "total_tokens"),
        ("total_api_calls", "total_api_calls"),
        ("total_tasks", "total_tasks"),
        ("successful", "successful"),
        ("errors", "errors"),
    ):
        if report_summary.get(source_key) is not None:
            metrics[target_key] = report_summary.get(source_key)

    metrics["primary_score"] = compute_primary_score(metrics)
    return clean_metrics(metrics)


def compute_primary_score(metrics: dict[str, Any]) -> float | None:
    accuracy = metrics.get("accuracy")
    if accuracy is None:
        accuracy = metrics.get("api_call_accuracy")
    if accuracy is None:
        return None

    valid = metrics.get("valid_answer_rate")
    process = metrics.get("path_score")
    if process is None:
        process = metrics.get("api_name_accuracy")
    tool_cost = metrics.get("avg_tool_calls")
    try:
        score = 0.75 * float(accuracy)
        if valid is not None:
            score += 0.15 * float(valid)
        if process is not None:
            score += 0.10 * float(process)
        if tool_cost is not None:
            score -= 0.01 * min(float(tool_cost), 20.0)
        return round(score, 6)
    except (TypeError, ValueError):
        return None


def make_run_id(
    *,
    experiment: str | None,
    round_id: str | None,
    dataset: str | None,
    harness: str,
    model: str | None,
    run_dir: str | None,
) -> str:
    parts = [
        experiment or "exp",
        round_id or "round",
        dataset or "dataset",
        harness,
        model or "model",
        Path(run_dir).name if run_dir else utc_now(),
    ]
    return "__".join(sanitize_id(part) for part in parts)


def record_run_from_summary(
    *,
    registry_path: Path,
    project_root: Path,
    harness: str,
    package: str,
    round_id: str | None,
    dataset: str | None,
    dataset_type: str | None,
    model_name: str | None,
    model_backend: str | None = None,
    model_alias: str | None = None,
    model_adapter: str | None = None,
    memory_provider: str | None = None,
    experiment: str | None = None,
    run_dir: str | Path | None = None,
    results_path: str | Path | None = None,
    report_path: str | Path | None = None,
    metrics_path: str | Path | None = None,
    result_summary: dict[str, Any] | None = None,
    benchmark_summary: dict[str, Any] | None = None,
    report_summary: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    harnesses = registry.setdefault("harnesses", {})
    harness_entry = harnesses.setdefault(
        harness,
        {
            "import_name": harness,
            "package": package,
            "path": None,
            "generation": generation_from_import_name(harness),
            "status": "candidate" if harness != "base_harness" else "active",
            "latest": {},
            "runs": [],
        },
    )
    harness_entry.setdefault("import_name", harness)
    harness_entry.setdefault("package", package)
    harness_entry.setdefault("generation", generation_from_import_name(harness))
    harness_entry.setdefault("latest", {})
    harness_entry.setdefault("runs", [])
    if memory_provider:
        harness_entry.setdefault("default_memory", memory_provider)

    metrics = merge_summary_metrics(
        result_summary=result_summary or {},
        benchmark_summary=benchmark_summary,
        report_summary=report_summary,
    )
    resolved_run_id = run_id or make_run_id(
        experiment=experiment,
        round_id=round_id,
        dataset=dataset,
        harness=harness,
        model=model_alias or model_name,
        run_dir=str(run_dir) if run_dir else None,
    )
    run_record = {
        "run_id": resolved_run_id,
        "recorded_at": utc_now(),
        "experiment": experiment,
        "round": round_id,
        "dataset": dataset,
        "dataset_type": dataset_type,
        "model": {
            "name": model_name,
            "alias": model_alias,
            "backend": model_backend,
            "adapter": model_adapter,
        },
        "memory_provider": memory_provider,
        "metrics": metrics,
        "paths": {
            "run_dir": relpath(run_dir, project_root),
            "results": relpath(results_path, project_root),
            "report": relpath(report_path, project_root),
            "metrics": relpath(metrics_path, project_root),
        },
    }

    runs = [row for row in harness_entry.get("runs", []) if row.get("run_id") != resolved_run_id]
    runs.append(run_record)
    harness_entry["runs"] = runs
    harness_entry["latest"] = {
        "run_id": resolved_run_id,
        "round": round_id,
        "dataset": dataset,
        "model": model_alias or model_name,
        "adapter": model_adapter,
        "primary_score": metrics.get("primary_score"),
        "accuracy": metrics.get("accuracy"),
        "valid_answer_rate": metrics.get("valid_answer_rate"),
        "avg_tool_calls": metrics.get("avg_tool_calls"),
        "avg_elapsed_time": metrics.get("avg_elapsed_time"),
        "avg_tokens": metrics.get("avg_tokens"),
    }
    save_registry(registry_path, registry)
    return run_record


def load_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def command_record_run(args: argparse.Namespace) -> None:
    registry_file = args.registry_file.resolve()
    project_root = args.project_root.resolve() if args.project_root else project_root_from_registry(registry_file)
    result_rows = read_jsonl(args.results) if args.results else []
    result_summary = summarize_results(result_rows)
    benchmark_summary = load_json_if_exists(args.metrics_overall)
    report_summary = load_json_if_exists(args.report_summary)
    record = record_run_from_summary(
        registry_path=registry_file,
        project_root=project_root,
        harness=args.harness,
        package=args.package,
        round_id=args.round,
        dataset=args.dataset,
        dataset_type=args.dataset_type,
        model_name=args.model,
        model_backend=args.model_backend,
        model_alias=args.model_alias,
        model_adapter=args.model_adapter,
        memory_provider=args.memory_provider,
        experiment=args.experiment,
        run_dir=args.run_dir,
        results_path=args.results,
        report_path=args.report,
        metrics_path=args.metrics_overall,
        result_summary=result_summary,
        benchmark_summary=benchmark_summary,
        report_summary=report_summary,
        run_id=args.run_id,
    )
    print(f"Recorded run {record['run_id']} for {args.harness}")


def iter_runs(registry: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for harness_name, harness in (registry.get("harnesses") or {}).items():
        if not isinstance(harness, dict):
            continue
        for run in harness.get("runs") or []:
            if isinstance(run, dict):
                rows.append((harness_name, run))
    return rows


def command_topk(args: argparse.Namespace) -> None:
    registry = load_registry(args.registry_file)
    candidates: list[dict[str, Any]] = []
    for harness_name, run in iter_runs(registry):
        if args.round and run.get("round") != args.round:
            continue
        if args.dataset and run.get("dataset") != args.dataset:
            continue
        if args.experiment and run.get("experiment") != args.experiment:
            continue
        metric_value = (run.get("metrics") or {}).get(args.metric)
        if metric_value is None:
            continue
        candidates.append(
            {
                "harness": harness_name,
                "run_id": run.get("run_id"),
                "round": run.get("round"),
                "dataset": run.get("dataset"),
                "experiment": run.get("experiment"),
                "model": (run.get("model") or {}).get("alias") or (run.get("model") or {}).get("name"),
                "adapter": (run.get("model") or {}).get("adapter"),
                "metric": args.metric,
                "score": metric_value,
                "metrics": run.get("metrics") or {},
                "paths": run.get("paths") or {},
            }
        )
    selected = sorted(candidates, key=lambda row: float(row["score"]), reverse=True)[: args.k]
    output = {
        "generated_at": utc_now(),
        "selection_rule": f"top_{args.k}_by_{args.metric}",
        "round": args.round,
        "dataset": args.dataset,
        "experiment": args.experiment,
        "selected": selected,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote top-k selection to {args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the harness pool registry.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Discover harness bundles into the registry.")
    discover.add_argument("--registry-file", type=Path, default=DEFAULT_REGISTRY_PATH)
    discover.add_argument("--project-root", type=Path, default=None)
    discover.add_argument("--package", type=str, default="harness_factory")
    discover.set_defaults(func=command_discover)

    record = subparsers.add_parser("record-run", help="Record one harness run summary.")
    record.add_argument("--registry-file", type=Path, default=DEFAULT_REGISTRY_PATH)
    record.add_argument("--project-root", type=Path, default=None)
    record.add_argument("--package", type=str, default="harness_factory")
    record.add_argument("--harness", type=str, required=True)
    record.add_argument("--round", type=str, default=None)
    record.add_argument("--dataset", type=str, default=None)
    record.add_argument("--dataset-type", type=str, default=None)
    record.add_argument("--experiment", type=str, default=None)
    record.add_argument("--model", type=str, default=None)
    record.add_argument("--model-alias", type=str, default=None)
    record.add_argument("--model-backend", type=str, default=None)
    record.add_argument("--model-adapter", type=str, default=None)
    record.add_argument("--memory-provider", type=str, default=None)
    record.add_argument("--run-id", type=str, default=None)
    record.add_argument("--run-dir", type=Path, default=None)
    record.add_argument("--results", type=Path, default=None)
    record.add_argument("--report", type=Path, default=None)
    record.add_argument("--metrics-overall", type=Path, default=None)
    record.add_argument("--report-summary", type=Path, default=None)
    record.set_defaults(func=command_record_run)

    topk = subparsers.add_parser("topk", help="Select top-k harness runs from the registry.")
    topk.add_argument("--registry-file", type=Path, default=DEFAULT_REGISTRY_PATH)
    topk.add_argument("--round", type=str, default=None)
    topk.add_argument("--dataset", type=str, default=None)
    topk.add_argument("--experiment", type=str, default=None)
    topk.add_argument("--metric", type=str, default="primary_score")
    topk.add_argument("--k", type=int, default=5)
    topk.add_argument("--output", type=Path, default=None)
    topk.set_defaults(func=command_topk)

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
