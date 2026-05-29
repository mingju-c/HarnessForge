#!/usr/bin/env python3
"""Build strict-clean round2 multiturn SFT data from round01 rollouts.

This cleaner is intentionally conservative:
- keep only fully correct tasks;
- remove guard/failed/repeated tool-call turns;
- remove EnvScaler terminal complete_task turns from SFT targets;
- reject non-EnvScaler complete_task targets;
- dedupe by benchmark + item_index, preferring shorter clean trajectories.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIRS = [
    PROJECT_ROOT / "output/exp_4_three_rounds/round01/harness_round01_2_run",
    PROJECT_ROOT / "output/exp_4_three_rounds/round01/harness_round01_4_run",
]
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "LlamaFactory/data/train_data/round2/strict_clean_from_round01"
)
DEFAULT_DATASET_NAME = "round2_strict_clean_from_round01_multiturn_sft"
DEFAULT_OUTPUT_FILE = "round2_strict_clean_from_round01_multiturn_sft.jsonl"

BAD_OBSERVATION_MARKERS = (
    "ROUND01_GUARD_BLOCK",
    "Unknown tool",
    "repeated_failed_call",
    "low_value_repeat",
    "schema_preflight",
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


def is_full_correct(row: dict[str, Any]) -> bool:
    benchmark = row.get("mixed_benchmark")
    score = to_float(row.get("score"))
    if benchmark == "envscaler":
        return (
            score == 1.0
            and to_float(row.get("envscaler_score"), score) == 1.0
            and to_float(row.get("envscaler_done")) == 1.0
        )
    if benchmark in {"searchqa", "toolhop"}:
        return score == 1.0 and to_float(row.get("answer_correct")) == 1.0
    return score == 1.0


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
    args = call.get("arguments") or {}
    return f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"


def compact_messages(raw_messages: Any, benchmark: str) -> tuple[list[dict[str, str]], Counter[str]]:
    """Return cleaned alternating user/assistant messages.

    Tool responses are folded into the user side, matching the previous SFT
    converter. Noisy action turns and their following tool observations are
    removed together.
    """
    stats: Counter[str] = Counter()
    if not isinstance(raw_messages, list):
        stats["missing_agent_messages"] += 1
        return [], stats

    kept: list[dict[str, str]] = []
    seen_nonterminal_calls: set[str] = set()
    skip_next_tool_response = False

    for raw_message in raw_messages:
        if not isinstance(raw_message, dict):
            continue

        raw_role = raw_message.get("role")
        text = content_to_text(raw_message.get("content")).strip()
        if not text:
            continue

        if raw_role == "tool-response":
            if skip_next_tool_response:
                stats["dropped_tool_response_after_noisy_action"] += 1
                skip_next_tool_response = False
                continue
            if any(marker in text for marker in BAD_OBSERVATION_MARKERS):
                stats["dropped_bad_tool_response"] += 1
                continue
            role = "user"
        elif raw_role == "assistant":
            payload = parse_tool_payload(text)
            if payload is not None:
                calls = [
                    call
                    for call in payload.get("tools") or []
                    if isinstance(call, dict) and isinstance(call.get("name"), str)
                ]
                if not calls:
                    stats["dropped_empty_tool_action"] += 1
                    skip_next_tool_response = True
                    continue

                names = [call["name"] for call in calls]
                if benchmark != "envscaler" and "complete_task" in names:
                    stats["dropped_non_env_complete_task_action"] += 1
                    skip_next_tool_response = True
                    continue

                if benchmark == "envscaler" and all(name == "complete_task" for name in names):
                    stats["dropped_env_terminal_complete_task"] += 1
                    skip_next_tool_response = True
                    continue

                nonterminal_signatures = [
                    call_signature(call)
                    for call in calls
                    if call.get("name") not in {"final_answer", "complete_task"}
                ]
                if any(sig in seen_nonterminal_calls for sig in nonterminal_signatures):
                    stats["dropped_duplicate_tool_action"] += 1
                    skip_next_tool_response = True
                    continue
                seen_nonterminal_calls.update(nonterminal_signatures)
            role = "assistant"
        else:
            role = "user"

        if kept and kept[-1]["role"] == role:
            kept[-1]["content"] = f'{kept[-1]["content"].rstrip()}\n\n{text}'
        else:
            kept.append({"role": role, "content": text})

    dropped_tail = 0
    while kept and kept[-1]["role"] != "assistant":
        kept.pop()
        dropped_tail += 1
    if dropped_tail:
        stats["dropped_trailing_user_messages"] += dropped_tail

    dropped_head = 0
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
        dropped_head += 1
    if dropped_head:
        stats["dropped_leading_assistant_messages"] += dropped_head

    return kept, stats


def validate_messages(messages: list[dict[str, str]]) -> tuple[bool, str]:
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
    return True, "ok"


def clean_key(record: dict[str, Any]) -> tuple[int, int]:
    messages = record["messages"]
    total_chars = sum(len(message["content"]) for message in messages)
    return (len(messages), total_chars)


def dataset_info(dataset_name: str, output_file: str) -> dict[str, Any]:
    return {
        dataset_name: {
            "file_name": output_file,
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant",
                "system_tag": "system",
            },
        }
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", action="append", type=Path, dest="input_dirs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dirs = args.input_dirs or DEFAULT_INPUT_DIRS
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    records_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    stats: dict[str, Any] = {
        "input_dirs": [str(path) for path in input_dirs],
        "output_dir": str(output_dir),
        "dataset_name": args.dataset_name,
        "output_file": args.output_file,
        "seen": 0,
        "full_correct_seen": 0,
        "kept_after_cleaning": 0,
        "by_benchmark_seen": Counter(),
        "by_benchmark_full_correct": Counter(),
        "by_benchmark_kept": Counter(),
        "invalid_reasons": Counter(),
        "cleaning_actions": Counter(),
        "source_kept": Counter(),
    }

    for input_dir in input_dirs:
        for path in numeric_json_files(input_dir):
            stats["seen"] += 1
            with path.open("r", encoding="utf-8") as handle:
                row = json.load(handle)

            benchmark = str(row.get("mixed_benchmark") or "unknown")
            stats["by_benchmark_seen"][benchmark] += 1

            if not is_full_correct(row):
                continue
            stats["full_correct_seen"] += 1
            stats["by_benchmark_full_correct"][benchmark] += 1

            messages, clean_stats = compact_messages(row.get("agent_messages"), benchmark)
            stats["cleaning_actions"].update(clean_stats)
            ok, reason = validate_messages(messages)
            if not ok:
                stats["invalid_reasons"][reason] += 1
                continue

            item_index = row.get("item_index")
            if not isinstance(item_index, int):
                stats["invalid_reasons"]["missing_item_index"] += 1
                continue

            record = {
                "messages": messages,
                "metadata": {
                    "source_run": input_dir.name,
                    "source_file": path.name,
                    "item_index": item_index,
                    "mixed_benchmark": benchmark,
                    "data_source": row.get("data_source"),
                    "ability": row.get("ability"),
                    "score": row.get("score"),
                    "answer_correct": row.get("answer_correct"),
                    "subem": row.get("subem"),
                    "envscaler_score": row.get("envscaler_score"),
                    "envscaler_done": row.get("envscaler_done"),
                },
            }

            key = (benchmark, item_index)
            existing = records_by_key.get(key)
            if existing is None or clean_key(record) < clean_key(existing):
                records_by_key[key] = record

    records = sorted(
        records_by_key.values(),
        key=lambda record: (
            str(record["metadata"].get("mixed_benchmark")),
            int(record["metadata"].get("item_index")),
        ),
    )
    stats["kept_after_cleaning"] = len(records)
    for record in records:
        benchmark = str(record["metadata"].get("mixed_benchmark"))
        stats["by_benchmark_kept"][benchmark] += 1
        stats["source_kept"][str(record["metadata"].get("source_run"))] += 1

    output_path = output_dir / args.output_file
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    (output_dir / "dataset_info.json").write_text(
        json.dumps(dataset_info(args.dataset_name, args.output_file), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    serializable_stats = {
        key: dict(value) if isinstance(value, Counter) else value
        for key, value in stats.items()
    }
    (output_dir / "stats.json").write_text(
        json.dumps(serializable_stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme = [
        "# Round2 Strict Clean From Round01",
        "",
        "Strict-clean multiturn SFT data from round01 harness rollouts.",
        "",
        "Rules:",
        "- keep only fully correct samples;",
        "- drop guard/unknown/repeated/noisy tool-call turns;",
        "- drop EnvScaler terminal `complete_task` turns instead of remapping them;",
        "- reject non-EnvScaler `complete_task` turns;",
        "- dedupe by `(mixed_benchmark, item_index)`, preferring shorter clean traces.",
        "",
        f"Dataset: `{args.dataset_name}`",
        f"Records: `{len(records)}`",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(json.dumps(serializable_stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
