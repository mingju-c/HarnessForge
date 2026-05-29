#!/usr/bin/env python3
"""Prepare round1 harness_2 trajectories as LlamaFactory multi-turn SFT data."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = (
    PROJECT_ROOT
    / "output"
    / "exp_4_three_rounds"
    / "round01"
    / "harness_round01_2_run"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "LlamaFactory"
    / "data"
    / "train_data"
    / "round1"
    / "harness_2"
)
DEFAULT_DATASET_NAME = "round1_harness_2_multiturn_sft"
DEFAULT_OUTPUT_FILE = "round1_harness_2_multiturn_sft.jsonl"


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def content_to_text(content: Any) -> str:
    """Flatten OpenAI content blocks into plain text for LlamaFactory."""
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


def compact_messages(raw_messages: Any) -> tuple[list[dict[str, str]], int, int]:
    """Convert raw agent messages into alternating user/assistant messages.

    LlamaFactory's sharegpt converter expects user/assistant turns to alternate and
    the final message to be an assistant target. Tool observations are model inputs,
    so they are merged into the user side.
    """
    messages: list[dict[str, str]] = []
    if not isinstance(raw_messages, list):
        return messages, 0, 0

    for raw_message in raw_messages:
        if not isinstance(raw_message, dict):
            continue

        raw_role = raw_message.get("role")
        role = "assistant" if raw_role == "assistant" else "user"
        content = content_to_text(raw_message.get("content")).strip()
        if not content:
            continue

        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] = f'{messages[-1]["content"].rstrip()}\n\n{content}'
        else:
            messages.append({"role": role, "content": content})

    dropped_tail = 0
    while messages and messages[-1]["role"] != "assistant":
        messages.pop()
        dropped_tail += 1

    dropped_head = 0
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
        dropped_head += 1

    return messages, dropped_head, dropped_tail


def validate_messages(messages: list[dict[str, str]]) -> tuple[bool, str]:
    if not messages:
        return False, "empty_messages"
    if len(messages) % 2 != 0:
        return False, "odd_message_count"
    for idx, message in enumerate(messages):
        expected_role = "user" if idx % 2 == 0 else "assistant"
        if message.get("role") != expected_role:
            return False, f"bad_role_at_{idx}"
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            return False, f"empty_content_at_{idx}"
    return True, "ok"


def should_keep(row: dict[str, Any], policy: str) -> bool:
    benchmark = row.get("mixed_benchmark")
    score = to_float(row.get("score"))
    answer_correct = to_float(row.get("answer_correct"))
    envscaler_score = to_float(row.get("envscaler_score"), score)

    if policy == "all":
        return True
    if policy == "score_positive":
        return score > 0.0
    if policy == "perfect":
        return score == 1.0
    if policy == "requested":
        if benchmark == "envscaler":
            return envscaler_score > 0.0
        if benchmark in {"searchqa", "toolhop"}:
            return answer_correct == 1.0
        return score > 0.0

    raise ValueError(f"Unknown policy: {policy}")


def numeric_json_files(input_dir: Path) -> list[Path]:
    return sorted(
        (path for path in input_dir.glob("*.json") if path.stem.isdigit()),
        key=lambda path: int(path.stem),
    )


def score_bucket(row: dict[str, Any]) -> str:
    score = to_float(row.get("score"))
    if score == 0.0:
        return "score=0"
    if score == 1.0:
        return "score=1"
    return "0<score<1"


def make_dataset_info(dataset_name: str, output_file: str) -> dict[str, Any]:
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


def write_readme(output_dir: Path, dataset_name: str, output_file: str, stats: dict[str, Any]) -> None:
    kept = stats["records_kept"]
    seen = stats["records_seen"]
    lines = [
        "# Round1 Harness 2 Multi-turn SFT",
        "",
        "LlamaFactory sharegpt/OpenAI-style multi-turn SFT data generated from round01 harness_2 trajectories.",
        "",
        "## Files",
        "",
        f"- `{output_file}`: JSONL training data with `messages`.",
        "- `dataset_info.json`: LlamaFactory dataset registration.",
        "- `stats.json`: cleaning and filtering statistics.",
        "",
        "## Filter",
        "",
        "- envscaler: keep samples with `envscaler_score > 0`.",
        "- searchqa/toolhop: keep samples with `answer_correct == 1`.",
        "",
        "## Dataset",
        "",
        f"- name: `{dataset_name}`",
        f"- kept: `{kept}` / `{seen}`",
        "",
    ]
    output_dir.joinpath("README.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE)
    parser.add_argument(
        "--policy",
        choices=("requested", "score_positive", "perfect", "all"),
        default="requested",
        help=(
            "requested keeps envscaler score>0 and searchqa/toolhop answer_correct==1; "
            "other policies are provided for ablations."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / args.output_file
    dataset_info_path = output_dir / "dataset_info.json"
    stats_path = output_dir / "stats.json"

    files = numeric_json_files(input_dir)
    records: list[dict[str, Any]] = []
    by_benchmark_seen: Counter[str] = Counter()
    by_benchmark_kept: Counter[str] = Counter()
    score_buckets_seen: dict[str, Counter[str]] = defaultdict(Counter)
    score_buckets_kept: dict[str, Counter[str]] = defaultdict(Counter)
    invalid_reasons: Counter[str] = Counter()
    turn_counts: list[int] = []
    dropped_tail_count = 0
    dropped_head_count = 0

    for path in files:
        with path.open("r", encoding="utf-8") as f:
            row = json.load(f)

        benchmark = str(row.get("mixed_benchmark") or "unknown")
        by_benchmark_seen[benchmark] += 1
        score_buckets_seen[benchmark][score_bucket(row)] += 1

        if not should_keep(row, args.policy):
            continue

        messages, dropped_head, dropped_tail = compact_messages(row.get("agent_messages"))
        dropped_head_count += dropped_head
        dropped_tail_count += dropped_tail
        ok, reason = validate_messages(messages)
        if not ok:
            invalid_reasons[reason] += 1
            continue

        by_benchmark_kept[benchmark] += 1
        score_buckets_kept[benchmark][score_bucket(row)] += 1
        turn_counts.append(len(messages) // 2)
        records.append(
            {
                "messages": messages,
                "metadata": {
                    "source_file": path.name,
                    "item_index": row.get("item_index"),
                    "mixed_benchmark": row.get("mixed_benchmark"),
                    "data_source": row.get("data_source"),
                    "ability": row.get("ability"),
                    "score": row.get("score"),
                    "answer_correct": row.get("answer_correct"),
                    "subem": row.get("subem"),
                    "envscaler_score": row.get("envscaler_score"),
                    "envscaler_done": row.get("envscaler_done"),
                    "tool_call_count": row.get("tool_call_count"),
                },
            }
        )

    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    dataset_info = make_dataset_info(args.dataset_name, args.output_file)
    dataset_info_path.write_text(json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stats = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "dataset_name": args.dataset_name,
        "output_file": args.output_file,
        "policy": args.policy,
        "records_seen": len(files),
        "records_kept": len(records),
        "records_filtered_or_invalid": len(files) - len(records),
        "by_benchmark_seen": dict(sorted(by_benchmark_seen.items())),
        "by_benchmark_kept": dict(sorted(by_benchmark_kept.items())),
        "score_buckets_seen": {k: dict(v) for k, v in sorted(score_buckets_seen.items())},
        "score_buckets_kept": {k: dict(v) for k, v in sorted(score_buckets_kept.items())},
        "invalid_reasons": dict(invalid_reasons),
        "dropped_leading_messages": dropped_head_count,
        "dropped_trailing_messages": dropped_tail_count,
        "turn_count": {
            "min": min(turn_counts) if turn_counts else None,
            "max": max(turn_counts) if turn_counts else None,
            "avg": round(sum(turn_counts) / len(turn_counts), 4) if turn_counts else None,
        },
    }
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(output_dir, args.dataset_name, args.output_file, stats)

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
