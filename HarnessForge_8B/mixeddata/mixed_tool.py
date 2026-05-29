from __future__ import annotations

import array
import json
import os
import sys
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEARCHQA_RETRIEVE_DIR = Path(
    os.getenv(
        "MIXED_SEARCHQA_RETRIEVE_DIR",
        "data/mixeddata/searchqa_retrieve_data",
    )
)
DEFAULT_ENVSCALER_ROOT = Path(
    os.getenv(
        "MIXED_ENVSCALER_ROOT",
        "data/mixeddata/envscaler/interact_with_env",
    )
)
DEFAULT_ENVSCALER_ENVS_PATH = Path(
    os.getenv(
        "MIXED_ENVSCALER_ENVS_PATH",
        "data/mixeddata/envdata/envs.json",
    )
)


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return repr(value)


def _stringify_observation(value: Any) -> str:
    return value if isinstance(value, str) else _json_dumps(value)


def _resolve_searchqa_retrieve_dir(config: dict[str, Any]) -> Path:
    candidates: list[Path] = []
    if config.get("retrieve_dir"):
        candidates.append(Path(str(config["retrieve_dir"])).expanduser())
    if os.getenv("MIXED_SEARCHQA_RETRIEVE_DIR"):
        candidates.append(Path(os.environ["MIXED_SEARCHQA_RETRIEVE_DIR"]).expanduser())
    candidates.extend(
        [
            PROJECT_ROOT / "data" / "mixeddata" / "searchqa_retrieve_data",
            DEFAULT_SEARCHQA_RETRIEVE_DIR,
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _resolve_envs_path(path: str | Path) -> Path:
    requested = Path(path).expanduser()
    if requested.exists():
        return requested
    candidates = [
        Path(os.environ["MIXED_ENVSCALER_ENVS_PATH"]).expanduser()
        for _ in [0]
        if os.getenv("MIXED_ENVSCALER_ENVS_PATH")
    ]
    candidates.extend(
        [
            PROJECT_ROOT / "data" / "mixeddata" / "envdata" / "envs.json",
            DEFAULT_ENVSCALER_ENVS_PATH,
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return requested


def _ensure_envscaler_path() -> None:
    candidates: list[Path] = []
    if os.getenv("MIXED_ENVSCALER_ROOT"):
        candidates.append(Path(os.environ["MIXED_ENVSCALER_ROOT"]).expanduser())
    candidates.extend(
        [
            PROJECT_ROOT.parent / "Benchmark_all" / "EnvScaler" / "interact_with_env",
            DEFAULT_ENVSCALER_ROOT,
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            value = str(candidate)
            if value not in sys.path:
                sys.path.insert(0, value)
            return
    value = str(candidates[0])
    if value not in sys.path:
        sys.path.insert(0, value)


class SearchQARetriever:
    def __init__(
        self,
        index_path: str | Path,
        corpus_path: str | Path,
        model_path: str | Path,
        topk: int = 3,
        device: str | None = None,
        use_fp16: bool = True,
    ) -> None:
        self.index_path = Path(index_path)
        self.corpus_path = Path(corpus_path)
        self.model_path = Path(model_path)
        self.topk = int(topk)
        self.device_name = device or os.getenv("MIXED_SEARCHQA_DEVICE", "auto")
        self.use_fp16 = bool(use_fp16)
        self._lock = threading.Lock()
        self._corpus_fh = None
        self.index = None
        self.offsets = None
        self.model = None
        self.tokenizer = None
        self.device = None

    def _ensure_loaded(self) -> None:
        with self._lock:
            if self.index is not None and self.model is not None and self.offsets is not None:
                return

            import faiss
            import torch
            from transformers import AutoModel, AutoTokenizer

            if self.index is None:
                self.index = faiss.read_index(str(self.index_path))

            if self.offsets is None:
                offset_path = self.corpus_path.with_suffix(self.corpus_path.suffix + ".offsets.u64")
                if not offset_path.exists():
                    self._build_offsets(offset_path)
                self.offsets = np.memmap(offset_path, dtype=np.uint64, mode="r")

            if self.model is None or self.tokenizer is None:
                if self.device_name == "auto":
                    self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                else:
                    self.device = torch.device(self.device_name)
                self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), use_fast=True, trust_remote_code=True)
                self.model = AutoModel.from_pretrained(str(self.model_path), trust_remote_code=True)
                self.model.eval().to(self.device)
                if self.use_fp16 and self.device.type == "cuda":
                    self.model.half()

    def _build_offsets(self, offset_path: Path) -> None:
        tmp_path = offset_path.with_suffix(offset_path.suffix + ".tmp")
        chunk = array.array("Q")
        offset = 0
        with self.corpus_path.open("rb") as src, tmp_path.open("wb") as dst:
            while True:
                line = src.readline()
                if not line:
                    break
                chunk.append(offset)
                if len(chunk) >= 1_000_000:
                    dst.write(chunk.tobytes())
                    chunk = array.array("Q")
                offset += len(line)
            if chunk:
                dst.write(chunk.tobytes())
        tmp_path.replace(offset_path)

    def _get_doc(self, doc_idx: int) -> dict[str, Any]:
        self._ensure_loaded()
        if doc_idx < 0 or doc_idx >= len(self.offsets):
            return {"contents": f"Document index {doc_idx} is out of range."}
        if self._corpus_fh is None:
            self._corpus_fh = self.corpus_path.open("rb")
        self._corpus_fh.seek(int(self.offsets[doc_idx]))
        line = self._corpus_fh.readline()
        try:
            return json.loads(line)
        except Exception:
            return {"contents": line.decode("utf-8", errors="replace")}

    def _encode_query(self, query: str) -> np.ndarray:
        self._ensure_loaded()
        import torch

        query_text = query if query.lower().startswith("query:") else f"query: {query}"
        inputs = self.tokenizer(
            [query_text],
            max_length=256,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.no_grad():
            output = self.model(**inputs, return_dict=True)
            hidden = output.last_hidden_state.masked_fill(~inputs["attention_mask"][..., None].bool(), 0.0)
            emb = hidden.sum(dim=1) / inputs["attention_mask"].sum(dim=1)[..., None]
            emb = torch.nn.functional.normalize(emb, dim=-1)
        return emb.detach().cpu().numpy().astype(np.float32, order="C")

    def search(self, query: str, topk: int | None = None) -> list[dict[str, Any]]:
        self._ensure_loaded()
        k = int(topk or self.topk)
        query_emb = self._encode_query(query)
        scores, idxs = self.index.search(query_emb, k=k)
        results = []
        for rank, (idx, score) in enumerate(zip(idxs[0].tolist(), scores[0].tolist()), start=1):
            doc = self._get_doc(int(idx))
            contents = doc.get("contents")
            if not contents:
                contents = f"{doc.get('title', '')}\n{doc.get('text', '')}".strip()
            results.append({"rank": rank, "score": float(score), "doc_id": int(idx), "contents": str(contents)})
        return results

    def format_results(self, query: str, topk: int | None = None) -> str:
        docs = self.search(query=query, topk=topk)
        lines = []
        for doc in docs:
            contents = doc["contents"].strip()
            if "\n" in contents:
                title, text = contents.split("\n", 1)
            else:
                title, text = "", contents
            prefix = f"Doc {doc['rank']}"
            if title:
                prefix += f" (Title: {title.strip()})"
            lines.append(f"{prefix} {text.strip()}")
        return "\n".join(lines)


_SEARCHQA_RETRIEVERS: dict[tuple[str, str, str, int], SearchQARetriever] = {}
_SEARCHQA_LOCK = threading.Lock()


def _get_searchqa_retriever(config: dict[str, Any]) -> SearchQARetriever:
    retrieve_dir = _resolve_searchqa_retrieve_dir(config)
    index_path = str(config.get("index_path") or retrieve_dir / "e5_Flat.index")
    corpus_path = str(config.get("corpus_path") or retrieve_dir / "wiki-18.jsonl")
    model_path = str(config.get("model_path") or retrieve_dir / "e5-base-v2")
    topk = int(config.get("topk", os.getenv("MIXED_SEARCHQA_TOPK", "3")))
    key = (index_path, corpus_path, model_path, topk)
    with _SEARCHQA_LOCK:
        retriever = _SEARCHQA_RETRIEVERS.get(key)
        if retriever is None:
            retriever = SearchQARetriever(
                index_path=index_path,
                corpus_path=corpus_path,
                model_path=model_path,
                topk=topk,
                use_fp16=str(config.get("use_fp16", "true")).lower() != "false",
            )
            _SEARCHQA_RETRIEVERS[key] = retriever
        return retriever


_ENV_ITEMS_CACHE: dict[str, dict[str, Any]] = {}


def _load_env_items(path: str | Path) -> dict[str, Any]:
    resolved_path = str(_resolve_envs_path(path))
    cached = _ENV_ITEMS_CACHE.get(resolved_path)
    if cached is not None:
        return cached
    with open(resolved_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"EnvScaler envs file must contain a JSON object: {resolved_path}")
    _ENV_ITEMS_CACHE[resolved_path] = data
    return data


class EnvScalerSession:
    def __init__(self, task_record: dict[str, Any], env_item: dict[str, Any]) -> None:
        _ensure_envscaler_path()
        from envscaler_env.utils.env_util import get_state_info, init_env_class, init_env_instance

        self.task_record = deepcopy(task_record)
        self.env_item = deepcopy(env_item)
        self.checklist = self.task_record.get("evaluation", {}).get("checklist_with_func", [])
        if not self.checklist:
            self.checklist = self.task_record.get("checklist_with_func", [])

        env_class_name = self.task_record["env_class_name"]
        env_class_code = self.env_item["env_class_code"]
        init_config = self.task_record.get("hidden_state", {}).get("init_config", self.task_record.get("init_config", {}))
        self.env_class = init_env_class(env_class_code, env_class_name)
        self.env_instance = init_env_instance(self.env_class, init_config)
        self.init_state = get_state_info(self.env_instance)
        self.final_state = None
        self.done = False
        self.score = 0.0

    def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, float, bool]:
        if name in {"complete_task", "task_completed"}:
            return self.complete()
        if name == "chat_with_user" and str(arguments.get("content", "")).strip() == "Task Completed":
            return self.complete()
        if self.done:
            return "Task is already completed.", self.score, True
        if not hasattr(self.env_instance, name):
            return f"Error: invalid EnvScaler tool '{name}'.", 0.0, False
        method = getattr(self.env_instance, name)
        result = method(**arguments)
        return _stringify_observation(result), 0.0, False

    def complete(self) -> tuple[str, float, bool]:
        from envscaler_env.utils.env_util import get_state_info, run_check_function

        self.final_state = get_state_info(self.env_instance)
        if not self.checklist:
            self.score = 0.0
        else:
            results = []
            for item in self.checklist:
                success, result, _ = run_check_function(
                    func_code=item["check_func"],
                    init_state=self.init_state,
                    final_state=self.final_state,
                )
                results.append(bool(success and result))
            self.score = round(sum(1.0 for item in results if item) / len(results), 4)
        self.done = True
        return f"Task finished. EnvScaler score: {self.score}", self.score, True
