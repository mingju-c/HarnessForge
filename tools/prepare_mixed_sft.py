#!/usr/bin/env python3
"""Build auditable mixed-task SFT data from one declared round/harness/policy.

Uses only the standard library. The default implements the final acceptance
rules specified by the maintainers: exact QA success and completed EnvScaler
trajectories with reward at least 0.9.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


SCORING_VERSION = "paper_c1_v1"
RECIPE_VERSION = "mixed_sft_v2"
BENCHMARKS = ("toolhop", "searchqa", "envscaler")
PROVENANCE_KEYS = ("round_id", "harness", "policy_id", "dataset_id", "data_split")
DEFAULT_CONFIG = {
    "min_scores": {"toolhop": 1.0, "searchqa": 1.0, "envscaler": 0.9},
    "sample_mode": "full",
    "eval_ratio": 0.05,
    "seed": 42,
    "reject_observation_markers": [
        "Error:", "Error for tool call", "Unknown tool", "GUARD_BLOCK",
        "PARTIAL_COMMIT", "schema_preflight", "repeated_failed_call",
        "low_value_repeat", "Reached max steps",
    ],
}


class Reject(ValueError):
    """A per-trajectory rejection reason, recorded in audit.jsonl."""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def load_config(path: Path | None) -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path:
        supplied = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(supplied, dict) or set(supplied) - set(config):
            raise ValueError("Unknown recipe options; see the mixed SFT configuration example.")
        config.update(supplied)
    if not isinstance(config["min_scores"], dict) or set(config["min_scores"]) != set(BENCHMARKS):
        raise ValueError("min_scores must specify toolhop, searchqa, and envscaler.")
    for value in config["min_scores"].values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("All score thresholds must be finite numbers in [0, 1].")
    if any(config["min_scores"][name] != 1.0 for name in ("toolhop", "searchqa")):
        raise ValueError("QA score thresholds must be 1; QA also requires answer_correct == 1.")
    if config["sample_mode"] not in {"full", "prefix"}:
        raise ValueError("sample_mode must be full or prefix.")
    ratio = config["eval_ratio"]
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not 0 <= ratio < 1:
        raise ValueError("eval_ratio must be in [0, 1).")
    if type(config["seed"]) is not int:
        raise ValueError("seed must be an integer.")
    markers = config["reject_observation_markers"]
    if not isinstance(markers, list) or any(not isinstance(marker, str) or not marker for marker in markers):
        raise ValueError("reject_observation_markers must be a list of non-empty strings.")
    return config


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Source manifest must be a JSON object.")
    for key in PROVENANCE_KEYS:
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f"Source manifest requires {key}.")
    if manifest["data_split"] not in {"evolution", "train"}:
        raise ValueError("SFT sources must be declared evolution/train data, never validation or test data.")
    if not isinstance(manifest.get("sources"), list) or not manifest["sources"]:
        raise ValueError("Source manifest requires a non-empty sources list.")
    return manifest


def source_files(manifest: dict[str, Any], base: Path) -> list[Path]:
    files = set()
    for source in manifest["sources"]:
        if not isinstance(source, str):
            raise ValueError("Each source must be a path string relative to the manifest.")
        path = (base / source).resolve()
        if path.is_dir():
            found = [p for p in path.glob("*.json") if p.stem.isdigit()]
            if not found:
                raise ValueError(f"No numeric task JSON files in {path}.")
            files.update(found)
        elif path.is_file() and path.suffix in {".json", ".jsonl"}:
            files.add(path)
        else:
            raise ValueError(f"Source must be JSONL, task JSON, or a directory of numeric task JSON files: {path}")
    return sorted(files)


def read_records(path: Path):
    with path.open(encoding="utf-8") as handle:
        if path.suffix == ".jsonl":
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError(f"{path}:{line_number}: expected a result object.")
                    yield line_number, row
        else:
            row = json.load(handle)
            if not isinstance(row, dict):
                raise ValueError(f"{path}: expected one task result object.")
            yield 1, row


def check_provenance(row: dict[str, Any], manifest: dict[str, Any], allow_declared: bool) -> str:
    provenance = row.get("provenance", {})
    if provenance is None:
        provenance = {}
    if not isinstance(provenance, dict):
        raise ValueError("Invalid row provenance.")
    missing = []
    for key in PROVENANCE_KEYS:
        value = provenance.get(key)
        if value is None:
            missing.append(key)
        elif value != manifest[key]:
            raise ValueError(f"Source provenance conflicts with manifest: {key}={value!r}, expected {manifest[key]!r}.")
    if missing and not allow_declared:
        raise ValueError(
            f"Rows lack provenance fields {missing}. Recollect with the updated runner, or explicitly use "
            "--allow-declared-provenance after independently checking the source."
        )
    return "manifest_declared" if missing else "row_metadata_matched"


def numeric_metric(row: dict[str, Any], key: str) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise Reject(f"missing_or_invalid_metric:{key}") from exc
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise Reject(f"missing_or_invalid_metric:{key}")
    return value


def validate_score(row: dict[str, Any], benchmark: str, config: dict[str, Any]) -> float:
    if row.get("status") != "success":
        raise Reject("execution_not_successful")
    score = numeric_metric(row, "score")
    if benchmark == "toolhop":
        answer = numeric_metric(row, "answer_correct")
        expected = 0.5 * answer + 0.5 * numeric_metric(row, "path_score")
        if answer != 1.0:
            raise Reject("toolhop_answer_incorrect")
    elif benchmark == "searchqa":
        expected = numeric_metric(row, "answer_f1")
        if numeric_metric(row, "answer_correct") != 1.0:
            raise Reject("searchqa_answer_incorrect")
    else:
        expected = numeric_metric(row, "envscaler_score")
        if numeric_metric(row, "envscaler_done") != 1.0:
            raise Reject("envscaler_not_done")
    if not math.isclose(score, expected, rel_tol=0, abs_tol=1e-6):
        raise Reject("score_component_mismatch")
    if benchmark in {"toolhop", "searchqa"} and score != 1.0:
        raise Reject("qa_score_not_perfect")
    threshold_value = expected if benchmark == "envscaler" else score
    if threshold_value < config["min_scores"][benchmark]:
        raise Reject("below_score_threshold")
    return score


def content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict) or block.get("type", "text") != "text" or not isinstance(block.get("text"), str):
                raise Reject("unsupported_content_block")
            parts.append(block["text"])
        return "\n".join(parts).strip()
    raise Reject("unsupported_message_content")


def parse_calls(message: dict[str, Any], text: str) -> list[dict[str, Any]]:
    calls = message.get("tool_calls")
    if calls is None and text.startswith("Calling tools:"):
        raw = text[len("Calling tools:"):].strip()
        try:
            payload = json.loads(raw)
        except ValueError:
            try:
                payload = ast.literal_eval(raw)
            except (ValueError, SyntaxError) as exc:
                raise Reject("malformed_tool_payload") from exc
        if not isinstance(payload, dict):
            raise Reject("malformed_tool_payload")
        calls = payload.get("tools")
        if not calls:
            raise Reject("empty_tool_payload")
    if calls is None:
        return []
    if not isinstance(calls, list) or not calls:
        raise Reject("malformed_tool_calls")
    normalized = []
    for call in calls:
        if not isinstance(call, dict):
            raise Reject("malformed_tool_call")
        call = call.get("function", call)
        if not isinstance(call, dict) or not isinstance(call.get("name"), str) or not call["name"]:
            raise Reject("malformed_tool_name")
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError as exc:
                raise Reject("malformed_tool_arguments") from exc
        if not isinstance(arguments, dict):
            raise Reject("malformed_tool_arguments")
        normalized.append({"name": call["name"], "arguments": arguments})
    return normalized


def terminal_domain(call: dict[str, Any]) -> str | None:
    name = call["name"]
    if name in {"final_answer", "submit_answer"}:
        return "qa"
    if name in {"complete_task", "task_completed"}:
        return "envscaler"
    if name == "chat_with_user" and str(call["arguments"].get("content", "")).strip() == "Task Completed":
        return "envscaler"
    return None


def clean_dialogue(row: dict[str, Any], benchmark: str, config: dict[str, Any]) -> tuple[list, str, Counter]:
    raw = row.get("agent_messages")
    if not isinstance(raw, list) or not raw:
        raise Reject("missing_agent_messages")
    for step in row.get("agent_trajectory") or []:
        if isinstance(step, dict) and step.get("error"):
            raise Reject("trajectory_execution_error")
    messages, systems = [], []
    actions = Counter()
    terminal = False
    waiting_observation = False
    observation_allowed = False
    for message in raw:
        if not isinstance(message, dict):
            raise Reject("malformed_message")
        role = message.get("role")
        if role not in {"user", "assistant", "system", "tool-response", "tool"}:
            raise Reject("unknown_message_role")
        text = content_text(message.get("content"))
        calls = parse_calls(message, text) if role == "assistant" else []
        if role in {"tool-response", "tool"}:
            if any(marker.casefold() in text.casefold() for marker in config["reject_observation_markers"]):
                raise Reject("failed_or_guarded_tool_observation")
        if terminal:
            if calls:
                raise Reject("tool_call_after_terminal")
            actions["dropped_terminal_echo_or_tail"] += 1
            continue
        if not text and not calls:
            actions["dropped_empty_message"] += 1
            continue
        if role == "system":
            if messages:
                raise Reject("system_message_mid_dialogue")
            systems.append(text)
            continue
        if role in {"tool-response", "tool"}:
            if not observation_allowed:
                raise Reject("orphan_tool_observation")
            waiting_observation = False
            role = "user"
            text = "[Tool observation]\n" + text
            actions["observation_as_input"] += 1
        else:
            if waiting_observation:
                raise Reject("missing_tool_observation")
            observation_allowed = False
        if calls:
            terminal_calls = [call for call in calls if terminal_domain(call)]
            if terminal_calls:
                if len(calls) != 1:
                    raise Reject("terminal_batched_with_other_calls")
                expected_domain = "envscaler" if benchmark == "envscaler" else "qa"
                if terminal_domain(calls[0]) != expected_domain:
                    raise Reject("wrong_terminal_tool")
                terminal = True
                actions["kept_terminal_action"] += 1
            else:
                waiting_observation = True
                observation_allowed = True
            if message.get("tool_calls") is not None:
                text = (text + "\n" if text else "") + "Calling tools:\n" + canonical({"tools": calls})
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + text
            actions["merged_adjacent_same_role"] += 1
        else:
            messages.append({"role": role, "content": text})
    if not terminal:
        raise Reject("missing_terminal_action")
    if not messages or len(messages) % 2 or messages[0]["role"] != "user" or messages[-1]["role"] != "assistant":
        raise Reject("invalid_dialogue_alternation")
    return messages, "\n\n".join(systems), actions


def task_identity(row: dict[str, Any], benchmark: str, dataset_id: str) -> tuple[str, str]:
    question = row.get("question")
    if not isinstance(question, str) or not question.strip():
        raise Reject("missing_question_for_task_split")
    normalized_question = " ".join(question.casefold().split())
    task_id = row.get("task_id", row.get("item_index"))
    task_key = digest([dataset_id, benchmark, task_id if task_id is not None else normalized_question])
    # Same question stays in the same partition even if task IDs differ or branch
    # acceptance sets differ. Distinct stateful tasks can still remain distinct.
    split_key = digest([benchmark, normalized_question])
    return task_key, split_key


def partition(split_key: str, config: dict[str, Any]) -> str:
    value = int(digest([config["seed"], split_key]), 16) / 2**256
    return "eval" if value < config["eval_ratio"] else "train"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical(row) + "\n")


def build_dataset(manifest_path: Path, output: Path, dataset_name: str, config: dict[str, Any], allow_declared=False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", dataset_name):
        raise ValueError("dataset_name must contain only letters, digits, underscores, and hyphens.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is not empty; use a new directory to preserve existing artifacts.")
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    files = source_files(manifest, manifest_path.parent)
    config_hash = digest(config)
    audit, accepted = [], {}
    provenance_counts, cleaning_counts, rejection_counts, seen_counts = Counter(), Counter(), Counter(), Counter()
    file_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    for path in files:
        for line, row in read_records(path):
            provenance_mode = check_provenance(row, manifest, allow_declared)
            if row.get("scoring_version") != SCORING_VERSION:
                raise ValueError(f"{path}:{line}: expected {SCORING_VERSION}; explicitly re-score historical trajectories first.")
            provenance_counts[provenance_mode] += 1
            benchmark = row.get("mixed_benchmark")
            seen_counts[str(benchmark)] += 1
            decision = {"source_file": str(path), "source_line": line, "item_index": row.get("item_index"), "benchmark": benchmark}
            audit.append(decision)
            try:
                if benchmark not in BENCHMARKS:
                    raise Reject("unsupported_benchmark")
                score = validate_score(row, benchmark, config)
                task_key, split_key = task_identity(row, benchmark, manifest["dataset_id"])
                messages, system, changes = clean_dialogue(row, benchmark, config)
            except Reject as exc:
                decision.update(decision="rejected", reason=str(exc))
                rejection_counts[str(exc)] += 1
                continue
            cleaning_counts.update(changes)
            decision.update(decision="accepted", task_key=task_key)
            metadata = {
                **{key: manifest[key] for key in PROVENANCE_KEYS},
                "scoring_version": SCORING_VERSION, "recipe_version": RECIPE_VERSION,
                "config_sha256": config_hash, "provenance_check": provenance_mode,
                "mixed_benchmark": benchmark, "task_key": task_key, "split_key": split_key,
                "source_file": str(path), "source_line": line, "score": score,
                "source_metrics": {key: row.get(key) for key in ("answer_correct", "path_score", "answer_f1", "envscaler_score", "envscaler_done")},
            }
            record = {"messages": messages, "system": system, "metadata": metadata}
            # One trajectory per task: prefer higher score, then shorter dialogue,
            # then content hash. Input ordering cannot affect the chosen content.
            rank = (-score, len(canonical(messages)), digest([system, messages]))
            previous = accepted.get(task_key)
            if previous is not None and previous[0] <= rank:
                decision.update(decision="rejected", reason="duplicate_task")
                rejection_counts["duplicate_task"] += 1
                continue
            if previous is not None:
                previous[2].update(decision="rejected", reason="duplicate_task")
                rejection_counts["duplicate_task"] += 1
            accepted[task_key] = (rank, record, decision)
    splits = {"train": [], "eval": []}
    task_counts = {name: Counter() for name in splits}
    for key in sorted(accepted):
        record = accepted[key][1]
        name = partition(record["metadata"]["split_key"], config)
        task_counts[name][record["metadata"]["mixed_benchmark"]] += 1
        ends = [len(record["messages"])] if config["sample_mode"] == "full" else list(range(2, len(record["messages"]) + 1, 2))
        for end in ends:
            splits[name].append({**record, "messages": record["messages"][:end], "metadata": {
                **record["metadata"], "partition": name, "sample_mode": config["sample_mode"], "target_turn": end // 2,
            }})
    training_options = {"train_on_prompt": False, "mask_history": config["sample_mode"] == "prefix"}
    stats = {
        "input_trajectories": len(audit), "accepted_trajectories": len(accepted),
        "seen_by_benchmark": dict(seen_counts), "rejections": dict(rejection_counts),
        "cleaning_actions": dict(cleaning_counts), "provenance_checks": dict(provenance_counts),
        "tasks_by_partition": {name: dict(counts) for name, counts in task_counts.items()},
        "samples_by_partition": {name: len(rows) for name, rows in splits.items()},
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        write_jsonl(output / f"{name}.jsonl", rows)
    tags = {"role_tag": "role", "content_tag": "content", "user_tag": "user", "assistant_tag": "assistant", "system_tag": "system"}
    write_json(output / "dataset_info.json", {
        f"{dataset_name}_{name}": {"file_name": f"{name}.jsonl", "formatting": "sharegpt", "columns": {"messages": "messages", "system": "system"}, "tags": tags}
        for name in splits
    })
    write_json(output / "manifest.json", {
        "recipe_version": RECIPE_VERSION, "scoring_version": SCORING_VERSION,
        "source_manifest": manifest, "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "config": config, "config_sha256": config_hash, "source_file_sha256": file_hashes,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "allow_declared_provenance": allow_declared, "training_options": training_options,
        "scope": "Unified reference for the maintainer-specified final filtering rules; source declarations and configuration are recorded for reproducibility.",
    })
    write_json(output / "stats.json", stats)
    write_jsonl(output / "audit.jsonl", audit)
    write_json(output / "training_options.json", training_options)
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--config", type=Path, help="JSON recipe; default is full-dialogue SFT with QA score/answer_correct == 1 and EnvScaler reward >= 0.9 plus done == 1.")
    parser.add_argument("--allow-declared-provenance", action="store_true", help="Accept missing row provenance using the manifest declaration; conflicts still fail.")
    args = parser.parse_args(argv)
    stats = build_dataset(args.manifest, args.output_dir, args.dataset_name, load_config(args.config), args.allow_declared_provenance)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if not stats["samples_by_partition"]["train"]:
        raise SystemExit("No training samples accepted. Inspect stats.json and audit.jsonl; no thresholds were automatically relaxed.")


if __name__ == "__main__":
    main()
