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

import os
import random
import argparse
import json
import logging
import re
import threading
import traceback
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm
from dotenv import load_dotenv

import harness_runtime  # noqa: F401
from Agents.utils import make_json_serializable
from data_paths import resolve_project_data_root
from utils import read_jsonl, write_jsonl
from runtime.toolhop import TOOLHOP_MODE_CLOSED, TOOLHOP_MODE_OPEN
from eval_utils import (
    TaskTimer,
    TokenCounter,
    save_task_result,
    generate_unified_report,
    enrich_result_with_metrics,
    create_run_directory,
)
from llm_runtime import LLMConfig, create_chat_model, get_default_model_name, resolve_llm_config
from runtime.toolhop.evaluation import (
    evaluate_toolhop_item,
    summarize_toolhop_results,
    write_toolhop_metrics,
)
from runtime.api_bank.evaluation import (
    evaluate_api_bank_item,
    summarize_api_bank_results,
    write_api_bank_metrics,
)
from runtime.restbench.evaluation import (
    evaluate_restbench_item,
    summarize_restbench_results,
    write_restbench_metrics,
)
from runtime.taubench.evaluation import (
    evaluate_taubench_item,
    summarize_taubench_results,
    write_taubench_metrics,
)
from mixeddata import (
    evaluate_mixeddata_item,
    extract_mixed_ground_truth,
    extract_mixed_task,
    get_mixed_benchmark,
    write_mixeddata_metrics,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_workspace_root(project_root: Path) -> Path:
    project_root = Path(project_root).resolve()
    candidates = [project_root.parent, project_root.parent.parent]
    marker_dirs = ("CODE", "related work")

    for candidate in candidates:
        if any((candidate / marker).exists() for marker in marker_dirs):
            return candidate

    return project_root.parent


DATA_ROOT = resolve_project_data_root(Path(SCRIPT_DIR))
WORKSPACE_ROOT = _resolve_workspace_root(Path(SCRIPT_DIR))
EVAL_BENCH_ROOT = (
    Path(SCRIPT_DIR).parent / "eval_bench"
    if (Path(SCRIPT_DIR).parent / "eval_bench").exists()
    else Path(SCRIPT_DIR) / "eval_bench"
)


@lru_cache(maxsize=1)
def _get_core_agent_class():
    from base_agent import CoreAgent

    return CoreAgent


def _resolve_existing_path(*candidates: str) -> str:
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return candidates[0]

TOOLHOP_SPLIT_ROOT = Path(_resolve_existing_path(
    str(EVAL_BENCH_ROOT / "toolhop" / "data" / "splits" / "seed_42_online_800_test_195_round_200"),
    str(DATA_ROOT / "toolhop" / "splits" / "seed_42_online_800_test_195_round_200"),
))
TOOLHOP_FINAL_TEST_PATH = Path(_resolve_existing_path(
    str(EVAL_BENCH_ROOT / "toolhop" / "data" / "toolhop_final_blind_test.json"),
    str(TOOLHOP_SPLIT_ROOT / "toolhop_final_blind_test.json"),
))


def resolve_toolhop_infile(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return raw

    candidate_path = Path(raw).expanduser()
    if candidate_path.exists() or raw.endswith('.json') or raw.endswith('.jsonl') or os.path.sep in raw:
        return raw

    normalized = raw.lower()
    round_match = re.fullmatch(r"(?:round[_-]?)?(\d+)", normalized)
    if round_match:
        round_id = int(round_match.group(1))
        if 1 <= round_id <= 4:
            round_path = TOOLHOP_SPLIT_ROOT / "rounds" / f"round_{round_id}.json"
            if round_path.exists():
                return str(round_path.resolve())
            return str(TOOLHOP_FINAL_TEST_PATH.resolve())
        raise ValueError(f"Unsupported ToolHop round selector: {raw}. Expected 1-4, round_1-round_4, or test.")

    if normalized in {"test", "final", "final_test", "final_blind", "final_blind_test"}:
        return str(TOOLHOP_FINAL_TEST_PATH.resolve())

    if normalized in {"dev", "online_dev"}:
        online_dev_path = TOOLHOP_SPLIT_ROOT / "toolhop_online_dev.json"
        if online_dev_path.exists():
            return str(online_dev_path.resolve())
        return str(TOOLHOP_FINAL_TEST_PATH.resolve())

    return raw

def _sanitize_name(value: Optional[str]) -> str:
    if not value:
        return "none"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")
    return safe or "none"

def _build_run_tag(
    planning_system: Optional[str],
    action_system: Optional[str],
    memory_provider: Optional[str],
    model: Optional[str] = None,
    model_backend: Optional[str] = None,
) -> str:
    plan = _sanitize_name(planning_system or "plan")
    action = _sanitize_name(action_system or planning_system or "action")
    mem = _sanitize_name(memory_provider or "nomem")
    model_part = _sanitize_name(model)
    backend_part = _sanitize_name(model_backend)
    return f"{plan}_{action}_{mem}_{backend_part}_{model_part}"

WEBWALKERQA_PROMPT_TEMPLATE = """You are tasked with answering a question that requires navigating through a website to find the information.

Question: {question}

Starting URL: {root_url}

Please:
1. Start from the provided root URL
2. Navigate through the website to find the information needed
3. Use web search and page crawling tools to explore the site
4. Provide a clear and accurate answer based on what you find

Important: You MUST begin by accessing {root_url}
"""

TOOLHOP_PROMPT_TEMPLATE = """You are solving a ToolHop question with structured tool calls.

Question: {question}

Important:
1. Use only the tools available in this environment for the current question.
2. ToolHop tools return useful information only when you choose the correct tool and pass accurate arguments.
3. Base your answer on tool observations rather than guessing.
4. When the answer is supported, call final_answer with the exact short answer only.
"""

API_BANK_PROMPT_TEMPLATE = """You are solving an API-Bank API request generation task with structured tool calls.

Use the dialogue context and API descriptions to identify the API request(s) that should be made next.

Important:
1. Call exactly the API tool(s) that match the required API request(s).
2. Use exact argument names and values from the task context.
3. Do not call tools that are not relevant to the next API request(s).
4. After the API tool call(s) are made, call final_answer with the request(s) in this format:
   API-Request: [ApiName(key1='value1', key2='value2'), OtherApi(key='value')]

Instruction:
{instruction}

Input:
{input_text}
"""

RESTBENCH_PROMPT_TEMPLATE = """You are solving a RestBench endpoint-selection task for the {dataset_name} API.

User request:
{query}

Available endpoints:
{available_endpoints}

Important:
1. Use the available REST endpoint tools to satisfy the request.
2. Endpoint tools are named after HTTP method and path, such as get_search_movie.
3. Prefer calling the specific endpoint tools directly. You may use get_api_details if you need schema details.
4. When all necessary endpoint calls have been made, call final_answer with a concise list of endpoint names you used.
"""

BENCHMARKS = {
    "webwalkerqa": {
        "path": _resolve_existing_path(
            str(DATA_ROOT / "webwalkerqa" / "webwalkerqa_subset_170.jsonl"),
            os.path.join(SCRIPT_DIR, "data", "webwalkerqa", "webwalkerqa_subset_170.jsonl"),
            os.path.join(SCRIPT_DIR, "FlashOAgents", "data", "webwalkerqa_subset_170.jsonl"),
        ),
        "type": "webwalkerqa",
        "name": "WebWalkerQA",
        "has_levels": True,
        "level_key": "difficulty",
    },
    "webwalkerqa_full": {
        "path": _resolve_existing_path(
            str(DATA_ROOT / "webwalkerqa" / "webwalkerqa_main.jsonl"),
            os.path.join(SCRIPT_DIR, "data", "webwalkerqa", "webwalkerqa_main.jsonl"),
            os.path.join(SCRIPT_DIR, "FlashOAgents", "data", "webwalkerqa_main.jsonl"),
        ),
        "type": "webwalkerqa",
        "name": "WebWalkerQA",
        "has_levels": True,
        "level_key": "difficulty",
    },
    "toolhop": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "toolhop" / "data" / "toolhop_final_blind_test.json"),
            str(EVAL_BENCH_ROOT / "toolhop" / "data" / "ToolHop.json"),
            str(WORKSPACE_ROOT / "Bench" / "ToolHop" / "ToolHop.json"),
            str(DATA_ROOT / "toolhop" / "ToolHop.json"),
            os.path.join(SCRIPT_DIR, "data", "toolhop", "ToolHop.json"),
            str(WORKSPACE_ROOT / "related work" / "DeepAgent" / "data" / "ToolHop" / "ToolHop.json"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "ToolHop" / "ToolHop.json"),
        ),
        "type": "toolhop",
        "name": "ToolHop",
        "has_levels": False,
        "level_key": "difficulty",
    },
    "mixeddata": {
        "path": _resolve_existing_path(
            str(DATA_ROOT / "mixeddata" / "all.jsonl"),
            os.path.join(SCRIPT_DIR, "data", "mixeddata", "all.jsonl"),
        ),
        "type": "mixeddata",
        "name": "MixedData",
        "has_levels": True,
        "level_key": "mixed_benchmark",
    },
    "mixeddata_train": {
        "path": _resolve_existing_path(
            str(DATA_ROOT / "mixeddata" / "train.jsonl"),
            os.path.join(SCRIPT_DIR, "data", "mixeddata", "train.jsonl"),
        ),
        "type": "mixeddata",
        "name": "MixedData Train",
        "has_levels": True,
        "level_key": "mixed_benchmark",
    },
    "mixeddata_val": {
        "path": _resolve_existing_path(
            str(DATA_ROOT / "mixeddata" / "val.jsonl"),
            os.path.join(SCRIPT_DIR, "data", "mixeddata", "val.jsonl"),
        ),
        "type": "mixeddata",
        "name": "MixedData Val",
        "has_levels": True,
        "level_key": "mixed_benchmark",
    },
    "searchqa": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "qa" / "data" / "all.jsonl"),
        ),
        "type": "mixeddata",
        "name": "SearchQA Offline",
        "has_levels": True,
        "level_key": "mixed_benchmark",
    },
    "searchqa_nq": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "qa" / "data" / "nq.jsonl"),
        ),
        "type": "mixeddata",
        "name": "SearchQA NQ",
        "has_levels": True,
        "level_key": "mixed_benchmark",
    },
    "searchqa_hotpotqa": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "qa" / "data" / "hotpotqa.jsonl"),
        ),
        "type": "mixeddata",
        "name": "SearchQA HotpotQA",
        "has_levels": True,
        "level_key": "mixed_benchmark",
    },
    "searchqa_2wikimultihopqa": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "qa" / "data" / "2wikimultihopqa.jsonl"),
        ),
        "type": "mixeddata",
        "name": "SearchQA 2WikiMultiHopQA",
        "has_levels": True,
        "level_key": "mixed_benchmark",
    },
    "searchqa_musique": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "qa" / "data" / "musique.jsonl"),
        ),
        "type": "mixeddata",
        "name": "SearchQA MuSiQue",
        "has_levels": True,
        "level_key": "mixed_benchmark",
    },
    "taubench": {
        "path": "taubench://retail/dev",
        "type": "taubench",
        "name": "tau-bench",
        "has_levels": True,
        "level_key": "taubench_domain",
        "taubench_domain": "retail",
        "taubench_split": "dev",
    },
    "taubench_retail_dev": {
        "path": "taubench://retail/dev",
        "type": "taubench",
        "name": "tau-bench retail dev",
        "has_levels": True,
        "level_key": "taubench_domain",
        "taubench_domain": "retail",
        "taubench_split": "dev",
    },
    "taubench_retail_test": {
        "path": "taubench://retail/test",
        "type": "taubench",
        "name": "tau-bench retail test",
        "has_levels": True,
        "level_key": "taubench_domain",
        "taubench_domain": "retail",
        "taubench_split": "test",
    },
    "taubench_retail_train": {
        "path": "taubench://retail/train",
        "type": "taubench",
        "name": "tau-bench retail train",
        "has_levels": True,
        "level_key": "taubench_domain",
        "taubench_domain": "retail",
        "taubench_split": "train",
    },
    "taubench_airline_test": {
        "path": "taubench://airline/test",
        "type": "taubench",
        "name": "tau-bench airline test",
        "has_levels": True,
        "level_key": "taubench_domain",
        "taubench_domain": "airline",
        "taubench_split": "test",
    },
    "restbench_spotify": {
        "path": _resolve_existing_path(
            str(WORKSPACE_ROOT / "Bench" / "RestBench" / "datasets" / "spotify.json"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "RestBench" / "datasets" / "spotify.json"),
        ),
        "type": "restbench",
        "name": "RestBench-Spotify",
        "has_levels": False,
        "level_key": "difficulty",
        "restbench_dataset": "spotify",
        "restbench_spec_path": _resolve_existing_path(
            str(WORKSPACE_ROOT / "Bench" / "RestBench" / "specs" / "spotify_oas.json"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "RestBench" / "specs" / "spotify_oas.json"),
        ),
    },
    "restbench_tmdb": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "tmdb" / "datasets" / "tmdb.json"),
            str(WORKSPACE_ROOT / "Bench" / "RestBench" / "datasets" / "tmdb.json"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "RestBench" / "datasets" / "tmdb.json"),
        ),
        "type": "restbench",
        "name": "RestBench-TMDB",
        "has_levels": False,
        "level_key": "difficulty",
        "restbench_dataset": "tmdb",
        "restbench_spec_path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "tmdb" / "specs" / "tmdb_oas.json"),
            str(WORKSPACE_ROOT / "Bench" / "RestBench" / "specs" / "tmdb_oas.json"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "RestBench" / "specs" / "tmdb_oas.json"),
        ),
    },
    "api_bank_lv1_test": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "api-bank" / "test-data" / "level-1-api.json"),
            str(WORKSPACE_ROOT / "Bench" / "API-Bank" / "test-data" / "level-1-api.json"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "API-Bank" / "test-data" / "level-1-api.json"),
            str(WORKSPACE_ROOT / "CODE" / "API-Bank" / "test-data" / "level-1-api.json"),
            str(WORKSPACE_ROOT / "related work" / "DeepAgent" / "data" / "API-Bank" / "test-data" / "level-1-api.json"),
        ),
        "type": "api_bank",
        "name": "API-Bank",
        "has_levels": True,
        "level_key": "api_bank_level",
        "api_bank_level": "lv1",
        "api_bank_split": "test",
    },
    "api_bank": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "api-bank" / "lv1-lv2-samples" / "level-1-given-desc-e2e"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "API-Bank" / "lv1-lv2-samples" / "level-1-given-desc-e2e"),
            str(WORKSPACE_ROOT / "Bench" / "API-Bank" / "lv1-lv2-samples" / "level-1-given-desc-e2e"),
        ),
        "type": "api_bank",
        "name": "API-Bank",
        "has_levels": True,
        "level_key": "api_bank_level",
        "api_bank_level": "deepagent_lv1",
        "api_bank_split": "deepagent_default",
    },
    "api_bank_lv2_test": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "api-bank" / "test-data" / "level-2-api.json"),
            str(WORKSPACE_ROOT / "Bench" / "API-Bank" / "test-data" / "level-2-api.json"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "API-Bank" / "test-data" / "level-2-api.json"),
            str(WORKSPACE_ROOT / "CODE" / "API-Bank" / "test-data" / "level-2-api.json"),
            str(WORKSPACE_ROOT / "related work" / "DeepAgent" / "data" / "API-Bank" / "test-data" / "level-2-api.json"),
        ),
        "type": "api_bank",
        "name": "API-Bank",
        "has_levels": True,
        "level_key": "api_bank_level",
        "api_bank_level": "lv2",
        "api_bank_split": "test",
    },
    "api_bank_lv3_test": {
        "path": _resolve_existing_path(
            str(EVAL_BENCH_ROOT / "api-bank" / "test-data" / "level-3-batch-inf.json"),
            str(WORKSPACE_ROOT / "Bench" / "API-Bank" / "test-data" / "level-3-batch-inf.json"),
            str(WORKSPACE_ROOT / "DeepAgent" / "data" / "API-Bank" / "test-data" / "level-3-batch-inf.json"),
            str(WORKSPACE_ROOT / "CODE" / "API-Bank" / "test-data" / "level-3-batch-inf.json"),
            str(WORKSPACE_ROOT / "related work" / "DeepAgent" / "data" / "API-Bank" / "test-data" / "level-3-batch-inf.json"),
        ),
        "type": "api_bank",
        "name": "API-Bank",
        "has_levels": True,
        "level_key": "api_bank_level",
        "api_bank_level": "lv3",
        "api_bank_split": "test",
    },
    "api_bank_lv1_train": {
        "path": _resolve_existing_path(
            str(WORKSPACE_ROOT / "CODE" / "API-Bank" / "training-data" / "lv1-api-train.json"),
        ),
        "type": "api_bank",
        "name": "API-Bank",
        "has_levels": True,
        "level_key": "api_bank_level",
        "api_bank_level": "lv1",
        "api_bank_split": "train",
    },
    "api_bank_lv2_train": {
        "path": _resolve_existing_path(
            str(WORKSPACE_ROOT / "CODE" / "API-Bank" / "training-data" / "lv2-api-train.json"),
        ),
        "type": "api_bank",
        "name": "API-Bank",
        "has_levels": True,
        "level_key": "api_bank_level",
        "api_bank_level": "lv2",
        "api_bank_split": "train",
    },
    "api_bank_lv3_train": {
        "path": _resolve_existing_path(
            str(WORKSPACE_ROOT / "CODE" / "API-Bank" / "training-data" / "lv3-api-train.json"),
        ),
        "type": "api_bank",
        "name": "API-Bank",
        "has_levels": True,
        "level_key": "api_bank_level",
        "api_bank_level": "lv3",
        "api_bank_split": "train",
    },
}

