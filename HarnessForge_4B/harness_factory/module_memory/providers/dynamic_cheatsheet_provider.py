from __future__ import annotations

import io
import os
import json
import uuid
import time
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from .model_loader import load_sentence_transformer

from ..base_memory import BaseMemoryProvider
from ..memory_types import (
    MemoryStatus,
    MemoryType,
    MemoryRequest,
    MemoryResponse,
    MemoryItem,
    MemoryItemType,
    TrajectoryData,
)

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: str, content: str) -> None:
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(content if content is not None else "")


def _extract_tag(text: str, tag: str = "cheatsheet") -> str:
    import re
    m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE)
    return (m.group(1).strip() if m else text).strip()


def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                         cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    return load_sentence_transformer(
        model_name=model_name,
        cache_dir=cache_dir,
        allow_unavailable=SentenceTransformer is None,
    )


class DynamicCheatsheetProvider(BaseMemoryProvider):

    def __init__(self, config: Optional[dict] = None):
        if config is None:
            raise ValueError("DynamicCheatsheetProvider requires an explicit config dict.")
        super().__init__(memory_type=MemoryType.DYNAMIC_CHEATSHEET, config=config)
        cfg = self.config
        
        self.store_path: str = cfg.get("store_path", "./dynamic_cheatsheet")
        self.records_file: str = cfg.get("records_file", "dynamic_cheatsheet.json")
        self.cheatsheet_file: str = cfg.get("cheatsheet_file", "global_cheatsheet.txt")
        
        self.records_path: str = os.path.join(self.store_path, self.records_file)
        self.cheatsheet_path: str = os.path.join(self.store_path, self.cheatsheet_file)

        self.top_k: int = int(cfg.get("top_k", 1))

        self.model = cfg.get("model") 
        self.embedding_model_name = cfg.get("embedding_model", 'sentence-transformers/all-MiniLM-L6-v2')
        self.embedding_cache_dir = cfg.get("embedding_cache_dir", './storage/models')
        
        self.embedding_model = None
        self._records: List[Dict[str, Any]] = [] 
        self._embs: Optional[np.ndarray] = None  

    def _load_memories_from_json(self):
        if os.path.exists(self.records_path):
            try:
                with open(self.records_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._records = data.get('memories', [])
                    embeddings_list = data.get('embeddings', [])
                    
                    if embeddings_list:
                        self._embs = np.array(embeddings_list, dtype=np.float32)
                        print(f"Loaded {len(self._records)} memories and embeddings from {self.records_path}")
                    else:
                        self._embs = None
                        print(f"Loaded {len(self._records)} memories from {self.records_path} (no embeddings found).")
                        
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {self.records_path}. Starting with empty memory.", file=sys.stderr)
                self._records = []
                self._embs = None
            except Exception as e:
                print(f"Error loading memories: {e}. Starting fresh.", file=sys.stderr)
                self._records = []
                self._embs = None
        else:
            print("No memory file found. Starting with empty memory.")
            self._records = []
            self._embs = None

    def _save_memories_to_json(self):
        try:
            db_dir = os.path.dirname(self.records_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            
            embeddings_list = []
            if self._embs is not None and self._embs.size > 0:
                embeddings_list = self._embs.tolist()

            data = {
                'memories': self._records,
                'embeddings': embeddings_list
            }
            
            with open(self.records_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"Error saving memories to {self.records_path}: {e}", file=sys.stderr)

    def initialize(self) -> bool:
        _ensure_dir(self.store_path)
        
        self.embedding_model = load_embedding_model(
            model_name=self.embedding_model_name,
            cache_dir=self.embedding_cache_dir
        )

        self._load_memories_from_json()

        if not os.path.exists(self.cheatsheet_path):
            _write_text(self.cheatsheet_path, "")
        
        return True

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts or self.embedding_model is None:
            return np.array([])
        vecs = self.embedding_model.encode(texts, convert_to_numpy=True)
        return vecs.astype(np.float32)

    def _chat_complete(self, prompt: str) -> str:
        if self.model is None:
            print("[WARN] No LLM model available for DynamicCheatsheetProvider.", file=sys.stderr)
            return ""
        try:
            resp = self.model([{"role": "user", "content": prompt}])
            content = getattr(resp, "content", str(resp))
            return str(content).strip()
        except Exception as e:
            print(f"[ERROR] LLM generation failed: {e}", file=sys.stderr)
            return ""

    def _reconstruct_trajectory_string(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return "No execution trajectory available"
        
        trajectory_parts = []
        trajectory_parts.append(f"Task: {trajectory_data.query}")
        trajectory_parts.append("")
        
        for i, step in enumerate(trajectory_data.trajectory, 1):
            step_type = step.get('type', 'step')
            content = step.get('content', '')
            trajectory_parts.append(f"Step {i} ({step_type}): {content}")
        
        if trajectory_data.result:
            trajectory_parts.append("")
            trajectory_parts.append(f"Final Result: {trajectory_data.result}")
        
        return "\n".join(trajectory_parts)

    def _summarize_trajectory_with_llm(self, trajectory_data: TrajectoryData) -> str:
        current_trajectory = self._reconstruct_trajectory_string(trajectory_data)
        if self.model is None:
            print("No LLM model provided for summarization. Falling back to full text.", file=sys.stderr)
            return current_trajectory
            
        is_correct = trajectory_data.metadata.get("is_correct", False)
        
        system_prompt = f"""Summarize this agent task execution trajectory step by step.

        Question: {trajectory_data.query}
        Final Result: {trajectory_data.result}
        Correctness: {'Correct' if is_correct else 'Wrong'}
        Trajectory: {current_trajectory}

        IMPORTANT: Provide a step-by-step summary in this format:

        Step 0: [Brief description of what happened in step 0, including memory guidance if any]
        Step 1: [Brief description of what happened in step 1, including tool calls and key observations]
        Step 2: [Brief description of what happened in step 2]
        ...

        After the step-by-step summary, add a brief conclusion about:
        - Overall approach taken
        - Whether memory guidance was effective
        - Why the task succeeded or failed

        Use actual step indices (0, 1, 2, ...) that match the trajectory array indices.
        Keep each step description to 1-2 sentences.
        Total length should be under 400 words."""
        
        try:
            resp = self.model([{"role": "user", "content": [{"type": "text", "text": system_prompt}]}])
            summary = getattr(resp, "content", str(resp)).strip()
            return summary if summary else current_trajectory
        except Exception as e:
            print(f"Error during trajectory summarization: {e}", file=sys.stderr)
            return current_trajectory

    def _search(self, qvec: np.ndarray, top_k: int) -> Tuple[List[int], List[float]]:
        if self._embs is None or self._embs.size == 0:
            return [], []
        if len(qvec.shape) == 1:
            qvec = qvec.reshape(1, -1)
            
        sims = cosine_similarity(qvec, self._embs)[0]
        idxs = np.argsort(-sims)[:top_k].tolist()
        scores = [float(sims[i]) for i in idxs]
        return idxs, scores

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status == MemoryStatus.IN:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4()))
            
        top_k = self.top_k
        query_text = (request.query or "").strip()
        
        qvec = self._embed_texts([query_text])[0]
        idxs, scores = self._search(qvec, top_k=top_k)

        selected: List[Dict[str, Any]] = []
        
        for i, sc in zip(idxs, scores):
            rec = dict(self._records[i])
            rec["_score"] = float(sc)
            selected.append(rec)

        if not selected:
            existing_cs = _read_text(self.cheatsheet_path).strip()
            
            return MemoryResponse(
                memories=[MemoryItem(
                    id=str(uuid.uuid4()),
                    content=existing_cs,
                    metadata={
                        "kind": "dynamic_cheatsheet",
                        "selected_count": 0,
                        "generation_skipped": True
                    },
                    type=MemoryItemType.TEXT,
                    score=0.0,
                )],
                memory_type=self.memory_type,
                total_count=1,
                request_id=str(uuid.uuid4()),
            )
        
        best = selected[0]
        traj_summary = best.get("trajectory_summary", "")
        
        trajectory_context = (
            f"Similarity: {best.get('_score'):.2f}\n"
            f"Content:\n{traj_summary}"
        )

        prev_cs = _read_text(self.cheatsheet_path).strip() or "(empty)"

        curator_prompt = (
f"""You are a "dynamic cheatsheet" curator.

Using the [previous cheatsheet] and ONE [similar query–trajectory], synthesize a concise, reusable cheatsheet for the CURRENT QUERY.

Guidelines:
- Extract only transferable heuristics, steps, checklists, and typical pitfalls.
- Capture process-level insights from the condensed trajectory.
- Stay domain-agnostic where possible.
- Prefer bullet points and micro-templates like “When X, first … then …”.
- **STRICT LIMIT: The cheatsheet MUST be under 200 words.**

Output ONLY the cheatsheet, wrapped in a single <cheatsheet>...</cheatsheet> block.

[Previous cheatsheet]
{prev_cs}

[Similar query–trajectory (Condensed)]
{trajectory_context}

[Current query]
{query_text}
"""
        )

        raw_response = self._chat_complete(curator_prompt)
        new_cheatsheet = _extract_tag(raw_response, "cheatsheet")
        
        if new_cheatsheet:
            _write_text(self.cheatsheet_path, new_cheatsheet)

        return MemoryResponse(
            memories=[MemoryItem(
                id=str(uuid.uuid4()),
                content=new_cheatsheet,
                metadata={"kind": "dynamic_cheatsheet", "selected_count": len(selected)},
                type=MemoryItemType.TEXT,
                score=1.0,
            )],
            memory_type=self.memory_type,
            total_count=1,
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        q = (trajectory_data.query or "").strip()
        if not q:
            raise ValueError("TrajectoryData.query must be non-empty.")

        summary_text = self._summarize_trajectory_with_llm(trajectory_data)

        q_emb = self._embed_texts([q])[0]
        rid = str(uuid.uuid4())

        rec = {
            "id": rid,
            "question": q,
            "trajectory_summary": summary_text,
            "meta": trajectory_data.metadata or {},
            "ts": int(time.time())
        }

        self._records.append(rec)
        if self._embs is None:
            self._embs = q_emb.reshape(1, -1)
        else:
            self._embs = np.vstack([self._embs, q_emb])

        self._save_memories_to_json()

        return True, f"ingested sample: id={rid}"