#!/usr/bin/env python3
"""Prepare clean round1 harness multiturn SFT data for round2 training.

Selection is benchmark-specific:
- envscaler: score >= 0.9 and envscaler_done == 1
- searchqa/toolhop: score == 1 and answer_correct == 1

Cleaning is trajectory-level surgery rather than whole-row rejection:
- remove guard/unknown/repeated/partial-commit tool turns and their observations;
- remove exact duplicate non-terminal tool calls and their observations;
- allow complete_task only for EnvScaler, preferably as the final clean terminal;
- remove complete_task from non-EnvScaler trajectories.
"""

from __future__ import annotations

import argparse
import ast
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
    "Unknown tool",
    "schema_preflight",
    "repeated_failed_call",
    "low_value_repeat",
    "ROUND01_PARTIAL_COMMIT",
)


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


def selected_for_training(row: dict[str, Any]) -> bool:
    benchmark = row.get("mixed_benchmark")
    score = to_float(row.get("score"))
    if benchmark == "envscaler":
        return score >= 0.9 and to_float(row.get("envscaler_done")) == 1.0
    if benchmark in {"searchqa", "toolhop"}:
        return score == 1.0 and to_float(row.get("answer_correct")) == 1.0
    return False


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
            "- Use final_answer for the final short answer.\n"
            "- Never call complete_task in ToolHop.\n"
        )
    if benchmark == "searchqa":
        return (
            "Benchmark terminal contract:\n"
            "- benchmark: searchqa\n"
            "- Use the benchmark's final answer format for the final short answer.\n"
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


def call_signature(call: dict[str, Any]) -> str:
    name = str(call.get("name") or "")
    arguments = call.get("arguments") or {}
    return f"{name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True)}"


def add_message(messages: list[dict[str, str]], role: str, content: str) -> None:
    content = content.strip()
    if not content:
        return
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"] = f'{messages[-1]["content"].rstrip()}\n\n{content}'
    else:
        messages.append({"role": role, "content": content})


def next_tool_response(raw_messages: list[dict[str, Any]], idx: int) -> tuple[int | None, str]:
    next_idx = idx + 1
    if next_idx >= len(raw_messages):
        return None, ""
    candidate = raw_messages[next_idx]
    if isinstance(candidate, dict) and candidate.get("role") == "tool-response":
        return next_idx, content_to_text(candidate.get("content")).strip()
    return None, ""


def should_drop_tool_turn(
    *,
    benchmark: str,
    calls: list[dict[str, Any]],
    observation: str,
    seen_signatures: set[str],
) -> tuple[bool, str]:
    if not calls:
        return True, "empty_tool_action"

    names = [str(call.get("name") or "") for call in calls]
    if benchmark != "envscaler" and "complete_task" in names:
        return True, "non_env_complete_task"

    if any(marker in observation for marker in BAD_OBSERVATION_MARKERS):
        return True, "bad_observation_marker"

    nonterminal_signatures = [
        call_signature(call)
        for call in calls
        if call.get("name") not in {"final_answer", "complete_task"}
    ]
    if any(signature in seen_signatures for signature in nonterminal_signatures):
        return True, "duplicate_tool_action"

    return False, "keep"


def compact_messages(raw_messages: Any, benchmark: str) -> tuple[list[dict[str, str]], Counter[str]]:
    stats: Counter[str] = Counter()
    if not isinstance(raw_messages, list):
        stats["missing_agent_messages"] += 1
        return [], stats

    messages: list[dict[str, str]] = []
    seen_signatures: set[str] = set()
    skip_indices: set[int] = set()

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
                calls = [
                    call
                    for call in payload.get("tools") or []
                    if isinstance(call, dict) and isinstance(call.get("name"), str)
                ]
                response_idx, observation = next_tool_response(raw_messages, idx)
                drop, reason = should_drop_tool_turn(
                    benchmark=benchmark,
                    calls=calls,
                    observation=observation,
                    seen_signatures=seen_signatures,
                )
                if drop:
                    stats[f"dropped:{reason}"] += 1
                    if response_idx is not None:
                        skip_indices.add(response_idx)
                    continue

                for call in calls:
                    if call.get("name") not in {"final_answer", "complete_task"}:
                        seen_signatures.add(call_signature(call))

                add_message(messages, "assistant", text)
                if response_idx is not None:
                    skip_indices.add(response_idx)
                    add_message(messages, "user", observation)
                continue

            if benchmark != "envscaler" and "complete_task" in text:
                text = "\n".join(
                    line for line in text.splitlines() if "complete_task" not in line
                ).strip()
            add_message(messages, "assistant", text)
            continue

        if raw_role == "tool-response":
            if any(marker in text for marker in BAD_OBSERVATION_MARKERS):
                stats["dropped:orphan_bad_tool_response"] += 1
                continue
            add_message(messages, "user", text)
            continue

        role = "user"
        if not messages:
            text = f"{terminal_contract(benchmark)}\n{text}"
        add_message(messages, role, text)

    if benchmark == "envscaler":
        first_complete_task_idx = None
        for idx, message in enumerate(messages):
            if (
                message.get("role") == "assistant"
                and "complete_task" in message.get("content", "")
            ):
                first_complete_task_idx = idx
                break
        if first_complete_task_idx is not None and first_complete_task_idx < len(messages) - 1:
            stats["dropped:envscaler_after_complete_task_messages"] += (
                len(messages) - first_complete_task_idx - 1
            )
            messages = messages[: first_complete_task_idx + 1]

    dropped_tail = 0
    while messages and messages[-1]["role"] != "assistant":
        messages.pop()
        dropped_tail += 1
    if dropped_tail:
        stats["dropped:trailing_user_messages"] += dropped_tail

    dropped_head = 0
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
        dropped_head += 1
    if dropped_head:
        stats["dropped:leading_assistant_messages"] += dropped_head

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
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            return False, f"empty_content_at_{idx}"

    text_blob = "\n".join(message["content"] for message in messages)
    for marker in BAD_OBSERVATION_MARKERS:
        if marker in text_blob:
            return False, f"bad_marker:{marker}"

    assistant_blob = "\n".join(
        message["content"] for message in messages if message.get("role") == "assistant"
    )
    if benchmark != "envscaler" and "complete_task" in assistant_blob:
        return False, "non_env_complete_task_remaining"
    if benchmark == "envscaler":
        complete_task_indices = [
            idx
            for idx, message in enumerate(messages)
            if (
                message.get("role") == "assistant"
                and "complete_task" in message.get("content", "")
            )
        ]
        if len(complete_task_indices) > 1:
            return False, "multiple_env_complete_task_remaining"
        if complete_task_indices and complete_task_indices[0] != len(messages) - 1:
            return False, "non_terminal_env_complete_task_remaining"

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--output-file", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = numeric_json_files(input_dir)
    records: list[dict[str, Any]] = []
    by_benchmark_seen: Counter[str] = Counter()
    by_benchmark_selected: Counter[str] = Counter()
    by_benchmark_kept: Counter[str] = Counter()
    invalid_reasons: Counter[str] = Counter()
    cleaning_actions: Counter[str] = Counter()
    score_buckets_seen: dict[str, Counter[str]] = defaultdict(Counter)
    score_buckets_selected: dict[str, Counter[str]] = defaultdict(Counter)
    turn_counts: list[int] = []

    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            row = json.load(handle)

        benchmark = str(row.get("mixed_benchmark") or "unknown")
        score = to_float(row.get("score"))
        by_benchmark_seen[benchmark] += 1
        if score == 0.0:
            bucket = "score=0"
        elif score == 1.0:
            bucket = "score=1"
        elif score >= 0.9:
            bucket = "0.9<=score<1"
        else:
            bucket = "0<score<0.9"
        score_buckets_seen[benchmark][bucket] += 1

        if not selected_for_training(row):
            continue

        by_benchmark_selected[benchmark] += 1
        score_buckets_selected[benchmark][bucket] += 1

        messages, clean_stats = compact_messages(row.get("agent_messages"), benchmark)
        cleaning_actions.update(clean_stats)
        ok, reason = validate_messages(messages, benchmark)
        if not ok:
            invalid_reasons[reason] += 1
            continue

        by_benchmark_kept[benchmark] += 1
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
                    "cleaning_policy": "env_score_ge_0.9_else_score_eq_1_repair_noisy_turns",
                },
            }
        )

    output_path = output_dir / args.output_file
    write_jsonl(output_path, records)

    dataset_info = {
        args.dataset_name: dataset_info_entry(args.output_file),
    }
    (output_dir / "dataset_info.json").write_text(
        json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    stats = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "dataset_name": args.dataset_name,
        "output_file": args.output_file,
        "policy": {
            "envscaler": "score>=0.9 and envscaler_done==1",
            "searchqa": "score==1 and answer_correct==1",
            "toolhop": "score==1 and answer_correct==1",
            "repair": "drop noisy tool turns inside selected trajectories",
            "terminal_contract": "complete_task allowed only for envscaler",
        },
        "records_seen": len(files),
        "records_selected_before_cleaning": sum(by_benchmark_selected.values()),
        "records_kept": len(records),
        "records_selected_but_invalid": sum(by_benchmark_selected.values()) - len(records),
        "by_benchmark_seen": dict(sorted(by_benchmark_seen.items())),
        "by_benchmark_selected": dict(sorted(by_benchmark_selected.items())),
        "by_benchmark_kept": dict(sorted(by_benchmark_kept.items())),
        "score_buckets_seen": {k: dict(v) for k, v in sorted(score_buckets_seen.items())},
        "score_buckets_selected": {k: dict(v) for k, v in sorted(score_buckets_selected.items())},
        "invalid_reasons": dict(invalid_reasons),
        "cleaning_actions": dict(cleaning_actions),
        "turn_count": {
            "min": min(turn_counts) if turn_counts else None,
            "max": max(turn_counts) if turn_counts else None,
            "avg": round(sum(turn_counts) / len(turn_counts), 4) if turn_counts else None,
        },
    }
    (output_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme = [
        f"# {args.dataset_name}",
        "",
        "Cleaned round1 harness multiturn SFT data for round2 training.",
        "",
        "Selection:",
        "- envscaler: score >= 0.9 and envscaler_done == 1",
        "- searchqa/toolhop: score == 1 and answer_correct == 1",
        "",
        "Trajectory repair:",
        "- remove guard/unknown/repeated/partial-commit turns",
        "- remove exact duplicate non-terminal tool calls",
        "- keep complete_task only for EnvScaler",
        "- add a benchmark terminal contract to the first user turn",
        "",
        f"Records kept: {len(records)}",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
