from __future__ import annotations

import ast
import json
import os
import re
from typing import Any


def evaluate_api_bank_item(
    *,
    item: dict[str, Any] | None,
    pred_answer: Any,
    trajectory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    expected_calls = extract_expected_api_calls(item or {})
    trajectory_calls = extract_predicted_api_calls(trajectory)
    final_calls = parse_api_requests(_stringify_answer(pred_answer))
    pred_calls = trajectory_calls if trajectory_calls else final_calls

    used_pred_indices: set[int] = set()
    name_matches = 0
    correct_api_calls = 0
    matched_calls: list[dict[str, Any]] = []

    for expected_call in expected_calls:
        expected_name = expected_call.get("name")
        expected_args = expected_call.get("arguments")
        candidate_indices = [
            idx
            for idx, call in enumerate(pred_calls)
            if idx not in used_pred_indices and call.get("name") == expected_name
        ]
        if candidate_indices:
            name_matches += 1
        for idx in candidate_indices:
            call = pred_calls[idx]
            if _normalize_arguments(call.get("arguments")) == _normalize_arguments(expected_args):
                correct_api_calls += 1
                used_pred_indices.add(idx)
                matched_calls.append(call)
                break

    gt_api_calls = len(expected_calls)
    path_score = correct_api_calls / gt_api_calls if gt_api_calls else 0.0
    name_score = name_matches / gt_api_calls if gt_api_calls else 0.0
    success_rate = 1.0 if gt_api_calls and correct_api_calls == gt_api_calls else 0.0

    return {
        "judgement": "correct" if success_rate else "incorrect",
        "raw": None,
        "error": None if expected_calls else "missing_expected_api_call",
        "pred_answer": _stringify_answer(pred_answer),
        "expected_api_call": expected_calls[0] if len(expected_calls) == 1 else None,
        "expected_api_calls": expected_calls,
        "pred_api_calls": pred_calls,
        "matched_api_call": matched_calls[0] if len(matched_calls) == 1 else None,
        "matched_api_calls": matched_calls,
        "has_valid_answer": int(bool(pred_calls) or bool(_stringify_answer(pred_answer))),
        "api_name_correct": name_score,
        "api_args_correct": path_score,
        "api_call_correct": success_rate,
        "api_success_rate": success_rate,
        "path_score": path_score,
        "gt_api_calls": gt_api_calls,
        "correct_api_calls": correct_api_calls,
        "tool_call_count": len(trajectory_calls),
    }


def summarize_api_bank_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in results if isinstance(row, dict)]
    metric_rows = [row for row in rows if row.get("api_call_correct") is not None]
    total_api_calls = sum(_to_int(row.get("gt_api_calls")) for row in metric_rows)
    correct_api_calls = sum(_to_int(row.get("correct_api_calls")) for row in metric_rows)
    api_accuracy = correct_api_calls / total_api_calls if total_api_calls else 0.0
    return {
        "total_instance": len(rows),
        "evaluated_instance": len(metric_rows),
        "has_valid_answer": _mean(row.get("has_valid_answer") for row in metric_rows),
        "api_accuracy": api_accuracy,
        "path_score": _mean(row.get("path_score") for row in metric_rows),
        "success_rate": _mean(row.get("api_success_rate", row.get("api_call_correct")) for row in metric_rows),
        "api_name_accuracy": _mean(row.get("api_name_correct") for row in metric_rows),
        "api_args_accuracy": _mean(row.get("api_args_correct") for row in metric_rows),
        "api_call_accuracy": _mean(row.get("api_call_correct") for row in metric_rows),
        "average_tool_calls": _mean(row.get("tool_call_count") for row in metric_rows),
        "total_api_calls": total_api_calls,
        "correct_api_calls": correct_api_calls,
    }


def write_api_bank_metrics(
    results: list[dict[str, Any]],
    output_dir: str,
    *,
    details_filename: str = "api_bank.metrics.json",
    overall_filename: str = "api_bank.metrics.overall.json",
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
                "golden_answer": row.get("golden_answer"),
                "agent_result": row.get("agent_result"),
                "expected_api_call": row.get("expected_api_call"),
                "expected_api_calls": row.get("expected_api_calls"),
                "matched_api_call": row.get("matched_api_call"),
                "matched_api_calls": row.get("matched_api_calls"),
                "pred_api_calls": row.get("pred_api_calls"),
                "metrics": {
                    "has_valid_answer": row.get("has_valid_answer"),
                    "path_score": row.get("path_score"),
                    "success_rate": row.get("api_success_rate", row.get("api_call_correct")),
                    "gt_api_calls": row.get("gt_api_calls"),
                    "correct_api_calls": row.get("correct_api_calls"),
                    "api_name_correct": row.get("api_name_correct"),
                    "api_args_correct": row.get("api_args_correct"),
                    "api_call_correct": row.get("api_call_correct"),
                    "tool_call_count": row.get("tool_call_count"),
                },
            }
        )

    overall = summarize_api_bank_results(results)
    with open(os.path.join(output_dir, details_filename), "w", encoding="utf-8") as details_file:
        json.dump(detailed_rows, details_file, indent=2, ensure_ascii=False)
    with open(os.path.join(output_dir, overall_filename), "w", encoding="utf-8") as overall_file:
        json.dump(overall, overall_file, indent=2, ensure_ascii=False)
    return overall


