#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "output"
HARNESS_ROOT = PROJECT_ROOT / "harness_factory"
LEGACY_FILES = ("toolhop_round1_report.md", "toolhop_round1_evolution_prompt.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic round1 ToolHop metrics.json and report.md files "
            "for harness1..7 under harness_factory/."
        )
    )
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--harness-root", type=Path, default=HARNESS_ROOT)
    parser.add_argument("--metrics-filename", default="metrics.json")
    parser.add_argument("--report-filename", default="report.md")
    parser.add_argument(
        "--keep-legacy-files",
        action="store_true",
        help="Do not remove legacy toolhop_round1_report.md and toolhop_round1_evolution_prompt.md files.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def find_result_file(run_dir: Path) -> Path:
    matches = sorted(run_dir.glob("toolhop_*_results.jsonl"))
    if not matches:
        raise FileNotFoundError(f"No ToolHop result file found under {run_dir}")
    return matches[0]


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def extract_framework_name(result_file: Path) -> str:
    name = result_file.name
    prefix = "toolhop_flash_searcher_flash_searcher_"
    suffix = "_local_qwen3-aevolve_closed_results.jsonl"
    if name.startswith(prefix):
        name = name[len(prefix):]
    if name.endswith(suffix):
        name = name[: -len(suffix)]
    return name


def extract_steps(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("agent_trajectory", "trajectory"):
        value = row.get(key)
        if isinstance(value, list):
            return [step for step in value if isinstance(step, dict)]
    return []


def extract_tool_names(row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for step in extract_steps(row):
        for call in step.get("tool_calls") or []:
            if isinstance(call, dict) and call.get("name"):
                names.append(str(call["name"]))
    return names


def extract_obs_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for step in extract_steps(row):
        obs = step.get("obs")
        if obs:
            parts.append(str(obs))
    return "\n".join(parts)


def parse_structure(description_text: str) -> dict[str, str]:
    structure = {"planning": "", "action": "", "memory": ""}
    for line in description_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Planning:"):
            structure["planning"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Execution:"):
            structure["action"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Memory:"):
            structure["memory"] = stripped.split(":", 1)[1].strip()
    return structure


def safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def round4(value: float) -> float:
    return round(value, 4)


def round2(value: float) -> float:
    return round(value, 2)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_metrics(rows: list[dict[str, Any]], harness_name: str, framework_name: str, result_file: Path) -> dict[str, Any]:
    prompt_tokens = [float((row.get("metrics") or {}).get("prompt_tokens", 0) or 0) for row in rows]
    completion_tokens = [float((row.get("metrics") or {}).get("completion_tokens", 0) or 0) for row in rows]
    total_tokens = [float((row.get("metrics") or {}).get("total_tokens", 0) or 0) for row in rows]
    runtime_sec = [float((row.get("metrics") or {}).get("elapsed_time", 0) or 0) for row in rows]
    actions = [float(row.get("toolhop_action_count", 0) or 0) for row in rows]
    tool_calls = [float(row.get("tool_call_count", 0) or 0) for row in rows]
    answer_correct = [float(row.get("answer_correct", 0) or 0) for row in rows]
    has_valid_answer = [float(row.get("has_valid_answer", 0) or 0) for row in rows]
    path_score = [float(row.get("path_score", 0) or 0) for row in rows]

    return {
        "num_tasks": len(rows),
        "answer_correct": round4(safe_mean(answer_correct)),
        "has_valid_answer": round4(safe_mean(has_valid_answer)),
        "path_score": round4(safe_mean(path_score)),
        "average_actions": round4(safe_mean(actions)),
        "average_tool_calls": round4(safe_mean(tool_calls)),
        "prompt_tokens_total": int(sum(prompt_tokens)),
        "completion_tokens_total": int(sum(completion_tokens)),
        "tokens_total": int(sum(total_tokens)),
        "prompt_tokens_avg": round2(safe_mean(prompt_tokens)),
        "completion_tokens_avg": round2(safe_mean(completion_tokens)),
        "tokens_avg": round2(safe_mean(total_tokens)),
        "runtime_total_min": round2(sum(runtime_sec) / 60.0),
        "runtime_avg_sec": round2(safe_mean(runtime_sec)),
        "harness_name": harness_name,
        "framework_name": framework_name,
        "source_result_file": str(result_file),
    }


def compute_type_breakdown(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("answer_type") or "unknown")].append(row)
    breakdown: dict[str, dict[str, float | int]] = {}
    for answer_type, items in sorted(grouped.items()):
        breakdown[answer_type] = {
            "count": len(items),
            "accuracy": round4(safe_mean([float(item.get("answer_correct", 0) or 0) for item in items])),
            "path_score": round4(safe_mean([float(item.get("path_score", 0) or 0) for item in items])),
        }
    return breakdown


def compute_failure_signals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [row for row in rows if int(row.get("answer_correct", 0)) != 1]
    successes = [row for row in rows if int(row.get("answer_correct", 0)) == 1]
    all_tools = Counter()
    first_tools = Counter()
    failure_tools = Counter()
    error_markers = Counter()
    answer_type_failures = Counter()
    short_action_failures = 0
    long_loop_failures = 0
    high_path_gap_failures = 0
    parallel_failures = 0
    worker_failures = 0

    for row in rows:
        tools = extract_tool_names(row)
        all_tools.update(tools)
        if tools:
            first_tools[tools[0]] += 1

    for row in failures:
        tools = extract_tool_names(row)
        failure_tools.update(tools)
        answer_type_failures[str(row.get("answer_type") or "unknown")] += 1
        obs = extract_obs_text(row)
        if "Error for tool call" in obs:
            error_markers["tool_call_error"] += 1
        if "missing 1 required positional argument" in obs:
            error_markers["missing_required_argument"] += 1
        if "You should only use this tool with a correct input" in obs:
            error_markers["schema_mismatch_hint"] += 1
        if float(row.get("toolhop_action_count", 0) or 0) <= 1.2:
            short_action_failures += 1
        if float(row.get("tool_call_count", 0) or 0) >= 8.0:
            long_loop_failures += 1
        if float(row.get("path_score", 0) or 0) >= 0.5:
            high_path_gap_failures += 1
        if any(name.startswith("parallel_agent_") or name == "expert_parallel" for name in tools):
            parallel_failures += 1
        if any(name.startswith("worker_") for name in tools):
            worker_failures += 1

    return {
        "top_tools": all_tools.most_common(10),
        "top_first_tools": first_tools.most_common(8),
        "top_failure_tools": failure_tools.most_common(10),
        "error_markers": dict(error_markers),
        "answer_type_failures": dict(answer_type_failures),
        "failure_count": len(failures),
        "success_count": len(successes),
        "short_action_failures": short_action_failures,
        "long_loop_failures": long_loop_failures,
        "high_path_gap_failures": high_path_gap_failures,
        "parallel_failures": parallel_failures,
        "worker_failures": worker_failures,
        "avg_failed_tool_calls": round2(safe_mean([float(row.get("tool_call_count", 0) or 0) for row in failures])),
        "avg_success_tool_calls": round2(safe_mean([float(row.get("tool_call_count", 0) or 0) for row in successes])),
        "avg_failed_actions": round2(safe_mean([float(row.get("toolhop_action_count", 0) or 0) for row in failures])),
        "avg_success_actions": round2(safe_mean([float(row.get("toolhop_action_count", 0) or 0) for row in successes])),
    }


def build_overall_assessment(metrics: dict[str, Any], type_breakdown: dict[str, dict[str, float | int]], signals: dict[str, Any]) -> str:
    acc = metrics["answer_correct"]
    path = metrics["path_score"]
    avg_actions = metrics["average_actions"]
    token_avg = metrics["tokens_avg"]
    framework_name = metrics["framework_name"]

    if acc >= 0.48 and token_avg <= 45000:
        opening = "整体上这是一个相对均衡的 harness，质量提升是实打实的，同时成本还没有失控。"
    elif acc >= 0.45 and token_avg > 60000:
        opening = "整体上更像是质量略有提升但成本明显升高的 harness，收益和代价之间并不划算。"
    elif acc < 0.35 and avg_actions <= 1.5:
        opening = "整体上属于成本压得很低、但收益也比较弱的 harness，主要短板是推理深度不够。"
    else:
        opening = "整体上这是一个中等表现的 harness，既有保留价值，也有很明确的结构瓶颈。"

    stronger_types = [name for name, stats in type_breakdown.items() if float(stats["accuracy"]) >= max(acc, 0.45)]
    weaker_types = [name for name, stats in type_breakdown.items() if float(stats["accuracy"]) <= min(acc - 0.15, 0.15)]

    if stronger_types:
        fit_text = f"它更适合 {', '.join(stronger_types[:3])} 这类证据链清晰、后处理较轻的题。"
    else:
        fit_text = "它更适合实体链较短、最后一步只需要简单变换的题。"

    if weaker_types:
        weak_text = f"它当前不太适合 {', '.join(weaker_types[:3])} 这类对字符串、时间或格式统一要求更高的题。"
    else:
        weak_text = "它对强格式约束、复杂字符串处理或时间换算类题目仍然偏脆。"

    if signals["short_action_failures"] >= max(8, int(signals["failure_count"] * 0.45)):
        close_text = (
            f"从行为上看，{framework_name} 的平均 action 只有 {avg_actions:.2f}，很多失败更像是还没走完整条 hop 链就提前提交了答案。"
        )
    else:
        close_text = (
            f"从行为上看，path score ({path:.4f}) 明显高于 exact accuracy ({acc:.4f})，说明它经常能找到部分正确中间结论，但最后汇总和提交仍然不稳。"
        )

    return " ".join([opening, fit_text, weak_text, close_text])


def build_failure_patterns(metrics: dict[str, Any], type_breakdown: dict[str, dict[str, float | int]], signals: dict[str, Any]) -> list[str]:
    bullets: list[str] = []
    if metrics["path_score"] - metrics["answer_correct"] >= 0.12:
        bullets.append("不少失败不是前面 hop 全错，而是中间链条部分正确、最后答案提交或汇总出错；这通常意味着 final synthesis 或 answer canonicalization 比检索本身更脆。")
    if signals["short_action_failures"] >= max(8, int(signals["failure_count"] * 0.45)):
        bullets.append("失败样本里有较高比例属于低 action 深度案例，说明这个 harness 经常过早终止，没有给 verify 或 repair 留出必要回合。")
    if signals["avg_failed_tool_calls"] >= signals["avg_success_tool_calls"] + 1.0:
        bullets.append("另一类失败则表现为无效探索过多：失败样本的平均 tool call 明显高于成功样本，说明系统在不确定时会反复试探，但缺少真正的收敛机制。")
    if signals["error_markers"]:
        rendered = ", ".join(f"{name}={count}" for name, count in signals["error_markers"].items())
        bullets.append(f"工具契约错误也是一部分稳定噪声，当前可见的错误标记包括 {rendered}，说明参数名、必填字段或 schema 理解还不够稳。")
    weakest = sorted(type_breakdown.items(), key=lambda item: float(item[1]["accuracy"]))[:2]
    if weakest:
        rendered = ", ".join(f"{name}({float(stats['accuracy']):.2f})" for name, stats in weakest)
        bullets.append(f"从题型分布看，当前最脆弱的通常是 {rendered}；这类题更依赖字符串处理、时间换算或最终答案格式对齐。")
    if signals["parallel_failures"] >= max(8, int(signals["failure_count"] * 0.35)):
        bullets.append("并行分支参与的失败占比不低，说明当前分支拆分和分支回收逻辑容易在依赖还没满足时就把子任务放出去，最后再被协调层错误合成。")
    if signals["worker_failures"] >= max(8, int(signals["failure_count"] * 0.35)):
        bullets.append("worker 型失败也比较明显，核心问题往往不是 worker 完全不会做，而是 coordinator 给出的子任务边界不够清晰，导致 worker 在缺少上游实体时被迫猜测。")
    if not bullets:
        bullets.append("没有单一压倒性的失败模式，更像是若干中小问题叠加拉低了最终准确率；这种 harness 更适合小步迭代，而不是整体推翻重做。")
    return bullets[:5]


def build_module_diagnosis(structure: dict[str, str], metrics: dict[str, Any], signals: dict[str, Any]) -> dict[str, dict[str, str]]:
    path_gap = metrics["path_score"] - metrics["answer_correct"]
    diagnosis: dict[str, dict[str, str]] = {}

    planning_help = structure["planning"] or "当前 harness 有明确的 planning 层。"
    if path_gap >= 0.1:
        planning_hurt = "planning 往往能把中间路径拆出来，但没有把这些中间结论稳定地约束到最终答案，因此出现了明显的 path-correct / final-wrong 落差。"
    elif metrics["average_actions"] <= 1.5:
        planning_hurt = "planning 虽然存在，但后续执行深度不够，计划没有真正转化为逐步落实的行动链。"
    else:
        planning_hurt = "planning 的帮助还不够稳定，更多时候只是提供了一个起手框架，而不是持续约束后续执行。"

    action_help = structure["action"] or "当前 harness 有明确的 action 层。"
    if signals["short_action_failures"] >= max(8, int(signals["failure_count"] * 0.45)):
        action_hurt = "action 层最大的短板是过早终止，很多失败像是一轮执行后就直接提交，没有设置 verify 或 repair 回合。"
    elif signals["avg_failed_tool_calls"] >= signals["avg_success_tool_calls"] + 1.0:
        action_hurt = "action 层在不确定时容易陷入低价值探索，失败样本的 tool call 偏多，说明停止规则和收敛机制还不够强。"
    else:
        action_hurt = "action 层能完成基本执行，但在多跳依赖场景下还缺少更强的证据闭环。"

    memory_help = structure["memory"] or "当前 harness 带有 memory 层。"
    if signals["parallel_failures"] > 0 or signals["worker_failures"] > 0:
        memory_hurt = "memory 更像是在辅助协调层讲故事，而不是提供对当前 hop 真正有约束力的工具契约或实体缓存，所以在并行或委派场景里容易放大错误。"
    elif path_gap >= 0.1:
        memory_hurt = "memory 可能帮助了中间分解，但没有稳定改善最终提交，说明它更像提供提示感，而不是提供强约束。"
    else:
        memory_hurt = "memory 的增益目前不够显著，还没有明显改变这个 harness 的主要失败模式。"

    diagnosis["Planning"] = {"help": planning_help, "hurt": planning_hurt}
    diagnosis["Action"] = {"help": action_help, "hurt": action_hurt}
    diagnosis["Memory"] = {"help": memory_help, "hurt": memory_hurt}
    return diagnosis


def render_metrics_section(metrics: dict[str, Any]) -> list[str]:
    return [
        f"- Evaluated tasks: {metrics['num_tasks']}",
        f"- Exact accuracy: {pct(metrics['answer_correct'])}",
        f"- Valid answer rate: {pct(metrics['has_valid_answer'])}",
        f"- Average path score: {metrics['path_score']:.4f}",
        f"- Average actions: {metrics['average_actions']:.2f}",
        f"- Average tool calls: {metrics['average_tool_calls']:.2f}",
        f"- Prompt / completion / total tokens: {metrics['prompt_tokens_total']} / {metrics['completion_tokens_total']} / {metrics['tokens_total']}",
        f"- Average prompt / completion / total tokens: {metrics['prompt_tokens_avg']:.2f} / {metrics['completion_tokens_avg']:.2f} / {metrics['tokens_avg']:.2f}",
        f"- Total runtime: {metrics['runtime_total_min']:.2f} min",
        f"- Average runtime per task: {metrics['runtime_avg_sec']:.2f} sec",
    ]


def build_report(harness_name: str, structure: dict[str, str], metrics: dict[str, Any], type_breakdown: dict[str, dict[str, float | int]], signals: dict[str, Any]) -> str:
    overall = build_overall_assessment(metrics, type_breakdown, signals)
    failure_patterns = build_failure_patterns(metrics, type_breakdown, signals)
    module_diagnosis = build_module_diagnosis(structure, metrics, signals)

    lines = [
        f"# {harness_name} Analysis",
        "",
        "## Structure",
        f"- Planning: {structure['planning'] or 'No explicit planning summary found.'}",
        f"- Action: {structure['action'] or 'No explicit action summary found.'}",
        f"- Memory: {structure['memory'] or 'No explicit memory summary found.'}",
        "",
        "## Aggregate Metrics",
        *render_metrics_section(metrics),
        "",
        "## Overall Assessment",
        overall,
        "",
        "## Failure Pattern Analysis",
    ]
    for bullet in failure_patterns:
        lines.append(f"- {bullet}")
    lines.extend(["", "## Module-level Diagnosis"])
    for module_name in ("Planning", "Action", "Memory"):
        lines.append(f"### {module_name}")
        lines.append(f"- What Helps: {module_diagnosis[module_name]['help']}")
        lines.append(f"- What Hurts: {module_diagnosis[module_name]['hurt']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def remove_legacy_files(harness_dir: Path) -> None:
    for filename in LEGACY_FILES:
        path = harness_dir / filename
        if path.exists():
            path.unlink()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def analyze_harness(harness_index: int, args: argparse.Namespace) -> None:
    harness_name = f"harness{harness_index}"
    run_dir = args.output_root / f"toolhop_round1_{harness_name}"
    harness_dir = args.harness_root / harness_name

    result_file = find_result_file(run_dir)
    rows = load_jsonl(result_file)
    framework_name = extract_framework_name(result_file)
    description = read_text_if_exists(harness_dir / "Description.md")
    structure = parse_structure(description)
    metrics = build_metrics(rows, harness_name, framework_name, result_file)
    type_breakdown = compute_type_breakdown(rows)
    signals = compute_failure_signals(rows)
    report = build_report(harness_name, structure, metrics, type_breakdown, signals)

    if not args.keep_legacy_files:
        remove_legacy_files(harness_dir)

    write_json(harness_dir / args.metrics_filename, metrics)
    (harness_dir / args.report_filename).write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    for harness_index in range(1, 8):
        analyze_harness(harness_index, args)


if __name__ == "__main__":
    main()
