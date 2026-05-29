#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "mixeddata" / "train.jsonl"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "mixeddata" / "evolution_splits"
DEFAULT_SEED = 42


def as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def infer_benchmark(row: dict[str, Any]) -> str:
    extra_info = as_dict(row.get("extra_info"))
    tools_kwargs = as_dict(extra_info.get("tools_kwargs"))
    mixed_call = as_dict(tools_kwargs.get("mixed_call"))
    create_kwargs = as_dict(mixed_call.get("create_kwargs"))
    for value in (
        row.get("benchmark"),
        extra_info.get("benchmark"),
        create_kwargs.get("benchmark"),
        row.get("data_source"),
    ):
        text = str(value or "").lower()
        if "envscaler" in text:
            return "envscaler"
        if "searchqa" in text:
            return "searchqa"
        if "toolhop" in text:
            return "toolhop"
    return "unknown"


def read_jsonl_with_keys(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for index, line in enumerate(f, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append(
                {
                    "source_index": index,
                    "raw": line.rstrip("\n"),
                    "benchmark": infer_benchmark(row),
                    "data_source": str(row.get("data_source") or ""),
                }
            )
    return rows


def assign_stratified(rows: list[dict[str, Any]], *, parts: int, seed: int) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["benchmark"]].append(row)

    rng = random.Random(seed + parts)
    assignments: list[list[dict[str, Any]]] = [[] for _ in range(parts)]
    totals = [0 for _ in range(parts)]

    for benchmark in sorted(grouped):
        bucket = list(grouped[benchmark])
        rng.shuffle(bucket)
        base_count, remainder = divmod(len(bucket), parts)
        target_counts = [base_count for _ in range(parts)]
        projected_totals = [totals[i] + base_count for i in range(parts)]

        for _ in range(remainder):
            split_index = min(range(parts), key=lambda i: (projected_totals[i], i))
            target_counts[split_index] += 1
            projected_totals[split_index] += 1

        offset = 0
        for split_index, count in enumerate(target_counts):
            assignments[split_index].extend(bucket[offset : offset + count])
            offset += count
            totals[split_index] = projected_totals[split_index]

    for split_rows in assignments:
        split_rows.sort(key=lambda item: int(item["source_index"]))
    return assignments


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(str(row["raw"]) + "\n")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "by_benchmark": dict(Counter(str(row["benchmark"]) for row in rows)),
        "by_data_source": dict(Counter(str(row["data_source"]) for row in rows)),
    }


def write_readme(output_dir: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# MixedData Evolution Splits",
        "",
        "These files are deterministic stratified splits of `data/mixeddata/train.jsonl`.",
        "They are intended for comparing one-round, two-round, and three-round harness/model evolution experiments.",
        "",
        f"- Seed: `{manifest['seed']}`",
        f"- Source: `{manifest['source']}`",
        f"- Source total: `{manifest['source_summary']['total']}`",
        f"- Source distribution: `{manifest['source_summary']['by_benchmark']}`",
        "",
        "Use `DATA_FILE=/absolute/path/to/file.jsonl ./run_mixeddata_infer.sh` to run any split directly.",
        "",
        "## Files",
        "",
    ]
    for experiment_name, experiment in manifest["experiments"].items():
        lines.append(f"### {experiment_name}")
        lines.append("")
        lines.append(experiment["description"])
        lines.append("")
        for split in experiment["splits"]:
            lines.append(
                f"- `{split['path']}`: total `{split['summary']['total']}`, "
                f"distribution `{split['summary']['by_benchmark']}`"
            )
        lines.append("")
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create deterministic stratified MixedData evolution splits.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source JSONL not found: {source}")

    rows = read_jsonl_with_keys(source)
    manifest: dict[str, Any] = {
        "source": str(source),
        "output_dir": str(output_dir),
        "seed": args.seed,
        "stratify_key": "benchmark",
        "source_summary": summarize(rows),
        "experiments": {},
    }

    one_round_path = output_dir / "one_round" / "round_01_train.jsonl"
    write_jsonl(one_round_path, rows)
    manifest["experiments"]["exp_2_one_round"] = {
        "description": "One evolution round: use the full train set for round_01.",
        "splits": [
            {
                "round": "round_01",
                "path": str(one_round_path.relative_to(PROJECT_ROOT)),
                "summary": summarize(rows),
            }
        ],
    }

    for experiment_name, parts in (("exp_3_two_rounds", 2), ("exp_4_three_rounds", 3)):
        assignments = assign_stratified(rows, parts=parts, seed=args.seed)
        split_entries = []
        folder = "two_rounds" if parts == 2 else "three_rounds"
        for index, split_rows in enumerate(assignments, start=1):
            split_path = output_dir / folder / f"round_{index:02d}_train.jsonl"
            write_jsonl(split_path, split_rows)
            split_entries.append(
                {
                    "round": f"round_{index:02d}",
                    "path": str(split_path.relative_to(PROJECT_ROOT)),
                    "summary": summarize(split_rows),
                }
            )
        manifest["experiments"][experiment_name] = {
            "description": f"{parts} evolution rounds: split train into {parts} balanced stratified parts.",
            "splits": split_entries,
        }

    manifest_path = output_dir / "manifest.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    write_readme(output_dir, manifest)

    print(f"Wrote evolution splits under {output_dir}")
    print(json.dumps(manifest["experiments"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
