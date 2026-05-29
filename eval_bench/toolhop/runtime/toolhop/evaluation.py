from __future__ import annotations

import json
import os
import re
import string
from typing import Any


def normalize_toolhop_answer(value: Any) -> str:
    text = _stringify_answer(value)
    if not text:
        return ""

    boxed = _extract_last_boxed(text)
    if boxed is not None:
        text = boxed
    elif "ANSWER:" in text:
        text = text.split("ANSWER:")[-1]
    elif "Answer:" in text:
        text = text.split("Answer:")[-1]

    return _strip_wrapping_punctuation(text).strip().lower()


def evaluate_toolhop_item(
    *,
    item: dict[str, Any] | None,
    pred_answer: Any,
    trajectory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_pred = normalize_toolhop_answer(pred_answer)
    labeled_answer = normalize_toolhop_answer((item or {}).get("answer", ""))

    has_valid_answer = int(bool(normalized_pred))
    answer_correct = int(has_valid_answer and normalized_pred == labeled_answer)

    tool_response_text = "\n".join(extract_tool_response_texts(trajectory)).lower()
    subtask_answers = {
        normalize_toolhop_answer(value)
        for value in ((item or {}).get("sub_task", {}) or {}).values()
        if normalize_toolhop_answer(value)
    }
    solved_subtasks = {
        subtask_answer
        for subtask_answer in subtask_answers
        if subtask_answer in tool_response_text
    }
    path_score = (
        len(solved_subtasks) / len(subtask_answers)
        if subtask_answers
        else 0.0
    )

    action_count = count_toolhop_action_steps(trajectory)
    tool_call_count = count_toolhop_tool_calls(trajectory)

    return {
        "judgement": "correct" if answer_correct else "incorrect",
        "raw": None,
        "error": None,
        "pred_answer": normalized_pred,
        "labeled_answer": labeled_answer,
        "has_valid_answer": has_valid_answer,
        "answer_correct": answer_correct,
        "path_score": path_score,
        "solved_subtasks": sorted(solved_subtasks),
        "subtask_count": len(subtask_answers),
        "action_count": action_count,
        "tool_call_count": tool_call_count,
    }


def summarize_toolhop_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in results if isinstance(row, dict)]
    metric_rows = [row for row in rows if row.get("has_valid_answer") is not None]

    return {
        "total_instance": len(rows),
        "evaluated_instance": len(metric_rows),
        "has_valid_answer": _mean(row.get("has_valid_answer") for row in metric_rows),
        "average_actions": _mean(row.get("toolhop_action_count", row.get("action_count")) for row in metric_rows),
        "average_tool_calls": _mean(row.get("tool_call_count") for row in metric_rows),
        "answer_correct": _mean(row.get("answer_correct") for row in metric_rows),
        "path_score": _mean(row.get("path_score") for row in metric_rows),
    }


def write_toolhop_metrics(
    results: list[dict[str, Any]],
    output_dir: str,
    *,
    details_filename: str = "toolhop.metrics.json",
    overall_filename: str = "toolhop.metrics.overall.json",
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
                "pred_answer": row.get("pred_answer"),
                "metrics": {
                    "has_valid_answer": row.get("has_valid_answer"),
                    "answer_correct": row.get("answer_correct"),
                    "path_score": row.get("path_score"),
                    "solved_subtasks": row.get("solved_subtasks"),
                    "subtask_count": row.get("subtask_count"),
                    "action_count": row.get("toolhop_action_count", row.get("action_count")),
                    "tool_call_count": row.get("tool_call_count"),
                },
            }
        )

    overall = summarize_toolhop_results(results)
    details_path = os.path.join(output_dir, details_filename)
    overall_path = os.path.join(output_dir, overall_filename)

    with open(details_path, "w", encoding="utf-8") as details_file:
        json.dump(detailed_rows, details_file, indent=2, ensure_ascii=False)
    with open(overall_path, "w", encoding="utf-8") as overall_file:
        json.dump(overall, overall_file, indent=2, ensure_ascii=False)

    return overall


def extract_tool_response_texts(trajectory: list[dict[str, Any]] | None) -> list[str]:
    responses: list[str] = []
    for step in trajectory or []:
        if not isinstance(step, dict) or step.get("name") != "action":
            continue
        tool_calls = step.get("tool_calls") or []
        non_final_calls = [
            tool_call
            for tool_call in tool_calls
            if isinstance(tool_call, dict) and tool_call.get("name") != "final_answer"
        ]
        if not non_final_calls:
            continue
        observation = step.get("obs") or step.get("observations") or step.get("observation")
        if observation is not None:
            responses.append(str(observation))
    return responses


def count_toolhop_action_steps(trajectory: list[dict[str, Any]] | None) -> int:
    count = 0
    for step in trajectory or []:
        if not isinstance(step, dict) or step.get("name") != "action":
            continue
        tool_calls = step.get("tool_calls") or []
        if any(
            isinstance(tool_call, dict) and tool_call.get("name") != "final_answer"
            for tool_call in tool_calls
        ):
            count += 1
    return count


def count_toolhop_tool_calls(trajectory: list[dict[str, Any]] | None) -> int:
    count = 0
    for step in trajectory or []:
        if not isinstance(step, dict) or step.get("name") != "action":
            continue
        for tool_call in step.get("tool_calls") or []:
            if isinstance(tool_call, dict) and tool_call.get("name") != "final_answer":
                count += 1
    return count


def _stringify_answer(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("answer", "final_answer", "response", "result"):
            if key in value:
                return _stringify_answer(value.get(key))
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _extract_last_boxed(text: str) -> str | None:
    matches = re.findall(r"\\boxed\{(.*?)\}", text, re.DOTALL)
    if matches:
        return matches[-1]
    return None


def _strip_wrapping_punctuation(text: str) -> str:
    value = str(text).strip()
    value = value.strip("`").strip()
    value = value.strip(string.whitespace)
    return value.strip("\"' ")


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
