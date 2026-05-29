from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _domain_counter(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for row in rows:
        domain = row.get("domain", "__missing__")
        counts[str(domain)] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].lower(), item[0])))


def _build_rounds(rows: list[dict[str, Any]], round_size: int) -> list[list[dict[str, Any]]]:
    if round_size <= 0:
        raise ValueError("round_size must be positive.")
    if len(rows) % round_size != 0:
        raise ValueError(f"{len(rows)} rows cannot be evenly divided into rounds of size {round_size}.")
    return [rows[start : start + round_size] for start in range(0, len(rows), round_size)]


def build_toolhop_split(
    source_path: Path,
    output_dir: Path,
    seed: int,
    online_dev_size: int,
    test_size: int,
    round_size: int,
) -> dict[str, Any]:
    data = _read_json(source_path)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list dataset at {source_path}, got {type(data).__name__}.")
    if len(data) != online_dev_size + test_size:
        raise ValueError(
            f"Dataset size mismatch: expected {online_dev_size + test_size}, found {len(data)}."
        )

    shuffled_rows = list(data)
    rng = random.Random(seed)
    rng.shuffle(shuffled_rows)

    online_dev_rows = shuffled_rows[:online_dev_size]
    final_blind_test_rows = shuffled_rows[online_dev_size:]
    rounds = _build_rounds(online_dev_rows, round_size=round_size)

    _write_json(output_dir / "toolhop_online_dev.json", online_dev_rows)
    _write_json(output_dir / "toolhop_final_blind_test.json", final_blind_test_rows)

    round_manifest: list[dict[str, Any]] = []
    for index, round_rows in enumerate(rounds, start=1):
        round_name = f"round_{index}"
        _write_json(output_dir / "rounds" / f"{round_name}.json", round_rows)
        _write_json(output_dir / "rounds" / f"{round_name}_ids.json", [row["id"] for row in round_rows])
        round_manifest.append(
            {
                "name": round_name,
                "size": len(round_rows),
                "ids": [row["id"] for row in round_rows],
                "domain_counts": _domain_counter(round_rows),
            }
        )

    manifest = {
        "source_path": str(source_path),
        "output_dir": str(output_dir),
        "seed": seed,
        "dataset_size": len(data),
        "split_scheme": {
            "online_dev_size": online_dev_size,
            "final_blind_test_size": test_size,
            "round_size": round_size,
            "num_rounds": len(rounds),
        },
        "split_ids": {
            "online_dev": [row["id"] for row in online_dev_rows],
            "final_blind_test": [row["id"] for row in final_blind_test_rows],
        },
        "summary": {
            "full_dataset_domain_counts": _domain_counter(data),
            "online_dev_domain_counts": _domain_counter(online_dev_rows),
            "final_blind_test_domain_counts": _domain_counter(final_blind_test_rows),
        },
        "rounds": round_manifest,
    }

    _write_json(output_dir / "split_manifest.json", manifest)
    _write_json(output_dir / "online_dev_ids.json", manifest["split_ids"]["online_dev"])
    _write_json(output_dir / "final_blind_test_ids.json", manifest["split_ids"]["final_blind_test"])
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Shuffle ToolHop with a fixed seed and split it into online development rounds and a final blind test set."
    )
    parser.add_argument(
        "--source",
        default="data/toolhop/ToolHop.json",
        help="Path to ToolHop.json.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/toolhop/splits/seed_42_online_800_test_195_round_200",
        help="Directory for the split artifacts.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed.")
    parser.add_argument("--online-dev-size", type=int, default=800, help="Number of examples in the online development stream.")
    parser.add_argument("--test-size", type=int, default=195, help="Number of examples in the final blind test set.")
    parser.add_argument("--round-size", type=int, default=200, help="Number of examples per online round.")
    args = parser.parse_args()

    manifest = build_toolhop_split(
        source_path=Path(args.source).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        seed=int(args.seed),
        online_dev_size=int(args.online_dev_size),
        test_size=int(args.test_size),
        round_size=int(args.round_size),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
