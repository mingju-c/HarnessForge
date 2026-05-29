#!/usr/bin/env python3
"""Prepare strict action-only round1 harness SFT data.

This cleaner is intentionally conservative:
- keep only strict successful trajectories;
- reject the whole trajectory if it contains guard/invalid/repeated-failure noise;
- reject non-EnvScaler trajectories that ever call complete_task;
- reject exact duplicate non-terminal tool calls;
- train only action/tool-call turns, never plan turns;
- downsample terminal turns so final_answer/complete_task does not dominate.
"""

from __future__ import annotations

import argparse
import ast
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BAD_OBSERVATION_MARKERS = (
    "ROUND01_GUARD_BLOCK",
    "Unknown tool",
    "schema_preflight",
    "repeated_failed_call",
    "low_value_repeat",
    "ROUND01_PARTIAL_COMMIT",
)

TERMINAL_TOOLS = {"final_answer", "complete_task"}

TAGS = {
    "role_tag": "role",
    "content_tag": "content",
    "user_tag": "user",
    "assistant_tag": "assistant",
    "system_tag": "system",
}


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def content_to_text(content: Any) -> str:
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


def numeric_json_files(input_dir: Path) -> list[Path]:
    return sorted(
        (path for path in input_dir.glob("*.json") if path.stem.isdigit()),
        key=lambda path: int(path.stem),
    )


def benchmark_of(row: dict[str, Any]) -> str:
    benchmark = row.get("mixed_benchmark")
    if isinstance(benchmark, str) and benchmark:
        return benchmark
    data_source = str(row.get("data_source") or "")
    return data_source.replace("mixed_", "") or "unknown"


def is_strict_success(row: dict[str, Any]) -> bool:
    benchmark = benchmark_of(row)
    score = to_float(row.get("score"))
    if benchmark in {"toolhop", "searchqa"}:
        return score == 1.0 and to_float(row.get("answer_correct")) == 1.0
    if benchmark == "envscaler":
        return score == 1.0 and to_float(row.get("envscaler_done")) == 1.0
    return False


def terminal_contract(benchmark: str) -> str:
    if benchmark == "envscaler":
        return (
            "Benchmark terminal contract:\n"
            "- benchmark: envscaler\n"
            "- complete_task is valid only for EnvScaler and only after every required state mutation is complete.\n"
            "- Do not use final_answer for EnvScaler.\n"
        )
    if benchmark == "toolhop":
        return (
            "Benchmark terminal contract:\n"
            "- benchmark: toolhop\n"
            "- Use final_answer for the final short answer only after tool observations support it.\n"
            "- Never call complete_task in ToolHop.\n"
        )
    if benchmark == "searchqa":
        return (
            "Benchmark terminal contract:\n"
            "- benchmark: searchqa\n"
            "- Use the benchmark final-answer tool/format only after evidence supports the answer.\n"
            "- Never call complete_task in SearchQA.\n"
        )
    return f"Benchmark terminal contract:\n- benchmark: {benchmark}\n"


def action_prompt() -> str:
    return (
        "Now choose the next action for this task. "
        "Output a valid Calling tools block with exact tool names and schema keys. "
        "Do not guess unsupported final answers."
    )


