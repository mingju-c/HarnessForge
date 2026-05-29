from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _extract_instance_id(entry: dict[str, Any]) -> str | None:
    meta = entry.get("meta")
    if isinstance(meta, dict):
        for key in ("instance_id", "qid", "id"):
            value = meta.get(key)
            if value is not None:
                return str(value)
    for key in ("instance_id", "qid", "id"):
        value = entry.get(key)
        if value is not None:
            return str(value)
    return None


def _subset_name(base_name: str, split_name: str) -> str:
    return f"{base_name}_{split_name}"


def build_split_bundle(
    source_dir: Path,
    output_dir: Path,
    reference_dataset: str,
    val_ratio: float,
    heldout_ratio: float,
    seed: int,
) -> dict[str, Any]:
    source_info = _read_json(source_dir / "dataset_info.json")
    if reference_dataset not in source_info:
        raise ValueError(f"Reference dataset '{reference_dataset}' not found in {source_dir / 'dataset_info.json'}.")

    datasets: dict[str, list[dict[str, Any]]] = {}
    for dataset_name, spec in source_info.items():
        file_name = spec.get("file_name")
        if not isinstance(file_name, str):
            continue
        datasets[dataset_name] = _read_json(source_dir / file_name)

    reference_entries = datasets[reference_dataset]
    reference_ids = sorted(
        {
            instance_id
            for entry in reference_entries
            if isinstance(entry, dict)
            for instance_id in [_extract_instance_id(entry)]
            if instance_id is not None
        },
        key=lambda value: int(value),
    )
    if not reference_ids:
        raise ValueError(f"Reference dataset '{reference_dataset}' has no instance_id-bearing examples.")

    shuffled_ids = reference_ids[:]
    random.Random(seed).shuffle(shuffled_ids)

    total = len(shuffled_ids)
    heldout_n = int(round(total * heldout_ratio))
    val_n = int(round(total * val_ratio))
    if heldout_ratio > 0 and heldout_n == 0 and total >= 3:
        heldout_n = 1
    if val_ratio > 0 and val_n == 0 and total >= 3:
        val_n = 1
    if heldout_n + val_n >= total:
        overflow = heldout_n + val_n - (total - 1)
        if overflow > 0:
            if heldout_n >= val_n:
                heldout_n = max(0, heldout_n - overflow)
            else:
                val_n = max(0, val_n - overflow)

    heldout_ids = sorted(shuffled_ids[:heldout_n], key=lambda value: int(value))
    val_ids = sorted(shuffled_ids[heldout_n : heldout_n + val_n], key=lambda value: int(value))
    train_ids = sorted(shuffled_ids[heldout_n + val_n :], key=lambda value: int(value))

    split_membership = {
        "train": set(train_ids),
        "val": set(val_ids),
        "heldout": set(heldout_ids),
    }

    split_dataset_info: dict[str, dict[str, Any]] = {}
    split_counts: dict[str, dict[str, int]] = {}
    heldout_references: dict[str, list[dict[str, Any]]] = {}

    for dataset_name, spec in source_info.items():
        rows = datasets[dataset_name]
        split_counts[dataset_name] = {}
        for split_name, split_ids in split_membership.items():
            filtered = []
            for entry in rows:
                if not isinstance(entry, dict):
                    continue
                instance_id = _extract_instance_id(entry)
                if instance_id is None:
                    continue
                if instance_id in split_ids:
                    filtered.append(entry)

            subset_key = _subset_name(dataset_name, split_name)
            subset_file = f"{subset_key}.json"
            split_dataset_info[subset_key] = dict(spec, file_name=subset_file)
            _write_json(output_dir / subset_file, filtered)
            split_counts[dataset_name][split_name] = len(filtered)

            if split_name == "heldout":
                heldout_references[dataset_name] = filtered

    manifest = {
        "source_dir": str(source_dir),
        "reference_dataset": reference_dataset,
        "seed": seed,
        "val_ratio": val_ratio,
        "heldout_ratio": heldout_ratio,
        "split_ids": {
            "train": train_ids,
            "val": val_ids,
            "heldout": heldout_ids,
        },
        "split_counts": split_counts,
    }

    _write_json(output_dir / "dataset_info.json", split_dataset_info)
    _write_json(output_dir / "split_manifest.json", manifest)
    _write_json(output_dir / "heldout_instance_ids.json", heldout_ids)
    _write_json(output_dir / "heldout_references.json", heldout_references)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a Trainer dataset bundle into train/val/heldout subsets by instance_id.")
    parser.add_argument("--source-dir", required=True, help="Directory containing dataset_info.json and dataset JSON files.")
    parser.add_argument("--output-dir", required=True, help="Output directory for the split bundle.")
    parser.add_argument("--reference-dataset", default="task_answer_sft", help="Dataset name used to define the task-level split universe.")
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Validation split ratio over reference tasks.")
    parser.add_argument("--heldout-ratio", type=float, default=0.15, help="Held-out split ratio over reference tasks.")
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed.")
    args = parser.parse_args()

    manifest = build_split_bundle(
        source_dir=Path(args.source_dir).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        reference_dataset=str(args.reference_dataset).strip(),
        val_ratio=float(args.val_ratio),
        heldout_ratio=float(args.heldout_ratio),
        seed=int(args.seed),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
