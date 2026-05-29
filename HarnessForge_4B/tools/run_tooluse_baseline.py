#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE = ""
API_BANK_BENCHMARKS = ("api_bank",)
DEFAULT_BENCHMARKS = ("toolhop", "restbench_tmdb", *API_BANK_BENCHMARKS)


def sanitize_id(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("_") or "none"


def infer_round(harness_name: str) -> str | None:
    text = str(harness_name or "")
    patterns = [
        r"(?:^|\.)Round[_-]?(\d+)(?:\.|$)",
        r"[_-]R(\d+)(?:$|[^0-9])",
        r"(?:^|[_-])round[_-]?(\d+)(?:$|[^0-9])",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return str(int(match.group(1)))
    return None


def normalize_harness_import(harness_name: str) -> tuple[str, str | None]:
    raw = str(harness_name or "").strip()
    if not raw:
        raise ValueError("--harness is required.")

    round_id = infer_round(raw)
    if raw.startswith("Round_") or raw.startswith("Round-"):
        return raw.replace("-", "_"), round_id
    if raw.startswith("base_harness"):
        return "base_harness", round_id
    if round_id and re.search(r"[_-]R\d+", raw, flags=re.IGNORECASE):
        return f"Round_{round_id}.{raw.replace('-', '_')}", round_id
    return raw.replace("-", "_"), round_id


def resolve_toolhop_file(args: argparse.Namespace, round_id: str | None) -> str:
    mode = str(args.toolhop_split or "test").strip().lower()
    if mode == "auto":
        return "test"
    if mode in {"harness_round", "inferred_round"}:
        return round_id if round_id else "test"
    if mode in {"full", "all", "bench"}:
        return str(args.toolhop_full_path)
    return mode


def selected_benchmarks(raw: str) -> list[str]:
    if not raw or raw.strip().lower() in {"all", "default"}:
        return list(DEFAULT_BENCHMARKS)
    aliases = {
        "spotify": "restbench_spotify",
        "tmdb": "restbench_tmdb",
        "restbench": "restbench_spotify,restbench_tmdb",
        "apibank": "api_bank",
        "api_bank": "api_bank",
        "apibank_all": "api_bank",
        "api_bank_all": "api_bank",
    }
    selected: list[str] = []
    for part in raw.split(","):
        name = aliases.get(part.strip().lower(), part.strip().lower())
        for sub_name in name.split(","):
            if sub_name:
                selected.append(sub_name)
    return selected


def build_command(
    *,
    args: argparse.Namespace,
    benchmark: str,
    harness_import: str,
    harness_label: str,
    round_id: str | None,
) -> list[str]:
    model_label = sanitize_id(args.model_alias or args.model)
    bench_label = benchmark
    if benchmark == "toolhop":
        toolhop_file = resolve_toolhop_file(args, round_id)
        if toolhop_file in {"1", "2", "3", "4"}:
            bench_label = f"toolhop_round{toolhop_file}"
        elif toolhop_file.lower() in {"test", "final", "final_test", "final_blind", "final_blind_test"}:
            bench_label = "toolhop_test"
        elif toolhop_file.lower() in {"dev", "online_dev"}:
            bench_label = "toolhop_online_dev"
        else:
            bench_label = "toolhop_full"
    run_dir = args.output_root / sanitize_id(harness_label) / model_label / bench_label
    storage_dir = args.storage_root / sanitize_id(harness_label) / model_label / bench_label

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "run_infer.py"),
        "--benchmark",
        benchmark,
        "--harness_package",
        args.harness_package,
        "--harness",
        harness_import,
        "--model",
        args.model,
        "--model-backend",
        args.model_backend,
        "--api-base",
        args.api_base,
        "--concurrency",
        str(args.concurrency),
        "--max_steps",
        str(args.max_steps),
        "--outfile",
        str(run_dir / "results.jsonl"),
        "--direct_output_dir",
        str(run_dir),
        "--memory_storage_dir",
        str(storage_dir),
    ]
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])
    if args.sample_num is not None:
        cmd.extend(["--sample_num", str(args.sample_num)])
    if args.task_indices:
        cmd.extend(["--task_indices", args.task_indices])
    if args.memory_provider:
        cmd.extend(["--memory_provider", args.memory_provider])
    if args.memory_write_only:
        cmd.extend(["--memory-write-only", "true"])
    if args.model_adapter:
        cmd.extend(["--model-adapter", args.model_adapter])
    if args.model_alias:
        cmd.extend(["--model-alias", args.model_alias])

    if benchmark == "toolhop":
        cmd.extend(["--toolhop-file", resolve_toolhop_file(args, round_id), "--toolhop-mode", "closed"])

    if args.record_harness_registry:
        cmd.extend(
            [
                "--record-harness-registry",
                "--registry-file",
                str(args.registry_file),
                "--registry-experiment",
                args.experiment,
                "--registry-dataset",
                bench_label,
            ]
        )
        if round_id:
            cmd.extend(["--registry-round", f"round_{round_id}"])
        elif benchmark == "toolhop":
            cmd.extend(["--registry-round", "full"])

    return cmd


def subprocess_env(args: argparse.Namespace) -> dict[str, str]:
    return os.environ.copy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the first MATE tool-use baselines from only a harness name and model name. "
            "Default benchmarks: ToolHop, RestBench-TMDB, DeepAgent-style API-Bank."
        )
    )
    parser.add_argument("--harness", required=True, help="Harness name, e.g. base_harness, base_harness_R1, harness9_R1.")
    parser.add_argument("--model", required=True, help="Served model name or OpenAI model id.")
    parser.add_argument("--model-alias", default=None, help="Optional shorter model label for output/registry paths.")
    parser.add_argument("--model-adapter", default=os.environ.get("MODEL_ADAPTER") or os.environ.get("LORA_ADAPTER"))
    parser.add_argument("--model-backend", default=os.environ.get("MODEL_BACKEND") or "local", choices=["api", "local"])
    parser.add_argument("--api-base", default=os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or DEFAULT_API_BASE)
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument(
        "--benchmarks",
        default="all",
        help=(
            "Comma-separated: toolhop, restbench_tmdb, api_bank, "
            "tmdb, apibank, api_bank_lv1_test, api_bank_lv2_test, api_bank_lv3_test, spotify, all."
        ),
    )
    parser.add_argument(
        "--toolhop-split",
        default="test",
        help=(
            "test (default, the retained 195-item final blind test), full, 1-4, "
            "online_dev, harness_round, or a JSON/JSONL path."
        ),
    )
    parser.add_argument(
        "--toolhop-full-path",
        type=Path,
        default=PROJECT_ROOT / "eval_bench" / "toolhop" / "data" / "ToolHop.json",
    )
    parser.add_argument("--harness-package", default="harness_factory")
    parser.add_argument("--sample-num", type=int, default=None)
    parser.add_argument("--task-indices", default=None)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--memory-provider", default=None)
    parser.add_argument("--memory-write-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "output" / "tooluse_baselines")
    parser.add_argument("--storage-root", type=Path, default=PROJECT_ROOT / "storage" / "tooluse_baselines")
    parser.add_argument("--registry-file", type=Path, default=PROJECT_ROOT / "registries" / "harness_pool.yaml")
    parser.add_argument("--experiment", default="tooluse_baseline")
    parser.add_argument("--record-harness-registry", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    harness_import, round_id = normalize_harness_import(args.harness)
    benchmarks = selected_benchmarks(args.benchmarks)

    if not args.api_base:
        raise SystemExit("--api-base is required, or set OPENAI_BASE_URL/OPENAI_API_BASE.")

    print(f"Harness input: {args.harness}")
    print(f"Harness import: {harness_import}")
    print(f"Inferred round: {round_id or 'none'}")
    print(f"Model: {args.model}")
    print(f"Benchmarks: {', '.join(benchmarks)}")
    run_env = subprocess_env(args)

    for benchmark in benchmarks:
        cmd = build_command(
            args=args,
            benchmark=benchmark,
            harness_import=harness_import,
            harness_label=args.harness,
            round_id=round_id,
        )
        print("\n$ " + " ".join(cmd))
        if args.dry_run:
            continue
        subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=run_env, check=True)


if __name__ == "__main__":
    main()