def _serialize_memory(agent: Any) -> list[dict[str, Any]]:
    underlying_agent = getattr(agent, "agent_fn", agent)
    rows: list[dict[str, Any]] = []
    for step in getattr(getattr(underlying_agent, "memory", None), "steps", []):
        if hasattr(step, "dict"):
            rows.append(step.dict())
        else:
            rows.append({"repr": str(step)})
    return rows


def _extract_structured_trajectory(agent: Any, result: Any = None) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        trajectory = result.get("agent_trajectory")
        if isinstance(trajectory, list):
            return trajectory

    if hasattr(agent, "capture_trajectory"):
        try:
            payload = agent.capture_trajectory()
            trajectory = payload.get("agent_trajectory")
            if isinstance(trajectory, list):
                return trajectory
        except Exception:
            pass

    underlying_agent = getattr(agent, "agent_fn", agent)
    if hasattr(underlying_agent, "capture_trajectory"):
        try:
            payload = underlying_agent.capture_trajectory()
            trajectory = payload.get("agent_trajectory")
            if isinstance(trajectory, list):
                return trajectory
        except Exception:
            pass

    return _serialize_memory(agent)


def _normalize_pred_answer(pred_answer):
    if isinstance(pred_answer, dict):
        for key in ("answer", "final_answer", "response", "result"):
            if key in pred_answer:
                return pred_answer.get(key)
        return json.dumps(pred_answer, ensure_ascii=False)
    return pred_answer


