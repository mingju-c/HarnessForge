#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "mixeddata" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "mixeddata"


def to_builtin(value: Any) -> Any:
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return to_builtin(value.item())
        except Exception:
            pass
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, dict)):
        try:
            return to_builtin(value.tolist())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def prompt_messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = row.get("prompt") or []
    if not isinstance(prompt, list):
        return []
    return [item for item in prompt if isinstance(item, dict)]


def prompt_text(row: dict[str, Any], role: str) -> str:
    for message in prompt_messages(row):
        if str(message.get("role") or "").lower() == role:
            content = message.get("content")
            if isinstance(content, str):
                return content
    return ""


def strip_tool_schema_section(system_content: str) -> str:
    marker = "Available tool schemas:"
    if marker not in system_content:
        return system_content.strip()
    return system_content.split(marker, 1)[0].strip()


def extract_tool_schemas(system_content: str) -> list[dict[str, Any]]:
    marker = "Available tool schemas:"
    if marker in system_content:
        system_content = system_content.split(marker, 1)[1]
    start = system_content.find("[")
    if start < 0:
        return []
    decoder = json.JSONDecoder()
    try:
        payload, _ = decoder.raw_decode(system_content[start:])
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def infer_benchmark(row: dict[str, Any]) -> str:
    extra_info = row.get("extra_info") if isinstance(row.get("extra_info"), dict) else {}
    create_kwargs = (
        extra_info.get("tools_kwargs", {})
        .get("mixed_call", {})
        .get("create_kwargs", {})
        if isinstance(extra_info, dict)
        else {}
    )
    for value in (
        extra_info.get("benchmark"),
        create_kwargs.get("benchmark") if isinstance(create_kwargs, dict) else None,
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


def normalize_row(row: dict[str, Any], *, split: str, split_index: int) -> dict[str, Any]:
    row = to_builtin(row)
    extra_info = row.get("extra_info") if isinstance(row.get("extra_info"), dict) else {}
    reward_model = row.get("reward_model") if isinstance(row.get("reward_model"), dict) else {}
    system_content = prompt_text(row, "system")
    user_content = prompt_text(row, "user")
    benchmark = infer_benchmark(row)
    question = str(extra_info.get("question") or user_content or "").strip()

    output = {
        "split": split,
        "split_index": split_index,
        "source_row_index": extra_info.get("index"),
        "id": extra_info.get("id") or f"{split}_{split_index}",
        "data_source": row.get("data_source"),
        "agent_name": row.get("agent_name"),
        "ability": row.get("ability"),
        "benchmark": benchmark,
        "question": question,
        "answer": reward_model.get("ground_truth") or extra_info.get("answer"),
        "prompt": row.get("prompt") or [],
        "mate_system_context": strip_tool_schema_section(system_content),
        "tool_schemas": extract_tool_schemas(system_content),
        "reward_model": reward_model,
        "extra_info": extra_info,
    }
    return output


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def convert_split(parquet_path: Path, *, split: str) -> list[dict[str, Any]]:
    frame = pd.read_parquet(parquet_path)
    rows = []
    for index, raw_row in enumerate(frame.to_dict(orient="records"), start=1):
        rows.append(normalize_row(raw_row, split=split, split_index=index))
    return rows


def copy_source_files(source_dir: Path, output_dir: Path) -> None:
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "smoke_train.parquet", "smoke_val.parquet"):
        src = source_dir / name
        if src.exists():
            shutil.copy2(src, raw_dir / name)


def write_manifest(output_dir: Path, train_rows: list[dict[str, Any]], val_rows: list[dict[str, Any]], source_dir: Path) -> None:
    all_rows = train_rows + val_rows
    counts = Counter(row.get("data_source") for row in all_rows)
    benchmark_counts = Counter(row.get("benchmark") for row in all_rows)
    manifest = {
        "source_dir": str(source_dir),
        "raw_copies": {
            "manifest": str(output_dir / "raw" / "manifest.json"),
            "train_parquet": str(output_dir / "raw" / "smoke_train.parquet"),
            "val_parquet": str(output_dir / "raw" / "smoke_val.parquet"),
        },
        "outputs": {
            "train_jsonl": str(output_dir / "train.jsonl"),
            "val_jsonl": str(output_dir / "val.jsonl"),
            "all_jsonl": str(output_dir / "all.jsonl"),
        },
        "counts": {
            "train": len(train_rows),
            "val": len(val_rows),
            "total": len(all_rows),
            "by_data_source": dict(counts),
            "by_benchmark": dict(benchmark_counts),
        },
        "note": "Converted from verl Trainv2_trainval parquet for MATE MixedData inference.",
    }
    with (output_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy and convert verl Trainv2_trainval data for MATE MixedData.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = args.source_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    train_parquet = source_dir / "smoke_train.parquet"
    val_parquet = source_dir / "smoke_val.parquet"
    if not train_parquet.exists() or not val_parquet.exists():
        raise FileNotFoundError(f"Expected smoke_train.parquet and smoke_val.parquet under {source_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    copy_source_files(source_dir, output_dir)
    train_rows = convert_split(train_parquet, split="train")
    val_rows = convert_split(val_parquet, split="val")
    write_jsonl(output_dir / "train.jsonl", train_rows)
    write_jsonl(output_dir / "val.jsonl", val_rows)
    write_jsonl(output_dir / "all.jsonl", train_rows + val_rows)
    write_manifest(output_dir, train_rows, val_rows, source_dir)

    print(f"Wrote {len(train_rows)} train rows, {len(val_rows)} val rows, {len(train_rows) + len(val_rows)} total.")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
