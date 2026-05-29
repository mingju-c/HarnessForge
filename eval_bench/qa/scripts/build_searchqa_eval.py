#!/usr/bin/env python3
"""Build AgentGym SearchQA offline-search eval files for MATE.

Default behavior is deliberately conservative: use AgentGym SearchQA test/dev
sources only, dedupe against the specified training JSONL, and do not fall back
to train splits unless --allow-train-fallback is explicitly set.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
from pathlib import Path
from typing import Any

SOURCE_REPO = "RUC-NLPIR/FlashRAG_datasets"
DEFAULT_BLACKLIST = Path(__file__).resolve().parents[1] / 'data' / 'blacklist.jsonl'
DEFAULT_AGENTGYM_ROOT = Path(__file__).resolve().parents[1] / 'source_data' / 'agentenv-searchqa'
DEFAULT_LOCAL_SOURCE_DATA = Path(__file__).resolve().parents[1] / 'source_data'

AGENTGYM_TEST_RANGES = {
    'nq': (0, 3610),
    'triviaqa': (3610, 14923),
    'popqa': (14923, 29190),
    'hotpotqa': (29190, 36595),
    '2wikimultihopqa': (36595, 49171),
    'musique': (49171, 51588),
    'bamboogle': (51588, 51713),
}

BASE_SYSTEM = """You are a careful tool-using agent.

Use the task-specific tools described below to solve the user request. Think briefly, call one tool at a time, read the observation, and continue until the task is solved.

