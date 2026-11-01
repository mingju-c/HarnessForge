from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from .runtime import extract_mixed_ground_truth, get_mixed_benchmark
from .mixed_reward import compute_score, toolhop_subtask_answers


def _scoring_extra_info(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("extra_info")
    if isinstance(value, str):
        value = json.loads(value)
    extra_info = dict(value) if isinstance(value, dict) else {}
    if "sub_task" in item:
        extra_info["sub_task"] = item["sub_task"]
    return extra_info


def validate_mixeddata_scoring_items(items: list[dict[str, Any]]) -> None:
    """Validate evaluator-only labels before spending rollout budget."""
    for index, item in enumerate(items):
        if get_mixed_benchmark(item) == "toolhop":
            try:
                toolhop_subtask_answers(extract_mixed_ground_truth(item), _scoring_extra_info(item))
            except ValueError as exc:
                raise ValueError(f"ToolHop item {index}: {exc}") from exc


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _trajectory_to_solution_str(
    trajectory: list[dict[str, Any]] | None,
    pred_answer: Any,
) -> str:
    parts: list[str] = []
    for step in trajectory or []:
        if not isinstance(step, dict):
            continue
        tool_calls = step.get("tool_calls") or []
        normalized_calls = []
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if isinstance(call, dict):
                    name = call.get("name")
                    arguments = call.get("arguments", {})
                else:
                    name = getattr(call, "name", None)
                    arguments = getattr(call, "arguments", {})
                if name:
                    normalized_calls.append({"name": name, "arguments": arguments or {}})
        if normalized_calls:
            parts.append(_json_dumps({"tools": normalized_calls}))
        observation = step.get("obs") or step.get("observations") or step.get("observation")
        evidence_calls = [call for call in normalized_calls if call["name"] not in {"final_answer", "submit_answer"}]
        if step.get("name") == "action" and evidence_calls and observation is not None and str(observation).strip():
            parts.append(f"<tool_response>\n{observation}\n</tool_response>")

    if pred_answer is not None and str(pred_answer).strip():
        parts.append(_json_dumps({"think": "supported", "answer": str(pred_answer).strip()}))
    return "\n".join(parts)


def evaluate_mixeddata_item(
    *,
    item: dict[str, Any] | None,
    pred_answer: Any,
    trajectory: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    item = item or {}
    extra_info = _scoring_extra_info(item)
    benchmark = get_mixed_benchmark(item)
    extra_info["benchmark"] = benchmark
    ground_truth = extract_mixed_ground_truth(item)
    solution_str = _trajectory_to_solution_str(trajectory, pred_answer)
    result = compute_score(
        data_source=item.get("data_source") or benchmark,
        solution_str=solution_str,
        ground_truth=ground_truth,
        extra_info=extra_info,
    )
    result["mixed_benchmark"] = benchmark
    return result


def summarize_mixeddata_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "success": 0,
            "score_sum": 0.0,
            "answer_correct_sum": 0.0,
            "answer_f1_sum": 0.0,
            "path_score_sum": 0.0,
            "subem_sum": 0.0,
            "envscaler_score_sum": 0.0,
            "envscaler_done_sum": 0.0,
            "tool_call_count_sum": 0,
        }
    )

    versions: set[str] = set()
    for row in results:
        if not isinstance(row, dict):
            continue
        benchmark = str(row.get("mixed_benchmark") or row.get("benchmark") or "unknown")
        bucket = totals[benchmark]
        versions.add(str(row.get("scoring_version") or "legacy_unversioned"))
        raw_score = row.get("score")
        if raw_score is None and row.get("status") != "error":
            raise ValueError("A non-error mixed result is missing its task score; re-evaluate this result.")
        score = 0.0 if row.get("status") == "error" else float(raw_score or 0.0)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError(f"Invalid mixed task score: {raw_score!r}")
        bucket["count"] += 1
        if row.get("status") == "success":
            bucket["success"] += 1
        bucket["score_sum"] += score
        for key in ("answer_correct", "answer_f1", "path_score", "subem", "envscaler_score", "envscaler_done"):
            try:
                bucket[f"{key}_sum"] += float(row.get(key) or 0.0)
            except Exception:
                pass
        try:
            bucket["tool_call_count_sum"] += int(row.get("tool_call_count") or 0)
        except Exception:
            pass

    if len(versions) > 1:
        raise ValueError(f"Cannot aggregate different scoring versions: {sorted(versions)}. Re-evaluate old results.")
    by_benchmark: dict[str, dict[str, Any]] = {}
    total_count = 0
    total_score = 0.0
    for benchmark, bucket in sorted(totals.items()):
        count = max(1, int(bucket["count"]))
        total_count += int(bucket["count"])
        total_score += float(bucket["score_sum"])
        by_benchmark[benchmark] = {
            "count": int(bucket["count"]),
            "success": int(bucket["success"]),
            "avg_score": float(bucket["score_sum"]) / count,
            "answer_correct": float(bucket["answer_correct_sum"]) / count,
            "answer_f1": float(bucket["answer_f1_sum"]) / count,
            "path_score": float(bucket["path_score_sum"]) / count,
            "subem": float(bucket["subem_sum"]) / count,
            "envscaler_score": float(bucket["envscaler_score_sum"]) / count,
            "envscaler_done": float(bucket["envscaler_done_sum"]) / count,
            "avg_tool_call_count": float(bucket["tool_call_count_sum"]) / count,
        }

    return {
        "scoring_version": next(iter(versions), "legacy_unversioned"),
        "score_aggregation": "micro",
        "total": total_count,
        "avg_score": (total_score / total_count) if total_count else 0.0,
        "by_benchmark": by_benchmark,
    }


def write_mixeddata_metrics(results: list[dict[str, Any]], run_dir: str | os.PathLike[str]) -> dict[str, Any]:
    summary = summarize_mixeddata_results(results)
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    metrics_path = run_path / "mixeddata.metrics.overall.json"
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary
