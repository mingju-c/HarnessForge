#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any


DEFAULT_HARNESSES = {
    "harness2": "output/toolhop_round1_harness2_R1/toolhop_flash_searcher_flash_searcher_expel_local_qwen3-aevolve_closed_results.jsonl",
    "harness4": "output/toolhop_round1_harness4_R1/toolhop_flash_searcher_flash_searcher_dynamic_cheatsheet_local_qwen3-aevolve_closed_results.jsonl",
    "harness6": "output/toolhop_round1_harness6_R1/toolhop_flash_searcher_flash_searcher_expel_local_qwen3-aevolve_closed_results.jsonl",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build ToolHop trajectory-level DPO pairs across harness rollouts."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="A-Evolve repository root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/toolhop_round1_cross_harness_dpo"),
        help="Output directory. Relative paths are resolved under repo-root.",
    )
    parser.add_argument(
        "--include-observations",
        action="store_true",
        help="Include tool observations in chosen/rejected transcripts. Off by default.",
    )
    return parser.parse_args()


def is_correct(row: dict[str, Any]) -> bool:
    return bool(row.get("answer_correct") == 1 or row.get("judgement") == "correct")


def bucket(row: dict[str, Any]) -> str:
    if is_correct(row):
        return "correct"
    if row.get("path_score", 0) == 1.0 and row.get("has_valid_answer") == 1:
        return "path1_format_mismatch"
    if float(row.get("path_score", 0) or 0) >= 0.75:
        return "high_path_incorrect"
    if float(row.get("path_score", 0) or 0) >= 0.5:
        return "mid_path_incorrect"
    return "low_path_incorrect"


def quality_key(row: dict[str, Any]) -> tuple[int, float, int, int]:
    return (
        1 if is_correct(row) else 0,
        float(row.get("path_score", 0) or 0),
        1 if row.get("has_valid_answer") == 1 else 0,
        -int(row.get("tool_call_count", 0) or 0),
    )


def load_rows(path: Path) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows[int(row["item_index"])] = row
    return rows


def prompt_for(row: dict[str, Any]) -> str:
    prompt = str(row.get("enhanced_question") or "").strip()
    if prompt:
        return prompt
    return (
        "You are solving a ToolHop question with structured tool calls.\n\n"
        f"Question: {str(row.get('question') or '').strip()}\n\n"
        "Important:\n"
        "1. Use only the tools available in this environment for the current question.\n"
        "2. ToolHop tools return useful information only when you choose the correct tool and pass accurate arguments.\n"
        "3. Base your answer on tool observations rather than guessing.\n"
        "4. When the answer is supported, call final_answer with the exact short answer only."
    ).strip()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def serialize_tool_calls(step: dict[str, Any]) -> str:
    calls: list[dict[str, Any]] = []
    for call in step.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        calls.append(
            {
                "name": str(call.get("name", "")).strip(),
                "arguments": call.get("arguments", {}),
            }
        )
    return json.dumps(calls, ensure_ascii=False, sort_keys=True)


def render_assistant_trajectory(row: dict[str, Any], *, include_observations: bool) -> str:
    parts: list[str] = []
    for step in row.get("agent_trajectory") or []:
        if not isinstance(step, dict):
            continue
        name = step.get("name")
        if name == "plan":
            value = step.get("value")
            if value:
                parts.append("[PLAN]\n" + (value.strip() if isinstance(value, str) else json_text(value)))
            continue
        if name == "summary":
            value = str(step.get("value") or "").strip()
            if value:
                parts.append("[SUMMARY]\n" + value)
            continue
        if name != "action":
            continue
        think = str(step.get("think") or "").strip()
        if think:
            parts.append("[THINK]\n" + think)
        calls = serialize_tool_calls(step)
        if calls != "[]":
            parts.append("[TOOL_CALLS]\n" + calls)
        obs = str(step.get("obs") or "").strip()
        if include_observations and obs:
            parts.append("[OBSERVATION]\n" + obs)
    return "\n\n".join(parts).strip()


