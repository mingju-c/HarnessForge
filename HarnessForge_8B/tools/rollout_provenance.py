"""Source declarations for newly collected rollouts; not historical evidence."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def build_rollout_provenance(args: Any, infile: str, model_name: str) -> dict:
    path = Path(infile).resolve()
    return {
        "round_id": getattr(args, "registry_round", None),
        "harness": args.harness,
        "policy_id": getattr(args, "model_alias", None) or model_name,
        "dataset_id": getattr(args, "registry_dataset", None) or path.stem,
        "data_split": getattr(args, "data_split", "unspecified"),
        "model_name": model_name,
        "model_adapter": getattr(args, "model_adapter", None),
        "input_path": str(path),
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_resume_provenance(rows: list[dict], expected: dict) -> None:
    for row in rows:
        recorded = row.get("provenance")
        if recorded != expected and (recorded is not None or expected["data_split"] != "unspecified"):
            raise ValueError(
                "Existing results have missing or conflicting rollout provenance. "
                "Use a new --outfile; do not relabel completed runs as another round, pair, or split."
            )
