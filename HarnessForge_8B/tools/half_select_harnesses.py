#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise SystemExit("PyYAML is required. Install requirements.txt before running this script.") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Registry must be a YAML mapping: {path}")
    return data


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def collect_candidates(registry: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for harness, entry in (registry.get("harnesses") or {}).items():
        if not isinstance(entry, dict):
            continue
        runs = entry.get("runs") or []
        if not runs and entry.get("latest"):
            runs = [{"run_id": entry["latest"].get("run_id"), "metrics": entry.get("latest"), "round": entry["latest"].get("round"), "dataset": entry["latest"].get("dataset"), "experiment": None}]
        for run in runs:
            if not isinstance(run, dict):
                continue
            if args.round and run.get("round") != args.round:
                continue
            if args.dataset and run.get("dataset") != args.dataset:
                continue
            if args.experiment and run.get("experiment") != args.experiment:
                continue
            metrics = run.get("metrics") or {}
            version = metrics.get("scoring_version") or "legacy_unversioned"
            if version != args.scoring_version:
                raise ValueError(
                    f"{harness}/{run.get('run_id')} uses {version}, expected {args.scoring_version}. "
                    "Re-evaluate historical runs before selection with the corrected scoring version."
                )
            if version == "paper_c1_v1":
                perf = as_float(metrics.get("avg_score"))
                primary_score = as_float(metrics.get("primary_score"))
                if (perf is None or primary_score is None or metrics.get("score_aggregation") != "micro"
                        or not math.isclose(perf, primary_score, abs_tol=1e-6)):
                    raise ValueError(f"{harness}/{run.get('run_id')} must record micro avg_score == primary_score.")
            quality = {name: as_float(metrics.get(name)) for name in args.quality_metric}
            cost = {name: as_float(metrics.get(name)) for name in args.cost_metric}
            missing = [name for name, value in {**quality, **cost}.items() if value is None]
            if missing:
                raise ValueError(f"{harness}/{run.get('run_id')} is missing finite selection metrics: {missing}")
            primary = quality.get(args.primary_metric)
            if primary is None:
                continue
            rows.append({
                "harness": harness,
                "run_id": run.get("run_id"),
                "round": run.get("round"),
                "dataset": run.get("dataset"),
                "experiment": run.get("experiment"),
                "quality": quality,
                "cost": cost,
                "primary_score": primary,
                "metrics": metrics,
                "paths": run.get("paths") or {},
            })
    return rows


def dominates(a: dict[str, Any], b: dict[str, Any], quality_metrics: list[str], cost_metrics: list[str]) -> bool:
    better = False
    for name in quality_metrics:
        av = a["quality"].get(name)
        bv = b["quality"].get(name)
        if av is None or bv is None:
            continue
        if av < bv:
            return False
        if av > bv:
            better = True
    for name in cost_metrics:
        av = a["cost"].get(name)
        bv = b["cost"].get(name)
        if av is None or bv is None:
            continue
        if av > bv:
            return False
        if av < bv:
            better = True
    return better


def pareto_front(rows: list[dict[str, Any]], quality_metrics: list[str], cost_metrics: list[str]) -> list[dict[str, Any]]:
    front = []
    for i, row in enumerate(rows):
        if any(i != j and dominates(other, row, quality_metrics, cost_metrics) for j, other in enumerate(rows)):
            continue
        front.append(row)
    return front


def half_select(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    target = max(args.min_survivors, math.ceil(len(rows) * args.keep_fraction))
    remaining = list(rows)
    selected: list[dict[str, Any]] = []
    while remaining and len(selected) < target:
        front = pareto_front(remaining, args.quality_metric, args.cost_metric)
        front = sorted(front, key=lambda row: row["primary_score"], reverse=True)
        for row in front:
            if len(selected) >= target:
                break
            selected.append(row)
        selected_ids = {(row["harness"], row["run_id"]) for row in selected}
        remaining = [row for row in remaining if (row["harness"], row["run_id"]) not in selected_ids]
    return selected[:target]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select the Pareto-competitive top half of evaluated harness candidates from harness_pool.yaml.")
    parser.add_argument("--registry-file", type=Path, default=Path("registries/harness_pool.yaml"))
    parser.add_argument("--round", type=str, default=None)
    parser.add_argument("--dataset", type=str, default=None)
    parser.add_argument("--experiment", type=str, default=None)
    parser.add_argument("--primary-metric", type=str, default="primary_score")
    parser.add_argument("--quality-metric", action="append", help="Override quality objectives; repeat for multiple objectives.")
    parser.add_argument("--cost-metric", action="append", help="Override cost objectives; repeat for multiple objectives.")
    parser.add_argument("--scoring-version", default="paper_c1_v1", help="Required scoring version; historical scores require an explicit override.")
    parser.add_argument("--keep-fraction", type=float, default=0.5)
    parser.add_argument("--min-survivors", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Preserve the released extended objective set. The task-aware primary
    # score fixes EnvScaler aggregation; explicit overrides select three goals.
    args.quality_metric = args.quality_metric or ["primary_score", "accuracy", "valid_answer_rate"]
    args.cost_metric = args.cost_metric or ["avg_tokens", "avg_elapsed_time", "avg_tool_calls"]
    if args.primary_metric not in args.quality_metric:
        parser.error("--primary-metric must be included in --quality-metric")
    if not 0 < args.keep_fraction <= 1 or args.min_survivors < 1:
        parser.error("--keep-fraction must be in (0, 1] and --min-survivors must be positive")
    return args


def main() -> None:
    args = parse_args()
    registry = load_yaml(args.registry_file)
    candidates = collect_candidates(registry, args)
    if not candidates:
        raise ValueError("No evaluated candidates match the requested filters.")
    selected = half_select(candidates, args)
    payload = {
        "selection_rule": "pareto_half_selection",
        "scoring_version": args.scoring_version,
        "primary_metric": args.primary_metric,
        "quality_metrics": args.quality_metric,
        "cost_metrics": args.cost_metric,
        "registry_file": str(args.registry_file),
        "round": args.round,
        "dataset": args.dataset,
        "experiment": args.experiment,
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "selected": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Selected {len(selected)} of {len(candidates)} candidates -> {args.output}")


if __name__ == "__main__":
    main()
