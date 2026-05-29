#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = PROJECT_ROOT / "output/round_00_seed200/round_00/train_first200"
REGISTRY_PATH = PROJECT_ROOT / "registries/harness_pool.yaml"
CARD_DIR = PROJECT_ROOT / "experiment_factory/round_00_base/harness_cards"
PROFILE_ID = "round_00_seed_profile_partial"


DECISIONS: dict[str, dict[str, Any]] = {
    "harness1": {
        "archive_tier": "strong_seed",
        "summary": "Best current quality signal; strong EnvScaler score and stable SearchQA tool use, but expensive.",
        "strengths": [
            "strongest all-available mixed primary score among non-trivial seeds",
            "best EnvScaler score in current pool",
            "SearchQA uses search reliably",
        ],
        "risks": [
            "high token cost and long wall time",
            "failures can keep accumulating long context before stopping",
        ],
        "evolution_recommendations": [
            "keep the direct single-executor structure as a quality reference",
            "add tighter stop and repeated-call guards for EnvScaler failures",
            "compress observations before reflection to reduce prompt growth",
        ],
    },
    "harness2": {
        "archive_tier": "repair_candidate",
        "summary": "SearchQA signal is good, but ToolHop and EnvScaler are weak and repeated failures make it slow.",
        "strengths": [
            "SearchQA uses search and currently has strong small-sample subEM",
            "concise-reflection idea is simple enough for future training",
        ],
        "risks": [
            "high max-step rate on EnvScaler",
            "weak ToolHop correctness",
            "repeated failed tool calls inflate runtime and tokens",
        ],
        "evolution_recommendations": [
            "strengthen repetition detection after failed observations",
            "force a strategy change after two identical tool failures",
            "tighten final verifier so ToolHop does not collapse to low exact accuracy",
        ],
    },
    "harness3": {
        "archive_tier": "diversity_seed",
        "summary": "Very token-efficient and rarely reaches max steps, but SearchQA does not actually search and EnvScaler score is low.",
        "strengths": [
            "low token footprint",
            "low max-step rate",
            "high EnvScaler done rate under the fair first-100 slice",
        ],
        "risks": [
            "SearchQA used_search is zero",
            "EnvScaler completion does not translate into high score",
            "some traces show no-observation loops",
        ],
        "evolution_recommendations": [
            "fix SearchQA route so retrieval/search tools are mandatory when available",
            "add final state verifier before completion on EnvScaler",
            "preserve its low-token guard style as a cost-control reference",
        ],
    },
    "harness4": {
        "archive_tier": "strong_seed",
        "summary": "Best balanced seed: good speed-quality tradeoff, normal SearchQA tool use, and reasonable ToolHop path quality.",
        "strengths": [
            "best current speed-quality balance",
            "SearchQA uses search reliably",
            "reflection critic is lighter than the original multi-expert design",
        ],
        "risks": [
            "EnvScaler score still trails harness1",
            "some max-step failures remain on stateful tasks",
        ],
        "evolution_recommendations": [
            "use as the default balanced parent for round-1 mutations",
            "keep critic non-acting and improve its stop/retry decisions",
            "borrow harness1's stronger direct execution discipline where useful",
        ],
    },
    "harness5": {
        "archive_tier": "repair_candidate",
        "summary": "Heavy orchestration consumes the most tokens and often reaches max steps; useful mainly as a negative-cost signal.",
        "strengths": [
            "moderate EnvScaler score despite high cost",
            "SearchQA uses search reliably",
        ],
        "risks": [
            "highest token cost in the current pool",
            "highest max-step rate among active candidates",
            "multi-agent orchestration appears too heavy for Qwen3-4B",
        ],
        "evolution_recommendations": [
            "shrink orchestration to one executor plus a small verifier",
            "cap reflection summaries and memory exposure",
            "avoid using this design as a direct parent unless cost is repaired",
        ],
    },
    "harness6": {
        "archive_tier": "efficiency_baseline",
        "summary": "Fastest and cheapest, but quality is too low; keep as a low-cost baseline and guard/reference source.",
        "strengths": [
            "lowest runtime and token cost",
            "zero max-step rate in current runs",
            "useful as a minimal guard baseline",
        ],
        "risks": [
            "very low EnvScaler done and score",
            "weak ToolHop correctness and path score",
            "SearchQA does not use search",
        ],
        "evolution_recommendations": [
            "do not use as a main quality parent",
            "reuse its budget discipline in stronger harnesses",
            "add mandatory retrieval route before any SearchQA reuse",
        ],
    },
    "harness7": {
        "archive_tier": "diversity_seed",
        "summary": "Router/debate has useful SearchQA behavior and good early ToolHop signal, but stateful tasks still run long.",
        "strengths": [
            "SearchQA uses search reliably",
            "fair first-100 ToolHop correctness is strong",
            "router/debate gives useful architectural diversity",
        ],
        "risks": [
            "EnvScaler max-step rate is high",
            "all-available ToolHop score drops after more samples",
            "stateful fallback still needs stronger stop and verifier rules",
        ],
        "evolution_recommendations": [
            "preserve debate only for read-only retrieval tasks",
            "make stateful route single-executor with stricter critic stop rules",
            "add route-level cost budget and repeated-call abort",
        ],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def relpath(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except Exception:
        return str(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def mean(values: list[Any]) -> float | None:
    nums: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            nums.append(number)
    return sum(nums) / len(nums) if nums else None


def clean(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def metric(row: dict[str, Any], key: str) -> Any:
    return (row.get("metrics") or {}).get(key)


def maxstep(row: dict[str, Any]) -> float:
    text = json.dumps(row.get("agent_messages", []), ensure_ascii=False)
    return 1.0 if "Reached max steps" in text else 0.0


def row_primary(row: dict[str, Any]) -> float | None:
    bench = row.get("mixed_benchmark")
    if bench == "envscaler":
        return row.get("envscaler_score")
    if bench == "searchqa":
        return row.get("subem")
    if bench == "toolhop":
        return row.get("answer_correct")
    if row.get("score") is not None:
        return row.get("score")
    return row.get("answer_correct")


def row_done(row: dict[str, Any]) -> float | None:
    bench = row.get("mixed_benchmark")
    if bench == "envscaler":
        return row.get("envscaler_done")
    if bench == "searchqa":
        return row.get("subem")
    if bench == "toolhop":
        return row.get("answer_correct")
    return row.get("has_valid_answer")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    benches = Counter(str(row.get("mixed_benchmark") or "unknown") for row in rows)
    summary: dict[str, Any] = {
        "total_tasks": len(rows),
        "status_success": sum(1 for row in rows if row.get("status") == "success"),
        "errors": sum(1 for row in rows if row.get("status") == "error"),
        "benchmark_distribution": dict(sorted(benches.items())),
        "mixed_primary_score": mean([row_primary(row) for row in rows]),
        "mixed_done_proxy": mean([row_done(row) for row in rows]),
        "valid_answer_rate": mean([row.get("has_valid_answer") for row in rows]),
        "avg_elapsed_time": mean([metric(row, "elapsed_time") for row in rows]),
        "avg_tokens": mean([metric(row, "total_tokens") for row in rows]),
        "avg_prompt_tokens": mean([metric(row, "prompt_tokens") for row in rows]),
        "avg_completion_tokens": mean([metric(row, "completion_tokens") for row in rows]),
        "avg_api_calls": mean([metric(row, "api_calls") for row in rows]),
        "total_tokens": sum(float(metric(row, "total_tokens") or 0) for row in rows),
        "total_api_calls": sum(float(metric(row, "api_calls") or 0) for row in rows),
        "maxstep_rate": mean([maxstep(row) for row in rows]),
        "by_benchmark": {},
    }
    for bench in sorted(benches):
        subset = [row for row in rows if str(row.get("mixed_benchmark") or "unknown") == bench]
        if bench == "toolhop":
            data = {
                "n": len(subset),
                "answer_correct": mean([row.get("answer_correct") for row in subset]),
                "path_score": mean([row.get("path_score") for row in subset]),
                "valid_answer_rate": mean([row.get("has_valid_answer") for row in subset]),
            }
        elif bench == "searchqa":
            data = {
                "n": len(subset),
                "subem": mean([row.get("subem") for row in subset]),
                "used_search": mean([row.get("used_search") for row in subset]),
                "answer_correct": mean([row.get("answer_correct") for row in subset]),
                "valid_answer_rate": mean([row.get("has_valid_answer") for row in subset]),
            }
        elif bench == "envscaler":
            data = {
                "n": len(subset),
                "done": mean([row.get("envscaler_done") for row in subset]),
                "score": mean([row.get("envscaler_score") for row in subset]),
                "maxstep_rate": mean([maxstep(row) for row in subset]),
            }
        else:
            data = {
                "n": len(subset),
                "score": mean([row.get("score") for row in subset]),
                "done_proxy": mean([row_done(row) for row in subset]),
            }
        summary["by_benchmark"][bench] = data
    return clean(summary)


def parse_constant(path: Path, name: str) -> str | None:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    match = re.search(rf"^\s*{name}\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    return match.group(1) if match else None


def parse_memory(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    match = re.search(r"MEMORY_SYSTEM\s*=\s*MemoryType\.([A-Z0-9_]+)\.value", text)
    if match:
        return match.group(1).lower()
    return parse_constant(path, "MEMORY_SYSTEM")


def structure_for(harness: str) -> dict[str, Any]:
    root = PROJECT_ROOT / "harness_factory" / harness
    planning = parse_constant(root / "planning_module/provider.py", "PLANNING_SYSTEM")
    action = parse_constant(root / "action_module/provider.py", "ACTION_SYSTEM")
    memory = parse_memory(root / "memory_module/provider.py")
    pairing_reason = parse_constant(root / "builder.py", "PAIRING_REASON")
    topology = "direct_react"
    if action and any(token in action for token in ("reflection", "critic", "committee", "debate", "orchestra", "guarded")):
        topology = "augmented_react"
    return {
        "planning": planning,
        "action": action,
        "memory": memory,
        "topology": topology,
        "pairing_reason": pairing_reason,
    }


def find_result_files() -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in sorted(RESULT_ROOT.glob("*/results.jsonl")):
        match = re.search(r"_(harness\d+)_", path.parent.name)
        if match:
            files[match.group(1)] = path
    return files


def make_profile(harness: str, results_path: Path) -> dict[str, Any]:
    rows = read_jsonl(results_path)
    run_dir = results_path.parent
    structure = structure_for(harness)
    profile = {
        "profile_id": PROFILE_ID,
        "harness": harness,
        "recorded_at": utc_now(),
        "status": "stopped_by_user_partial",
        "round": "round_00",
        "role": "seed",
        "experiment": "round_00_seed200",
        "dataset": "mixeddata_train_prefix_partial",
        "dataset_note": "Prefix of mixeddata train; run was stopped before all harnesses reached the same count.",
        "model": {
            "name": "qwen3-4b-base",
            "alias": "qwen3-4b-base",
            "backend": "local",
            "adapter": None,
        },
        "memory_provider": structure.get("memory"),
        "structure": structure,
        "paths": {
            "run_dir": relpath(run_dir),
            "results": relpath(results_path),
            "registry": relpath(REGISTRY_PATH),
        },
        "metrics_all_available": summarize(rows),
        "metrics_fair_first100": summarize(rows[:100]),
        "assessment": DECISIONS.get(harness, {}),
    }
    return clean(profile)


def update_registry(profiles: dict[str, dict[str, Any]]) -> None:
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    registry.setdefault("schema_version", 1)
    registry.setdefault("harnesses", {})
    registry["updated_at"] = utc_now()
    for harness, profile in profiles.items():
        entry = registry["harnesses"].setdefault(harness, {})
        structure = profile["structure"]
        entry.setdefault("import_name", f"rounds.round_00_base.{harness}")
        entry.setdefault("package", "harness_factory")
        entry.setdefault("path", f"harness_factory/rounds/round_00_base/{harness}")
        entry.setdefault("generation", 0)
        entry.setdefault("status", "seed")
        entry["default_memory"] = structure.get("memory")
        entry["structure"] = {
            "planning": structure.get("planning"),
            "action": structure.get("action"),
            "topology": structure.get("topology"),
        }
        entry["pairing_reason"] = structure.get("pairing_reason")
        entry["round"] = "round_00"
        entry["role"] = "seed"
        entry["archive_decision"] = profile["assessment"].get("archive_tier")
        entry["latest_profile"] = profile
        metrics = profile["metrics_all_available"]
        run_id = f"{PROFILE_ID}__{harness}"
        run_record = {
            "run_id": run_id,
            "recorded_at": profile["recorded_at"],
            "experiment": profile["experiment"],
            "round": profile["round"],
            "dataset": profile["dataset"],
            "dataset_type": "mixeddata",
            "status": profile["status"],
            "model": profile["model"],
            "memory_provider": profile["memory_provider"],
            "metrics": metrics,
            "fair_first100_metrics": profile["metrics_fair_first100"],
            "assessment": profile["assessment"],
            "paths": profile["paths"],
        }
        runs = [row for row in entry.get("runs", []) if row.get("run_id") != run_id]
        runs.append(run_record)
        entry["runs"] = runs
        entry["latest"] = {
            "run_id": run_id,
            "round": profile["round"],
            "dataset": profile["dataset"],
            "model": profile["model"]["alias"],
            "adapter": None,
            "primary_score": metrics.get("mixed_primary_score"),
            "accuracy": metrics.get("mixed_done_proxy"),
            "valid_answer_rate": metrics.get("valid_answer_rate"),
            "avg_tool_calls": metrics.get("avg_api_calls"),
            "avg_elapsed_time": metrics.get("avg_elapsed_time"),
            "avg_tokens": metrics.get("avg_tokens"),
        }
    REGISTRY_PATH.write_text(
        yaml.safe_dump(registry, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def update_card(harness: str, profile: dict[str, Any]) -> None:
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    json_path = CARD_DIR / f"{harness}.json"
    card = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
    card.setdefault("schema_version", 1)
    card.setdefault("harness_id", harness)
    card.setdefault("current_runs", {})
    card["current_runs"][PROFILE_ID] = {
        "status": profile["status"],
        "experiment": profile["experiment"],
        "round": profile["round"],
        "dataset": profile["dataset"],
        "model": profile["model"],
        "memory_provider": profile["memory_provider"],
        "run_id": f"{PROFILE_ID}__{harness}",
        "metrics_all_available": profile["metrics_all_available"],
        "metrics_fair_first100": profile["metrics_fair_first100"],
        "paths": profile["paths"],
    }
    card["archive_assessment"] = profile["assessment"]
    card["updated_at"] = utc_now()
    json_path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_path = CARD_DIR / f"{harness}.md"
    existing = md_path.read_text(encoding="utf-8") if md_path.exists() else f"# {harness} Harness Card\n"
    section = markdown_profile_section(profile)
    start = "<!-- ROUND00_SEED_PROFILE_START -->"
    end = "<!-- ROUND00_SEED_PROFILE_END -->"
    block = f"\n{start}\n{section}\n{end}\n"
    if start in existing and end in existing:
        pattern = re.compile(rf"\n?{re.escape(start)}.*?{re.escape(end)}\n?", re.DOTALL)
        updated = pattern.sub(block, existing)
    else:
        updated = existing.rstrip() + "\n" + block
    md_path.write_text(updated, encoding="utf-8")


def pct(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{100 * float(value):.1f}%"


def num(value: Any, digits: int = 1) -> str:
    if value is None:
        return "NA"
    return f"{float(value):.{digits}f}"


def markdown_profile_section(profile: dict[str, Any]) -> str:
    allm = profile["metrics_all_available"]
    fair = profile["metrics_fair_first100"]
    assess = profile["assessment"]
    lines = [
        "## Round 00 Seed Profile - Partial Train Prefix",
        f"- Status: `{profile['status']}`",
        f"- Profile id: `{profile['profile_id']}`",
        f"- Dataset: `{profile['dataset']}`",
        f"- Completed rows: `{allm['total_tasks']}`",
        f"- Archive tier: `{assess.get('archive_tier')}`",
        f"- Summary: {assess.get('summary')}",
        "",
        "### Fair First-100 Metrics",
        f"- Benchmark distribution: `{fair.get('benchmark_distribution')}`",
        f"- Mixed primary score: `{num(fair.get('mixed_primary_score'), 4)}`",
        f"- Mixed done proxy: `{num(fair.get('mixed_done_proxy'), 4)}`",
        f"- Average elapsed time: `{num(fair.get('avg_elapsed_time'))}` sec",
        f"- Average tokens: `{num(fair.get('avg_tokens'), 0)}`",
        f"- Average API calls: `{num(fair.get('avg_api_calls'))}`",
        f"- Max-step rate: `{pct(fair.get('maxstep_rate'))}`",
        "",
        "### All Available Metrics",
        f"- Benchmark distribution: `{allm.get('benchmark_distribution')}`",
        f"- Mixed primary score: `{num(allm.get('mixed_primary_score'), 4)}`",
        f"- Mixed done proxy: `{num(allm.get('mixed_done_proxy'), 4)}`",
        f"- Average elapsed time: `{num(allm.get('avg_elapsed_time'))}` sec",
        f"- Average tokens: `{num(allm.get('avg_tokens'), 0)}`",
        f"- Average API calls: `{num(allm.get('avg_api_calls'))}`",
        f"- Max-step rate: `{pct(allm.get('maxstep_rate'))}`",
        "",
        "### Per-Benchmark Signals",
    ]
    for scope_name, metrics in (("fair_first100", fair), ("all_available", allm)):
        lines.append(f"- `{scope_name}`: `{metrics.get('by_benchmark')}`")
    lines.extend(["", "### Strengths"])
    lines.extend(f"- {item}" for item in assess.get("strengths", []))
    lines.extend(["", "### Risks"])
    lines.extend(f"- {item}" for item in assess.get("risks", []))
    lines.extend(["", "### Evolution Recommendations"])
    lines.extend(f"- {item}" for item in assess.get("evolution_recommendations", []))
    return "\n".join(lines)


def write_summary(profiles: dict[str, dict[str, Any]]) -> None:
    rows = []
    for harness, profile in sorted(profiles.items(), key=lambda item: int(item[0].replace("harness", ""))):
        allm = profile["metrics_all_available"]
        fair = profile["metrics_fair_first100"]
        rows.append(
            {
                "harness": harness,
                "completed_rows": allm["total_tasks"],
                "archive_tier": profile["assessment"].get("archive_tier"),
                "fair_first100": fair,
                "all_available": allm,
                "assessment": profile["assessment"],
                "paths": profile["paths"],
            }
        )
    payload = {
        "profile_id": PROFILE_ID,
        "generated_at": utc_now(),
        "status": "partial_stopped_by_user",
        "notes": [
            "Use fair_first100 for cross-harness comparison because harness2 has the fewest rows.",
            "Use all_available for runtime and stability diagnosis.",
        ],
        "rows": rows,
    }
    json_path = CARD_DIR / f"{PROFILE_ID}_summary.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        f"# {PROFILE_ID} Summary",
        "",
        "This profile was registered after the user stopped the partial train-prefix run.",
        "Use the fair first-100 slice for cross-harness comparison and all available rows for stability/cost diagnosis.",
        "",
        "| Harness | Rows | Tier | Fair primary | Fair env score | Fair ToolHop correct | Fair SearchQA subEM | Fair avg sec | Fair avg tokens | Fair max-step |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        fair = row["fair_first100"]
        by = fair.get("by_benchmark", {})
        env = by.get("envscaler", {})
        th = by.get("toolhop", {})
        sq = by.get("searchqa", {})
        md_lines.append(
            "| {harness} | {rows} | {tier} | {primary} | {env_score} | {toolhop} | {searchqa} | {sec} | {tok} | {maxstep} |".format(
                harness=row["harness"],
                rows=row["completed_rows"],
                tier=row["archive_tier"],
                primary=num(fair.get("mixed_primary_score"), 3),
                env_score=pct(env.get("score")),
                toolhop=pct(th.get("answer_correct")),
                searchqa=pct(sq.get("subem")),
                sec=num(fair.get("avg_elapsed_time")),
                tok=num(fair.get("avg_tokens"), 0),
                maxstep=pct(fair.get("maxstep_rate")),
            )
        )
    md_lines.extend(["", "## Archive Decisions"])
    for row in rows:
        assess = row["assessment"]
        md_lines.extend(
            [
                f"### {row['harness']} - {row['archive_tier']}",
                assess.get("summary", ""),
                "",
                "Recommended evolution moves:",
            ]
        )
        md_lines.extend(f"- {item}" for item in assess.get("evolution_recommendations", []))
        md_lines.append("")
    md_path = CARD_DIR / f"{PROFILE_ID}_summary.md"
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    results = find_result_files()
    profiles = {harness: make_profile(harness, path) for harness, path in sorted(results.items())}
    update_registry(profiles)
    for harness, profile in profiles.items():
        update_card(harness, profile)
    write_summary(profiles)
    print(f"Archived {len(profiles)} harness profiles into {REGISTRY_PATH}")
    print(f"Summary: {CARD_DIR / (PROFILE_ID + '_summary.md')}")


if __name__ == "__main__":
    main()
