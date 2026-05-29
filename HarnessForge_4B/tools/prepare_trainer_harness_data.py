from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_PREFER_HARNESSES = [
    "harness_demo1",
    "base_harness",
    "harness_demo2",
    "harness_demo3",
]


def _flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item and isinstance(item["text"], str):
                    parts.append(item["text"])
                elif "value" in item and isinstance(item["value"], str):
                    parts.append(item["value"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if isinstance(content, dict):
        if "text" in content and isinstance(content["text"], str):
            return content["text"]
        if "value" in content and isinstance(content["value"], str):
            return content["value"]
    return str(content or "")


def _serialize_messages(messages: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "unknown")).upper()
        content = _flatten_content(message.get("content", ""))
        rendered.append(f"[{role}]\n{content}".strip())
    return "\n\n".join(part for part in rendered if part.strip()).strip()


def _extract_assistant_output(step: dict[str, Any]) -> str:
    model_output = step.get("model_output_messages")
    if isinstance(model_output, dict):
        content = model_output.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if "tool_calls" in model_output:
            return json.dumps(model_output["tool_calls"], ensure_ascii=False)
    if isinstance(step.get("action_output"), str) and step["action_output"].strip():
        return step["action_output"].strip()
    if isinstance(step.get("observations"), str) and step["observations"].strip():
        return step["observations"].strip()
    return ""


def _extract_tool_names(step: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for call in step.get("tool_calls") or []:
        if isinstance(call, dict) and isinstance(call.get("name"), str):
            names.append(call["name"])
    return names


def _extract_cost(step: dict[str, Any]) -> float:
    model_output = step.get("model_output_messages")
    if not isinstance(model_output, dict):
        return 0.0
    raw = model_output.get("raw")
    if not isinstance(raw, dict):
        return 0.0
    output = raw.get("output")
    if not isinstance(output, dict):
        return 0.0
    usage = output.get("usage")
    if not isinstance(usage, dict):
        return 0.0
    cost = usage.get("cost")
    return float(cost) if isinstance(cost, (int, float)) else 0.0


def _row_cost(row: dict[str, Any]) -> float:
    return sum(_extract_cost(step) for step in row.get("trajectory") or [] if isinstance(step, dict))


def _row_step_count(row: dict[str, Any]) -> int:
    count = 0
    for step in row.get("trajectory") or []:
        if not isinstance(step, dict):
            continue
        if "step_number" in step or "plan" in step or "tool_calls" in step:
            count += 1
    return count


def _row_passed(row: dict[str, Any]) -> int:
    eval_payload = row.get("eval")
    if isinstance(eval_payload, dict) and eval_payload.get("passed") is not None:
        return int(bool(eval_payload.get("passed")))
    if row.get("answer_correct") is not None:
        try:
            return int(float(row.get("answer_correct")) > 0)
        except (TypeError, ValueError):
            return int(bool(row.get("answer_correct")))
    judgement = str(row.get("judgement", "")).strip().lower()
    if judgement in {"correct", "incorrect"}:
        return int(judgement == "correct")
    return 0


def _row_key_for_dedupe(row: dict[str, Any]) -> tuple[int, int, float, int]:
    return (
        1 if not bool(row.get("memory_write_only")) else 0,
        _row_passed(row),
        -_row_cost(row),
        -_row_step_count(row),
    )


def _choose_better(existing: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return candidate
    if _row_key_for_dedupe(candidate) >= _row_key_for_dedupe(existing):
        return candidate
    return existing


def _load_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            instance_id = str(payload.get("instance_id"))
            payload["_source_file"] = str(path)
            payload["_source_name"] = path.name
            payload["_passed"] = _row_passed(payload)
            rows[instance_id] = _choose_better(rows.get(instance_id), payload)
    return rows


def _prefer_index(harness_name: str, prefer_harnesses: list[str]) -> int:
    try:
        return prefer_harnesses.index(harness_name)
    except ValueError:
        return len(prefer_harnesses)


def _quality_key(row: dict[str, Any], prefer_harnesses: list[str]) -> tuple[int, int, int, float, int]:
    return (
        _row_passed(row),
        1 if not bool(row.get("memory_write_only")) else 0,
        -_prefer_index(str(row.get("harness_name", "")), prefer_harnesses),
        -_row_cost(row),
        -_row_step_count(row),
    )


def _normalize_response_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _stringify_response(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("answer", "final_answer", "response", "result"):
            if key in value:
                return _stringify_response(value.get(key))
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _extract_task_response(row: dict[str, Any]) -> str:
    for key in ("pred_answer", "agent_result", "final_answer", "answer"):
        text = _normalize_response_text(_stringify_response(row.get(key)))
        if text:
            return text
    return ""


def _canonical_task_prompt(row: dict[str, Any]) -> str:
    longest_user = ""
    for step in row.get("trajectory") or []:
        if not isinstance(step, dict):
            continue
        for message in step.get("model_input_messages") or []:
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = _flatten_content(message.get("content", ""))
            if len(content) > len(longest_user):
                longest_user = content
    if longest_user:
        return longest_user.strip()

    question = str(row.get("question", "")).strip()
    if question:
        return (
            "You are solving a tool-use benchmark task.\n"
            "Use the available task tools when needed and provide the exact final answer.\n\n"
            f"Question: {question}"
        )
    return ""


def _extract_plan_step(row: dict[str, Any]) -> dict[str, str] | None:
    for step in row.get("trajectory") or []:
        if not isinstance(step, dict):
            continue
        plan = step.get("plan")
        messages = step.get("model_input_messages")
        if isinstance(plan, str) and plan.strip() and isinstance(messages, list) and messages:
            return {
                "instruction": _serialize_messages(messages),
                "output": plan.strip(),
            }
    return None


def _extract_action_steps(row: dict[str, Any]) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    for step in row.get("trajectory") or []:
        if not isinstance(step, dict):
            continue
        messages = step.get("model_input_messages")
        if not isinstance(messages, list) or not messages:
            continue
        tool_names = _extract_tool_names(step)
        if not tool_names:
            continue
        output = _extract_assistant_output(step)
        if not output:
            continue
        if "final_answer" not in tool_names:
            continue
        samples.append(
            {
                "instruction": _serialize_messages(messages),
                "output": output,
                "tool_names": ",".join(tool_names),
            }
        )
    return samples


def _to_sft_entry(instruction: str, output: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "instruction": instruction.strip(),
        "input": "",
        "output": output.strip(),
        "meta": meta,
    }


def _to_dpo_entry(instruction: str, chosen: str, rejected: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "instruction": instruction.strip(),
        "input": "",
        "chosen": chosen.strip(),
        "rejected": rejected.strip(),
        "meta": meta,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def build_dataset_bundle(
    actor_files: list[Path],
    candidate_files: list[Path],
    output_dir: Path,
    prefer_harnesses: list[str],
    include_memory_write_only: bool,
) -> dict[str, Any]:
    actor_rows_by_file = {str(path): _load_rows(path) for path in actor_files}
    candidate_rows_by_file = {str(path): _load_rows(path) for path in candidate_files}

    grouped_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rows in candidate_rows_by_file.values():
        for instance_id, row in rows.items():
            if not include_memory_write_only and bool(row.get("memory_write_only")):
                continue
            grouped_candidates[instance_id].append(row)

    plan_sft: list[dict[str, Any]] = []
    action_sft: list[dict[str, Any]] = []
    task_answer_sft: list[dict[str, Any]] = []
    task_answer_dpo: list[dict[str, Any]] = []

    actor_kept_counter = Counter()
    pairwise_counter = Counter()

    for rows in actor_rows_by_file.values():
        for instance_id, row in rows.items():
            if not include_memory_write_only and bool(row.get("memory_write_only")):
                continue
            if not _row_passed(row):
                continue

            plan_step = _extract_plan_step(row)
            if plan_step is not None:
                plan_sft.append(
                    _to_sft_entry(
                        plan_step["instruction"],
                        plan_step["output"],
                        {
                            "instance_id": instance_id,
                            "task_id": row.get("item_index", row.get("instance_id")),
                            "harness_name": row.get("harness_name"),
                            "sample_type": "plan",
                        },
                    )
                )
                actor_kept_counter["plan"] += 1

            for sample in _extract_action_steps(row):
                action_sft.append(
                    _to_sft_entry(
                        sample["instruction"],
                        sample["output"],
                        {
                            "instance_id": instance_id,
                            "task_id": row.get("item_index", row.get("instance_id")),
                            "harness_name": row.get("harness_name"),
                            "sample_type": "action",
                            "tool_names": sample["tool_names"],
                        },
                    )
                )
                actor_kept_counter["action"] += 1

    for instance_id, rows in sorted(grouped_candidates.items(), key=lambda item: int(item[0])):
        correct_rows = [row for row in rows if _row_passed(row)]
        incorrect_rows = [row for row in rows if not _row_passed(row)]
        if not correct_rows:
            continue

        best_correct = max(correct_rows, key=lambda row: _quality_key(row, prefer_harnesses))
        instruction = _canonical_task_prompt(best_correct)
        chosen_answer = _extract_task_response(best_correct)
        if instruction and chosen_answer:
            task_answer_sft.append(
                _to_sft_entry(
                    instruction,
                    chosen_answer,
                    {
                        "instance_id": instance_id,
                        "task_id": best_correct.get("item_index", best_correct.get("instance_id")),
                        "chosen_harness": best_correct.get("harness_name"),
                    },
                )
            )

        if not incorrect_rows:
            pairwise_counter["skipped_no_incorrect"] += 1
            continue

        best_incorrect = max(
            incorrect_rows,
            key=lambda row: (
                1 if not bool(row.get("memory_write_only")) else 0,
                -_prefer_index(str(row.get("harness_name", "")), prefer_harnesses),
                -_row_cost(row),
            ),
        )
        rejected_answer = _extract_task_response(best_incorrect)
        if not instruction or not chosen_answer or not rejected_answer or chosen_answer == rejected_answer:
            pairwise_counter["skipped_same_or_empty"] += 1
            continue

        task_answer_dpo.append(
            _to_dpo_entry(
                instruction,
                chosen_answer,
                rejected_answer,
                {
                    "instance_id": instance_id,
                    "task_id": best_correct.get("item_index", best_correct.get("instance_id")),
                    "chosen_harness": best_correct.get("harness_name"),
                    "rejected_harness": best_incorrect.get("harness_name"),
                },
            )
        )
        pairwise_counter["kept"] += 1

    dataset_info = {
        "harness_plan_sft": {
            "file_name": "harness_plan_sft.json",
            "columns": {
                "prompt": "instruction",
                "query": "input",
                "response": "output",
            },
        },
        "harness_action_sft": {
            "file_name": "harness_action_sft.json",
            "columns": {
                "prompt": "instruction",
                "query": "input",
                "response": "output",
            },
        },
        "task_answer_sft": {
            "file_name": "task_answer_sft.json",
            "columns": {
                "prompt": "instruction",
                "query": "input",
                "response": "output",
            },
        },
        "task_answer_dpo": {
            "file_name": "task_answer_dpo.json",
            "ranking": True,
            "columns": {
                "prompt": "instruction",
                "query": "input",
                "chosen": "chosen",
                "rejected": "rejected",
            },
        },
    }

    summary = {
        "actor_files": [str(path) for path in actor_files],
        "candidate_files": [str(path) for path in candidate_files],
        "prefer_harnesses": prefer_harnesses,
        "include_memory_write_only": include_memory_write_only,
        "counts": {
            "harness_plan_sft": len(plan_sft),
            "harness_action_sft": len(action_sft),
            "task_answer_sft": len(task_answer_sft),
            "task_answer_dpo": len(task_answer_dpo),
        },
        "actor_kept_counter": dict(actor_kept_counter),
        "pairwise_counter": dict(pairwise_counter),
        "candidate_row_counter": {
            path.name: {
                "rows": len(rows),
                "passed": sum(_row_passed(row) for row in rows.values()),
            }
            for path, rows in (
                (Path(path), loaded_rows) for path, loaded_rows in candidate_rows_by_file.items()
            )
        },
    }

    _write_json(output_dir / "harness_plan_sft.json", plan_sft)
    _write_json(output_dir / "harness_action_sft.json", action_sft)
    _write_json(output_dir / "task_answer_sft.json", task_answer_sft)
    _write_json(output_dir / "task_answer_dpo.json", task_answer_dpo)
    _write_json(output_dir / "dataset_info.json", dataset_info)
    _write_json(output_dir / "summary.json", summary)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert harness trajectories into Trainer-compatible SFT/DPO datasets.")
    parser.add_argument(
        "--actor-files",
        nargs="+",
        required=True,
        help="JSONL result files used to create harness-specific SFT data. Prefer a single actor harness such as harness_demo1.",
    )
    parser.add_argument(
        "--candidate-files",
        nargs="+",
        required=True,
        help="JSONL result files used to build best-of-N task-answer SFT data and DPO pairs.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory that will contain dataset_info.json and the generated datasets.",
    )
    parser.add_argument(
        "--prefer-harnesses",
        default=",".join(DEFAULT_PREFER_HARNESSES),
        help="Comma-separated harness preference order when multiple correct candidates exist.",
    )
    parser.add_argument(
        "--include-memory-write-only",
        action="store_true",
        help="Keep rows with memory_write_only=true. Disabled by default to avoid mixing quick-run artifacts.",
    )
    args = parser.parse_args()

    actor_files = [Path(path).resolve() for path in args.actor_files]
    candidate_files = [Path(path).resolve() for path in args.candidate_files]
    output_dir = Path(args.output_dir).resolve()
    prefer_harnesses = [item.strip() for item in str(args.prefer_harnesses).split(",") if item.strip()]

    summary = build_dataset_bundle(
        actor_files=actor_files,
        candidate_files=candidate_files,
        output_dir=output_dir,
        prefer_harnesses=prefer_harnesses,
        include_memory_write_only=bool(args.include_memory_write_only),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
