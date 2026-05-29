#!/usr/bin/env python3
"""Summarize per-sample lengths for LlamaFactory message-style SFT data."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "LlamaFactory"
    / "data"
    / "train_data"
    / "round1"
    / "harness_2"
)
DEFAULT_DATA_FILE = DEFAULT_OUTPUT_DIR / "round1_harness_2_multiturn_sft.jsonl"


def percentile(values: list[int], pct: int) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = round((len(ordered) - 1) * pct / 100)
    return ordered[idx]


def describe(values: list[int]) -> dict[str, Any]:
    if not values:
        return {}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 4),
        "median": median(values),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
    }


def qwen3_pair_text(user_content: str, assistant_content: str) -> tuple[str, str]:
    source = f"<|im_start|>user\n{user_content}<|im_end|>\n<|im_start|>assistant\n"
    target = f"{assistant_content}<|im_end|>\n"
    return source, target


def load_tokenizer(tokenizer_path: Path | None):
    if tokenizer_path is None:
        return None
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(str(tokenizer_path), trust_remote_code=True)


def token_len(tokenizer, text: str) -> int:
    if tokenizer is None:
        return 0
    return len(tokenizer.encode(text, add_special_tokens=False))


def summarize_cutoff(lengths: list[dict[str, Any]], cutoffs: list[int]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for cutoff in cutoffs:
        if not cutoff:
            continue
        over = [item for item in lengths if item.get("total_tokens", 0) > cutoff]
        result[str(cutoff)] = {
            "over_count": len(over),
            "over_ratio": round(len(over) / len(lengths), 6) if lengths else 0.0,
            "max_over_by": max((item.get("total_tokens", 0) - cutoff for item in over), default=0),
        }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tokenizer-path", type=Path, default=None)
    parser.add_argument("--cutoffs", nargs="*", type=int, default=[10240, 12288, 16384, 20480])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tokenizer = load_tokenizer(args.tokenizer_path)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    per_sample_path = args.output_dir / "lengths.jsonl"
    summary_path = args.output_dir / "length_summary.json"

    lengths: list[dict[str, Any]] = []
    with args.data_file.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            messages = row["messages"]
            meta = row.get("metadata", {})
            user_chars = sum(len(msg["content"]) for msg in messages if msg["role"] == "user")
            assistant_chars = sum(len(msg["content"]) for msg in messages if msg["role"] == "assistant")

            source_tokens = 0
            target_tokens = 0
            if tokenizer is not None:
                for idx in range(0, len(messages), 2):
                    source, target = qwen3_pair_text(messages[idx]["content"], messages[idx + 1]["content"])
                    source_tokens += token_len(tokenizer, source)
                    target_tokens += token_len(tokenizer, target)

            item = {
                "source_file": meta.get("source_file"),
                "item_index": meta.get("item_index"),
                "mixed_benchmark": meta.get("mixed_benchmark"),
                "score": meta.get("score"),
                "answer_correct": meta.get("answer_correct"),
                "envscaler_score": meta.get("envscaler_score"),
                "turns": len(messages) // 2,
                "messages": len(messages),
                "total_chars": user_chars + assistant_chars,
                "user_chars": user_chars,
                "assistant_chars": assistant_chars,
                "source_tokens": source_tokens if tokenizer is not None else None,
                "target_tokens": target_tokens if tokenizer is not None else None,
                "total_tokens": source_tokens + target_tokens if tokenizer is not None else None,
            }
            lengths.append(item)

    with per_sample_path.open("w", encoding="utf-8") as f:
        for item in lengths:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    by_benchmark: dict[str, dict[str, Any]] = {}
    for bench in sorted({str(item["mixed_benchmark"]) for item in lengths}):
        subset = [item for item in lengths if str(item["mixed_benchmark"]) == bench]
        by_benchmark[bench] = {
            key: describe([int(item[key]) for item in subset if item.get(key) is not None])
            for key in ("turns", "messages", "total_chars", "user_chars", "assistant_chars", "total_tokens")
        }

    summary = {
        "data_file": str(args.data_file.resolve()),
        "tokenizer_path": str(args.tokenizer_path.resolve()) if args.tokenizer_path else None,
        "count": len(lengths),
        "overall": {
            key: describe([int(item[key]) for item in lengths if item.get(key) is not None])
            for key in ("turns", "messages", "total_chars", "user_chars", "assistant_chars", "total_tokens")
        },
        "by_benchmark": by_benchmark,
        "cutoff_summary": summarize_cutoff(lengths, args.cutoffs) if tokenizer is not None else {},
        "longest_by_tokens": sorted(
            (item for item in lengths if item.get("total_tokens") is not None),
            key=lambda item: int(item["total_tokens"]),
            reverse=True,
        )[:20],
        "longest_by_chars": sorted(lengths, key=lambda item: int(item["total_chars"]), reverse=True)[:20],
        "turn_count_distribution": dict(Counter(str(item["turns"]) for item in lengths)),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
