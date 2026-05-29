from __future__ import annotations

import json
import os
import re
from typing import Any

from .runtime import normalize_endpoint_tool_name


def evaluate_restbench_item(
    *,
    item: dict[str, Any] | None,
    pred_answer: Any = None,
    trajectory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    solution_endpoints = [
        str(endpoint).strip()
        for endpoint in ((item or {}).get("solution") or [])
        if str(endpoint).strip()
    ]
    required_tool_names = [normalize_endpoint_tool_name(endpoint) for endpoint in solution_endpoints]
    used_tool_names = extract_used_restbench_tool_names(trajectory)

    if required_tool_names:
        correct_count = sum(1 for name in required_tool_names if name in used_tool_names)
        path_rate = correct_count / len(required_tool_names)
    else:
        correct_count = 0
        path_rate = 0.0
    success = int(bool(required_tool_names) and path_rate == 1.0)

    return {
        "judgement": "correct" if success else "incorrect",
        "raw": None,
        "error": None,
        "pred_answer": _stringify_answer(pred_answer),
        "labeled_answer": ", ".join(solution_endpoints),
        "has_valid_answer": int(bool(used_tool_names)),
        "answer_correct": success,
        "restbench_path_rate": path_rate,
        "restbench_success": success,
        "restbench_correct_endpoint_count": correct_count,
        "restbench_required_endpoint_count": len(required_tool_names),
        "restbench_required_endpoints": solution_endpoints,
        "restbench_required_tool_names": required_tool_names,
        "restbench_used_tool_names": used_tool_names,
        "tool_call_count": count_restbench_tool_calls(trajectory),
    }


def extract_used_restbench_tool_names(trajectory: list[dict[str, Any]] | None) -> list[str]:
    used: list[str] = []
    for call in iter_restbench_tool_calls(trajectory):
        name = str(call.get("name") or "").strip()
        args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        if name == "final_answer" or not name:
            continue
        if name in {"call_api", "get_api_details"}:
            endpoint_name = str(args.get("endpoint_name") or "").strip()
            if endpoint_name:
                used.append(normalize_endpoint_tool_name(endpoint_name))
            continue
        used.append(name)
    return list(dict.fromkeys(used))


def count_restbench_tool_calls(trajectory: list[dict[str, Any]] | None) -> int:
    return sum(1 for _ in iter_restbench_tool_calls(trajectory))


def iter_restbench_tool_calls(trajectory: list[dict[str, Any]] | None):
    for step in trajectory or []:
        if not isinstance(step, dict) or step.get("name") != "action":
            continue
        for call in step.get("tool_calls") or []:
            if isinstance(call, dict) and call.get("name") != "final_answer":
                yield call


def summarize_restbench_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in results if isinstance(row, dict)]
    metric_rows = [
        row
        for row in rows
        if row.get("restbench_path_rate") is not None
    ]
    return {
        "total_instance": len(rows),
        "evaluated_instance": len(metric_rows),
        "path_rate": _mean(row.get("restbench_path_rate") for row in metric_rows),
        "success_rate": _mean(row.get("restbench_success") for row in metric_rows),
        "has_valid_answer": _mean(row.get("has_valid_answer") for row in metric_rows),
        "average_tool_calls": _mean(row.get("tool_call_count") for row in metric_rows),
    }


def write_restbench_metrics(
    results: list[dict[str, Any]],
    output_dir: str,
    *,
    details_filename: str = "restbench.metrics.json",
    overall_filename: str = "restbench.metrics.overall.json",
) -> dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    detailed_rows: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        detailed_rows.append(
            {
                "item_index": row.get("item_index"),
                "question": row.get("question"),
                "solution": row.get("restbench_required_endpoints"),
                "agent_result": row.get("agent_result"),
                "metrics": {
                    "path_rate": row.get("restbench_path_rate"),
                    "success_rate": row.get("restbench_success"),
                    "required_tool_names": row.get("restbench_required_tool_names"),
                    "used_tool_names": row.get("restbench_used_tool_names"),
                    "tool_call_count": row.get("tool_call_count"),
                },
            }
        )

    overall = summarize_restbench_results(results)
    details_path = os.path.join(output_dir, details_filename)
    overall_path = os.path.join(output_dir, overall_filename)
    with open(details_path, "w", encoding="utf-8") as details_file:
        json.dump(detailed_rows, details_file, indent=2, ensure_ascii=False)
    with open(overall_path, "w", encoding="utf-8") as overall_file:
        json.dump(overall, overall_file, indent=2, ensure_ascii=False)
    return overall


def _stringify_answer(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("answer", "final_answer", "response", "result"):
            if key in value:
                return _stringify_answer(value.get(key))
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", str(value)).strip()


def _mean(values: Any) -> float:
    numeric_values: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            continue
    return sum(numeric_values) / len(numeric_values) if numeric_values else 0.0