def extract_expected_api_calls(item: dict[str, Any]) -> list[dict[str, Any]]:
    api_calls = item.get("api_calls")
    if isinstance(api_calls, list):
        calls = []
        for api_call in api_calls:
            if not isinstance(api_call, dict):
                continue
            name = str(api_call.get("api_name") or api_call.get("name") or "").strip()
            arguments = api_call.get("param_dict") or api_call.get("input") or {}
            if name:
                calls.append({"name": name, "arguments": arguments if isinstance(arguments, dict) else {}})
        return calls

    raw = item.get("expected_output")
    if raw is None:
        raw = item.get("output")
    return parse_api_requests(_stringify_answer(raw))


def extract_expected_api_call(item: dict[str, Any]) -> dict[str, Any] | None:
    calls = extract_expected_api_calls(item)
    return calls[0] if calls else None


def parse_api_requests(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if not text:
        return calls
    pattern = re.compile(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)", flags=re.DOTALL)
    for match in pattern.finditer(text):
        name = match.group(1)
        args_text = match.group(2).strip()
        arguments = _parse_keyword_arguments(args_text)
        if arguments is not None:
            calls.append({"name": name, "arguments": arguments})
    return calls


def parse_api_request(text: str) -> dict[str, Any] | None:
    calls = parse_api_requests(text)
    return calls[0] if calls else None


def extract_predicted_api_calls(trajectory: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for tool_call in _iter_tool_calls(trajectory):
        name = tool_call.get("name")
        if not name or name == "final_answer":
            continue
        arguments = tool_call.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append({"name": name, "arguments": arguments})
    return calls


def _iter_tool_calls(trajectory: Any):
    if not isinstance(trajectory, list):
        return
    for step in trajectory:
        if not isinstance(step, dict):
            continue
        for tool_call in step.get("tool_calls") or []:
            if isinstance(tool_call, dict):
                yield tool_call
        nested = step.get("subagent_trajectories")
        if isinstance(nested, dict):
            for child in nested.values():
                if isinstance(child, dict):
                    yield from _iter_tool_calls(child.get("agent_trajectory") or child.get("trajectory"))
                else:
                    yield from _iter_tool_calls(child)
        elif isinstance(nested, list):
            for child in nested:
                if isinstance(child, dict):
                    yield from _iter_tool_calls(child.get("agent_trajectory") or child.get("trajectory"))
                else:
                    yield from _iter_tool_calls(child)


def _parse_keyword_arguments(args_text: str) -> dict[str, Any] | None:
    if not args_text:
        return {}
    try:
        parsed = ast.parse(f"_f({args_text})", mode="eval")
        call = parsed.body
        if not isinstance(call, ast.Call):
            return None
        arguments: dict[str, Any] = {}
        for keyword in call.keywords:
            if keyword.arg is None:
                return None
            arguments[keyword.arg] = ast.literal_eval(keyword.value)
        return arguments
    except Exception:
        return _parse_simple_string_arguments(args_text)


def _parse_simple_string_arguments(args_text: str) -> dict[str, Any] | None:
    arguments: dict[str, Any] = {}
    pattern = re.compile(r"([A-Za-z_]\w*)\s*=\s*('([^']*)'|\"([^\"]*)\")")
    for match in pattern.finditer(args_text):
        arguments[match.group(1)] = match.group(3) if match.group(3) is not None else match.group(4)
    if arguments:
        return arguments

    for part in _split_unquoted_commas(args_text):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", key):
            continue
        arguments[key] = value.strip().strip("\"'")
    return arguments if arguments else None


def _split_unquoted_commas(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in text:
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        if char == "," and quote is None:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def _normalize_arguments(arguments: Any) -> dict[str, str]:
    if not isinstance(arguments, dict):
        return {}
    return {str(key): _normalize_value(value) for key, value in sorted(arguments.items())}


def _normalize_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _stringify_answer(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("answer", "final_answer", "response", "result"):
            if key in value:
                return _stringify_answer(value.get(key))
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


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


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
