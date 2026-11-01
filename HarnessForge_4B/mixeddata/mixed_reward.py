from __future__ import annotations

import ast
import json
import re
import string
from collections import Counter
from typing import Any


SCORING_VERSION = "paper_c1_v1"

_REWARD_EXTRA_DEFAULTS: dict[str, Any] = {
    "scoring_version": SCORING_VERSION,
    "score": 0.0,
    "answer_correct": 0.0,
    "answer_f1": 0.0,
    "subem": 0.0,
    "path_score": 0.0,
    "tool_call_count": 0,
    "has_valid_answer": 0.0,
    "used_search": 0.0,
    "envscaler_score": 0.0,
    "envscaler_done": 0.0,
    "webshop_score": 0.0,
    "webshop_done": 0.0,
    "alfworld_score": 0.0,
    "alfworld_done": 0.0,
    "taubench_reward": 0.0,
    "taubench_done": 0.0,
    "taubench_task_id": -1.0,
    "pred_answer": "",
    "mixed_benchmark": "unknown",
    "error": "",
}


def _maybe_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _maybe_literal(value: Any) -> Any:
    value = _maybe_scalar(value)
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{\"'":
        return value
    try:
        return json.loads(stripped)
    except Exception:
        pass
    try:
        return ast.literal_eval(stripped)
    except Exception:
        return value


def _gold_answers(ground_truth: Any, extra_info: dict[str, Any] | None = None) -> list[str]:
    ground_truth = _maybe_literal(ground_truth)
    if isinstance(ground_truth, dict):
        target = ground_truth.get("target", ground_truth.get("answers", ground_truth.get("answer")))
        return _gold_answers(target, extra_info)
    if isinstance(ground_truth, (list, tuple, set)):
        return [str(item) for item in ground_truth if str(item).strip()]
    if ground_truth is not None and str(ground_truth).strip():
        parsed = _maybe_literal(str(ground_truth))
        if parsed is not ground_truth:
            parsed_answers = _gold_answers(parsed, None)
            if parsed_answers:
                return parsed_answers
        return [str(ground_truth)]
    if extra_info:
        for key in ("golden_answers", "answers", "target"):
            if key in extra_info and extra_info[key] is not None:
                fallback_answers = _gold_answers(extra_info[key], None)
                if fallback_answers:
                    return fallback_answers
    return []


def normalize_answer(text: Any) -> str:
    def remove_articles(value: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", value)

    def white_space_fix(value: str) -> str:
        return " ".join(value.split())

    def remove_punc(value: str) -> str:
        exclude = set(string.punctuation)
        return "".join(ch for ch in value if ch not in exclude)

    return white_space_fix(remove_articles(remove_punc(str(text).lower())))


def _em(prediction: str, golden_answers: list[str]) -> float:
    normalized_prediction = normalize_answer(prediction)
    return float(any(normalize_answer(answer) == normalized_prediction for answer in golden_answers))


def _subem(prediction: str, golden_answers: list[str]) -> float:
    normalized_prediction = normalize_answer(prediction)
    return float(any(normalize_answer(answer) in normalized_prediction for answer in golden_answers))


def _answer_f1(prediction: str, golden_answers: list[str]) -> float:
    """Normalized token-multiset F1, taking the best accepted reference answer."""
    predicted_tokens = normalize_answer(prediction).split()
    if not predicted_tokens:
        return 0.0
    best = 0.0
    for answer in golden_answers:
        gold_tokens = normalize_answer(answer).split()
        if not gold_tokens:
            continue
        overlap = sum((Counter(predicted_tokens) & Counter(gold_tokens)).values())
        best = max(best, 2.0 * overlap / (len(predicted_tokens) + len(gold_tokens)))
    return best


def toolhop_subtask_answers(ground_truth: Any, extra_info: dict[str, Any] | None) -> list[str]:
    """Require the original subgoal labels; a final answer cannot supply a path."""
    labels = _maybe_literal((extra_info or {}).get("sub_task"))
    truth = _maybe_literal(ground_truth)
    if labels is None and isinstance(truth, dict):
        labels = _maybe_literal(truth.get("sub_task"))
    if not isinstance(labels, dict) or not labels:
        raise ValueError(
            "Paper ToolHop scoring requires a non-empty sub_task mapping in the item, "
            "extra_info, or ground_truth. Preserve the original ToolHop subgoal labels."
        )
    answers = [normalize_answer(value) if value is not None else "" for value in labels.values()]
    if not all(answers):
        raise ValueError("ToolHop sub_task labels must contain non-empty normalized answers.")
    return answers


def _extract_json_answer(solution_str: str) -> str:
    decoder = json.JSONDecoder()
    for match in reversed(list(re.finditer(r"\{", solution_str))):
        try:
            payload, _ = decoder.raw_decode(solution_str[match.start() :])
        except Exception:
            continue
        if isinstance(payload, dict):
            for key in ("answer", "final_answer", "response", "result"):
                value = payload.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
    return ""


def _extract_answer(solution_str: str) -> str:
    # Tool-returned JSON can contain an "answer" field, but is not a final answer.
    solution_str = re.sub(r"<tool_response>.*?</tool_response>", "", solution_str, flags=re.DOTALL)
    answer_tag_matches = re.findall(r"<answer>\s*(.*?)\s*</answer>", solution_str, flags=re.DOTALL | re.IGNORECASE)
    if answer_tag_matches:
        return answer_tag_matches[-1].strip()
    json_answer = _extract_json_answer(solution_str)
    if json_answer:
        return json_answer
    final_matches = re.findall(r"final answer\s*[:：]\s*([^\n\r]+)", solution_str, flags=re.IGNORECASE)
    if final_matches:
        return final_matches[-1].strip().strip("`'\" ")
    return ""


def _tool_call_count(solution_str: str) -> int:
    names = re.findall(r'"name"\s*:\s*"([^"]+)"', solution_str)
    return sum(1 for name in names if name not in {"final_answer", "submit_answer"})


def _score_answer_task(solution_str: str, ground_truth: Any, extra_info: dict[str, Any] | None) -> dict[str, Any]:
    pred = _extract_answer(solution_str)
    answers = _gold_answers(ground_truth, extra_info)
    exact = _em(pred, answers) if pred and answers else 0.0
    subem = _subem(pred, answers) if pred and answers else 0.0
    score = exact if exact else 0.5 * subem
    if not pred:
        score = 0.0
    return {
        "score": float(score),
        "answer_correct": float(exact),
        "subem": float(subem),
        "has_valid_answer": float(bool(pred)),
        "pred_answer": pred,
        "tool_call_count": _tool_call_count(solution_str),
    }


def _score_toolhop(solution_str: str, ground_truth: Any, extra_info: dict[str, Any] | None) -> dict[str, Any]:
    result = _score_answer_task(solution_str, ground_truth, extra_info)
    subtask_answers = toolhop_subtask_answers(ground_truth, extra_info)
    # Only tool observations count as intermediate evidence, never the final answer.
    observations = re.findall(r"<tool_response>\s*(.*?)\s*</tool_response>", solution_str, flags=re.DOTALL)
    observed_text = normalize_answer("\n".join(observations))
    solved = sum(answer in observed_text for answer in subtask_answers)
    result["path_score"] = solved / len(subtask_answers)
    result["solved_subtasks"] = solved
    result["subtask_count"] = len(subtask_answers)
    result["score"] = 0.5 * result["answer_correct"] + 0.5 * result["path_score"]
    return result


def _score_searchqa(solution_str: str, ground_truth: Any, extra_info: dict[str, Any] | None) -> dict[str, Any]:
    result = _score_answer_task(solution_str, ground_truth, extra_info)
    result["answer_f1"] = _answer_f1(result["pred_answer"], _gold_answers(ground_truth, extra_info))
    result["score"] = result["answer_f1"]
    has_search = "<information>" in solution_str or '"name": "search"' in solution_str or '"name":"search"' in solution_str
    result["used_search"] = float(bool(has_search))
    return result


def _score_envscaler(extra_info: dict[str, Any] | None) -> dict[str, Any]:
    rollout_scores = (extra_info or {}).get("rollout_reward_scores", {})
    rollout_scores = _maybe_scalar(rollout_scores)
    if isinstance(rollout_scores, dict):
        score = rollout_scores.get("envscaler_score")
        done = rollout_scores.get("envscaler_done", 0.0)
    else:
        score, done = None, 0.0
    score = float(score) if score is not None else 0.0
    return {
        "score": score,
        "envscaler_score": score,
        "envscaler_done": float(bool(done)),
    }


def _score_taubench(solution_str: str, extra_info: dict[str, Any] | None) -> dict[str, Any]:
    rollout_scores = (extra_info or {}).get("rollout_reward_scores", {})
    rollout_scores = _maybe_scalar(rollout_scores)
    if isinstance(rollout_scores, dict) and "taubench_reward" in rollout_scores:
        score = rollout_scores.get("taubench_reward")
        done = rollout_scores.get("taubench_done", 0.0)
        task_id = rollout_scores.get("taubench_task_id", (extra_info or {}).get("taubench_task_id", -1))
    else:
        score, done, task_id = None, 0.0, (extra_info or {}).get("taubench_task_id", -1)
    score = float(score) if score is not None else 0.0
    return {
        "score": score,
        "taubench_reward": score,
        "taubench_done": float(bool(done)),
        "taubench_task_id": task_id,
    }


def _finalize_result(result: dict[str, Any], benchmark: str) -> dict[str, Any]:
    finalized = dict(_REWARD_EXTRA_DEFAULTS)
    finalized.update(result)
    finalized["mixed_benchmark"] = benchmark
    for key in (
        "score",
        "answer_correct",
        "answer_f1",
        "subem",
        "path_score",
        "has_valid_answer",
        "used_search",
        "envscaler_score",
        "envscaler_done",
        "webshop_score",
        "webshop_done",
        "alfworld_score",
        "alfworld_done",
        "taubench_reward",
        "taubench_done",
        "taubench_task_id",
    ):
        try:
            finalized[key] = float(_maybe_scalar(finalized[key]))
        except Exception:
            finalized[key] = 0.0
    try:
        finalized["tool_call_count"] = int(_maybe_scalar(finalized["tool_call_count"]))
    except Exception:
        finalized["tool_call_count"] = 0
    finalized["pred_answer"] = str(finalized.get("pred_answer") or "")
    finalized["error"] = str(finalized.get("error") or "")
    return finalized


def compute_score(
    data_source: str | None,
    solution_str: str,
    ground_truth: Any,
    extra_info: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    extra_info = extra_info or {}
    benchmark = str(extra_info.get("benchmark") or data_source or "").lower()
    if "toolhop" in benchmark:
        return _finalize_result(_score_toolhop(solution_str, ground_truth, extra_info), "toolhop")
    if "searchqa" in benchmark or benchmark in {"nq", "hotpotqa", "2wikimultihopqa", "offline"}:
        return _finalize_result(_score_searchqa(solution_str, ground_truth, extra_info), "searchqa")
    if "envscaler" in benchmark:
        return _finalize_result(_score_envscaler(extra_info), "envscaler")
    if "webshop" in benchmark:
        return _finalize_result({"score": 0.0}, "webshop")
    if "alfworld" in benchmark:
        return _finalize_result({"score": 0.0}, "alfworld")
    if "taubench" in benchmark or "tau-bench" in benchmark or "tau_bench" in benchmark:
        return _finalize_result(_score_taubench(solution_str, extra_info), "taubench")
    return _finalize_result({"score": 0.0, "error": "unknown_benchmark"}, benchmark or "unknown")
