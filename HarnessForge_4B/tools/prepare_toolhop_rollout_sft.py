#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ERROR_OBS_MARKERS = (
    "no observations",
    "unable to determine",
    "insufficient",
    "{'error'",
    '"error"',
    "error for tool call",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clean ToolHop rollout JSONL files into turn-level SFT datasets. "
            "The script emits strict / balanced / aggressive tiers together "
            "with reasoning-only, action-only and combined supervision files."
        )
    )
    parser.add_argument("--input", type=Path, required=True, help="ToolHop rollout jsonl file.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for cleaned outputs.")
    parser.add_argument(
        "--include-summary-samples",
        action="store_true",
        help="Also export summary turns as reasoning targets.",
    )
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def is_correct(row: dict[str, Any]) -> bool:
    return bool(row.get("answer_correct") == 1 or row.get("judgement") == "correct")


def row_bucket(row: dict[str, Any]) -> str:
    if is_correct(row):
        return "correct"
    if row.get("path_score", 0) == 1.0 and row.get("has_valid_answer") == 1:
        return "path1_format_mismatch"
    if float(row.get("path_score", 0) or 0) >= 0.75:
        return "high_path_incorrect"
    if float(row.get("path_score", 0) or 0) >= 0.5:
        return "mid_path_incorrect"
    return "low_path_incorrect"


def bucket_allowed(bucket: str, tier: str) -> bool:
    if tier == "strict":
        return bucket == "correct"
    if tier == "balanced":
        return bucket in {"correct", "path1_format_mismatch"}
    if tier == "aggressive":
        return bucket in {"correct", "path1_format_mismatch", "high_path_incorrect"}
    raise ValueError(f"Unknown tier: {tier}")


def allow_final(bucket: str, tier: str) -> bool:
    if tier == "strict":
        return bucket == "correct"
    return bucket in {"correct", "path1_format_mismatch"}


def obs_is_error_like(obs: str) -> bool:
    lowered = str(obs or "").lower()
    return any(marker in lowered for marker in ERROR_OBS_MARKERS)


def normalize_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render_context(history: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for message in history:
        role = message["role"].upper()
        content = message["content"].strip()
        if content:
            parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts).strip()


def serialize_plan(step: dict[str, Any]) -> str:
    value = step.get("value")
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def serialize_summary(step: dict[str, Any]) -> str:
    value = step.get("value")
    if value is None:
        return ""
    return str(value).strip()


def serialize_tool_calls(step: dict[str, Any], override_final_answer: str | None = None) -> str:
    calls = step.get("tool_calls") or []
    cooked: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name", "")).strip()
        arguments = call.get("arguments", {})
        if override_final_answer is not None and name == "final_answer":
            arguments = {"answer": override_final_answer}
        cooked.append({"name": name, "arguments": arguments})
    return normalize_json_text(cooked)


def initial_history(row: dict[str, Any]) -> list[dict[str, str]]:
    prompt = str(row.get("enhanced_question") or "").strip()
    if not prompt:
        prompt = (
            "You are solving a ToolHop question with structured tool calls.\n\n"
            f"Question: {str(row.get('question') or '').strip()}\n"
        ).strip()
    return [{"role": "user", "content": prompt}]


def make_sample(
    *,
    history: list[dict[str, str]],
    target: str,
    row: dict[str, Any],
    step_index: int,
    sample_kind: str,
    tier: str,
    bucket: str,
    used_gold_final_answer: bool = False,
) -> dict[str, Any]:
    return {
        "instruction": render_context(history),
        "input": "",
        "output": target.strip(),
        "meta": {
            "sample_kind": sample_kind,
            "quality_tier": tier,
            "source_bucket": bucket,
            "source_item_index": row.get("item_index"),
            "question": row.get("question"),
            "step_index": step_index,
            "judgement": row.get("judgement"),
            "answer_correct": row.get("answer_correct"),
            "path_score": row.get("path_score"),
            "toolhop_action_count": row.get("toolhop_action_count"),
            "tool_call_count": row.get("tool_call_count"),
            "used_gold_final_answer": used_gold_final_answer,
        },
    }


def append_assistant(history: list[dict[str, str]], content: str) -> None:
    text = str(content or "").strip()
    if text:
        history.append({"role": "assistant", "content": text})


def append_observation(history: list[dict[str, str]], obs: str) -> None:
    text = str(obs or "").strip()
    if text:
        history.append({"role": "observation", "content": text})