def parse_tool_payload(text: str) -> dict[str, Any] | None:
    prefix = "Calling tools:"
    stripped = text.strip()
    if not stripped.startswith(prefix):
        return None
    payload_text = stripped[len(prefix) :].strip()
    try:
        payload = ast.literal_eval(payload_text)
    except (SyntaxError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def calls_from_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    calls = payload.get("tools")
    if not isinstance(calls, list):
        return []
    return [
        call
        for call in calls
        if isinstance(call, dict) and isinstance(call.get("name"), str)
    ]


def call_signature(call: dict[str, Any]) -> str:
    name = str(call.get("name") or "")
    arguments = call.get("arguments") or {}
    return f"{name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True)}"


def add_message(messages: list[dict[str, str]], role: str, content: str) -> None:
    content = content.strip()
    if not content:
        return
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"] = f'{messages[-1]["content"].rstrip()}\n\n{content}'
    else:
        messages.append({"role": role, "content": content})


def next_tool_response(raw_messages: list[dict[str, Any]], idx: int) -> tuple[int | None, str]:
    next_idx = idx + 1
    if next_idx >= len(raw_messages):
        return None, ""
    candidate = raw_messages[next_idx]
    if isinstance(candidate, dict) and candidate.get("role") == "tool-response":
        return next_idx, content_to_text(candidate.get("content")).strip()
    return None, ""


def row_reject_reason(row: dict[str, Any]) -> str | None:
    benchmark = benchmark_of(row)
    raw_messages = row.get("agent_messages")
    if not isinstance(raw_messages, list):
        return "missing_agent_messages"

    text_blob = json.dumps(
        {
            "agent_messages": raw_messages,
            "agent_trajectory": row.get("agent_trajectory"),
        },
        ensure_ascii=False,
    )
    for marker in BAD_OBSERVATION_MARKERS:
        if marker in text_blob:
            return f"dirty_marker:{marker}"

    seen_nonterminal: set[str] = set()
    has_tool_action = False
    for raw_message in raw_messages:
        if not isinstance(raw_message, dict) or raw_message.get("role") != "assistant":
            continue
        payload = parse_tool_payload(content_to_text(raw_message.get("content")))
        calls = calls_from_payload(payload)
        if not calls:
            continue
        has_tool_action = True
        names = [str(call.get("name") or "") for call in calls]
        if benchmark != "envscaler" and "complete_task" in names:
            return "non_env_complete_task"
        if benchmark == "envscaler" and "final_answer" in names:
            return "env_final_answer"
        for call in calls:
            if call.get("name") in TERMINAL_TOOLS:
                continue
            signature = call_signature(call)
            if signature in seen_nonterminal:
                return "duplicate_nonterminal_tool_call"
            seen_nonterminal.add(signature)

    if not has_tool_action:
        return "no_tool_actions"
    return None


def is_planning_prompt(text: str) -> bool:
    return "begin your planning analysis" in text.lower()


def build_clean_dialogue(row: dict[str, Any]) -> tuple[list[dict[str, str]], Counter[str]]:
    benchmark = benchmark_of(row)
    raw_messages = row.get("agent_messages")
    stats: Counter[str] = Counter()
    if not isinstance(raw_messages, list):
        stats["missing_agent_messages"] += 1
        return [], stats

    messages: list[dict[str, str]] = []
    skip_indices: set[int] = set()
    inserted_action_prompt = False
    added_first_user = False

    for idx, raw_message in enumerate(raw_messages):
        if idx in skip_indices or not isinstance(raw_message, dict):
            continue
        raw_role = raw_message.get("role")
        text = content_to_text(raw_message.get("content")).strip()
        if not text:
            continue

        if raw_role == "assistant":
            payload = parse_tool_payload(text)
            calls = calls_from_payload(payload)
            if not calls:
                stats["dropped:plan_or_non_tool_assistant"] += 1
                continue

            response_idx, observation = next_tool_response(raw_messages, idx)
            is_terminal = any(call.get("name") in TERMINAL_TOOLS for call in calls)
            if response_idx is None:
                stats["dropped:missing_tool_response"] += 1
                continue
            if any(marker in observation for marker in BAD_OBSERVATION_MARKERS):
                stats["dropped:bad_observation_marker"] += 1
                skip_indices.add(response_idx)
                continue
            if not inserted_action_prompt:
                add_message(messages, "user", action_prompt())
                inserted_action_prompt = True
            add_message(messages, "assistant", text)
            skip_indices.add(response_idx)
            if not is_terminal:
                add_message(messages, "user", observation)
            continue

        if raw_role == "tool-response":
            stats["dropped:orphan_tool_response"] += 1
            continue

        if is_planning_prompt(text):
            stats["dropped:planning_prompt"] += 1
            continue
        if not added_first_user:
            text = f"{terminal_contract(benchmark)}\n{text}"
            added_first_user = True
        add_message(messages, "user", text)

    while messages and messages[-1]["role"] != "assistant":
        messages.pop()
        stats["dropped:trailing_user_message"] += 1
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
        stats["dropped:leading_assistant_message"] += 1
    return messages, stats


def validate_messages(messages: list[dict[str, str]], benchmark: str) -> tuple[bool, str]:
    if not messages:
        return False, "empty_messages"
    if len(messages) % 2 != 0:
        return False, "odd_message_count"
    for idx, message in enumerate(messages):
        expected = "user" if idx % 2 == 0 else "assistant"
        if message.get("role") != expected:
            return False, f"bad_role_at_{idx}"
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            return False, f"empty_content_at_{idx}"

    text_blob = "\n".join(message["content"] for message in messages)
    for marker in BAD_OBSERVATION_MARKERS:
        if marker in text_blob:
            return False, f"bad_marker:{marker}"

    assistant_blob = "\n".join(
        message["content"] for message in messages if message.get("role") == "assistant"
    )
    if "[PLAN]" in assistant_blob:
        return False, "plan_remaining"
    if benchmark != "envscaler" and "complete_task" in assistant_blob:
        return False, "non_env_complete_task_remaining"
    if benchmark == "envscaler" and "final_answer" in assistant_blob:
        return False, "env_final_answer_remaining"
    return True, "ok"


def target_tool_names(message: dict[str, str]) -> list[str]:
    if message.get("role") != "assistant":
        return []
    payload = parse_tool_payload(message.get("content", ""))
    return [str(call.get("name") or "") for call in calls_from_payload(payload)]


def make_prefix_samples(
    messages: list[dict[str, str]],
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    action_samples: list[dict[str, Any]] = []
    terminal_samples: list[dict[str, Any]] = []
    assistant_turn_index = 0
    for idx, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        names = target_tool_names(message)
        if not names:
            continue
        prefix = messages[: idx + 1]
        ok, reason = validate_messages(prefix, str(metadata["mixed_benchmark"]))
        if not ok:
            continue
        sample = {
            "messages": prefix,
            "metadata": {
                **metadata,
                "sample_type": "strict_action_prefix",
                "target_tool_names": names,
                "target_is_terminal": any(name in TERMINAL_TOOLS for name in names),
                "assistant_turn_index": assistant_turn_index,
                "prefix_message_count": len(prefix),
            },
        }
        assistant_turn_index += 1
        if sample["metadata"]["target_is_terminal"]:
            terminal_samples.append(sample)
        else:
            action_samples.append(sample)
    return action_samples, terminal_samples


def downsample_terminal_by_benchmark(
    action_samples: list[dict[str, Any]],
    terminal_samples: list[dict[str, Any]],
    max_terminal_ratio: float,
    seed: int,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    stats: Counter[str] = Counter()
    action_by_bench: dict[str, list[dict[str, Any]]] = defaultdict(list)
    terminal_by_bench: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in action_samples:
        action_by_bench[str(sample["metadata"].get("mixed_benchmark"))].append(sample)
    for sample in terminal_samples:
        terminal_by_bench[str(sample["metadata"].get("mixed_benchmark"))].append(sample)

    rng = random.Random(seed)
    kept_terminal: list[dict[str, Any]] = []
    for bench in sorted(terminal_by_bench):
        terminals = terminal_by_bench[bench]
        nonterminal_count = len(action_by_bench.get(bench, []))
        if max_terminal_ratio <= 0 or nonterminal_count <= 0:
            cap = 0
        else:
            cap = int(nonterminal_count * max_terminal_ratio / (1.0 - max_terminal_ratio))
            cap = max(1, cap)
        cap = min(cap, len(terminals))
        rng.shuffle(terminals)
        kept_terminal.extend(terminals[:cap])
        stats[f"terminal_seen:{bench}"] = len(terminals)
        stats[f"terminal_kept:{bench}"] = cap
        stats[f"terminal_dropped:{bench}"] = len(terminals) - cap
    return kept_terminal, stats


def dataset_info_entry(file_name: str) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "formatting": "sharegpt",
        "columns": {"messages": "messages"},
        "tags": TAGS,
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def split_rows(
    rows: list[dict[str, Any]],
    eval_ratio: float,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    by_bench: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_bench[str(row.get("metadata", {}).get("mixed_benchmark") or "unknown")].append(row)

    rng = random.Random(seed)
    train_rows: list[dict[str, Any]] = []
    eval_rows: list[dict[str, Any]] = []
    detail: dict[str, Any] = {}
    for bench in sorted(by_bench):
        items = by_bench[bench][:]
        rng.shuffle(items)
        if len(items) <= 1 or eval_ratio <= 0:
            eval_count = 0
        else:
            eval_count = max(1, round(len(items) * eval_ratio))
            eval_count = min(eval_count, len(items) - 1)
        eval_part = items[:eval_count]
        train_part = items[eval_count:]
        eval_rows.extend(eval_part)
        train_rows.extend(train_part)
        detail[bench] = {
            "total": len(items),
            "train": len(train_part),
            "eval": len(eval_part),
            "eval_ratio": round(len(eval_part) / len(items), 6) if items else 0.0,
        }
    rng.shuffle(train_rows)
    rng.shuffle(eval_rows)
    return train_rows, eval_rows, detail


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--max-terminal-ratio", type=float, default=0.25)
    parser.add_argument("--eval-ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = numeric_json_files(input_dir)
    by_benchmark_seen: Counter[str] = Counter()
    by_benchmark_strict_success: Counter[str] = Counter()
    by_benchmark_clean_trajectory: Counter[str] = Counter()
    reject_reasons: Counter[str] = Counter()
    invalid_reasons: Counter[str] = Counter()
    cleaning_actions: Counter[str] = Counter()

    action_samples: list[dict[str, Any]] = []
    terminal_samples: list[dict[str, Any]] = []

    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            row = json.load(handle)

        benchmark = benchmark_of(row)
        by_benchmark_seen[benchmark] += 1
        if not is_strict_success(row):
            continue
        by_benchmark_strict_success[benchmark] += 1

        reason = row_reject_reason(row)
        if reason is not None:
            reject_reasons[reason] += 1
            continue
        by_benchmark_clean_trajectory[benchmark] += 1

        messages, clean_stats = build_clean_dialogue(row)
        cleaning_actions.update(clean_stats)
        ok, reason = validate_messages(messages, benchmark)
        if not ok:
            invalid_reasons[reason] += 1
            continue

        metadata = {
            "source_run": input_dir.name,
            "source_file": path.name,
            "item_index": row.get("item_index"),
            "mixed_benchmark": benchmark,
            "data_source": row.get("data_source"),
            "ability": row.get("ability"),
            "score": row.get("score"),
            "answer_correct": row.get("answer_correct"),
            "subem": row.get("subem"),
            "envscaler_score": row.get("envscaler_score"),
            "envscaler_done": row.get("envscaler_done"),
            "cleaning_policy": "strict_success_whole_clean_action_only_terminal_downsampled",
        }
        actions, terminals = make_prefix_samples(messages, metadata)
        action_samples.extend(actions)
        terminal_samples.extend(terminals)

    kept_terminal, terminal_stats = downsample_terminal_by_benchmark(
        action_samples=action_samples,
        terminal_samples=terminal_samples,
        max_terminal_ratio=args.max_terminal_ratio,
        seed=args.seed,
    )
    records = action_samples + kept_terminal
    rng = random.Random(args.seed)
    rng.shuffle(records)

    output_path = output_dir / args.output_file
    write_jsonl(output_path, records)

    train_rows, eval_rows, split_detail = split_rows(records, args.eval_ratio, args.seed)
    train_name = f"{args.dataset_name}_train"
    eval_name = f"{args.dataset_name}_eval"
    train_file = f"{train_name}.jsonl"
    eval_file = f"{eval_name}.jsonl"
    write_jsonl(output_dir / train_file, train_rows)
    write_jsonl(output_dir / eval_file, eval_rows)

    dataset_info = {
        args.dataset_name: dataset_info_entry(args.output_file),
        train_name: dataset_info_entry(train_file),
        eval_name: dataset_info_entry(eval_file),
    }
    (output_dir / "dataset_info.json").write_text(
        json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    target_tool_counter = Counter()
    for row in records:
        for name in row.get("metadata", {}).get("target_tool_names") or []:
            target_tool_counter[str(name)] += 1

    stats = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "dataset_name": args.dataset_name,
        "output_file": args.output_file,
        "train_dataset": train_name,
        "eval_dataset": eval_name,
        "train_file": train_file,
        "eval_file": eval_file,
        "policy": {
            "trajectory_selection": {
                "toolhop": "score == 1 and answer_correct == 1",
                "searchqa": "score == 1 and answer_correct == 1",
                "envscaler": "score == 1 and envscaler_done == 1",
            },
            "trajectory_rejection": [
                "any ROUND01_GUARD_BLOCK / Unknown tool / schema_preflight / repeated_failed_call / low_value_repeat / partial commit marker",
                "any non-EnvScaler complete_task",
                "any EnvScaler final_answer",
                "any exact duplicate non-terminal tool call",
            ],
            "sample_generation": "action-only prefix SFT; plan turns are never targets",
            "terminal_downsampling": f"terminal target ratio capped by benchmark at <= {args.max_terminal_ratio}",
        },
        "records_seen": len(files),
        "by_benchmark_seen": dict(sorted(by_benchmark_seen.items())),
        "by_benchmark_strict_success": dict(sorted(by_benchmark_strict_success.items())),
        "by_benchmark_clean_trajectory": dict(sorted(by_benchmark_clean_trajectory.items())),
        "reject_reasons": dict(sorted(reject_reasons.items())),
        "invalid_reasons": dict(sorted(invalid_reasons.items())),
        "cleaning_actions": dict(sorted(cleaning_actions.items())),
        "action_samples_before_terminal": len(action_samples),
        "terminal_samples_before_downsample": len(terminal_samples),
        "terminal_downsample": dict(sorted(terminal_stats.items())),
        "records_kept": len(records),
        "train_total": len(train_rows),
        "eval_total": len(eval_rows),
        "split_detail": split_detail,
        "records_by_benchmark": dict(
            sorted(Counter(row["metadata"]["mixed_benchmark"] for row in records).items())
        ),
        "train_by_benchmark": dict(
            sorted(Counter(row["metadata"]["mixed_benchmark"] for row in train_rows).items())
        ),
        "eval_by_benchmark": dict(
            sorted(Counter(row["metadata"]["mixed_benchmark"] for row in eval_rows).items())
        ),
        "target_tool_counter_top50": target_tool_counter.most_common(50),
    }
    (output_dir / "strict_action_sft_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme = [
        f"# {args.dataset_name}",
        "",
        "Strict action-only round1 SFT data.",
        "",
        "Selection:",
        "- toolhop/searchqa: score == 1 and answer_correct == 1",
        "- envscaler: score == 1 and envscaler_done == 1",
        "",
        "Trajectory-level rejection:",
        "- any guard/unknown/repeated/low-value/partial-commit marker",
        "- non-EnvScaler complete_task",
        "- EnvScaler final_answer",
        "- exact duplicate non-terminal tool call",
        "",
        "Sample construction:",
        "- plan turns are removed and never trained",
        "- each record is a prefix ending at one action/tool-call assistant turn",
        "- terminal actions are downsampled by benchmark",
        "",
        f"Records kept: {len(records)}",
        f"Train/eval: {len(train_rows)} / {len(eval_rows)}",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
