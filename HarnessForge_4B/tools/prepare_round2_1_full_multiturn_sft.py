#!/usr/bin/env python3
"""Prepare full round02_01 trajectories as LlamaFactory multi-turn SFT data.

This follows the round1 clean09 selection idea, but writes one full cleaned
trajectory per source item instead of prefix/action-only samples.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TAGS = {
    "role_tag": "role",
    "content_tag": "content",
    "user_tag": "user",
    "assistant_tag": "assistant",
    "system_tag": "system",
}

BAD_OBSERVATION_MARKERS = (
    "ROUND01_GUARD_BLOCK",
    "ROUND02_GUARD_BLOCK",
    "ROUND01_PARTIAL_COMMIT",
    "ROUND02_PARTIAL_COMMIT",
    "Unknown tool",
    "schema_preflight",
    "repeated_failed_call",
    "low_value_repeat",
)

TERMINAL_TOOLS = {"final_answer", "complete_task"}


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("text") is not None:
                    parts.append(str(block["text"]))
                elif block.get("value") is not None:
                    parts.append(str(block["value"]))
                else:
                    parts.append(json.dumps(block, ensure_ascii=False, sort_keys=True))
            elif block is not None:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def numeric_json_files(input_dir: Path) -> list[Path]:
    return sorted(
        (path for path in input_dir.glob("*.json") if path.stem.isdigit()),
        key=lambda path: int(path.stem),
    )


def benchmark_of(row: dict[str, Any]) -> str:
    benchmark = row.get("mixed_benchmark")
    if isinstance(benchmark, str) and benchmark:
        return benchmark
    data_source = str(row.get("data_source") or "")
    return data_source.replace("mixed_", "") or "unknown"


def selected_for_training(row: dict[str, Any], policy: str) -> bool:
    benchmark = benchmark_of(row)
    score = to_float(row.get("score"))
    answer_correct = to_float(row.get("answer_correct"))
    env_done = to_float(row.get("envscaler_done"))
    env_score = to_float(row.get("envscaler_score"), score)

    if policy == "clean09":
        if benchmark == "envscaler":
            return env_score >= 0.9 and env_done == 1.0
        if benchmark in {"searchqa", "toolhop"}:
            return score == 1.0 and answer_correct == 1.0
        return False

    if policy == "strict":
        if benchmark == "envscaler":
            return env_score == 1.0 and env_done == 1.0
        if benchmark in {"searchqa", "toolhop"}:
            return score == 1.0 and answer_correct == 1.0
        return False

    if policy == "requested":
        if benchmark == "envscaler":
            return env_score > 0.0 and env_done == 1.0
        if benchmark in {"searchqa", "toolhop"}:
            return answer_correct == 1.0
        return score > 0.0

    raise ValueError(f"Unknown selection policy: {policy}")


def terminal_contract(benchmark: str) -> str:
    if benchmark == "envscaler":
        return (
            "Benchmark terminal contract:\n"
            "- benchmark: envscaler\n"
            "- complete_task is valid only for EnvScaler and only after required state mutations are complete.\n"
            "- Do not use final_answer for EnvScaler.\n"
        )
    if benchmark == "toolhop":
        return (
            "Benchmark terminal contract:\n"
            "- benchmark: toolhop\n"
            "- Use final_answer for the final short answer only after tool observations support it.\n"
            "- Never call complete_task in ToolHop.\n"
        )
    if benchmark == "searchqa":
        return (
            "Benchmark terminal contract:\n"
            "- benchmark: searchqa\n"
            "- Use final_answer for the final short answer only after search observations support it.\n"
            "- Never call complete_task in SearchQA.\n"
        )
    return f"Benchmark terminal contract:\n- benchmark: {benchmark}\n"


def parse_tool_payload(text: str) -> dict[str, Any] | None:
    prefix = "Calling tools:"
    stripped = text.strip()
    if not stripped.startswith(prefix):
        return None
    payload_text = stripped[len(prefix) :].strip()
    try:
        payload = ast.literal_eval(payload_text)
    except (SyntaxError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def calls_from_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    calls = payload.get("tools")
    if not isinstance(calls, list):
        return []
    return [
        call
        for call in calls
        if isinstance(call, dict) and isinstance(call.get("name"), str)
    ]


def call_signature(call: dict[str, Any]) -> str:
    name = str(call.get("name") or "")
    args = call.get("arguments") or {}
    return f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"


def add_message(messages: list[dict[str, str]], role: str, content: str) -> None:
    text = content.strip()
    if not text:
        return
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"] = f'{messages[-1]["content"].rstrip()}\n\n{text}'
    else:
        messages.append({"role": role, "content": text})


def next_tool_response(raw_messages: list[dict[str, Any]], idx: int) -> tuple[int | None, str]:
    next_idx = idx + 1
    if next_idx >= len(raw_messages):
        return None, ""
    candidate = raw_messages[next_idx]
    if isinstance(candidate, dict) and candidate.get("role") == "tool-response":
        return next_idx, content_to_text(candidate.get("content")).strip()
    return None, ""


def has_bad_marker(text: str) -> bool:
    return any(marker in text for marker in BAD_OBSERVATION_MARKERS)


def is_memory_guidance(text: str) -> bool:
    lowered = text.lower()
    return (
        "memory system guidance" in lowered
        or "failure_lesson" in lowered
        or "failure lesson" in lowered
        or "trace sketch" in lowered
        or "observed sequence sketch" in lowered
    )


def should_drop_tool_turn(
    *,
    benchmark: str,
    calls: list[dict[str, Any]],
    observation: str,
    seen_nonenv_signatures: set[str],
    seen_env_call_obs: set[str],
) -> tuple[bool, str]:
    if not calls:
        return True, "empty_tool_action"

    names = [str(call.get("name") or "") for call in calls]
    if benchmark != "envscaler" and "complete_task" in names:
        return True, "non_env_complete_task"
    if benchmark == "envscaler" and "final_answer" in names:
        return True, "env_final_answer"
    if has_bad_marker(observation):
        return True, "bad_observation_marker"

    nonterminal_signatures = [
        call_signature(call)
        for call in calls
        if call.get("name") not in TERMINAL_TOOLS
    ]
    if benchmark == "envscaler":
        obs_key = json.dumps(
            {"calls": nonterminal_signatures, "observation": observation},
            ensure_ascii=False,
            sort_keys=True,
        )
        if nonterminal_signatures and obs_key in seen_env_call_obs:
            return True, "duplicate_env_call_and_observation"
        return False, "keep"

    if any(signature in seen_nonenv_signatures for signature in nonterminal_signatures):
        return True, "duplicate_nonterminal_tool_action"

    return False, "keep"


def compact_messages(raw_messages: Any, benchmark: str) -> tuple[list[dict[str, str]], Counter[str]]:
    stats: Counter[str] = Counter()
    if not isinstance(raw_messages, list):
        stats["missing_agent_messages"] += 1
        return [], stats

    messages: list[dict[str, str]] = []
    skip_indices: set[int] = set()
    seen_nonenv_signatures: set[str] = set()
    seen_env_call_obs: set[str] = set()
    added_first_user = False

    for idx, raw_message in enumerate(raw_messages):
        if idx in skip_indices or not isinstance(raw_message, dict):
            continue

        raw_role = raw_message.get("role")
        text = content_to_text(raw_message.get("content")).strip()
        if not text:
            continue

        if raw_role == "assistant":
            payload = parse_tool_payload(text)
            if payload is not None:
                calls = calls_from_payload(payload)
                response_idx, observation = next_tool_response(raw_messages, idx)
                drop, reason = should_drop_tool_turn(
                    benchmark=benchmark,
                    calls=calls,
                    observation=observation,
                    seen_nonenv_signatures=seen_nonenv_signatures,
                    seen_env_call_obs=seen_env_call_obs,
                )
                if drop:
                    stats[f"dropped:{reason}"] += 1
                    if response_idx is not None:
                        skip_indices.add(response_idx)
                    continue

                nonterminal_signatures = [
                    call_signature(call)
                    for call in calls
                    if call.get("name") not in TERMINAL_TOOLS
                ]
                if benchmark == "envscaler" and nonterminal_signatures:
                    seen_env_call_obs.add(
                        json.dumps(
                            {"calls": nonterminal_signatures, "observation": observation},
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                else:
                    seen_nonenv_signatures.update(nonterminal_signatures)

                add_message(messages, "assistant", text)
                if response_idx is not None:
                    skip_indices.add(response_idx)
                    add_message(messages, "user", observation)
                else:
                    stats["missing_tool_response_after_action"] += 1
                continue

            add_message(messages, "assistant", text)
            continue

        if raw_role == "tool-response":
            if has_bad_marker(text):
                stats["dropped:orphan_bad_tool_response"] += 1
                continue
            add_message(messages, "user", text)
            continue

        if has_bad_marker(text):
            if is_memory_guidance(text):
                stats["dropped:user_memory_with_bad_marker"] += 1
                continue
            stats["dropped:user_message_with_bad_marker"] += 1
            continue

        if not added_first_user:
            text = f"{terminal_contract(benchmark)}\n{text}"
            added_first_user = True
        add_message(messages, "user", text)

    if benchmark == "envscaler":
        complete_task_indices = [
            idx
            for idx, message in enumerate(messages)
            if message.get("role") == "assistant" and "complete_task" in message.get("content", "")
        ]
        if complete_task_indices:
            first_complete = complete_task_indices[0]
            if first_complete < len(messages) - 1:
                stats["dropped:envscaler_after_complete_task_messages"] += len(messages) - first_complete - 1
                messages = messages[: first_complete + 1]

    while messages and messages[-1]["role"] != "assistant":
        messages.pop()
        stats["dropped:trailing_user_messages"] += 1
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
        stats["dropped:leading_assistant_messages"] += 1

    return messages, stats


def validate_messages(messages: list[dict[str, str]], benchmark: str) -> tuple[bool, str]:
    if not messages:
        return False, "empty_messages"
    if len(messages) % 2 != 0:
        return False, "odd_message_count"
    for idx, message in enumerate(messages):
        expected = "user" if idx % 2 == 0 else "assistant"
        if message.get("role") != expected:
            return False, f"bad_role_at_{idx}"
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return False, f"empty_content_at_{idx}"

    text_blob = "\n".join(message["content"] for message in messages)
    for marker in BAD_OBSERVATION_MARKERS:
        if marker in text_blob:
            return False, f"bad_marker:{marker}"

    assistant_blob = "\n".join(
        message["content"] for message in messages if message.get("role") == "assistant"
    )
    final_assistant = messages[-1]["content"]

    if benchmark == "envscaler":
        if "final_answer" in assistant_blob:
            return False, "env_final_answer_remaining"
        complete_task_indices = [
            idx
            for idx, message in enumerate(messages)
            if message.get("role") == "assistant" and "complete_task" in message.get("content", "")
        ]
        if len(complete_task_indices) != 1:
            return False, "missing_or_multiple_env_complete_task"
        if complete_task_indices[0] != len(messages) - 1:
            return False, "non_terminal_env_complete_task"
        return True, "ok"

    if "complete_task" in assistant_blob:
        return False, "non_env_complete_task_remaining"
    if "final_answer" not in final_assistant:
        return False, "missing_terminal_final_answer"

    return True, "ok"


def dataset_info_entry(file_name: str) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "formatting": "sharegpt",
        "columns": {"messages": "messages"},
        "tags": TAGS,
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def stable_split(records: list[dict[str, Any]], eval_ratio: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_benchmark: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        benchmark = str(record["metadata"].get("mixed_benchmark") or "unknown")
        by_benchmark[benchmark].append(record)

    train: list[dict[str, Any]] = []
    eval_records: list[dict[str, Any]] = []
    for benchmark, group in by_benchmark.items():
        ranked = sorted(
            group,
            key=lambda record: hashlib.md5(
                f"{benchmark}:{record['metadata'].get('item_index')}".encode("utf-8")
            ).hexdigest(),
        )
        eval_count = int(round(len(ranked) * eval_ratio))
        if eval_ratio > 0.0 and len(ranked) > 1:
            eval_count = max(1, eval_count)
        eval_ids = {
            (record["metadata"].get("mixed_benchmark"), record["metadata"].get("item_index"))
            for record in ranked[:eval_count]
        }
        for record in group:
            key = (record["metadata"].get("mixed_benchmark"), record["metadata"].get("item_index"))
            if key in eval_ids:
                eval_records.append(record)
            else:
                train.append(record)

    sort_key = lambda record: (
        str(record["metadata"].get("mixed_benchmark") or ""),
        int(record["metadata"].get("item_index") or -1),
    )
    return sorted(train, key=sort_key), sorted(eval_records, key=sort_key)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--eval-ratio", type=float, default=0.05)
    parser.add_argument(
        "--selection-policy",
        choices=("clean09", "strict", "requested"),
        default="clean09",
        help=(
            "clean09 keeps envscaler envscaler_score>=0.9 & done plus fully correct "
            "searchqa/toolhop, matching the round1 clean09 rule."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_name = args.dataset_name
    output_file = args.output_file
    stem = output_file[:-6] if output_file.endswith(".jsonl") else output_file
    train_name = f"{dataset_name}_train"
    eval_name = f"{dataset_name}_eval"
    train_file = f"{stem}_train.jsonl"
    eval_file = f"{stem}_eval.jsonl"

    records: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "dataset_name": dataset_name,
        "output_file": output_file,
        "train_dataset": train_name,
        "eval_dataset": eval_name,
        "train_file": train_file,
        "eval_file": eval_file,
        "selection_policy": args.selection_policy,
        "eval_ratio": args.eval_ratio,
        "records_seen": 0,
        "records_selected_before_cleaning": 0,
        "records_kept": 0,
        "by_benchmark_seen": Counter(),
        "by_benchmark_selected": Counter(),
        "by_benchmark_kept": Counter(),
        "score_buckets_seen": defaultdict(Counter),
        "score_buckets_selected": defaultdict(Counter),
        "invalid_reasons": Counter(),
        "cleaning_actions": Counter(),
    }
    turn_counts: list[int] = []

    for path in numeric_json_files(input_dir):
        stats["records_seen"] += 1
        with path.open("r", encoding="utf-8") as handle:
            row = json.load(handle)

        benchmark = benchmark_of(row)
        stats["by_benchmark_seen"][benchmark] += 1
        score = to_float(row.get("score"))
        if score == 0.0:
            score_bucket = "score=0"
        elif score == 1.0:
            score_bucket = "score=1"
        elif score >= 0.9:
            score_bucket = "0.9<=score<1"
        else:
            score_bucket = "0<score<0.9"
        stats["score_buckets_seen"][benchmark][score_bucket] += 1

        if not selected_for_training(row, args.selection_policy):
            continue
        stats["records_selected_before_cleaning"] += 1
        stats["by_benchmark_selected"][benchmark] += 1
        stats["score_buckets_selected"][benchmark][score_bucket] += 1

        messages, clean_stats = compact_messages(row.get("agent_messages"), benchmark)
        stats["cleaning_actions"].update(clean_stats)
        ok, reason = validate_messages(messages, benchmark)
        if not ok:
            stats["invalid_reasons"][reason] += 1
            continue

        stats["by_benchmark_kept"][benchmark] += 1
        turn_counts.append(len(messages) // 2)
        records.append(
            {
                "messages": messages,
                "metadata": {
                    "source_run": input_dir.name,
                    "source_file": path.name,
                    "item_index": row.get("item_index"),
                    "mixed_benchmark": benchmark,
                    "data_source": row.get("data_source"),
                    "ability": row.get("ability"),
                    "score": row.get("score"),
                    "answer_correct": row.get("answer_correct"),
                    "subem": row.get("subem"),
                    "envscaler_score": row.get("envscaler_score"),
                    "envscaler_done": row.get("envscaler_done"),
                    "tool_call_count": row.get("tool_call_count"),
                    "metrics": row.get("metrics"),
                    "cleaning_policy": (
                        "round2_1_full_multiturn_clean09_selection_keep_full_trajectory"
                    ),
                },
            }
        )

    records = sorted(
        records,
        key=lambda record: (
            str(record["metadata"].get("mixed_benchmark") or ""),
            int(record["metadata"].get("item_index") or -1),
        ),
    )
    train_records, eval_records = stable_split(records, args.eval_ratio)

    write_jsonl(output_dir / output_file, records)
    write_jsonl(output_dir / train_file, train_records)
    write_jsonl(output_dir / eval_file, eval_records)

    dataset_info = {
        dataset_name: dataset_info_entry(output_file),
        train_name: dataset_info_entry(train_file),
        eval_name: dataset_info_entry(eval_file),
    }
    (output_dir / "dataset_info.json").write_text(
        json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    stats["records_kept"] = len(records)
    stats["train_total"] = len(train_records)
    stats["eval_total"] = len(eval_records)
    stats["records_selected_but_invalid"] = (
        stats["records_selected_before_cleaning"] - len(records)
    )
    stats["records_by_benchmark"] = Counter(
        str(record["metadata"].get("mixed_benchmark") or "unknown")
        for record in records
    )
    stats["train_by_benchmark"] = Counter(
        str(record["metadata"].get("mixed_benchmark") or "unknown")
        for record in train_records
    )
    stats["eval_by_benchmark"] = Counter(
        str(record["metadata"].get("mixed_benchmark") or "unknown")
        for record in eval_records
    )
    stats["turn_count"] = {
        "min": min(turn_counts) if turn_counts else None,
        "max": max(turn_counts) if turn_counts else None,
        "avg": round(sum(turn_counts) / len(turn_counts), 4) if turn_counts else None,
    }
    stats["policy"] = {
        "selection": {
            "clean09": {
                "envscaler": "envscaler_score >= 0.9 and envscaler_done == 1",
                "searchqa": "score == 1 and answer_correct == 1",
                "toolhop": "score == 1 and answer_correct == 1",
            },
            "strict": {
                "envscaler": "envscaler_score == 1 and envscaler_done == 1",
                "searchqa": "score == 1 and answer_correct == 1",
                "toolhop": "score == 1 and answer_correct == 1",
            },
            "requested": {
                "envscaler": "envscaler_score > 0 and envscaler_done == 1",
                "searchqa": "answer_correct == 1",
                "toolhop": "answer_correct == 1",
            },
        }[args.selection_policy],
        "format": "LlamaFactory sharegpt messages; tool-response observations folded into user turns",
        "trajectory": "one full cleaned trajectory per selected source item",
        "repair": [
            "drop guard/unknown/schema/repeated/partial-commit tool turns and observations",
            "drop non-EnvScaler complete_task turns",
            "drop EnvScaler final_answer turns",
            "drop duplicate nonterminal calls for SearchQA/ToolHop",
            "for EnvScaler, only drop duplicate call+identical observation pairs",
        ],
    }

    def serialize(value: Any) -> Any:
        if isinstance(value, Counter):
            return dict(sorted(value.items()))
        if isinstance(value, defaultdict):
            return {key: serialize(val) for key, val in sorted(value.items())}
        if isinstance(value, dict):
            return {key: serialize(val) for key, val in value.items()}
        return value

    serializable_stats = serialize(stats)
    (output_dir / "stats.json").write_text(
        json.dumps(serializable_stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme = [
        f"# {dataset_name}",
        "",
        "Full cleaned round02_01 multi-turn SFT data.",
        "",
        "Files:",
        f"- `{output_file}`: all records.",
        f"- `{train_file}`: train split.",
        f"- `{eval_file}`: eval split.",
        "- `dataset_info.json`: LlamaFactory sharegpt registration.",
        "- `stats.json`: selection, cleaning, and split statistics.",
        "",
        "Cleaning:",
        "- one source trajectory becomes one SFT record;",
        "- plan/action/summary/terminal assistant turns are preserved;",
        "- tool observations are folded into user turns to keep sharegpt alternation;",
        "- noisy guard/schema/repeat/partial-commit tool turns are removed with their observations.",
        "",
        f"Records kept: {len(records)}",
        f"Train/eval: {len(train_records)} / {len(eval_records)}",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(json.dumps(serializable_stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
