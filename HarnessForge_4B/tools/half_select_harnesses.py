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
            quality = {name: as_float(metrics.get(name)) for name in args.quality_metric}
            cost = {name: as_float(metrics.get(name)) for name in args.cost_metric}
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Select the Pareto-competitive top half of evaluated harness candidates from harness_pool.yaml.")
    parser.add_argument("--registry-file", type=Path, default=Path("registries/harness_pool.yaml"))
    parser.add_argument("--round", type=str, default=None)
    parser.add_argument("--dataset", type=str, default=None)
    parser.add_argument("--experiment", type=str, default=None)
    parser.add_argument("--primary-metric", type=str, default="primary_score")
    parser.add_argument("--quality-metric", action="append", default=["primary_score", "accuracy", "valid_answer_rate"])
    parser.add_argument("--cost-metric", action="append", default=["avg_tokens", "avg_elapsed_time", "avg_tool_calls"])
    parser.add_argument("--keep-fraction", type=float, default=0.5)
    parser.add_argument("--min-survivors", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    registry = load_yaml(args.registry_file)
    candidates = collect_candidates(registry, args)
    selected = half_select(candidates, args)
    payload = {
        "selection_rule": "pareto_half_selection",
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