def _extract_judgement(text):
    if not text:
        return None
    try:
        data = json.loads(text)
        judgement = data.get("judgement")
        if isinstance(judgement, str):
            return judgement.strip().lower()
    except Exception:
        pass

    match = re.search(r'"?judgement"?\s*:\s*"?(correct|incorrect)"?', text, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    if "correct" in text.lower():
        return "correct"
    if "incorrect" in text.lower():
        return "incorrect"
    return None


def judge_answer(question, golden_answer, pred_answer, judge_llm_config: Optional[LLMConfig]):
    if judge_llm_config is None:
        return {"judgement": None, "raw": None, "error": "judge_model_not_set"}

    pred_text = _normalize_pred_answer(pred_answer)
    if pred_text is None or (isinstance(pred_text, str) and pred_text.strip() == ""):
        return {"judgement": "incorrect", "raw": None, "error": "empty_prediction"}

    prompt = f"""You are a general AI assistant. Based on the [Correct Answer] provided below, determine whether the [Response] to the [Original Question] is correct.

[Original Question]: {question}

[Correct Answer]: {golden_answer}

[Response]: {pred_text}

Your judgment must follow this standard:
- Focus only on whether there are substantial differences between the [Response] and the [Correct Answer]
- Do not comment on the background of the question
- Do not attempt to resolve the problem again
- Only focus on judging whether the answers are consistent
- If the [Response] is consistent with the [Correct Answer], or within an acceptable small margin of error for numerical questions, judge as "correct"
- Otherwise (i.e., in cases of any inconsistency, ambiguity, non-equivalence, or incorrectly extracted answer), judge as "incorrect"

Output JSON format:
{{
  "judgement": "correct" or "incorrect"
}}"""

    try:
        model = create_chat_model(
            judge_llm_config,
            max_completion_tokens=64,
        )
        response = model(
            [
                {
                    "role": "system",
                    "content": "You are a fair judge. Focus on answer correctness, not formatting."
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=64,
        )
        content = getattr(response, "content", None)
        raw = content.strip() if isinstance(content, str) else str(content or "")
        judgement = _extract_judgement(raw)
        if judgement not in ("correct", "incorrect"):
            judgement = "incorrect"
        return {"judgement": judgement, "raw": raw, "error": None}
    except Exception as e:
        logger.error(f"Judge failed: {e}")
        return {"judgement": "error", "raw": None, "error": str(e)}


def _stringify_answer(value: Any) -> str:
    normalized = _normalize_pred_answer(value)
    if normalized is None:
        return ""
    if isinstance(normalized, str):
        return normalized.strip()
    return str(normalized).strip()


def _collect_trajectory_observations(trajectory: list[dict[str, Any]] | None) -> list[str]:
    observations: list[str] = []
    for step in trajectory or []:
        if not isinstance(step, dict):
            continue
        for key in ("obs", "observations", "observation"):
            value = step.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                observations.append(text)
    return observations


def evaluate_toolhop_answer(
    item: dict[str, Any] | None,
    pred_answer: Any,
    trajectory: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    return evaluate_toolhop_item(
        item=item,
        pred_answer=pred_answer,
        trajectory=trajectory,
    )


def evaluate_prediction(
    *,
    dataset_type: str,
    item: dict[str, Any] | None,
    question: str,
    golden_answer: str,
    pred_answer: Any,
    trajectory: list[dict[str, Any]] | None,
    judge_llm_config: Optional[LLMConfig],
) -> dict[str, Any]:
    if dataset_type == "toolhop":
        return evaluate_toolhop_answer(item, pred_answer, trajectory)
    if dataset_type == "taubench":
        return evaluate_taubench_item(
            item=item,
            pred_answer=pred_answer,
            trajectory=trajectory,
        )
    if dataset_type == "api_bank":
        return evaluate_api_bank_item(
            item=item,
            pred_answer=pred_answer,
            trajectory=trajectory,
        )
    if dataset_type == "restbench":
        return evaluate_restbench_item(
            item=item,
            pred_answer=pred_answer,
            trajectory=trajectory,
        )
    if dataset_type == "mixeddata":
        return evaluate_mixeddata_item(
            item=item,
            pred_answer=pred_answer,
            trajectory=trajectory,
        )
    return judge_answer(
        question=question,
        golden_answer=golden_answer,
        pred_answer=pred_answer,
        judge_llm_config=judge_llm_config,
    )


def _metric_is_positive(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return float(value) > 0.0

    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "on", "correct", "success", "succeeded"}:
        return True
    if text in {"", "false", "no", "n", "off", "incorrect", "error", "none", "null"}:
        return False
    try:
        return float(text) > 0.0
    except ValueError:
        return False


def _metric_is_complete(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    try:
        return float(value) >= 1.0
    except (TypeError, ValueError):
        return False


def eval_result_is_success(eval_result: dict[str, Any], dataset_type: str) -> bool:
    judgement = str(eval_result.get("judgement", "")).strip().lower()
    if judgement == "correct":
        return True

    success_fields = (
        "answer_correct",
        "api_success_rate",
        "api_call_correct",
        "restbench_success",
        "taubench_done",
        "webshop_done",
        "alfworld_done",
    )
    if any(_metric_is_positive(eval_result.get(field)) for field in success_fields):
        return True

    if dataset_type == "mixeddata":
        benchmark = str(eval_result.get("mixed_benchmark", "")).strip().lower()
        if "envscaler" in benchmark and _metric_is_complete(eval_result.get("envscaler_score")):
            return True
        if _metric_is_complete(eval_result.get("score")):
            return True

    return False


def append_toolhop_report(results: list[dict[str, Any]], report_path: str) -> None:
    overall_metrics = summarize_toolhop_results(results)
    if overall_metrics.get("evaluated_instance", 0) == 0:
        return

    with open(report_path, "a", encoding="utf-8") as report_file:
        report_file.write("ToolHop Metrics\n")
        report_file.write("-" * 80 + "\n")
        report_file.write(f"Has Valid Answer: {overall_metrics['has_valid_answer'] * 100:.2f}%\n")
        report_file.write(f"Answer Correct: {overall_metrics['answer_correct'] * 100:.2f}%\n")
        report_file.write(f"Path Score: {overall_metrics['path_score'] * 100:.2f}%\n")
        report_file.write(f"Average Actions: {overall_metrics['average_actions']:.2f}\n")
        report_file.write(f"Average Tool Calls: {overall_metrics['average_tool_calls']:.2f}\n")
        report_file.write("=" * 80 + "\n")

    logger.info(
        "ToolHop metrics | "
        f"has_valid_answer={overall_metrics['has_valid_answer']:.3f} | "
        f"answer_correct={overall_metrics['answer_correct']:.3f} | "
        f"path_score={overall_metrics['path_score']:.3f} | "
        f"average_actions={overall_metrics['average_actions']:.2f}"
    )


def append_api_bank_report(results: list[dict[str, Any]], report_path: str) -> None:
    overall_metrics = summarize_api_bank_results(results)
    if overall_metrics.get("evaluated_instance", 0) == 0:
        return

    with open(report_path, "a", encoding="utf-8") as report_file:
        report_file.write("API-Bank Metrics\n")
        report_file.write("-" * 80 + "\n")
        report_file.write(f"Has Valid Answer: {overall_metrics['has_valid_answer'] * 100:.2f}%\n")
        report_file.write(f"API Accuracy: {overall_metrics['api_accuracy'] * 100:.2f}%\n")
        report_file.write(f"Path Score: {overall_metrics['path_score'] * 100:.2f}%\n")
        report_file.write(f"Success Rate: {overall_metrics['success_rate'] * 100:.2f}%\n")
        report_file.write(f"API Name Accuracy: {overall_metrics['api_name_accuracy'] * 100:.2f}%\n")
        report_file.write(f"API Args Accuracy: {overall_metrics['api_args_accuracy'] * 100:.2f}%\n")
        report_file.write(f"API Call Accuracy: {overall_metrics['api_call_accuracy'] * 100:.2f}%\n")
        report_file.write(f"Average Tool Calls: {overall_metrics['average_tool_calls']:.2f}\n")
        report_file.write(f"Correct API Calls: {overall_metrics['correct_api_calls']}/{overall_metrics['total_api_calls']}\n")
        report_file.write("=" * 80 + "\n")

    logger.info(
        "API-Bank metrics | "
        f"api_accuracy={overall_metrics['api_accuracy']:.3f} | "
        f"path_score={overall_metrics['path_score']:.3f} | "
        f"success_rate={overall_metrics['success_rate']:.3f} | "
        f"api_name_accuracy={overall_metrics['api_name_accuracy']:.3f} | "
        f"api_args_accuracy={overall_metrics['api_args_accuracy']:.3f} | "
        f"api_call_accuracy={overall_metrics['api_call_accuracy']:.3f} | "
        f"average_tool_calls={overall_metrics['average_tool_calls']:.2f}"
    )


def append_restbench_report(results: list[dict[str, Any]], report_path: str) -> None:
    overall_metrics = summarize_restbench_results(results)
    if overall_metrics.get("evaluated_instance", 0) == 0:
        return

    with open(report_path, "a", encoding="utf-8") as report_file:
        report_file.write("RestBench Metrics\n")
        report_file.write("-" * 80 + "\n")
        report_file.write(f"Path Rate: {overall_metrics['path_rate'] * 100:.2f}%\n")
        report_file.write(f"Success Rate: {overall_metrics['success_rate'] * 100:.2f}%\n")
        report_file.write(f"Has Valid Answer: {overall_metrics['has_valid_answer'] * 100:.2f}%\n")
        report_file.write(f"Average Tool Calls: {overall_metrics['average_tool_calls']:.2f}\n")
        report_file.write("=" * 80 + "\n")

    logger.info(
        "RestBench metrics | "
        f"path_rate={overall_metrics['path_rate']:.3f} | "
        f"success_rate={overall_metrics['success_rate']:.3f} | "
        f"average_tool_calls={overall_metrics['average_tool_calls']:.2f}"
    )


def append_taubench_report(results: list[dict[str, Any]], report_path: str) -> None:
    overall_metrics = summarize_taubench_results(results)
    if overall_metrics.get("evaluated_instance", 0) == 0:
        return

    with open(report_path, "a", encoding="utf-8") as report_file:
        report_file.write("tau-bench Metrics\n")
        report_file.write("-" * 80 + "\n")
        report_file.write(f"Average Reward: {overall_metrics['average_reward']:.3f}\n")
        report_file.write(f"Success Rate: {overall_metrics['success_rate'] * 100:.2f}%\n")
        report_file.write(f"Average Tool Calls: {overall_metrics['average_tool_calls']:.2f}\n")
        pass_hat_ks = overall_metrics.get("pass_hat_ks") or {}
        if pass_hat_ks:
            report_file.write("Pass^k:\n")
            for key in sorted(pass_hat_ks, key=lambda item: int(item)):
                report_file.write(f"  k={key}: {pass_hat_ks[key]:.3f}\n")
        report_file.write("=" * 80 + "\n")

    logger.info(
        "tau-bench metrics | "
        f"average_reward={overall_metrics['average_reward']:.3f} | "
        f"success_rate={overall_metrics['success_rate']:.3f} | "
        f"average_tool_calls={overall_metrics['average_tool_calls']:.2f}"
    )


def parse_task_indices(indices_str):
    if not indices_str:
        return None

    indices = set()
    parts = indices_str.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            start, end = int(start.strip()), int(end.strip())
            if start > end:
                raise ValueError(f"Invalid range: {part} (start > end)")
            indices.update(range(start, end + 1))
        else:
            indices.add(int(part))
    return indices


def load_memory_provider(
    memory_type_str,
    model=None,
    write_only=False,
    harness_name=None,
    storage_root=None,
):
    if not memory_type_str:
        return None

    try:
        provider = harness_runtime.build_memory_provider(
            memory_system=memory_type_str,
            base_dir=Path(SCRIPT_DIR),
            model=model,
            write_only=write_only,
            storage_namespace=harness_name,
            storage_root=Path(storage_root).expanduser().resolve()
            if storage_root
            else None,
        )
        logger.info(
            f"Memory provider loaded: {memory_type_str}"
            + (" (write-only)" if write_only else "")
        )
        return provider
    except Exception as e:
        logger.error(f"Failed to load memory provider {memory_type_str}: {e}")
        logger.error(traceback.format_exc())
        return None


def resolve_memory_provider_name(
    memory_type_str: Optional[str],
    harness_name: Optional[str],
) -> Optional[str]:
    if memory_type_str:
        if str(memory_type_str).strip().lower() in {"none", "off", "disable", "disabled", "null"}:
            return None
        return memory_type_str
    if not harness_name:
        return None

    try:
        harness_module = harness_runtime.import_harness_module(harness_name)
    except Exception as exc:
        logger.warning(
            "Failed to import harness '%s' when resolving default memory system: %s",
            harness_name,
            exc,
        )
        return None

    default_memory_system = getattr(harness_module, "DEFAULT_MEMORY_SYSTEM", None)
    if default_memory_system:
        resolved = str(default_memory_system).strip()
        if resolved:
            logger.info(
                "No --memory_provider specified; using harness default memory system '%s' for harness '%s'.",
                resolved,
                harness_name,
            )
            return resolved
    return None


def backfill_memory_from_completed_results(
    completed_items: list[dict[str, Any]],
    memory_provider_str: Optional[str],
    memory_storage_dir: Optional[str],
    dataset_type: str,
    harness_name: Optional[str],
) -> int:
    if not completed_items or not memory_provider_str:
        return 0

    memory_provider = load_memory_provider(
        memory_provider_str,
        write_only=True,
        harness_name=harness_name,
        storage_root=memory_storage_dir,
    )
    if memory_provider is None:
        return 0

    try:
        memory_types = harness_runtime.get_memory_types_module(
            memory_provider=memory_provider,
            harness_name=harness_name,
        )
    except Exception as exc:
        logger.warning("Memory backfill skipped: failed to load memory types: %s", exc)
        return 0

    TrajectoryData = memory_types.TrajectoryData
    ingested = 0
    skipped = 0
    for item in completed_items:
        if not isinstance(item, dict):
            continue
        if not eval_result_is_success(item, dataset_type):
            continue
        trajectory = item.get("agent_trajectory") or item.get("trajectory") or []
        if not trajectory:
            skipped += 1
            continue
        full_query = item.get("enhanced_question") or item.get("question") or ""
        trajectory_data = TrajectoryData(
            query=item.get("question") or full_query,
            trajectory=trajectory,
            result=item.get("agent_result") or item.get("pred_answer") or item.get("answer"),
            metadata={
                "item_index": item.get("item_index"),
                "status": item.get("status", "success"),
                "is_correct": True,
                "full_query": full_query,
                "backfilled_from_outfile": True,
            },
        )
        try:
            success, msg = memory_provider.take_in_memory(trajectory_data)
        except Exception as exc:
            logger.warning("Memory backfill failed for item %s: %s", item.get("item_index"), exc)
            skipped += 1
            continue
        if success:
            ingested += 1
        else:
            skipped += 1
            logger.debug("Memory backfill skipped for item %s: %s", item.get("item_index"), msg)

    if ingested or skipped:
        logger.info(
            "Memory backfill from existing outfile complete: ingested=%s skipped=%s",
            ingested,
            skipped,
        )
    return ingested


def load_data(infile):
    if str(infile).startswith("taubench://"):
        from runtime.taubench.runtime import load_taubench_items, parse_taubench_uri

        domain, split = parse_taubench_uri(str(infile))
        data = load_taubench_items(domain, split)
    elif os.path.isdir(infile):
        from runtime.api_bank.runtime import load_deepagent_api_bank_level1

        data = load_deepagent_api_bank_level1(infile)
    elif infile.lower().endswith('.json'):
        with open(infile, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = read_jsonl(infile)

    data_out = []
    for idx, item in enumerate(data):
        if isinstance(item, dict):
            item = dict(item)
            item["_global_index"] = idx + 1
        data_out.append(item)
    return data_out


def get_resume_key(item: dict[str, Any] | None) -> str:
    keys = get_resume_keys(item)
    return next(iter(keys), "")


def get_resume_keys(item: dict[str, Any] | None) -> set[str]:
    if not isinstance(item, dict):
        return set()
    keys: set[str] = set()
    if item.get("item_index") is not None:
        keys.add(f"idx:{item.get('item_index')}")
    if item.get("_global_index") is not None:
        keys.add(f"idx:{item.get('_global_index')}")
    for key in ("question", "Question", "query", "input", "enhanced_question"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            keys.add(f"text:{value.strip()}")
    if not keys:
        keys.add(f"json:{json.dumps(item, ensure_ascii=False, sort_keys=True)}")
    return keys


def resolve_benchmark(args):
    if not args.benchmark:
        return None
    name = args.benchmark.lower()
    if name not in BENCHMARKS:
        available = ", ".join(sorted(BENCHMARKS.keys()))
        raise ValueError(f"Unknown benchmark: {name}. Available: {available}")
    cfg = dict(BENCHMARKS[name])
    if args.infile:
        cfg["path"] = resolve_toolhop_infile(args.infile) if name == "toolhop" else args.infile
    if cfg.get("type") == "taubench":
        domain = getattr(args, "taubench_env", None) or cfg.get("taubench_domain", "retail")
        split = getattr(args, "taubench_split", None) or cfg.get("taubench_split", "dev")
        from runtime.taubench.runtime import _validate_domain_split

        domain, split = _validate_domain_split(domain, split)
        cfg["taubench_domain"] = domain
        cfg["taubench_split"] = split
        if not args.infile:
            cfg["path"] = f"taubench://{domain}/{split}"
        cfg["name"] = f"tau-bench {domain} {split}"
    cfg["benchmark"] = name
    return cfg


def token_counter_from_agent(agent):
    try:
        steps = agent.agent_fn.memory.steps
    except Exception:
        steps = []
    return TokenCounter.from_memory_steps(steps)


def build_task_fields(item, dataset_type, *, toolhop_mode: str = TOOLHOP_MODE_CLOSED):
    question = item.get("question", "") if isinstance(item, dict) else ""
    golden_answer = item.get("answer", "") if isinstance(item, dict) else ""
    enhanced_question = question
    extra = {}

    if dataset_type == "webwalkerqa":
        root_url = item.get("root_url", "") if isinstance(item, dict) else ""
        info = item.get("info", {}) if isinstance(item, dict) else {}
        enhanced_question = WEBWALKERQA_PROMPT_TEMPLATE.format(
            question=question,
            root_url=root_url,
        )
        extra = {
            "root_url": root_url,
            "domain": info.get("domain", ""),
            "difficulty": info.get("difficulty_level", ""),
            "language": info.get("lang", "en"),
            "type": info.get("type", ""),
            "source_websites": info.get("source_website", []),
            "golden_path": info.get("golden_path", []),
        }
    elif dataset_type == "toolhop":
        enhanced_question = TOOLHOP_PROMPT_TEMPLATE.format(question=question)
        extra = {
            "toolhop_mode": toolhop_mode,
            "answer_type": item.get("answer_type", "") if isinstance(item, dict) else "",
            "previous_answer_type": item.get("previous_answer_type", "") if isinstance(item, dict) else "",
            "tool_count": len((item.get("tools", {}) if isinstance(item, dict) else {}) or {}),
        }
    elif dataset_type == "taubench":
        from runtime.taubench.runtime import build_taubench_prompt, prepare_taubench_item

        session = prepare_taubench_item(item if isinstance(item, dict) else {})
        question = f"tau-bench {session.domain}/{session.split} task {session.task_id}"
        golden_answer = ""
        enhanced_question = build_taubench_prompt(item if isinstance(item, dict) else {})
        extra = {
            "taubench_domain": session.domain,
            "taubench_split": session.split,
            "taubench_task_id": session.task_id,
            "taubench_user_model": session.user_model,
            "taubench_user_provider": session.user_provider,
            "taubench_user_strategy": session.user_strategy,
            "tool_count": len(getattr(session.env, "tools_info", []) or []) + 1,
        }
    elif dataset_type == "mixeddata":
        question = extract_mixed_task(item if isinstance(item, dict) else {})
        golden_answer = extract_mixed_ground_truth(item if isinstance(item, dict) else {})
        enhanced_question = question
        extra = {
            "mixed_benchmark": get_mixed_benchmark(item if isinstance(item, dict) else {}),
            "data_source": item.get("data_source", "") if isinstance(item, dict) else "",
            "ability": item.get("ability", "") if isinstance(item, dict) else "",
            "tool_count": len(item.get("tool_schemas", []) or []) if isinstance(item, dict) else 0,
        }
    elif dataset_type == "api_bank":
        from runtime.api_bank.runtime import (
            extract_api_descriptions,
            format_deepagent_dialogue,
            format_expected_api_requests,
        )

        if isinstance(item, dict) and item.get("chat_history"):
            question = format_deepagent_dialogue(item.get("chat_history") or [])
            tool_specs = extract_api_descriptions(item)
            api_descriptions = "\n".join(json.dumps(spec, ensure_ascii=False) for spec in tool_specs)
            instruction = (
                "Generate API request(s) based on the previous dialogue context. "
                "Use dates, times, tokens, and other values exactly as provided by the dialogue or tool observations."
            )
            input_text = (
                f"{question}\n\n"
                f"API descriptions:\n{api_descriptions}\n\n"
                "Generate API Request:"
            )
            golden_answer = format_expected_api_requests(item.get("api_calls") or [])
        else:
            instruction = item.get("instruction", "") if isinstance(item, dict) else ""
            input_text = item.get("input", "") if isinstance(item, dict) else ""
            question = input_text.strip()
            golden_answer = (
                item.get("expected_output")
                if isinstance(item, dict) and item.get("expected_output") is not None
                else item.get("output", "") if isinstance(item, dict) else ""
            )
        enhanced_question = API_BANK_PROMPT_TEMPLATE.format(
            instruction=instruction,
            input_text=input_text,
        )
        extra = {
            "api_bank_level": item.get("_api_bank_level", "") if isinstance(item, dict) else "",
            "api_bank_split": item.get("_api_bank_split", "") if isinstance(item, dict) else "",
            "tool_count": len(extract_api_descriptions(item if isinstance(item, dict) else {})),
        }
    elif dataset_type == "restbench":
        query = item.get("query", "") if isinstance(item, dict) else ""
        solution = item.get("solution", []) if isinstance(item, dict) else []
        dataset_name = item.get("_restbench_dataset", "restbench") if isinstance(item, dict) else "restbench"
        spec_path = item.get("_restbench_spec_path", "") if isinstance(item, dict) else ""
        available_endpoints = ""
        if spec_path:
            try:
                from runtime.restbench.runtime import extract_restbench_endpoints

                available_endpoints = "\n".join(
                    f"{endpoint.get('endpoint_name')}: {endpoint.get('description')}"
                    for endpoint in extract_restbench_endpoints(spec_path)
                )
            except Exception:
                available_endpoints = ""
        question = query
        golden_answer = ", ".join(str(endpoint) for endpoint in solution) if isinstance(solution, list) else str(solution)
        enhanced_question = RESTBENCH_PROMPT_TEMPLATE.format(
            dataset_name=dataset_name,
            query=query,
            available_endpoints=available_endpoints,
        )
        extra = {
            "restbench_dataset": dataset_name,
            "tool_count": item.get("_restbench_tool_count", 0) if isinstance(item, dict) else 0,
        }

    return question, golden_answer, enhanced_question, extra


def build_dataset_agent_kwargs(
    item: dict[str, Any] | None,
    dataset_type: str,
    *,
    toolhop_mode: str = TOOLHOP_MODE_CLOSED,
) -> dict[str, Any]:
    if dataset_type == "toolhop":
        return {
            "toolhop_mode": toolhop_mode,
            "toolhop_sample": item,
        }
    if dataset_type == "taubench":
        return {
            "taubench_sample": item,
            "max_tool_calls_per_step": 1,
        }
    if dataset_type == "api_bank":
        return {
            "api_bank_sample": item,
        }
    if dataset_type == "restbench":
        return {
            "restbench_sample": item,
        }
    if dataset_type == "mixeddata":
        return {
            "mixed_sample": item,
        }
    return {}


def process_item(
    item,
    task_llm_config: LLMConfig,
    max_tokens,
    summary_interval,
    prompts_type,
    max_steps,
    planning_system,
    action_system,
    judge_llm_config: Optional[LLMConfig],
    memory_provider_str,
    memory_storage_dir,
    memory_write_only,
    dataset_type,
    harness_name,
    toolhop_mode,
):
    timer = TaskTimer()
    timer.start()

    item_index = item.get("_global_index") if isinstance(item, dict) else None
    question, golden_answer, enhanced_question, extra_fields = build_task_fields(
        item,
        dataset_type,
        toolhop_mode=toolhop_mode,
    )
    search_agent = None
    memory_provider = None

    try:
        task_model = create_chat_model(
            task_llm_config,
            custom_role_conversions={"tool-call": "assistant", "tool-response": "user"},
            max_tokens=max_tokens,
        )
        memory_provider = (
            load_memory_provider(
                memory_provider_str,
                task_model,
                write_only=memory_write_only,
                harness_name=harness_name,
                storage_root=memory_storage_dir,
            )
            if memory_provider_str
            else None
        )
        agent_kwargs = build_dataset_agent_kwargs(
            item,
            dataset_type,
            toolhop_mode=toolhop_mode,
        )

        search_agent = _get_core_agent_class()(
            task_model,
            summary_interval=summary_interval,
            prompts_type=prompts_type if prompts_type != "default" else None,
            max_steps=max_steps,
            planning_system=planning_system,
            action_system=action_system,
            memory_provider=memory_provider,
            bench_type=dataset_type,
            harness_name=harness_name,
            **agent_kwargs,
        )

        result = search_agent(enhanced_question)
        structured_trajectory = _extract_structured_trajectory(search_agent, result=result)

        try:
            agent_messages = search_agent.agent_fn.write_memory_to_messages()
            if agent_messages:
                agent_messages = agent_messages[1:]
        except Exception:
            agent_messages = []

        eval_result = evaluate_prediction(
            dataset_type=dataset_type,
            item=item,
            question=question,
            golden_answer=golden_answer,
            pred_answer=result.get("agent_result"),
            trajectory=structured_trajectory,
            judge_llm_config=judge_llm_config,
        )
        judgement = eval_result.get("judgement")
        is_correct = eval_result_is_success(eval_result, dataset_type)

        task_result = {
            "status": "success",
            "item_index": item_index,
            "question": question,
            "enhanced_question": enhanced_question,
            "golden_answer": golden_answer,
            "agent_result": result.get("agent_result"),
            "judgement": judgement,
            "model": task_llm_config.model,
            "model_backend": task_llm_config.backend,
            "judge_model": judge_llm_config.model if judge_llm_config else None,
            "judge_backend": judge_llm_config.backend if judge_llm_config else None,
            "judge_raw": eval_result.get("raw"),
            "agent_trajectory": structured_trajectory,
            "agent_messages": agent_messages,
            "pred_answer": eval_result.get("pred_answer"),
            "has_valid_answer": eval_result.get("has_valid_answer"),
            "answer_correct": eval_result.get("answer_correct"),
            "path_score": eval_result.get("path_score"),
            "solved_subtasks": eval_result.get("solved_subtasks"),
            "subtask_count": eval_result.get("subtask_count"),
            "toolhop_action_count": eval_result.get("action_count"),
            "tool_call_count": eval_result.get("tool_call_count"),
            "score": eval_result.get("score"),
            "taubench_done": eval_result.get("taubench_done"),
            "taubench_reward": eval_result.get("taubench_reward"),
            "taubench_domain": eval_result.get("taubench_domain"),
            "taubench_split": eval_result.get("taubench_split"),
            "taubench_task_id": eval_result.get("taubench_task_id"),
            "taubench_info": eval_result.get("taubench_info"),
            "taubench_events": eval_result.get("taubench_events"),
            "subem": eval_result.get("subem"),
            "used_search": eval_result.get("used_search"),
            "mixed_benchmark": eval_result.get("mixed_benchmark") or extra_fields.get("mixed_benchmark"),
            "mixed_error": eval_result.get("error"),
            "envscaler_score": eval_result.get("envscaler_score"),
            "envscaler_done": eval_result.get("envscaler_done"),
            "webshop_score": eval_result.get("webshop_score"),
            "webshop_done": eval_result.get("webshop_done"),
            "alfworld_score": eval_result.get("alfworld_score"),
            "alfworld_done": eval_result.get("alfworld_done"),
            "expected_api_call": eval_result.get("expected_api_call"),
            "expected_api_calls": eval_result.get("expected_api_calls"),
            "pred_api_calls": eval_result.get("pred_api_calls"),
            "matched_api_call": eval_result.get("matched_api_call"),
            "matched_api_calls": eval_result.get("matched_api_calls"),
            "api_name_correct": eval_result.get("api_name_correct"),
            "api_args_correct": eval_result.get("api_args_correct"),
            "api_call_correct": eval_result.get("api_call_correct"),
            "api_success_rate": eval_result.get("api_success_rate"),
            "gt_api_calls": eval_result.get("gt_api_calls"),
            "correct_api_calls": eval_result.get("correct_api_calls"),
            "restbench_path_rate": eval_result.get("restbench_path_rate"),
            "restbench_success": eval_result.get("restbench_success"),
            "restbench_correct_endpoint_count": eval_result.get("restbench_correct_endpoint_count"),
            "restbench_required_endpoint_count": eval_result.get("restbench_required_endpoint_count"),
            "restbench_required_endpoints": eval_result.get("restbench_required_endpoints"),
            "restbench_required_tool_names": eval_result.get("restbench_required_tool_names"),
            "restbench_used_tool_names": eval_result.get("restbench_used_tool_names"),
            **extra_fields,
        }

        if memory_provider:
            try:
                memory_types = harness_runtime.get_memory_types_module(
                    memory_provider=memory_provider,
                    harness_name=harness_name,
                )
                TrajectoryData = memory_types.TrajectoryData
                trajectory_data = TrajectoryData(
                    query=question,
                    trajectory=structured_trajectory,
                    result=result.get("agent_result"),
                    metadata={
                        "item_index": item_index,
                        "status": "success",
                        "is_correct": is_correct,
                        "full_query": enhanced_question,
                    }
                )
                success, msg = memory_provider.take_in_memory(trajectory_data)
                if success:
                    logger.debug(f"Memory ingested: {msg}")
                else:
                    logger.warning(f"Memory ingestion failed: {msg}")
            except Exception as e:
                logger.warning(f"take_in_memory failed: {e}")

        token_counter = token_counter_from_agent(search_agent)
        timer.stop()
        return enrich_result_with_metrics(task_result, timer, token_counter)

    except Exception as e:
        error_msg = traceback.format_exc()
        structured_trajectory = _extract_structured_trajectory(search_agent) if search_agent is not None else []
        try:
            agent_messages = search_agent.agent_fn.write_memory_to_messages() if search_agent is not None else []
            if agent_messages:
                agent_messages = agent_messages[1:]
        except Exception:
            agent_messages = []

        task_result = {
            "status": "error",
            "error": str(e),
            "error_traceback": error_msg,
            "item_index": item_index,
            "question": question,
            "enhanced_question": enhanced_question,
            "golden_answer": golden_answer,
            "agent_result": None,
            "judgement": None,
            "model": task_llm_config.model,
            "model_backend": task_llm_config.backend,
            "judge_model": judge_llm_config.model if judge_llm_config else None,
            "judge_backend": judge_llm_config.backend if judge_llm_config else None,
            "judge_raw": None,
            "agent_trajectory": structured_trajectory,
            "agent_messages": agent_messages,
            "pred_answer": None,
            "has_valid_answer": None,
            "answer_correct": None,
            "path_score": None,
            "solved_subtasks": None,
            "subtask_count": None,
            "toolhop_action_count": None,
            "tool_call_count": None,
            "score": None,
            "taubench_done": None,
            "taubench_reward": 0.0 if dataset_type == "taubench" else None,
            "taubench_domain": extra_fields.get("taubench_domain"),
            "taubench_split": extra_fields.get("taubench_split"),
            "taubench_task_id": extra_fields.get("taubench_task_id"),
            "taubench_info": None,
            "taubench_events": None,
            "subem": None,
            "used_search": None,
            "mixed_benchmark": extra_fields.get("mixed_benchmark"),
            "mixed_error": str(e),
            "envscaler_score": None,
            "envscaler_done": None,
            "webshop_score": None,
            "webshop_done": None,
            "alfworld_score": None,
            "alfworld_done": None,
            "expected_api_call": None,
            "expected_api_calls": None,
            "pred_api_calls": None,
            "matched_api_call": None,
            "matched_api_calls": None,
            "api_name_correct": None,
            "api_args_correct": None,
            "api_call_correct": None,
            "api_success_rate": None,
            "gt_api_calls": None,
            "correct_api_calls": None,
            "restbench_path_rate": None,
            "restbench_success": None,
            "restbench_correct_endpoint_count": None,
            "restbench_required_endpoint_count": None,
            "restbench_required_endpoints": None,
            "restbench_required_tool_names": None,
            "restbench_used_tool_names": None,
            **extra_fields,
        }

        if memory_provider:
            try:
                memory_types = harness_runtime.get_memory_types_module(
                    memory_provider=memory_provider,
                    harness_name=harness_name,
                )
                TrajectoryData = memory_types.TrajectoryData
                trajectory_data = TrajectoryData(
                    query=question,
                    trajectory=structured_trajectory,
                    result=None,
                    metadata={
                        "item_index": item_index,
                        "status": "error",
                        "is_correct": False,
                        "full_query": enhanced_question,
                    }
                )
                success, msg = memory_provider.take_in_memory(trajectory_data)
                if success:
                    logger.debug(f"Memory ingested (error case): {msg}")
                else:
                    logger.warning(f"Memory ingestion failed (error case): {msg}")
            except Exception as e:
                logger.warning(f"take_in_memory failed (error case): {e}")

        token_counter = token_counter_from_agent(search_agent) if search_agent is not None else TokenCounter()
        timer.stop()
        return enrich_result_with_metrics(task_result, timer, token_counter)


def main(args):
    harness_package = getattr(args, "harness_package", None)
    harness_package_root = getattr(args, "harness_package_root", None)
    if harness_package or harness_package_root:
        harness_runtime.activate_harness_package(
            harness_package or harness_runtime.get_active_harness_package(),
            harness_package_root,
        )
    elif not getattr(args, "harness", None):
        harness_runtime.activate_harness_package("harness")
    _get_core_agent_class()

    task_llm_config = resolve_llm_config(
        args.model or get_default_model_name(default=""),
        backend=args.model_backend,
        api_key=args.api_key,
        api_base=args.api_base,
    )
    judge_llm_config = None
    if args.judge_model:
        judge_backend = args.judge_model_backend or task_llm_config.backend
        judge_api_key = args.judge_api_key
        judge_api_base = args.judge_api_base
        if judge_backend == task_llm_config.backend:
            if judge_api_key is None:
                judge_api_key = task_llm_config.api_key
            if judge_api_base is None:
                judge_api_base = task_llm_config.api_base
        judge_llm_config = resolve_llm_config(
            args.judge_model,
            backend=judge_backend,
            api_key=judge_api_key,
            api_base=judge_api_base,
        )

    effective_memory_provider = resolve_memory_provider_name(
        args.memory_provider,
        args.harness,
    )

    run_tag = _build_run_tag(
        args.planning_system,
        args.action_system,
        effective_memory_provider,
        model=task_llm_config.model,
        model_backend=task_llm_config.backend,
    )
    benchmark_cfg = resolve_benchmark(args)
    dataset_type = benchmark_cfg["type"] if benchmark_cfg else "generic"
    dataset_name = benchmark_cfg["name"] if benchmark_cfg else "Custom"
    if dataset_type == "toolhop":
        run_tag = f"{run_tag}_{_sanitize_name(args.toolhop_mode)}"
        if args.toolhop_mode == TOOLHOP_MODE_OPEN:
            raise NotImplementedError(
                "ToolHop open-set mode is exposed in the CLI for future work, but only closed-set mode is implemented right now."
            )
    elif dataset_type == "api_bank":
        run_tag = (
            f"{run_tag}_"
            f"{_sanitize_name(benchmark_cfg.get('api_bank_level'))}_"
            f"{_sanitize_name(benchmark_cfg.get('api_bank_split'))}"
        )
    elif dataset_type == "restbench":
        run_tag = f"{run_tag}_{_sanitize_name(benchmark_cfg.get('restbench_dataset'))}"
    elif dataset_type == "taubench":
        run_tag = (
            f"{run_tag}_"
            f"{_sanitize_name(benchmark_cfg.get('taubench_domain'))}_"
            f"{_sanitize_name(benchmark_cfg.get('taubench_split'))}_"
            f"user-{_sanitize_name(args.taubench_user_model)}"
        )
    infile = benchmark_cfg["path"] if benchmark_cfg else args.infile
    if not infile:
        raise ValueError("Please provide --infile or set --benchmark to a known dataset.")

    data = load_data(infile)
    if benchmark_cfg and dataset_type == "api_bank":
        for row in data:
            if isinstance(row, dict):
                row["_api_bank_level"] = benchmark_cfg.get("api_bank_level", "")
                row["_api_bank_split"] = benchmark_cfg.get("api_bank_split", "")
                row["_benchmark"] = benchmark_cfg.get("benchmark", "")
    elif benchmark_cfg and dataset_type == "restbench":
        try:
            from runtime.restbench.runtime import count_restbench_endpoints

            restbench_tool_count = count_restbench_endpoints(benchmark_cfg["restbench_spec_path"])
        except Exception:
            restbench_tool_count = 0
        for row in data:
            if isinstance(row, dict):
                row["_restbench_dataset"] = benchmark_cfg.get("restbench_dataset", "")
                row["_restbench_spec_path"] = benchmark_cfg.get("restbench_spec_path", "")
                row["_restbench_tool_count"] = restbench_tool_count
                row["_benchmark"] = benchmark_cfg.get("benchmark", "")
    elif benchmark_cfg and dataset_type == "mixeddata":
        for row in data:
            if isinstance(row, dict):
                row["_benchmark"] = benchmark_cfg.get("benchmark", "")
                row["mixed_benchmark"] = get_mixed_benchmark(row)
    elif benchmark_cfg and dataset_type == "taubench":
        for row in data:
            if isinstance(row, dict):
                row["_benchmark"] = benchmark_cfg.get("benchmark", "")
                row["taubench_domain"] = benchmark_cfg.get("taubench_domain", row.get("taubench_domain", "retail"))
                row["taubench_split"] = benchmark_cfg.get("taubench_split", row.get("taubench_split", "dev"))
                row["_taubench_user_model"] = args.taubench_user_model
                row["_taubench_user_model_provider"] = args.taubench_user_model_provider
                row["_taubench_user_strategy"] = args.taubench_user_strategy

    if args.task_indices:
        selected_indices = parse_task_indices(args.task_indices)
        data = [data[i - 1] for i in sorted(selected_indices) if 0 < i <= len(data)]
    elif args.sample_num is not None:
        data = data[:args.sample_num]

    if not args.outfile:
        base_out_dir = args.output_dir or "./output"
        base_name = benchmark_cfg["benchmark"] if benchmark_cfg else os.path.splitext(os.path.basename(infile))[0]
        args.outfile = os.path.join(base_out_dir, f"{base_name}_{run_tag}_results.jsonl")

    out_dir = os.path.dirname(args.outfile)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    if args.direct_output_dir:
        run_dir = args.direct_output_dir
        os.makedirs(run_dir, exist_ok=True)
    else:
        base_out_dir = args.output_dir or os.path.dirname(args.outfile) or "."
        run_dir = create_run_directory(base_out_dir, dataset_name, memory_name=f"{run_tag}_")

    try:
        out_data = read_jsonl(args.outfile)
    except Exception:
        out_data = []

    if out_data and effective_memory_provider:
        backfill_memory_from_completed_results(
            out_data,
            effective_memory_provider,
            args.memory_storage_dir,
            dataset_type,
            args.harness,
        )

    done_keys = set()
    for item in out_data:
        done_keys.update(get_resume_keys(item))
    data_to_run = [item for item in data if isinstance(item, dict) and not (get_resume_keys(item) & done_keys)]
    completed_count = len(data) - len(data_to_run)
    logger.info(f"Total data: {len(data)}, Completed: {completed_count}, Remaining: {len(data_to_run)}")
    if dataset_type not in {"toolhop", "api_bank", "restbench", "mixeddata", "taubench"} and not args.judge_model:
        logger.warning("JUDGE_MODEL not set. Evaluation will be skipped (judgement=None).")

    results = []
    file_lock = threading.Lock()

    def safe_write(result):
        with file_lock:
            write_jsonl(args.outfile, [result], "a")

    def safe_save_task(result):
        with file_lock:
            filename = f"{result.get('item_index')}.json" if result.get("item_index") else None
            save_task_result(result, run_dir, filename)

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        summary_interval = random.randint(args.summary_interval - 1, args.summary_interval + 1)

        futures = [
            executor.submit(
                process_item,
                item,
                task_llm_config,
                args.max_tokens,
                summary_interval,
                args.prompts_type,
                args.max_steps,
                args.planning_system,
                args.action_system,
                judge_llm_config,
                effective_memory_provider,
                args.memory_storage_dir,
                args.memory_write_only,
                dataset_type,
                args.harness,
                args.toolhop_mode,
            ) for item in data_to_run
        ]

        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing"):
            try:
                result = future.result()
            except Exception:
                logger.error(f"Failed to get result from future: {traceback.format_exc()}")
                continue

            if result:
                result = make_json_serializable(result)
                results.append(result)
                safe_write(result)
                safe_save_task(result)

                metrics = result.get("metrics", {})
                if result.get("status") == "success":
                    logger.info(
                        f"Task done [{len(results)}/{len(futures)}]: {result.get('question', '')[:80]}... "
                        f"| Time: {metrics.get('elapsed_time', 0):.1f}s | Tokens: {metrics.get('total_tokens', 0)}"
                    )
                elif result.get("status") == "error":
                    logger.warning(
                        f"Task error [{len(results)}/{len(futures)}]: {result.get('question', '')[:80]}... "
                        f"| Error: {result.get('error', 'Unknown')}"
                    )

    logger.info(f"Processing completed. Newly added: {len(results)}, Total completed: {completed_count + len(results)}")

    all_results = out_data + results
    report_path = os.path.join(run_dir, "report.txt")
    report_summary = generate_unified_report(
        all_results,
        report_path,
        dataset_name=dataset_name,
        has_levels=bool(benchmark_cfg and benchmark_cfg.get("has_levels")),
        level_key=(benchmark_cfg.get("level_key") if benchmark_cfg else "difficulty"),
    )
    benchmark_overall = None
    benchmark_metrics_path = None
    if dataset_type == "toolhop":
        toolhop_overall = write_toolhop_metrics(all_results, run_dir)
        benchmark_overall = toolhop_overall
        benchmark_metrics_path = os.path.join(run_dir, "toolhop.metrics.overall.json")
        append_toolhop_report(all_results, report_path)
        logger.info(f"ToolHop overall metrics saved: {toolhop_overall}")
    elif dataset_type == "api_bank":
        api_bank_overall = write_api_bank_metrics(all_results, run_dir)
        benchmark_overall = api_bank_overall
        benchmark_metrics_path = os.path.join(run_dir, "api_bank.metrics.overall.json")
        append_api_bank_report(all_results, report_path)
        logger.info(f"API-Bank overall metrics saved: {api_bank_overall}")
    elif dataset_type == "restbench":
        restbench_overall = write_restbench_metrics(all_results, run_dir)
        benchmark_overall = restbench_overall
        benchmark_metrics_path = os.path.join(run_dir, "restbench.metrics.overall.json")
        append_restbench_report(all_results, report_path)
        logger.info(f"RestBench overall metrics saved: {restbench_overall}")
    elif dataset_type == "mixeddata":
        mixeddata_overall = write_mixeddata_metrics(all_results, run_dir)
        benchmark_overall = mixeddata_overall
        benchmark_metrics_path = os.path.join(run_dir, "mixeddata.metrics.overall.json")
        logger.info(f"MixedData overall metrics saved: {mixeddata_overall}")
    elif dataset_type == "taubench":
        taubench_overall = write_taubench_metrics(all_results, run_dir)
        benchmark_overall = taubench_overall
        benchmark_metrics_path = os.path.join(run_dir, "taubench.metrics.overall.json")
        append_taubench_report(all_results, report_path)
        logger.info(f"tau-bench overall metrics saved: {taubench_overall}")

    if getattr(args, "record_harness_registry", False):
        try:
            from tools.harness_pool_registry import (
                record_run_from_summary,
                summarize_results,
            )

            harness_for_registry = args.harness or _build_run_tag(
                args.planning_system,
                args.action_system,
                effective_memory_provider,
                model=None,
                model_backend=None,
            )
            raw_round = getattr(args, "registry_round", None)
            if raw_round is None and benchmark_cfg and benchmark_cfg.get("benchmark") == "toolhop":
                raw_round = str(args.infile or Path(infile).stem)
            if raw_round is None:
                raw_round = Path(infile).stem

            registry_dataset = (
                getattr(args, "registry_dataset", None)
                or (benchmark_cfg.get("benchmark") if benchmark_cfg else None)
                or Path(infile).stem
            )
            registry_file = Path(getattr(args, "registry_file", "./registries/harness_pool.yaml"))
            if not registry_file.is_absolute():
                registry_file = Path(SCRIPT_DIR) / registry_file

            run_record = record_run_from_summary(
                registry_path=registry_file,
                project_root=Path(SCRIPT_DIR),
                harness=harness_for_registry,
                package=harness_runtime.get_active_harness_package(),
                round_id=raw_round,
                dataset=registry_dataset,
                dataset_type=dataset_type,
                model_name=task_llm_config.model,
                model_backend=task_llm_config.backend,
                model_alias=getattr(args, "model_alias", None),
                model_adapter=getattr(args, "model_adapter", None),
                memory_provider=effective_memory_provider,
                experiment=getattr(args, "registry_experiment", None),
                run_dir=run_dir,
                results_path=args.outfile,
                report_path=report_path,
                metrics_path=benchmark_metrics_path,
                result_summary=summarize_results(all_results),
                benchmark_summary=benchmark_overall,
                report_summary=report_summary,
            )
            logger.info(
                "Harness registry updated: %s -> %s",
                registry_file,
                run_record.get("run_id"),
            )
        except Exception:
            logger.warning(
                "Failed to update harness registry: %s",
                traceback.format_exc(),
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Unified inference runner')

    parser.add_argument('--benchmark', type=str, default=None, help='Benchmark name (e.g., webwalkerqa)')
    parser.add_argument('--infile', '--dataset-path', '--dataset-file', '--toolhop-file', dest='infile', type=str, default=None, help='Input dataset path (JSONL or JSON). For ToolHop, also accepts 1-4, round_1-round_4, test, or online_dev.')
    parser.add_argument('--outfile', type=str, default=None, help='Output path for results JSONL')
    parser.add_argument('--output_dir', type=str, default=None, help='Base directory for run outputs')
    parser.add_argument('--direct_output_dir', type=str, default=None, help='Direct output directory (skips timestamped nesting)')
    parser.add_argument('--sample_num', type=int, default=None, help='Number of samples to process')
    parser.add_argument('--task_indices', type=str, default=None, help='Task indices: "5", "1-10", or "1,3,5-8"')
    parser.add_argument('--summary_interval', type=int, default=8, help='Summary interval')
    parser.add_argument('--prompts_type', type=str, default=None, help='Type of prompts to use (defaults to planning_system if not specified)')
    parser.add_argument('--concurrency', type=int, default=15, help='Number of concurrency')
    parser.add_argument('--max_steps', type=int, default=50, help='Maximum number of steps')
    parser.add_argument('--max_tokens', type=int, default=None, help='Maximum output tokens for each model call')
    parser.add_argument('--model', type=str, default=None, help='Task model ID. If omitted, it falls back to EXECUTE_MODEL/PLANNING_MODEL.')
    parser.add_argument(
        '--model-backend',
        type=str,
        default=None,
        help="Task model backend: 'api' for remote OpenAI-compatible APIs, 'local' for a local OpenAI-compatible server.",
    )
    parser.add_argument('--api-base', type=str, default=None, help='Task model endpoint base URL. Required when --model-backend=local.')
    parser.add_argument('--api-key', type=str, default=None, help='Optional task model API key override.')
    parser.add_argument('--planning_system', type=str, default="flash_searcher", help='Planning system to use')
    parser.add_argument('--action_system', type=str, default=None, help='Action system to use (defaults to planning_system if not specified)')
    parser.add_argument('--harness', type=str, default=None, help='Optional harness bundle name under the active harness package, e.g. harness1')
    parser.add_argument('--harness_package', type=str, default=None, help='Optional harness package name, e.g. runtime_harnesses')
    parser.add_argument('--harness_package_root', type=str, default=None, help='Parent directory containing the harness package root')
    parser.add_argument('--judge_model', type=str, default=os.environ.get("JUDGE_MODEL"), help='Model used for answer judgement')
    parser.add_argument(
        '--judge-model-backend',
        type=str,
        default=None,
        help='Optional judge backend override. Defaults to the task model backend.',
    )
    parser.add_argument('--judge-api-base', type=str, default=None, help='Optional judge endpoint base URL override.')
    parser.add_argument('--judge-api-key', type=str, default=None, help='Optional judge API key override.')
    parser.add_argument('--memory_provider', type=str, default=None, help='Memory provider type (e.g., "cerebra_fusion_memory", "memp")')
    parser.add_argument(
        '--memory_storage_dir',
        '--storage_root',
        dest='memory_storage_dir',
        type=str,
        default=None,
        help='Optional root directory for memory/storage outputs. Defaults to ./storage when omitted.',
    )
    parser.add_argument(
        '--toolhop-mode',
        type=str,
        default=TOOLHOP_MODE_CLOSED,
        choices=[TOOLHOP_MODE_CLOSED, TOOLHOP_MODE_OPEN],
        help='ToolHop execution mode. Only closed-set is implemented right now; open-set is reserved for future retrieval integration.',
    )
    parser.add_argument(
        '--taubench-env',
        type=str,
        default=None,
        choices=['retail', 'airline'],
        help='tau-bench domain. Used with --benchmark taubench; defaults to retail.',
    )
    parser.add_argument(
        '--taubench-split',
        type=str,
        default=None,
        choices=['train', 'dev', 'test'],
        help='tau-bench split. retail supports train/dev/test; airline supports test.',
    )
    parser.add_argument(
        '--taubench-user-model',
        type=str,
        default='gpt-4o',
        help='Model used by the tau-bench user simulator.',
    )
    parser.add_argument(
        '--taubench-user-model-provider',
        type=str,
        default='openai',
        help='LiteLLM provider used by the tau-bench user simulator.',
    )
    parser.add_argument(
        '--taubench-user-strategy',
        type=str,
        default='llm',
        choices=['llm', 'react', 'verify', 'reflection'],
        help='tau-bench user simulator strategy.',
    )
    parser.add_argument(
        '--memory-write-only',
        type=lambda x: str(x).strip().lower() in {"1", "true", "t", "yes", "y", "on"},
        default=False,
        help='Shared memory switch. True means store new memory but never retrieve old memory.',
    )
    parser.add_argument(
        '--record-harness-registry',
        action='store_true',
        help='Record this run into the harness pool registry after evaluation finishes.',
    )
    parser.add_argument(
        '--registry-file',
        type=str,
        default='./registries/harness_pool.yaml',
        help='Harness pool registry YAML path used with --record-harness-registry.',
    )
    parser.add_argument(
        '--registry-experiment',
        type=str,
        default=None,
        help='Optional experiment id recorded in the harness pool registry.',
    )
    parser.add_argument(
        '--registry-round',
        type=str,
        default=None,
        help='Optional round id recorded in the harness pool registry.',
    )
    parser.add_argument(
        '--registry-dataset',
        type=str,
        default=None,
        help='Optional dataset id recorded in the harness pool registry.',
    )
    parser.add_argument(
        '--model-alias',
        type=str,
        default=None,
        help='Optional human-friendly model alias recorded in the harness pool registry.',
    )
    parser.add_argument(
        '--model-adapter',
        type=str,
        default=os.environ.get("MODEL_ADAPTER") or os.environ.get("LORA_ADAPTER"),
        help='Optional adapter/checkpoint path or id recorded in the harness pool registry.',
    )

    return parser


def cli() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    main(args)


if __name__ == '__main__':
    cli()
