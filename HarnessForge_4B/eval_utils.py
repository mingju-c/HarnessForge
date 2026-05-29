#!/usr/bin/env python
# coding=utf-8
# Copyright 2025 The OPPO Inc. PersonalAI team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unified utilities for evaluation tasks including logging, reporting, and statistics.
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskTimer:
    """Timer for tracking task execution time"""

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def start(self):
        self.start_time = time.time()

    def stop(self):
        self.end_time = time.time()
        return self.elapsed()

    def elapsed(self):
        if self.start_time is None:
            return 0
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time


class TokenCounter:
    """Counter for tracking token usage and API calls"""

    def __init__(self):
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.api_calls = 0

    def add(self, prompt_tokens: int = 0, completion_tokens: int = 0, api_calls: int = 1):
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += (prompt_tokens + completion_tokens)
        self.api_calls += api_calls

    def to_dict(self):
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "api_calls": self.api_calls
        }

    @staticmethod
    def from_trajectory(trajectory: List[Dict]) -> 'TokenCounter':
        counter = TokenCounter()
        for step in trajectory:
            if isinstance(step, dict):
                usage = step.get("usage", {})
                if usage:
                    counter.add(
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        api_calls=1
                    )
        return counter

    @staticmethod
    def from_memory_steps(steps: List[Any]) -> 'TokenCounter':
        counter = TokenCounter()
        for step in steps:
            prompt_tokens = getattr(step, "input_tokens", 0) or 0
            completion_tokens = getattr(step, "output_tokens", 0) or 0
            if prompt_tokens or completion_tokens:
                counter.add(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, api_calls=1)
        return counter

    @staticmethod
    def from_model(model) -> 'TokenCounter':
        counter = TokenCounter()
        if hasattr(model, 'get_total_counts'):
            counts = model.get_total_counts()
            counter.total_tokens = counts.get("total_tokens", 0)
            counter.prompt_tokens = counts.get("total_input_tokens", 0)
            counter.completion_tokens = counts.get("total_output_tokens", 0)
            counter.api_calls = counts.get("total_api_calls", 0)
        elif hasattr(model, 'get_token_counts'):
            counts = model.get_token_counts()
            prompt_tokens = counts.get("input_token_count", 0) or 0
            completion_tokens = counts.get("output_token_count", 0) or 0
            if prompt_tokens or completion_tokens:
                counter.add(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, api_calls=1)
        return counter


