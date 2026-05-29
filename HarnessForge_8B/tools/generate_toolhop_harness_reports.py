#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "output"
HARNESS_ROOT = PROJECT_ROOT / "harness_factory"


@dataclass
class SplitConfig:
    label: str
    output_prefix: str
    expected_count: int
    base_expected_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reproducible ToolHop reports and evolution prompts for each harness."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--harness-root", type=Path, default=HARNESS_ROOT)
    parser.add_argument("--round1-expected", type=int, default=80)
    parser.add_argument("--round1-base-expected", type=int, default=200)
    parser.add_argument("--test-expected", type=int, default=30)
    parser.add_argument("--test-base-expected", type=int, default=195)
    parser.add_argument(
        "--include-base",
        action="store_true",
        help="Also emit report files under harness_factory/base_harness.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def find_result_file(output_root: Path, prefix: str, harness_name: str) -> Path | None:
    run_dir = output_root / f"{prefix}_{harness_name}"
    matches = sorted(run_dir.glob("toolhop_*_results.jsonl"))
    return matches[0] if matches else None


def maybe_read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def iter_trajectory_steps(row: dict[str, Any]) -> list[dict[str, Any]]:
    value = row.get("agent_trajectory")
    if isinstance(value, list):
        return [step for step in value if isinstance(step, dict)]
    value = row.get("trajectory")
    if isinstance(value, list):
        return [step for step in value if isinstance(step, dict)]
    return []


def extract_tool_names(row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for step in iter_trajectory_steps(row):
        for call in step.get("tool_calls") or []:
            if isinstance(call, dict) and call.get("name"):
                names.append(str(call["name"]))
    return names


def extract_first_tool(row: dict[str, Any]) -> str | None:
    names = extract_tool_names(row)
    return names[0] if names else None


def extract_error_markers(row: dict[str, Any]) -> Counter[str]:
    markers: Counter[str] = Counter()
    for step in iter_trajectory_steps(row):
        obs = str(step.get("obs") or "")
        if "Error for tool call" in obs:
            markers["tool_call_error"] += 1
        if "missing 1 required positional argument" in obs:
            markers["missing_required_argument"] += 1
        if "You should only use this tool with a correct input" in obs:
            markers["schema_mismatch_hint"] += 1
        if "No tool observation" in obs:
            markers["empty_observation"] += 1
    return markers


def safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def f2(value: float) -> str:
    return f"{value:.2f}"


def pick_top(counter: Counter[str], limit: int = 5) -> list[tuple[str, int]]:
    return counter.most_common(limit)


def compute_stats(rows: list[dict[str, Any]], expected_count: int) -> dict[str, Any]:
    count = len(rows)
    correct_rows = [row for row in rows if int(row.get("answer_correct", 0)) == 1]
    failed_rows = [row for row in rows if int(row.get("answer_correct", 0)) != 1]
    tool_counter: Counter[str] = Counter()
    first_tool_counter: Counter[str] = Counter()
    failure_tool_counter: Counter[str] = Counter()
    error_counter: Counter[str] = Counter()
    parallel_first_pass = 0
    single_action_like = 0

    for row in rows:
        tool_names = extract_tool_names(row)
        tool_counter.update(tool_names)
        first_tool = extract_first_tool(row)
        if first_tool:
            first_tool_counter[first_tool] += 1
        if any(name.startswith("parallel_agent_") for name in tool_names):
            parallel_first_pass += 1
        if float(row.get("toolhop_action_count", 0) or 0) <= 1.1:
            single_action_like += 1
        if row in failed_rows:
            failure_tool_counter.update(tool_names)
        error_counter.update(extract_error_markers(row))

    def metric(row: dict[str, Any], name: str, nested: str | None = None) -> float:
        if nested:
            return float((row.get(name) or {}).get(nested, 0) or 0)
        return float(row.get(name, 0) or 0)

    stats = {
        "count": count,
        "expected_count": expected_count,
        "coverage": min(count / expected_count, 1.0) if expected_count else 0.0,
        "count_delta": count - expected_count,
        "accuracy": safe_mean([metric(row, "answer_correct") for row in rows]),
        "valid_answer_rate": safe_mean([metric(row, "has_valid_answer") for row in rows]),
        "path_score": safe_mean([metric(row, "path_score") for row in rows]),
        "tool_calls": safe_mean([metric(row, "tool_call_count") for row in rows]),
        "actions": safe_mean([metric(row, "toolhop_action_count") for row in rows]),
        "tools_available": safe_mean([metric(row, "tool_count") for row in rows]),
        "subtask_count": safe_mean([metric(row, "subtask_count") for row in rows]),
        "tokens": safe_mean([metric(row, "metrics", "total_tokens") for row in rows]),
        "elapsed_time": safe_mean([metric(row, "metrics", "elapsed_time") for row in rows]),
        "correct_count": len(correct_rows),
        "failed_count": len(failed_rows),
        "correct_tool_calls": safe_mean([metric(row, "tool_call_count") for row in correct_rows]),
        "failed_tool_calls": safe_mean([metric(row, "tool_call_count") for row in failed_rows]),
        "correct_actions": safe_mean([metric(row, "toolhop_action_count") for row in correct_rows]),
        "failed_actions": safe_mean([metric(row, "toolhop_action_count") for row in failed_rows]),
        "correct_tokens": safe_mean([metric(row, "metrics", "total_tokens") for row in correct_rows]),
        "failed_tokens": safe_mean([metric(row, "metrics", "total_tokens") for row in failed_rows]),
        "top_tools": pick_top(tool_counter),
        "top_first_tools": pick_top(first_tool_counter),
        "top_failure_tools": pick_top(failure_tool_counter),
        "error_markers": dict(error_counter),
        "parallel_ratio": parallel_first_pass / count if count else 0.0,
        "single_action_ratio": single_action_like / count if count else 0.0,
    }
    return stats


def harness_dirs(harness_root: Path, include_base: bool) -> list[Path]:
    dirs = []
    for path in sorted(harness_root.iterdir()):
        if not path.is_dir():
            continue
        if not ((path / "builder.py").exists() or (path / "Description.md").exists()):
            continue
        dirs.append(path)
    if include_base:
        return dirs
    return [path for path in dirs if path.name != "base_harness"]


def format_top_items(items: list[tuple[str, int]]) -> str:
    if not items:
        return "none"
    return ", ".join(f"{name} ({count})" for name, count in items)


def classify_cost_profile(stats: dict[str, Any], base_stats: dict[str, Any]) -> str:
    if stats["tokens"] >= base_stats["tokens"] * 1.2 and stats["accuracy"] <= base_stats["accuracy"]:
        return "high_cost_low_return"
    if stats["tokens"] <= base_stats["tokens"] * 0.25 and stats["accuracy"] < base_stats["accuracy"] - 0.08:
        return "under_reasoned"
    if stats["accuracy"] >= base_stats["accuracy"] and stats["tokens"] <= base_stats["tokens"]:
        return "efficient_gain"
    return "mixed"


def build_focus_points(
    split_label: str,
    stats: dict[str, Any],
    base_stats: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if stats["count_delta"] != 0:
        notes.append(
            f"{split_label} observed sample count is {stats['count']} while the configured expectation is {stats['expected_count']}; keep this mismatch in mind when comparing rankings."
        )
    if stats["coverage"] < 0.95:
        notes.append(
            f"{split_label} coverage is only {pct(stats['coverage'])}; treat this harness's ranking as provisional until the missing samples are completed."
        )
    if stats["accuracy"] < base_stats["accuracy"] - 0.08 and stats["actions"] < base_stats["actions"] * 0.4:
        notes.append(
            "The harness appears to terminate too early: action depth is far below base while accuracy is materially worse."
        )
    if stats["path_score"] - stats["accuracy"] > 0.12:
        notes.append(
            "Path score is noticeably above exact accuracy, which suggests decomposition often starts correctly but final synthesis or answer commitment fails."
        )
    if stats["failed_tool_calls"] > stats["correct_tool_calls"] + 1.0:
        notes.append(
            "Failures use substantially more tool calls than successes, so later evolution should prune redundant loops and add earlier stop conditions."
        )
    if stats["correct_tool_calls"] > stats["failed_tool_calls"] + 0.8:
        notes.append(
            "Correct runs usually take more tool calls than failures, so the harness likely needs one extra repair or verification turn before final answer."
        )
    if stats["parallel_ratio"] > 0.35 and stats["accuracy"] < base_stats["accuracy"]:
        notes.append(
            "Parallel-agent usage is frequent without matching accuracy gains; add stronger gating on when to branch and tighter evidence synthesis after branch returns."
        )
    if stats["single_action_ratio"] > 0.55 and stats["accuracy"] < 0.35:
        notes.append(
            "A large share of runs look like one-shot execution; this is too brittle for ToolHop and should be replaced with explicit multi-step recovery logic."
        )
    if stats["tokens"] > base_stats["tokens"] * 1.35 and stats["accuracy"] <= base_stats["accuracy"] + 0.03:
        notes.append(
            "Token cost is much higher than base for little or no accuracy gain, so the next mutation should compress planning verbosity and repeated verification."
        )
    if not notes:
        notes.append(
            "No single dominant failure mode stands out from the aggregate metrics; favor targeted, one-change-at-a-time harness mutations instead of a broad rewrite."
        )
    return notes


def build_evolution_actions(
    description: str,
    stats: dict[str, Any],
    base_stats: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if "parallel" in description.lower() and stats["accuracy"] < base_stats["accuracy"]:
        actions.append(
            "Reduce unconditional parallel branching. Trigger branch creation only after the main agent detects ambiguity, tool-schema uncertainty, or two credible candidate paths."
        )
        actions.append(
            "After parallel branches return, require a dedicated synthesis step that compares evidence quality before calling `final_answer`."
        )
    if stats["actions"] < base_stats["actions"] * 0.4:
        actions.append(
            "Add an explicit repair policy: if the first tool result is incomplete or schema-sensitive, force one more grounded follow-up action before termination."
        )
    if stats["path_score"] - stats["accuracy"] > 0.12:
        actions.append(
            "Strengthen answer aggregation. Preserve intermediate evidence in a compact scratchpad and convert it into a final answer only after consistency checks."
        )
    if stats["failed_tool_calls"] > stats["correct_tool_calls"] + 1.0:
        actions.append(
            "Introduce a loop budget with a fallback summarizer so the harness stops repeated low-value calls and converges sooner."
        )
    if stats["tokens"] > base_stats["tokens"] * 1.25:
        actions.append(
            "Shorten planning output and branch prompts. Keep only the minimum fields needed to direct the next action."
        )
    if stats["error_markers"].get("missing_required_argument", 0) > 0:
        actions.append(
            "Add tool-schema reflection before the first call: list required arguments and confirm they are present before execution."
        )
    if stats["single_action_ratio"] > 0.50:
        actions.append(
            "Avoid one-shot answering. Force a separate verify-or-repair phase whenever the answer depends on chained evidence."
        )
    if not actions:
        actions.append(
            "Keep the harness topology mostly stable and mutate only one coordination rule at a time so round-to-round gains remain interpretable."
        )
    return actions[:6]


def build_report_markdown(
    harness_name: str,
    description: str,
    round1_stats: dict[str, Any] | None,
    test_stats: dict[str, Any] | None,
    base_round1_stats: dict[str, Any] | None,
    base_test_stats: dict[str, Any] | None,
) -> str:
    lines: list[str] = [f"# ToolHop Harness Report: {harness_name}", ""]
    if description:
        lines.extend(["## Harness Intent", description, ""])

    def add_split_block(label: str, stats: dict[str, Any] | None, base_stats: dict[str, Any] | None) -> None:
        if not stats:
            lines.extend([f"## {label}", "No result file found.", ""])
            return
        lines.extend(
            [
                f"## {label}",
                f"- Samples: {stats['count']}",
                f"- Coverage: {pct(stats['coverage'])}",
                f"- Expected samples: {stats['expected_count']}",
                f"- Accuracy: {pct(stats['accuracy'])}",
                f"- Valid answer rate: {pct(stats['valid_answer_rate'])}",
                f"- Path score: {f2(stats['path_score'])}",
                f"- Avg tool calls: {f2(stats['tool_calls'])}",
                f"- Avg actions: {f2(stats['actions'])}",
                f"- Avg total tokens: {stats['tokens']:.1f}",
                f"- Avg elapsed time: {stats['elapsed_time']:.2f}s",
                f"- Top first tools: {format_top_items(stats['top_first_tools'])}",
                f"- Top tools in failures: {format_top_items(stats['top_failure_tools'])}",
                f"- Error markers: {stats['error_markers'] or 'none'}",
            ]
        )
        if base_stats:
            lines.extend(
                [
                    f"- Delta vs base accuracy: {(stats['accuracy'] - base_stats['accuracy']) * 100:+.1f} pts",
                    f"- Delta vs base path score: {stats['path_score'] - base_stats['path_score']:+.2f}",
                    f"- Cost profile vs base: {classify_cost_profile(stats, base_stats)}",
                ]
            )
            lines.append("")
            lines.append("### Focus Points")
            for note in build_focus_points(label, stats, base_stats):
                lines.append(f"- {note}")
        lines.append("")

    add_split_block("Round 1", round1_stats, base_round1_stats)
    add_split_block("Test", test_stats, base_test_stats)

    if round1_stats and test_stats:
        generalization_gap = test_stats["accuracy"] - round1_stats["accuracy"]
        lines.extend(
            [
                "## Stability Read",
                f"- Accuracy gap (test - round1): {generalization_gap * 100:+.1f} pts",
                f"- Round1 coverage warning: {'yes' if round1_stats['coverage'] < 0.95 else 'no'}",
                f"- Test coverage warning: {'yes' if test_stats['coverage'] < 0.95 else 'no'}",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def build_prompt_markdown(
    harness_name: str,
    description: str,
    round1_stats: dict[str, Any] | None,
    test_stats: dict[str, Any] | None,
    base_round1_stats: dict[str, Any] | None,
    base_test_stats: dict[str, Any] | None,
) -> str:
    lines: list[str] = [f"# Evolution Prompt Seed: {harness_name}", ""]
    lines.extend(
        [
            "Use this prompt as structured guidance for the next harness mutation.",
            "",
            "## Context",
            f"- Current harness: `{harness_name}`",
        ]
    )
    if description:
        one_line_description = " ".join(description.split())
        lines.append(f"- Current design summary: {one_line_description}")

    if round1_stats and base_round1_stats:
        lines.extend(
            [
                f"- Round1 accuracy: {pct(round1_stats['accuracy'])} vs base {pct(base_round1_stats['accuracy'])}",
                f"- Round1 path score: {f2(round1_stats['path_score'])} vs base {f2(base_round1_stats['path_score'])}",
                f"- Round1 avg tokens: {round1_stats['tokens']:.1f} vs base {base_round1_stats['tokens']:.1f}",
                f"- Round1 coverage: {pct(round1_stats['coverage'])}",
            ]
        )
    if test_stats and base_test_stats:
        lines.extend(
            [
                f"- Test accuracy: {pct(test_stats['accuracy'])} vs base {pct(base_test_stats['accuracy'])}",
                f"- Test path score: {f2(test_stats['path_score'])} vs base {f2(base_test_stats['path_score'])}",
                f"- Test avg tokens: {test_stats['tokens']:.1f} vs base {base_test_stats['tokens']:.1f}",
                f"- Test coverage: {pct(test_stats['coverage'])}",
            ]
        )

    focus_notes: list[str] = []
    action_notes: list[str] = []
    if round1_stats and base_round1_stats:
        focus_notes.extend(build_focus_points("Round 1", round1_stats, base_round1_stats))
        action_notes.extend(build_evolution_actions(description, round1_stats, base_round1_stats))
    if test_stats and base_test_stats:
        focus_notes.extend(build_focus_points("Test", test_stats, base_test_stats))
        action_notes.extend(build_evolution_actions(description, test_stats, base_test_stats))

    dedup_focus = list(dict.fromkeys(focus_notes))[:6]
    dedup_actions = list(dict.fromkeys(action_notes))[:6]

    lines.extend(["", "## Mutation Guardrails"])
    lines.append("- Preserve any behavior that improves path score unless you also fix the final aggregation weakness.")
    lines.append("- Do not train on trajectories collected under an outdated harness; only use post-mutation rollouts as query data.")
    lines.append("- Prefer one interpretable structural change per round so gains remain attributable.")
    if round1_stats and round1_stats["coverage"] < 0.95:
        lines.append("- Finish the missing round1 samples before making strong keep/drop decisions for this harness.")
    if test_stats and test_stats["coverage"] < 0.95:
        lines.append("- Treat current test conclusions as directional only because the blind-test coverage is incomplete.")

    lines.extend(["", "## What To Fix"])
    for note in dedup_focus:
        lines.append(f"- {note}")

    lines.extend(["", "## Recommended Mutation Directions"])
    for note in dedup_actions:
        lines.append(f"- {note}")

    lines.extend(
        [
            "",
            "## Prompt Template",
            "You are mutating a ToolHop harness for online co-evolution.",
            f"Start from harness `{harness_name}` and keep its useful identity, but fix the following weaknesses:",
        ]
    )
    for note in dedup_focus[:4]:
        lines.append(f"- {note}")
    lines.extend(
        [
            "Mutation requirements:",
            "- Make only 1-2 structural changes.",
            "- Prefer coordination, verification, and stopping-rule edits over broad rewrites.",
            "- Improve exact answer correctness without exploding token cost.",
            "- Keep the output compatible with the current harness factory layout.",
            "Return:",
            "- A short design rationale.",
            "- The concrete module-level changes.",
            "- Why the mutation should help on ToolHop failure cases.",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def generate_reports(args: argparse.Namespace) -> None:
    round1_cfg = SplitConfig(
        label="round1",
        output_prefix="toolhop_round1",
        expected_count=args.round1_expected,
        base_expected_count=args.round1_base_expected,
    )
    test_cfg = SplitConfig(
        label="test",
        output_prefix="toolhop_test",
        expected_count=args.test_expected,
        base_expected_count=args.test_base_expected,
    )

    base_round1_file = find_result_file(args.output_root, round1_cfg.output_prefix, "base_harness")
    base_test_file = find_result_file(args.output_root, test_cfg.output_prefix, "base_harness")
    if not base_round1_file or not base_test_file:
        raise FileNotFoundError("Base harness round1/test result files are required to build comparative reports.")

    base_round1_rows = load_jsonl(base_round1_file)
    base_test_rows = load_jsonl(base_test_file)
    base_round1_stats = compute_stats(base_round1_rows, round1_cfg.base_expected_count)
    base_test_stats = compute_stats(base_test_rows, test_cfg.base_expected_count)

    for harness_dir in harness_dirs(args.harness_root, include_base=args.include_base):
        harness_name = harness_dir.name
        round1_file = find_result_file(args.output_root, round1_cfg.output_prefix, harness_name)
        test_file = find_result_file(args.output_root, test_cfg.output_prefix, harness_name)
        round1_stats = compute_stats(
            load_jsonl(round1_file),
            round1_cfg.base_expected_count if harness_name == "base_harness" else round1_cfg.expected_count,
        ) if round1_file else None
        test_stats = compute_stats(
            load_jsonl(test_file),
            test_cfg.base_expected_count if harness_name == "base_harness" else test_cfg.expected_count,
        ) if test_file else None
        description = maybe_read_text(harness_dir / "Description.md")

        report_path = harness_dir / "toolhop_round1_report.md"
        prompt_path = harness_dir / "toolhop_round1_evolution_prompt.md"
        report_path.write_text(
            build_report_markdown(
                harness_name=harness_name,
                description=description,
                round1_stats=round1_stats,
                test_stats=test_stats,
                base_round1_stats=base_round1_stats,
                base_test_stats=base_test_stats,
            ),
            encoding="utf-8",
        )
        prompt_path.write_text(
            build_prompt_markdown(
                harness_name=harness_name,
                description=description,
                round1_stats=round1_stats,
                test_stats=test_stats,
                base_round1_stats=base_round1_stats,
                base_test_stats=base_test_stats,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {report_path}")
        print(f"Wrote {prompt_path}")


if __name__ == "__main__":
    generate_reports(parse_args())
