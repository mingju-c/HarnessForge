#!/usr/bin/env python3
"""Create deterministic benchmark-stratified train/eval splits for LlamaFactory SFT jsonl files."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

TAGS = {
    "role_tag": "role",
    "content_tag": "content",
    "user_tag": "user",
    "assistant_tag": "assistant",
    "system_tag": "system",
}


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def bench_of(row: dict) -> str:
    metadata = row.get("metadata") or {}
    return metadata.get("mixed_benchmark") or metadata.get("benchmark") or metadata.get("data_source") or "unknown"


def dataset_info_entry(file_name: str) -> dict:
    return {
        "file_name": file_name,
        "formatting": "sharegpt",
        "columns": {"messages": "messages"},
        "tags": TAGS,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--eval-ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    data_path = args.data_dir / args.input_file
    rows = read_jsonl(data_path)
    by_bench: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_bench[bench_of(row)].append(row)

    rng = random.Random(args.seed)
    train_rows: list[dict] = []
    eval_rows: list[dict] = []
    split_detail = {}

    for bench in sorted(by_bench):
        items = by_bench[bench]
        rng.shuffle(items)
        if len(items) <= 1 or args.eval_ratio <= 0:
            eval_count = 0
        else:
            eval_count = max(1, round(len(items) * args.eval_ratio))
            eval_count = min(eval_count, len(items) - 1)

        eval_part = items[:eval_count]
        train_part = items[eval_count:]
        eval_rows.extend(eval_part)
        train_rows.extend(train_part)
        split_detail[bench] = {
            "total": len(items),
            "train": len(train_part),
            "eval": len(eval_part),
            "eval_ratio": round(len(eval_part) / len(items), 6) if items else 0.0,
        }

    rng.shuffle(train_rows)
    rng.shuffle(eval_rows)

    train_name = f"{args.dataset_name}_train"
    eval_name = f"{args.dataset_name}_eval"
    train_file = f"{train_name}.jsonl"
    eval_file = f"{eval_name}.jsonl"

    write_jsonl(args.data_dir / train_file, train_rows)
    write_jsonl(args.data_dir / eval_file, eval_rows)

    info_path = args.data_dir / "dataset_info.json"
    if info_path.exists():
        dataset_info = json.loads(info_path.read_text(encoding="utf-8"))
    else:
        dataset_info = {}

    dataset_info[args.dataset_name] = dataset_info_entry(args.input_file)
    dataset_info[train_name] = dataset_info_entry(train_file)
    dataset_info[eval_name] = dataset_info_entry(eval_file)
    info_path.write_text(json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stats = {
        "dataset_name": args.dataset_name,
        "source_file": args.input_file,
        "eval_ratio_requested": args.eval_ratio,
        "seed": args.seed,
        "total": len(rows),
        "train_total": len(train_rows),
        "eval_total": len(eval_rows),
        "source_by_benchmark": dict(Counter(bench_of(row) for row in rows)),
        "train_by_benchmark": dict(Counter(bench_of(row) for row in train_rows)),
        "eval_by_benchmark": dict(Counter(bench_of(row) for row in eval_rows)),
        "split_detail": split_detail,
        "train_dataset": train_name,
        "eval_dataset": eval_name,
        "train_file": train_file,
        "eval_file": eval_file,
    }
    (args.data_dir / "stratified_split_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