def save_task_result(
    result: Dict[str, Any],
    run_dir: str,
    filename: Optional[str] = None
) -> str:
    os.makedirs(run_dir, exist_ok=True)

    if filename is None:
        idx = result.get("item_index") or result.get("task_id")
        if idx is not None:
            filename = f"{idx}.json"
        else:
            import uuid
            filename = f"{uuid.uuid4().hex}.json"

    filepath = os.path.join(run_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return filepath


def generate_unified_report(
    results: List[Dict[str, Any]],
    output_path: str,
    dataset_name: str = "Evaluation",
    has_levels: bool = True,
    level_key: str = "level"
) -> Dict[str, Any]:
    if not results:
        logger.warning("No results to generate report")
        return {}

    total = len(results)
    successful = sum(1 for r in results if r.get("status") == "success")
    errors = sum(1 for r in results if r.get("status") == "error")

    correct = sum(1 for r in results if str(r.get("judgement") or "").strip().lower() == "correct")
    incorrect = sum(1 for r in results if str(r.get("judgement") or "").strip().lower() == "incorrect")

    total_tokens = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_api_calls = 0
    total_time = 0.0

    for r in results:
        metrics = r.get("metrics", {})
        total_tokens += metrics.get("total_tokens", 0)
        total_prompt_tokens += metrics.get("prompt_tokens", 0)
        total_completion_tokens += metrics.get("completion_tokens", 0)
        total_api_calls += metrics.get("api_calls", 0)
        total_time += metrics.get("elapsed_time", 0)

    by_level = defaultdict(lambda: {"total": 0, "correct": 0})
    if has_levels:
        for r in results:
            level = r.get(level_key, "unknown")
            by_level[level]["total"] += 1
            if str(r.get("judgement") or "").strip().lower() == "correct":
                by_level[level]["correct"] += 1

    stats = {
        "dataset": dataset_name,
        "total_tasks": total,
        "successful": successful,
        "errors": errors,
        "correct": correct,
        "incorrect": incorrect,
        "accuracy": correct / total if total > 0 else 0,
        "total_tokens": total_tokens,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_api_calls": total_api_calls,
        "total_time": total_time,
        "avg_tokens_per_task": total_tokens / total if total > 0 else 0,
        "avg_prompt_tokens_per_task": total_prompt_tokens / total if total > 0 else 0,
        "avg_completion_tokens_per_task": total_completion_tokens / total if total > 0 else 0,
        "avg_time_per_task": total_time / total if total > 0 else 0,
    }

    if has_levels:
        stats["by_level"] = dict(by_level)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"{dataset_name} Evaluation Report\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Total Tasks: {total}\n")
        f.write(f"Successful: {successful} ({successful/total*100:.1f}%)\n")
        f.write(f"Errors: {errors} ({errors/total*100:.1f}%)\n\n")

        f.write(f"Correct: {correct}\n")
        f.write(f"Incorrect: {incorrect}\n")
        f.write(f"Accuracy: {correct/total*100:.2f}%\n\n")

        f.write("-" * 80 + "\n")
        f.write("Resource Usage\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total Tokens: {total_tokens:,}\n")
        f.write(f"  - Prompt Tokens: {total_prompt_tokens:,}\n")
        f.write(f"  - Completion Tokens: {total_completion_tokens:,}\n")
        f.write(f"Total API Calls: {total_api_calls}\n")
        f.write(f"Total Time: {total_time:.2f}s ({total_time/60:.2f}m)\n\n")
        f.write("Average Per Task:\n")
        f.write(f"  - Tokens: {stats['avg_tokens_per_task']:.1f}\n")
        f.write(f"  - Prompt Tokens: {stats['avg_prompt_tokens_per_task']:.1f}\n")
        f.write(f"  - Completion Tokens: {stats['avg_completion_tokens_per_task']:.1f}\n")
        f.write(f"  - Time: {stats['avg_time_per_task']:.2f}s\n\n")

        if has_levels:
            f.write("-" * 80 + "\n")
            f.write(f"By {level_key.capitalize()}\n")
            f.write("-" * 80 + "\n")
            for level in sorted(by_level.keys()):
                level_stats = by_level[level]
                acc = level_stats["correct"] / level_stats["total"] * 100 if level_stats["total"] > 0 else 0
                f.write(f"  {level}: {level_stats['correct']}/{level_stats['total']} ({acc:.1f}%)\n")
            f.write("\n")

        f.write("=" * 80 + "\n")

    logger.info(f"Report saved to {output_path}")

    print("\n" + "=" * 80)
    print(f"{dataset_name} Evaluation Summary")
    print("=" * 80)
    print(f"Accuracy: {correct}/{total} = {correct/total*100:.2f}%")
    print(f"Tokens: {total_tokens:,} (Prompt: {total_prompt_tokens:,} | Completion: {total_completion_tokens:,})")
    print(f"API Calls: {total_api_calls} | Time: {total_time/60:.1f}m")
    print("=" * 80 + "\n")

    return stats


def enrich_result_with_metrics(
    result: Dict[str, Any],
    timer: TaskTimer,
    token_counter: Optional[TokenCounter] = None,
    trajectory: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    elapsed_time = timer.elapsed()

    if token_counter is None and trajectory is not None:
        token_counter = TokenCounter.from_trajectory(trajectory)

    metrics = {
        "elapsed_time": elapsed_time,
    }

    if token_counter:
        metrics.update(token_counter.to_dict())

    result["metrics"] = metrics
    return result


def create_run_directory(
    base_dir: str,
    dataset_name: str,
    memory_name: str = "",
    use_timestamp: bool = True
) -> str:
    if not use_timestamp:
        os.makedirs(base_dir, exist_ok=True)
        return base_dir

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_name = f"{memory_name}{timestamp}" if memory_name else timestamp
    run_dir = os.path.join(base_dir, f"{dataset_name}_runs", run_name)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir
