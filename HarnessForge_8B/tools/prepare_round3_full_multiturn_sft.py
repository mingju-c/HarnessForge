#!/usr/bin/env python3
"""Prepare clean09-style full multi-turn SFT data for round3 harness runs."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BENCHMARK_ORDER = ("envscaler", "searchqa", "toolhop")

TERMINAL_CONTRACTS = {
    "envscaler": (
        "Benchmark terminal contract:\n"
        "- benchmark: envscaler\n"
        "- complete_task is valid only for EnvScaler and only after required state mutations are complete.\n"
        "- Do not use final_answer for EnvScaler."
    ),
    "searchqa": (
        "Benchmark terminal contract:\n"
        "- benchmark: searchqa\n"
        "- Use final_answer for the final short answer only after search observations support it.\n"
        "- Never call complete_task in SearchQA."
    ),
    "toolhop": (
        "Benchmark terminal contract:\n"
        "- benchmark: toolhop\n"
        "- Use final_answer for the final short answer only after tool observations support it.\n"
        "- Never call complete_task in ToolHop."
    ),
}

DEFAULT_ROOT = Path(".")

DEFAULT_JOBS = (
    ("round3_1", "harness4", "output/exp_4_three_rounds/round03_01/harness_round03_01_4_run"),
    ("round3_1", "harness5", "output/exp_4_three_rounds/round03_01/harness_round03_01_5_run"),
    ("round3_2", "harness1", "output/exp_4_three_rounds/round03_02/harness_round03_02_1_run"),
    ("round3_2", "harness3", "output/exp_4_three_rounds/round03_02/harness_round03_02_3_run"),
    ("round3_3", "harness6", "output/exp_4_three_rounds/round03_03/harness_round03_03_6_run"),
    ("round3_3", "harness7", "output/exp_4_three_rounds/round03_03/harness_round03_03_7_run"),
    ("round3_4", "harness1", "output/exp_4_three_rounds/round03_04/harness_round03_04_1_run"),
    ("round3_4", "harness6", "output/exp_4_three_rounds/round03_04/harness_round03_04_6_run"),
)


def flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    marker = "Calling tools:"
    if marker not in text:
        return []
    payload = text.split(marker, 1)[1].strip()
    if not payload:
        return []
    try:
        parsed = ast.literal_eval(payload)
    except (SyntaxError, ValueError):
        return []
    tools = parsed.get("tools") if isinstance(parsed, dict) else None
    if not isinstance(tools, list):
        return []
    calls = []
    for call in tools:
        if isinstance(call, dict) and isinstance(call.get("name"), str):
            calls.append(call)
    return calls


def tool_call_key(calls: list[dict[str, Any]]) -> str:
    compact = [
        {"name": call.get("name"), "arguments": call.get("arguments", {})}
        for call in calls
    ]
    return canonical_json(compact)


def is_bad_observation(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    bad_markers = {
        "Tool calling observation:",
        "Tool calling observation:\n",
    }
    return stripped in bad_markers


def normalized_messages(raw_messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages = []
    for msg in raw_messages:
        role = msg.get("role", "")
        content = flatten_content(msg.get("content"))
        if role and content:
            messages.append({"role": role, "content": content})
    return messages


def append_message(messages: list[dict[str, str]], role: str, content: str) -> None:
    content = content.strip()
    if not content:
        return
    if role == "tool-response":
        role = "user"
    if role not in {"user", "assistant", "system"}:
        role = "user"
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"] = f"{messages[-1]['content']}\n\n{content}"
    else:
        messages.append({"role": role, "content": content})


def add_terminal_contract(first_content: str, benchmark: str) -> str:
    if first_content.startswith("Benchmark terminal contract:"):
        return first_content
    contract = TERMINAL_CONTRACTS.get(benchmark)
    if not contract:
        return first_content
    return f"{contract}\n\n{first_content}"


def clean_messages(
    raw_messages: list[dict[str, Any]],
    benchmark: str,
    cleaning_actions: Counter[str],
) -> list[dict[str, str]]:
    raw = normalized_messages(raw_messages)
    cleaned: list[dict[str, str]] = []
    seen_nonterminal: set[str] = set()
    seen_env_pairs: set[tuple[str, str]] = set()
    terminal_reached = False
    first_user_seen = False
    i = 0

    while i < len(raw):
        msg = raw[i]
        role = msg["role"]
        content = msg["content"]

        if terminal_reached:
            if benchmark == "envscaler":
                cleaning_actions["dropped:envscaler_after_complete_task_messages"] += 1
            i += 1
            continue

        if role == "assistant":
            calls = parse_tool_calls(content)
            names = [call["name"] for call in calls]
            has_complete_task = "complete_task" in names
            has_final_answer = "final_answer" in names
            is_terminal = has_complete_task or has_final_answer
            next_obs = ""
            if i + 1 < len(raw) and raw[i + 1]["role"] == "tool-response":
                next_obs = raw[i + 1]["content"].strip()

            drop_reason = ""
            if benchmark != "envscaler" and has_complete_task:
                drop_reason = "dropped:non_envscaler_complete_task"
            elif benchmark == "envscaler" and has_final_answer:
                drop_reason = "dropped:envscaler_final_answer"
            elif calls and not is_terminal:
                key = tool_call_key(calls)
                if benchmark in {"searchqa", "toolhop"}:
                    if key in seen_nonterminal:
                        drop_reason = "dropped:duplicate_nonterminal_tool_action"
                    else:
                        seen_nonterminal.add(key)
                elif benchmark == "envscaler":
                    pair_key = (key, next_obs)
                    if pair_key in seen_env_pairs:
                        drop_reason = "dropped:duplicate_env_call_and_observation"
                    else:
                        seen_env_pairs.add(pair_key)

            if drop_reason:
                cleaning_actions[drop_reason] += 1
                i += 1
                if i < len(raw) and raw[i]["role"] == "tool-response":
                    i += 1
                continue

            append_message(cleaned, "assistant", content)
            if benchmark == "envscaler" and has_complete_task:
                terminal_reached = True
            elif benchmark in {"searchqa", "toolhop"} and has_final_answer:
                terminal_reached = True
            i += 1
            continue

        if role == "tool-response":
            if is_bad_observation(content):
                cleaning_actions["dropped:bad_observation_marker"] += 1
            else:
                append_message(cleaned, "user", content)
            i += 1
            continue

        if role == "user" and not first_user_seen:
            content = add_terminal_contract(content, benchmark)
            first_user_seen = True
        append_message(cleaned, role, content)
        i += 1

    while cleaned and cleaned[-1]["role"] != "assistant":
        cleaned.pop()
        cleaning_actions["dropped:trailing_user_messages"] += 1

    if cleaned and cleaned[0]["role"] != "user":
        return []
    for left, right in zip(cleaned, cleaned[1:]):
        if left["role"] == right["role"]:
            return []
    return cleaned


def numeric_file_key(path: Path) -> tuple[int, str]:
    try:
        return (int(path.stem), path.name)
    except ValueError:
        return (math.inf, path.name)


def score_for_bucket(record: dict[str, Any], benchmark: str) -> float:
    if benchmark == "envscaler":
        return float(record.get("envscaler_score") or 0.0)
    return float(record.get("score") or 0.0)


def score_bucket(score: float) -> str:
    if score == 1:
        return "score=1"
    if score >= 0.9:
        return "0.9<=score<1"
    if score > 0:
        return "0<score<0.9"
    return "score=0"


def selected(record: dict[str, Any], benchmark: str) -> bool:
    if benchmark == "envscaler":
        return (
            float(record.get("envscaler_score") or 0.0) >= 0.9
            and float(record.get("envscaler_done") or 0.0) == 1.0
        )
    if benchmark in {"searchqa", "toolhop"}:
        return (
            float(record.get("score") or 0.0) == 1.0
            and float(record.get("answer_correct") or 0.0) == 1.0
        )
    return False


def metadata_for(record: dict[str, Any], input_dir: Path, source_file: Path, round_name: str) -> dict[str, Any]:
    keys = [
        "item_index",
        "mixed_benchmark",
        "data_source",
        "ability",
        "score",
        "answer_correct",
        "subem",
        "envscaler_score",
        "envscaler_done",
        "tool_call_count",
        "metrics",
    ]
    metadata = {
        "source_run": input_dir.name,
        "source_file": source_file.name,
    }
    for key in keys:
        if key in record:
            metadata[key] = record[key]
    metadata["cleaning_policy"] = f"{round_name}_full_multiturn_clean09_selection_keep_full_trajectory"
    return metadata


def dataset_info(dataset_name: str, train_dataset: str, eval_dataset: str) -> dict[str, Any]:
    def entry(file_name: str) -> dict[str, Any]:
        return {
            "file_name": file_name,
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

    return {
        dataset_name: entry(f"{dataset_name}.jsonl"),
        train_dataset: entry(f"{train_dataset}.jsonl"),
        eval_dataset: entry(f"{eval_dataset}.jsonl"),
    }


def choose_eval(records: list[dict[str, Any]], eval_ratio: float, seed: int) -> set[int]:
    by_benchmark: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        by_benchmark[record["metadata"]["mixed_benchmark"]].append(index)

    eval_indices: set[int] = set()
    for benchmark in BENCHMARK_ORDER:
        indices = by_benchmark.get(benchmark, [])
        count = int(len(indices) * eval_ratio)
        if count <= 0:
            continue
        rng = random.Random(f"{seed}:{benchmark}")
        eval_indices.update(rng.sample(indices, count))
    return eval_indices


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def make_readme(dataset_name: str, stats: dict[str, Any]) -> str:
    return (
        f"# {dataset_name}\n\n"
        f"Full cleaned {stats['round_display']} multi-turn SFT data.\n\n"
        "Files:\n"
        f"- `{stats['output_file']}`: all records.\n"
        f"- `{stats['train_file']}`: train split.\n"
        f"- `{stats['eval_file']}`: eval split.\n"
        "- `dataset_info.json`: LlamaFactory sharegpt registration.\n"
        "- `stats.json`: selection, cleaning, and split statistics.\n\n"
        "Cleaning:\n"
        "- one source trajectory becomes one SFT record;\n"
        "- plan/action/summary/terminal assistant turns are preserved;\n"
        "- tool observations are folded into user turns to keep sharegpt alternation;\n"
        "- noisy guard/schema/repeat/partial-commit tool turns are removed with their observations.\n\n"
        f"Records kept: {stats['records_kept']}\n"
        f"Train/eval: {stats['train_total']} / {stats['eval_total']}\n"
    )


def process_job(
    root: Path,
    round_name: str,
    harness_name: str,
    input_rel: str,
    eval_ratio: float,
    seed: int,
) -> dict[str, Any]:
    input_dir = root / input_rel
    output_dir = root / "LlamaFactory/data/traindata" / round_name / harness_name
    dataset_name = f"{round_name}_{harness_name}_full_multiturn_sft"
    train_dataset = f"{dataset_name}_train"
    eval_dataset = f"{dataset_name}_eval"

    by_benchmark_seen: Counter[str] = Counter()
    by_benchmark_selected: Counter[str] = Counter()
    score_buckets_seen: dict[str, Counter[str]] = defaultdict(Counter)
    score_buckets_selected: dict[str, Counter[str]] = defaultdict(Counter)
    cleaning_actions: Counter[str] = Counter()
    invalid_reasons: Counter[str] = Counter()
    records_by_benchmark: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    records_selected_before_cleaning = 0

    source_files = [
        path
        for path in input_dir.glob("*.json")
        if path.name != "mixeddata.metrics.overall.json"
    ]
    records_seen = len(source_files)
    by_benchmark_records: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)

    for source_file in sorted(source_files, key=numeric_file_key):
        with source_file.open("r", encoding="utf-8") as f:
            raw_record = json.load(f)
        benchmark = raw_record.get("mixed_benchmark") or raw_record.get("data_source", "").removeprefix("mixed_")
        if benchmark not in BENCHMARK_ORDER:
            benchmark = str(benchmark or "unknown")
        by_benchmark_seen[benchmark] += 1
        score_buckets_seen[benchmark][score_bucket(score_for_bucket(raw_record, benchmark))] += 1
        by_benchmark_records[benchmark].append((source_file, raw_record))

    for benchmark in BENCHMARK_ORDER:
        for source_file, raw_record in by_benchmark_records.get(benchmark, []):
            if not selected(raw_record, benchmark):
                continue
            records_selected_before_cleaning += 1
            by_benchmark_selected[benchmark] += 1
            score_buckets_selected[benchmark][score_bucket(score_for_bucket(raw_record, benchmark))] += 1
            messages = clean_messages(raw_record.get("agent_messages") or [], benchmark, cleaning_actions)
            if not messages:
                invalid_reasons["empty_or_non_alternating_messages"] += 1
                continue
            records.append(
                {
                    "messages": messages,
                    "metadata": metadata_for(raw_record, input_dir, source_file, round_name),
                }
            )
            records_by_benchmark[benchmark] += 1

    eval_indices = choose_eval(records, eval_ratio, seed)
    train_records = [record for idx, record in enumerate(records) if idx not in eval_indices]
    eval_records = [record for idx, record in enumerate(records) if idx in eval_indices]

    train_by_benchmark = Counter(record["metadata"]["mixed_benchmark"] for record in train_records)
    eval_by_benchmark = Counter(record["metadata"]["mixed_benchmark"] for record in eval_records)
    turn_counts = [len(record["messages"]) for record in records]

    stats = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "dataset_name": dataset_name,
        "output_file": f"{dataset_name}.jsonl",
        "train_dataset": train_dataset,
        "eval_dataset": eval_dataset,
        "train_file": f"{train_dataset}.jsonl",
        "eval_file": f"{eval_dataset}.jsonl",
        "selection_policy": "clean09",
        "eval_ratio": eval_ratio,
        "records_seen": records_seen,
        "records_selected_before_cleaning": records_selected_before_cleaning,
        "records_kept": len(records),
        "by_benchmark_seen": dict(by_benchmark_seen),
        "by_benchmark_selected": dict(by_benchmark_selected),
        "by_benchmark_kept": dict(records_by_benchmark),
        "score_buckets_seen": {key: dict(value) for key, value in score_buckets_seen.items()},
        "score_buckets_selected": {key: dict(value) for key, value in score_buckets_selected.items()},
        "invalid_reasons": dict(invalid_reasons),
        "cleaning_actions": dict(cleaning_actions),
        "train_total": len(train_records),
        "eval_total": len(eval_records),
        "records_selected_but_invalid": records_selected_before_cleaning - len(records),
        "records_by_benchmark": dict(records_by_benchmark),
        "train_by_benchmark": dict(train_by_benchmark),
        "eval_by_benchmark": dict(eval_by_benchmark),
        "turn_count": {
            "min": min(turn_counts) if turn_counts else 0,
            "max": max(turn_counts) if turn_counts else 0,
            "avg": round(sum(turn_counts) / len(turn_counts), 4) if turn_counts else 0,
        },
        "policy": {
            "selection": {
                "envscaler": "envscaler_score >= 0.9 and envscaler_done == 1",
                "searchqa": "score == 1 and answer_correct == 1",
                "toolhop": "score == 1 and answer_correct == 1",
            },
            "format": "LlamaFactory sharegpt messages; tool-response observations folded into user turns",
            "trajectory": "one full cleaned trajectory per selected source item",
            "repair": [
                "drop guard/unknown/schema/repeated/partial-commit tool turns and observations",
                "drop non-EnvScaler complete_task turns",
                "drop EnvScaler final_answer turns",
                "drop duplicate nonterminal calls for SearchQA/ToolHop",
                "for EnvScaler, only drop duplicate call+identical observation pairs",
            ],
        },
        "round_display": round_name.replace("round", "round0").replace("_", "_"),
    }
    stats.pop("round_display")

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / f"{dataset_name}.jsonl", records)
    write_jsonl(output_dir / f"{train_dataset}.jsonl", train_records)
    write_jsonl(output_dir / f"{eval_dataset}.jsonl", eval_records)
    write_json(output_dir / "dataset_info.json", dataset_info(dataset_name, train_dataset, eval_dataset))
    write_json(output_dir / "stats.json", stats)

    readme_stats = dict(stats)
    readme_stats["round_display"] = round_name.replace("round", "round0")
    (output_dir / "README.md").write_text(make_readme(dataset_name, readme_stats), encoding="utf-8")
    return stats


def parse_job(job: str) -> tuple[str, str, str]:
    parts = job.split(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("job must be ROUND:HARNESS:INPUT_REL_PATH")
    return parts[0], parts[1], parts[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--eval-ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--job",
        action="append",
        type=parse_job,
        help="ROUND:HARNESS:INPUT_REL_PATH. Defaults to all requested round3 jobs.",
    )
    args = parser.parse_args()

    jobs = args.job or DEFAULT_JOBS
    summaries = []
    for round_name, harness_name, input_rel in jobs:
        stats = process_job(args.root, round_name, harness_name, input_rel, args.eval_ratio, args.seed)
        summaries.append(
            {
                "dataset_name": stats["dataset_name"],
                "records_seen": stats["records_seen"],
                "records_kept": stats["records_kept"],
                "train_total": stats["train_total"],
                "eval_total": stats["eval_total"],
                "output_dir": stats["output_dir"],
            }
        )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
