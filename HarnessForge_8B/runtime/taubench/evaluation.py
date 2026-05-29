from __future__ import annotations

import json
import os
from math import comb
from typing import Any


def _loads_maybe_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def _find_terminal_payload(pred_answer: Any, trajectory: list[dict[str, Any]] | None) -> dict[str, Any]:
    parsed = _loads_maybe_json(pred_answer)
    if isinstance(parsed, dict) and "taubench_reward" in parsed:
        return parsed

    for step in reversed(trajectory or []):
        if not isinstance(step, dict):
            continue
        for key in ("obs", "observations", "observation"):
            raw = step.get(key)
            if not isinstance(raw, str):
                continue
            start = raw.find('{"taubench_done"')
            if start >= 0:
                candidate = _loads_maybe_json(raw[start:])
                if isinstance(candidate, dict) and "taubench_reward" in candidate:
                    return candidate
            for line in reversed(raw.splitlines()):
                candidate = _loads_maybe_json(line.strip())
                if isinstance(candidate, dict) and "taubench_reward" in candidate:
                    return candidate
    return {}


def _count_tool_calls(trajectory: list[dict[str, Any]] | None) -> int:
    count = 0
    for step in trajectory or []:
        if not isinstance(step, dict) or step.get("name") != "action":
            continue
        tool_calls = step.get("tool_calls") or []
        if isinstance(tool_calls, list):
            count += len(tool_calls)
    return count


def evaluate_taubench_item(
    *,
    item: dict[str, Any] | None,
    pred_answer: Any,
    trajectory: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload = _find_terminal_payload(pred_answer, trajectory)
    reward = float(payload.get("taubench_reward", 0.0) or 0.0)
    done = bool(payload.get("taubench_done", False))
    success = (1 - 1e-6) <= reward <= (1 + 1e-6)
    return {
        "judgement": "correct" if success else "incorrect",
        "raw": pred_answer,
        "pred_answer": pred_answer,
        "has_valid_answer": done,
        "answer_correct": success,
        "taubench_done": done,
        "taubench_reward": reward,
        "taubench_domain": payload.get("taubench_domain") or (item or {}).get("taubench_domain"),
        "taubench_split": payload.get("taubench_split") or (item or {}).get("taubench_split"),
        "taubench_task_id": payload.get("taubench_task_id") if "taubench_task_id" in payload else (item or {}).get("task_id"),
        "taubench_info": payload.get("taubench_info"),
        "taubench_events": payload.get("taubench_events", []),
        "tool_call_count": _count_tool_calls(trajectory),
        "score": reward,
    }


def summarize_taubench_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [row for row in results if isinstance(row, dict)]
    if not evaluated:
        return {
            "evaluated_instance": 0,
            "average_reward": 0.0,
            "success_rate": 0.0,
            "pass_hat_ks": {},
        }

    rewards = [float(row.get("taubench_reward", 0.0) or 0.0) for row in evaluated]
    successes = [1 if (1 - 1e-6) <= reward <= (1 + 1e-6) else 0 for reward in rewards]
    task_success_counts: dict[Any, int] = {}
    task_trial_counts: dict[Any, int] = {}
    for row, success in zip(evaluated, successes):
        task_id = row.get("taubench_task_id", row.get("task_id", row.get("item_index")))
        task_success_counts[task_id] = task_success_counts.get(task_id, 0) + success
        task_trial_counts[task_id] = task_trial_counts.get(task_id, 0) + 1

    num_trials = min(task_trial_counts.values()) if task_trial_counts else 1
    pass_hat_ks: dict[str, float] = {}
    if num_trials > 0 and task_success_counts:
        for k in range(1, num_trials + 1):
            denom = comb(num_trials, k)
            if denom == 0:
                continue
            pass_hat_ks[str(k)] = sum(
                comb(min(c, num_trials), k) / denom
                for c in task_success_counts.values()
            ) / len(task_success_counts)

    return {
        "evaluated_instance": len(evaluated),
        "average_reward": sum(rewards) / len(rewards),
        "success_rate": sum(successes) / len(successes),
        "average_tool_calls": sum(int(row.get("tool_call_count", 0) or 0) for row in evaluated) / len(evaluated),
        "pass_hat_ks": pass_hat_ks,
    }


def write_taubench_metrics(results: list[dict[str, Any]], run_dir: str) -> dict[str, Any]:
    os.makedirs(run_dir, exist_ok=True)
    overall = summarize_taubench_results(results)
    metrics_path = os.path.join(run_dir, "taubench.metrics.overall.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(overall, f, ensure_ascii=False, indent=2)
    return overall