Strict output contract:
- Return exactly one JSON object, no markdown or extra text.
- For tool use: {"think":"brief next-step reasoning","tools":[{"name":"actual_tool_name","arguments":{"arg":"value"}}]}
- Tool names and argument keys must exactly match the schemas. Never invent tools or arguments.
- Use one tool call each step by default.
- For ordinary QA or ToolHop tasks, submit the final answer as {"think":"supported","answer":"raw answer"} or by calling final_answer.
- For EnvScaler state-change tasks, when all required state changes are complete, call complete_task with {"answer":"Task Completed"}.
- For WebShop shopping tasks, use search and click until you are ready, then click buy now.
- For ALFWorld household tasks, first call observe, then repeatedly call act with one exact admissible command from the latest observation."""

SEARCH_TOOL_SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'search',
        'description': 'Offline Wikipedia search over the AgentGym SearchQA E5/FAISS retriever.',
        'parameters': {
            'type': 'object',
            'required': ['query'],
            'properties': {'query': {'type': 'string', 'description': 'Search query.'}},
        },
    },
}


def normalize_question(text: Any) -> str:
    return re.sub(r'\s+', ' ', str(text or '').strip().lower())


def parse_original_index(example_id: Any) -> int | None:
    text = str(example_id or '')
    match = re.search(r'(\d+)$', text)
    return int(match.group(1)) if match else None


def read_blacklist(path: Path) -> dict[str, set[Any]]:
    blocked = {'ids': set(), 'questions': set(), 'source_index': set()}
    if not path.exists():
        return blocked
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            row_id = row.get('id')
            if row_id is not None:
                blocked['ids'].add(str(row_id))
            q = normalize_question(row.get('question') or (row.get('extra_info') or {}).get('question'))
            if q:
                blocked['questions'].add(q)
            extra = row.get('extra_info') if isinstance(row.get('extra_info'), dict) else {}
            source = str(extra.get('source_config') or row.get('data_source') or '').lower()
            idx = extra.get('original_index')
            if source and idx is not None:
                try:
                    blocked['source_index'].add((source, int(idx)))
                except Exception:
                    pass
    return blocked


def load_agentgym_parquet(agentgym_root: Path, source: str) -> tuple[list[dict[str, Any]], str]:
    query_path = agentgym_root / 'agentenv_searchqa' / 'queries' / 'test.parquet'
    if not query_path.exists() or source not in AGENTGYM_TEST_RANGES:
        return [], ''
    from datasets import load_dataset
    dataset = load_dataset('parquet', data_files=str(query_path), keep_in_memory=False)['train']
    start, end = AGENTGYM_TEST_RANGES[source]
    rows = []
    for global_item_id in range(start, end):
        local_idx = global_item_id
        row = dict(dataset[local_idx])
        row['_agentgym_item_id'] = global_item_id
        row['_source_row_index'] = global_item_id - start
        rows.append(row)
    return rows, 'agentgym_test_parquet'



def load_local_source_data(source_data_dir: Path, source: str, *, allow_train_fallback: bool) -> tuple[list[dict[str, Any]], str]:
    source_dir = source_data_dir / source
    split_order = ['test', 'dev']
    if allow_train_fallback:
        split_order.append('train')
    for split in split_order:
        path = source_dir / f'{split}.jsonl'
        if not path.exists():
            continue
        rows = []
        with path.open(encoding='utf-8') as handle:
            for idx, line in enumerate(handle):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                row['_source_row_index'] = idx
                rows.append(row)
        return rows, f'local_{split}'
    return [], ''

def load_flashrag(source: str, *, allow_train_fallback: bool, offline: bool) -> tuple[list[dict[str, Any]], str]:
    if offline:
        os.environ.setdefault('HF_DATASETS_OFFLINE', '1')
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
    from datasets import load_dataset
    ds = load_dataset(SOURCE_REPO, source)
    if 'test' in ds:
        split = 'test'
    elif 'dev' in ds:
        split = 'dev'
    elif allow_train_fallback and 'train' in ds:
        split = 'train'
    else:
        available = ','.join(ds.keys())
        raise RuntimeError(f'{source}: no test/dev split available (available={available}); refusing train fallback')
    rows = [dict(ds[split][idx]) for idx in range(len(ds[split]))]
    for idx, row in enumerate(rows):
        row['_source_row_index'] = idx
    return rows, split


def load_source(source: str, args: argparse.Namespace) -> tuple[list[dict[str, Any]], str]:
    rows, split = load_agentgym_parquet(args.agentgym_root, source)
    if rows:
        return rows, split
    rows, split = load_local_source_data(args.source_data_dir, source, allow_train_fallback=args.allow_train_fallback)
    if rows:
        return rows, split
    return load_flashrag(source, allow_train_fallback=args.allow_train_fallback, offline=args.offline)


def golden_answers(row: dict[str, Any]) -> list[str]:
    value = row.get('golden_answers')
    if value is None:
        value = row.get('answers', row.get('answer'))
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith('[') or stripped.startswith('{'):
            try:
                value = json.loads(stripped)
            except Exception:
                value = [value]
        else:
            value = [value]
    if isinstance(value, dict):
        value = value.get('target') or value.get('answers') or value.get('answer') or []
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


def make_record(row: dict[str, Any], *, source: str, split: str, sample_index: int, retrieve_dir: Path) -> dict[str, Any]:
    question = str(row.get('question') or '').strip()
    if question and question[-1] != '?':
        question += '?'
    answers = golden_answers(row)
    answer_json = json.dumps(answers, ensure_ascii=False)
    source_row_index = row.get('_source_row_index')
    original_index = parse_original_index(row.get('id'))
    if original_index is None and source_row_index is not None:
        try:
            original_index = int(source_row_index)
        except Exception:
            original_index = None
    item_id = row.get('_agentgym_item_id')
    record_id = f'{source}_{split}_{original_index if original_index is not None else sample_index}'
    system_content = BASE_SYSTEM + '\n\nAvailable tool schemas:\n' + json.dumps([SEARCH_TOOL_SCHEMA], ensure_ascii=False)
    return {
        'split': split,
        'split_index': sample_index,
        'source_row_index': original_index,
        'id': record_id,
        'data_source': 'mixed_searchqa',
        'agent_name': 'tool_agent',
        'ability': 'fact_reasoning',
        'benchmark': 'searchqa',
        'question': question,
        'answer': answer_json,
        'prompt': [
            {'role': 'system', 'content': system_content},
            {'role': 'user', 'content': f'Question: {question}'},
        ],
        'mate_system_context': BASE_SYSTEM,
        'tool_schemas': [SEARCH_TOOL_SCHEMA],
        'reward_model': {'style': 'rule', 'ground_truth': answer_json},
        'extra_info': {
            'benchmark': 'searchqa',
            'index': original_index,
            'id': row.get('id'),
            'question': question,
            'answer': None,
            'sub_task_json': None,
            'need_tools_kwargs': True,
            'tool_selection': 'mixed_call',
            'tools_kwargs': {
                'mixed_call': {
                    'create_kwargs': {
                        'benchmark': 'searchqa',
                        'functions_json': '[]',
                        'tools_json': '[]',
                        'retrieve_dir': str(retrieve_dir),
                        'topk': 3,
                        'envs_path': '',
                        'task_record_json': '{}',
                    }
                }
            },
            'golden_answers': answer_json,
            'source_repo': SOURCE_REPO,
            'source_config': source,
            'source_split': split,
            'agentgym_item_id': item_id,
        },
    }


def sample_source(source: str, rows: list[dict[str, Any]], split: str, args: argparse.Namespace, blocked: dict[str, set[Any]]) -> list[dict[str, Any]]:
    rng = random.Random(args.seed + sum(ord(ch) for ch in source))
    indices = list(range(len(rows)))
    rng.shuffle(indices)
    selected = []
    for idx in indices:
        row = rows[idx]
        q_norm = normalize_question(row.get('question'))
        row_id = str(row.get('id') or '')
        original_index = parse_original_index(row_id)
        if original_index is None:
            original_index = idx
        if row_id in blocked['ids']:
            continue
        if q_norm and q_norm in blocked['questions']:
            continue
        if (source.lower(), int(original_index)) in blocked['source_index']:
            continue
        answers = golden_answers(row)
        if not q_norm or not answers:
            continue
        selected.append(make_record(row, source=source, split=split, sample_index=len(selected), retrieve_dir=args.retrieve_dir))
        if len(selected) >= args.count:
            break
    return selected


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')


def maybe_write_parquet(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    from datasets import Dataset
    Dataset.from_list(records).to_parquet(str(path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'data')
    parser.add_argument('--agentgym-root', type=Path, default=DEFAULT_AGENTGYM_ROOT)
    parser.add_argument('--source-data-dir', type=Path, default=DEFAULT_LOCAL_SOURCE_DATA)
    parser.add_argument('--blacklist', type=Path, default=DEFAULT_BLACKLIST)
    parser.add_argument('--retrieve-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'retrieve_data')
    parser.add_argument('--sources', default='nq,hotpotqa,2wikimultihopqa,musique')
    parser.add_argument('--count', type=int, default=200)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--offline', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--allow-missing', action='store_true')
    parser.add_argument('--allow-train-fallback', action='store_true')
    parser.add_argument('--write-parquet', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    blocked = read_blacklist(args.blacklist)
    manifest = {
        'version': 1,
        'source': 'AgentGym SearchQA / RUC-NLPIR FlashRAG_datasets',
        'blacklist': str(args.blacklist),
        'dedupe': {'ids': len(blocked['ids']), 'questions': len(blocked['questions']), 'source_index': len(blocked['source_index'])},
        'requested_count_per_source': args.count,
        'seed': args.seed,
        'offline': args.offline,
        'allow_train_fallback': args.allow_train_fallback,
        'retrieve_dir': str(args.retrieve_dir),
        'sources': {},
        'missing_sources': {},
    }
    all_records: list[dict[str, Any]] = []
    for raw_source in args.sources.split(','):
        source = raw_source.strip()
        if not source:
            continue
        try:
            rows, split = load_source(source, args)
            records = sample_source(source, rows, split, args, blocked)
            out_path = args.output_dir / f'{source}.jsonl'
            write_jsonl(out_path, records)
            if args.write_parquet:
                maybe_write_parquet(args.output_dir / f'{source}.parquet', records)
            all_records.extend(records)
            manifest['sources'][source] = {
                'available_rows': len(rows),
                'split': split,
                'selected_rows': len(records),
                'jsonl': out_path.name,
            }
        except Exception as exc:
            manifest['missing_sources'][source] = str(exc)
            if not args.allow_missing:
                raise
    write_jsonl(args.output_dir / 'all.jsonl', all_records)
    if args.write_parquet:
        maybe_write_parquet(args.output_dir / 'all.parquet', all_records)
    with (args.output_dir / 'manifest.json').open('w', encoding='utf-8') as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'total': len(all_records), 'sources': manifest['sources'], 'missing_sources': manifest['missing_sources']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