def build_datasets(rows: list[dict[str, Any]], include_summary_samples: bool) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    tiers = ("strict", "balanced", "aggressive")
    dataset_map: dict[str, list[dict[str, Any]]] = {
        f"{tier}_{kind}": []
        for tier in tiers
        for kind in ("action", "reasoning", "combined")
    }
    stats: dict[str, Any] = {
        "rows": len(rows),
        "bucket_counts": Counter(),
        "tier_counts": defaultdict(Counter),
    }

    for row in rows:
        bucket = row_bucket(row)
        stats["bucket_counts"][bucket] += 1

        for tier in tiers:
            if not bucket_allowed(bucket, tier):
                continue

            history = initial_history(row)
            tier_counter: Counter[str] = stats["tier_counts"][tier]

            for step_index, step in enumerate(row.get("agent_trajectory") or []):
                if not isinstance(step, dict):
                    continue
                name = step.get("name")

                if name == "plan":
                    plan_text = serialize_plan(step)
                    if plan_text:
                        sample = make_sample(
                            history=history,
                            target=plan_text,
                            row=row,
                            step_index=step_index,
                            sample_kind="plan",
                            tier=tier,
                            bucket=bucket,
                        )
                        dataset_map[f"{tier}_reasoning"].append(sample)
                        dataset_map[f"{tier}_combined"].append(sample)
                        tier_counter["plan"] += 1
                        append_assistant(history, plan_text)
                    continue

                if name == "summary":
                    summary_text = serialize_summary(step)
                    if include_summary_samples and summary_text:
                        sample = make_sample(
                            history=history,
                            target=summary_text,
                            row=row,
                            step_index=step_index,
                            sample_kind="summary",
                            tier=tier,
                            bucket=bucket,
                        )
                        dataset_map[f"{tier}_reasoning"].append(sample)
                        dataset_map[f"{tier}_combined"].append(sample)
                        tier_counter["summary"] += 1
                    continue

                if name != "action":
                    continue

                tool_calls = step.get("tool_calls") or []
                think_text = str(step.get("think") or "").strip()
                obs_text = str(step.get("obs") or "").strip()
                has_final = any(
                    isinstance(call, dict) and str(call.get("name", "")).strip() == "final_answer"
                    for call in tool_calls
                )

                if not tool_calls:
                    tier_counter["noop_action"] += 1
                    continue

                if has_final:
                    if allow_final(bucket, tier):
                        final_target = serialize_tool_calls(
                            step,
                            override_final_answer=(
                                str(row.get("golden_answer")).strip()
                                if bucket == "path1_format_mismatch"
                                else None
                            ),
                        )
                        if think_text:
                            reasoning_sample = make_sample(
                                history=history,
                                target=think_text,
                                row=row,
                                step_index=step_index,
                                sample_kind="final_think",
                                tier=tier,
                                bucket=bucket,
                                used_gold_final_answer=bucket == "path1_format_mismatch",
                            )
                            dataset_map[f"{tier}_reasoning"].append(reasoning_sample)
                            dataset_map[f"{tier}_combined"].append(reasoning_sample)
                            tier_counter["final_think"] += 1

                        action_sample = make_sample(
                            history=history,
                            target=final_target,
                            row=row,
                            step_index=step_index,
                            sample_kind="final_action",
                            tier=tier,
                            bucket=bucket,
                            used_gold_final_answer=bucket == "path1_format_mismatch",
                        )
                        dataset_map[f"{tier}_action"].append(action_sample)
                        dataset_map[f"{tier}_combined"].append(action_sample)
                        tier_counter["final_action"] += 1
                        append_assistant(history, final_target)
                        append_observation(history, obs_text)
                    continue

                if obs_is_error_like(obs_text):
                    tier_counter["error_like_tool_turn"] += 1
                    append_assistant(history, serialize_tool_calls(step))
                    append_observation(history, obs_text)
                    continue

                if think_text:
                    reasoning_sample = make_sample(
                        history=history,
                        target=think_text,
                        row=row,
                        step_index=step_index,
                        sample_kind="tool_think",
                        tier=tier,
                        bucket=bucket,
                    )
                    dataset_map[f"{tier}_reasoning"].append(reasoning_sample)
                    dataset_map[f"{tier}_combined"].append(reasoning_sample)
                    tier_counter["tool_think"] += 1

                action_target = serialize_tool_calls(step)
                action_sample = make_sample(
                    history=history,
                    target=action_target,
                    row=row,
                    step_index=step_index,
                    sample_kind="tool_action",
                    tier=tier,
                    bucket=bucket,
                )
                dataset_map[f"{tier}_action"].append(action_sample)
                dataset_map[f"{tier}_combined"].append(action_sample)
                tier_counter["tool_action"] += 1
                append_assistant(history, action_target)
                append_observation(history, obs_text)

    stats["bucket_counts"] = dict(stats["bucket_counts"])
    stats["tier_counts"] = {tier: dict(counter) for tier, counter in stats["tier_counts"].items()}
    stats["dataset_sizes"] = {name: len(payload) for name, payload in dataset_map.items()}
    return dataset_map, stats


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    rows = load_rows(args.input)
    datasets, stats = build_datasets(rows, include_summary_samples=bool(args.include_summary_samples))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in datasets.items():
        write_jsonl(args.output_dir / f"{name}.jsonl", payload)

    report = {
        "input_file": str(args.input),
        "output_dir": str(args.output_dir),
        "include_summary_samples": bool(args.include_summary_samples),
        "stats": stats,
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