def make_pair(
    *,
    item_index: int,
    chosen_name: str,
    chosen_row: dict[str, Any],
    rejected_name: str,
    rejected_row: dict[str, Any],
    include_observations: bool,
    pair_kind: str,
) -> dict[str, Any]:
    return {
        "instruction": prompt_for(chosen_row),
        "input": "",
        "chosen": render_assistant_trajectory(
            chosen_row, include_observations=include_observations
        ),
        "rejected": render_assistant_trajectory(
            rejected_row, include_observations=include_observations
        ),
        "meta": {
            "pair_kind": pair_kind,
            "item_index": item_index,
            "question": chosen_row.get("question"),
            "golden_answer": chosen_row.get("golden_answer"),
            "chosen_harness": chosen_name,
            "rejected_harness": rejected_name,
            "chosen_bucket": bucket(chosen_row),
            "rejected_bucket": bucket(rejected_row),
            "chosen_answer_correct": chosen_row.get("answer_correct"),
            "rejected_answer_correct": rejected_row.get("answer_correct"),
            "chosen_path_score": chosen_row.get("path_score"),
            "rejected_path_score": rejected_row.get("path_score"),
            "chosen_agent_result": chosen_row.get("agent_result"),
            "rejected_agent_result": rejected_row.get("agent_result"),
            "include_observations": include_observations,
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    by_harness: dict[str, dict[int, dict[str, Any]]] = {}
    for name, rel_path in DEFAULT_HARNESSES.items():
        by_harness[name] = load_rows(repo_root / rel_path)

    common_items = sorted(set.intersection(*(set(rows) for rows in by_harness.values())))
    pairwise: list[dict[str, Any]] = []
    best: list[dict[str, Any]] = []
    pair_counter: Counter[tuple[str, str]] = Counter()

    for item_index in common_items:
        candidates = [(name, rows[item_index]) for name, rows in by_harness.items()]

        for (left_name, left_row), (right_name, right_row) in combinations(candidates, 2):
            if is_correct(left_row) == is_correct(right_row):
                continue
            if is_correct(left_row):
                chosen_name, chosen_row = left_name, left_row
                rejected_name, rejected_row = right_name, right_row
            else:
                chosen_name, chosen_row = right_name, right_row
                rejected_name, rejected_row = left_name, left_row
            pairwise.append(
                make_pair(
                    item_index=item_index,
                    chosen_name=chosen_name,
                    chosen_row=chosen_row,
                    rejected_name=rejected_name,
                    rejected_row=rejected_row,
                    include_observations=args.include_observations,
                    pair_kind="strict_correct_vs_incorrect_pairwise",
                )
            )
            pair_counter[(chosen_name, rejected_name)] += 1

        correct = [(name, row) for name, row in candidates if is_correct(row)]
        incorrect = [(name, row) for name, row in candidates if not is_correct(row)]
        if correct and incorrect:
            chosen_name, chosen_row = max(correct, key=lambda pair: quality_key(pair[1]))
            rejected_name, rejected_row = min(incorrect, key=lambda pair: quality_key(pair[1]))
            best.append(
                make_pair(
                    item_index=item_index,
                    chosen_name=chosen_name,
                    chosen_row=chosen_row,
                    rejected_name=rejected_name,
                    rejected_row=rejected_row,
                    include_observations=args.include_observations,
                    pair_kind="strict_correct_vs_incorrect_best_of_item",
                )
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "strict_pairwise_trajectory_dpo.jsonl", pairwise)
    write_jsonl(output_dir / "strict_best_trajectory_dpo.jsonl", best)

    report = {
        "output_dir": str(output_dir),
        "inputs": {name: str((repo_root / path).resolve()) for name, path in DEFAULT_HARNESSES.items()},
        "format": "alpaca_preference_jsonl",
        "columns": {
            "prompt": "instruction",
            "query": "input",
            "chosen": "chosen",
            "rejected": "rejected",
        },
        "pairing": "cross-harness same item_index; strict correct-vs-incorrect only",
        "include_observations": bool(args.include_observations),
        "common_items": len(common_items),
        "dataset_sizes": {
            "strict_pairwise_trajectory_dpo": len(pairwise),
            "strict_best_trajectory_dpo": len(best),
        },
        "pair_counts": {f"{a}>{b}": n for (a, b), n in sorted(pair_counter.items())},
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
