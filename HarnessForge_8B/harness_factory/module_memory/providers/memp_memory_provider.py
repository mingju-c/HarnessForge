# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import os
import json
import uuid
import time
import sys
import re
from typing import Any, Dict, List, Optional, Tuple, Callable

import numpy as np
from sentence_transformers import SentenceTransformer
from .model_loader import load_sentence_transformer
from sklearn.metrics.pairwise import cosine_similarity

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


def _extract_tag(text: str, tag: str = "script") -> str:
    m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE)
    return (m.group(1).strip() if m else text).strip()


def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                         cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    return load_sentence_transformer(
        model_name=model_name,
        cache_dir=cache_dir,
        allow_unavailable=SentenceTransformer is None,
    )


class MempMemoryProvider(BaseMemoryProvider):
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            raise ValueError("MempProvider requires an explicit config dict.")
        super().__init__(memory_type=MemoryType.MEMP, config=config)
        cfg = self.config
        
        self.store_path: str = cfg.get("store_path", "./memp_storage")
        self.db_path: str = os.path.join(self.store_path, cfg.get("records_file", "procedural_records.json"))

        self.model: Optional[Callable] = cfg.get("model")
        if self.model is None:
            print("Warning: 'model' (LLM callable) is not provided in config.")

        self.embedding_model_name: str = cfg.get("embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2")
        self.embedding_cache_dir: str = cfg.get("embedding_cache_dir", "./storage/models")
        self.embedding_model: Optional[SentenceTransformer] = None 
        self.embedding_dim: Optional[int] = None

        self.memories: List[Dict[str, Any]] = []
        self.embeddings_cache: Optional[np.ndarray] = None
        self._last_provided_cache: Dict[str, List[str]] = {}

    def _load_memories_from_json(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.memories = data.get('memories', [])
                    embeddings_list = data.get('embeddings', [])
                    
                    if embeddings_list:
                        self.embeddings_cache = np.array(embeddings_list)
                    else:
                        if self.embedding_dim is None:
                            self.embeddings_cache = np.empty((0, 0))
                        else:
                            self.embeddings_cache = np.empty((0, self.embedding_dim))
            except json.JSONDecodeError:
                self.memories = []
                self.embeddings_cache = np.empty((0, self.embedding_dim or 0))
            except Exception:
                self.memories = []
                self.embeddings_cache = np.empty((0, self.embedding_dim or 0))
        else:
            self.memories = []
            self.embeddings_cache = np.empty((0, self.embedding_dim or 0))

    def _save_memories_to_json(self):
        if self.embedding_model is None:
            return

        if self.embeddings_cache is None:
            embeddings_list = []
        else:
            embeddings_list = self.embeddings_cache.tolist()

        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            
            data = {
                'memories': self.memories,
                'embeddings': embeddings_list
            }
            
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"Error saving memories to {self.db_path}: {e}", file=sys.stderr)

    def initialize(self) -> bool:
        _ensure_dir(self.store_path)
        
        try:
            self.embedding_model = load_embedding_model(
                self.embedding_model_name, self.embedding_cache_dir
            )
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        except Exception as e:
            print(f"Failed to load embedding model: {e}", file=sys.stderr)
            return False
        
        self._load_memories_from_json()
        return True

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        if self.embedding_model is None:
            return np.array([], dtype=np.float32)
        if not texts:
            return np.array([], dtype=np.float32)
        try:
            vecs = self.embedding_model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
            return vecs.astype(np.float32)
        except Exception:
            return np.array([], dtype=np.float32)

    def _call_llm(self, prompt: str) -> str:
        if self.model is None:
            return "(LLM call failed: Model not configured)"
        
        messages = [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ]
        
        try:
            resp = self.model(messages)
            content = getattr(resp, "content", str(resp)).strip()
            if not content:
                return "(LLM returned empty response)"
            return content
        except Exception as e:
            return f"(LLM call error: {e})"
    
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

    def _generate_script_for_trace(self, trajectory_data: TrajectoryData) -> str:
        trace_txt = self._reconstruct_trajectory_string(trajectory_data)
        query = trajectory_data.query or ""
        
        if not trace_txt:
            return "(No trace available to generate script)"
        
        prompt = f"""
You are an expert in **distilling abstract procedural knowledge**.
Your task is to analyze the [Solution Trace] for a specific [Query] and extract the **underlying general strategy** used to solve it.

**Goal:** Create a generic, reusable "mental model" or "high-level script" that is significantly **shorter and more abstract** than a step-by-step summary.

**Guidelines:**
1.  **Abstract Away Specifics:** Remove all specific entities, numbers, names, or direct answers. Replace them with general categories (e.g., change "Searched for 'Elon Musk'" to "Search for the target entity").
2.  **Focus on Logic, Not Actions:** Do not list every click. Instead, capture the *logical flow* (e.g., "Information Retrieval -> Cross-Verification -> Calculation").
3.  **Ultra-Concise:** Use short bullet points. **The total output must be STRICTLY UNDER 100 WORDS.**
4.  **Format:** Output *strictly* wrapped in <script>...</script> tags.

[Query]
{query}

[Solution Trace]
{trace_txt}
"""
        
        try:
            raw_response = self._call_llm(prompt)
            script = _extract_tag(raw_response, "script")
            return script or "(Script generation failed)"
        except Exception:
            return "(Script generation error)"

    def _summarize_trajectory_with_llm(self, trajectory_data: TrajectoryData) -> str:
        current_trajectory = self._reconstruct_trajectory_string(trajectory_data)
        
        if self.model is None:
            return current_trajectory
            
        is_correct = trajectory_data.metadata.get("is_correct", False)
        
        system_prompt = (
f"""Generate an ultra-concise summary of the agent's actions.

Question: {trajectory_data.query}
Final Result: {trajectory_data.result}
Correctness: {'Correct' if is_correct else 'Wrong'}
Trajectory: {current_trajectory}

IMPORTANT: Provide a "bare bones" step-by-step summary. Focus *only* on the single most important action, tool call, or observation for each step. Omit all filler words.

Format:
Step 0: [Key action/thought (e.g., "Initial plan")]
Step 1: [Key action/tool (e.g., "Called search(X)")]
Step 2: [Key observation/result (e.g., "Found Y")]
...

Rules:
* Use actual step indices (0, 1, 2, ...).
* **Each step description MUST be a single short phrase or sentence (max 10 words).**
* After the steps, add a **single sentence conclusion** explaining the final outcome (success/failure reason).
* Keep the **total length under 150 words**.
"""
)
        
        messages = [
            {"role": "user", "content": [{"type": "text", "text": system_prompt}]}
        ]
        
        try:
            resp = self.model(messages)
            summary = getattr(resp, "content", str(resp)).strip()
            
            if not summary:
                return current_trajectory
                
            return summary
            
        except Exception:
            return current_trajectory

    def _search(self, qvec: np.ndarray, top_k: int) -> Tuple[List[int], List[float]]:
        if self.embeddings_cache is None or self.embeddings_cache.size == 0:
            return [], []
        
        k = min(top_k, self.embeddings_cache.shape[0])
        
        sims = cosine_similarity(qvec, self.embeddings_cache)[0]
        idxs = np.argsort(-sims)[:k].tolist()
        scores = [float(sims[i]) for i in idxs]
        return idxs, scores

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status != MemoryStatus.BEGIN:
            return MemoryResponse(
                memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4())
            )
        
        top_k = 1
        query_text = (request.query or "").strip()

        qvec = self._embed_texts([query_text])
        
        if qvec.size == 0:
             return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4()))

        idxs, scores = self._search(qvec, top_k=top_k)

        selected: List[Dict[str, Any]] = []
        for i, sc in zip(idxs, scores):
            rec = dict(self.memories[i])
            rec["_score"] = float(sc)
            selected.append(rec)
            
        if selected and query_text:
            top_mem_ids = [rec.get("id") for rec in selected if rec.get("id")]
            if top_mem_ids:
                self._last_provided_cache[query_text] = top_mem_ids
        
        memories: List[MemoryItem] = []
        for rec in selected:
            script = rec.get("procedural_script", "(No script available)")
            concrete_summary = rec.get("concrete_steps_summary")
            
            if not concrete_summary:
                concrete_summary = "No concrete_steps_summary available"
            
            content = (
                f"--- Retrieved Procedural Memory (Score: {rec.get('_score', 0.0):.4f}) ---\n"
                f"**[High-Level Script]**\n{script}\n\n"
                f"**[Concrete Steps (Example)]**\n{concrete_summary}\n"
                f"--- End of Retrieved Memory ---"
            )
            
            metadata_kind = "procedural_combined"

            memories.append(
                MemoryItem(
                    id=rec.get("id", str(uuid.uuid4())),
                    content=content,
                    metadata={
                        "kind": metadata_kind, 
                        "score": rec.get("_score", None),
                        "original_question": rec.get("question")
                    },
                    type=MemoryItemType.TEXT,
                    score=rec.get("_score", None),
                )
            )
        
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def _add_new_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        q = (trajectory_data.query or "").strip()
        if not q:
            raise ValueError("TrajectoryData.query must be non-empty.")
        
        meta = trajectory_data.metadata or {}

        q_emb_array = self._embed_texts([q])
        if q_emb_array.size == 0:
             return False, "Ingestion failed: Query embedding returned empty vector."
        q_emb = q_emb_array[0]

        new_script = self._generate_script_for_trace(trajectory_data)
        new_concrete_summary = self._summarize_trajectory_with_llm(trajectory_data)

        rid = str(uuid.uuid4())

        rec = {
            "id": rid,
            "question": q,
            "procedural_script": new_script,
            "concrete_steps_summary": new_concrete_summary,
            "meta": meta,
            "ts": int(time.time()),
        }
        
        _ensure_dir(self.store_path)
        
        self.memories.append(rec)
        
        if self.embeddings_cache is None or self.embeddings_cache.size == 0:
            self.embeddings_cache = q_emb.reshape(1, -1)
        else:
            self.embeddings_cache = np.vstack([self.embeddings_cache, q_emb])

        self._save_memories_to_json()

        return True, f"Ingested new sample: id={rid}"

    def _adjust_memory(self, original_id: str, failed_trajectory_data: TrajectoryData) -> tuple[bool, str]:
        original_record = None
        record_index = -1
        for i, rec in enumerate(self.memories):
            if rec.get("id") == original_id:
                original_record = rec
                record_index = i
                break

        if original_record is None or record_index == -1:
            return False, f"Adjustment failed: Original memory ID {original_id} not found"

        original_query = original_record.get("question", "")
        original_script = original_record.get("procedural_script", "")
        original_summary = original_record.get("concrete_steps_summary", "")

        new_failed_query = (failed_trajectory_data.query or "").strip()
        new_failed_trace_txt = self._reconstruct_trajectory_string(failed_trajectory_data)

        prompt = f"""
You are a memory analyst. An agent used an [Original Memory] as guidance for a [New Query], but this resulted in a [New Failed Trace].

Your goal is to analyze the failure, extract the *lesson* (heuristic or pitfall), and use it to *refine* the [Original Memory]. 

The original memory must *still* be a valid guide for the [Original Query], but it should be updated (e.g., with a new warning or refined step) to prevent similar failures in the future.

[Original Memory (for Original Query)]
Original Query: {original_query}
Original Script (High-Level): {original_script}
Original Summary (Concrete Steps): {original_summary}

[Failure Context (for New Query)]
New Query (that failed): {new_failed_query}
New Failed Trace: {new_failed_trace_txt}

---
**CRITICAL CONSTRAINTS:**
1. **Strict Length Limit (Script):** The revised 'procedural_script' must be **STRICTLY UNDER 100 WORDS**. Use concise bullet points.
2. **Strict Length Limit (Summary):** The revised 'concrete_steps_summary' must be **STRICTLY UNDER 150 WORDS**.
3. **Condense, Don't Just Append:** Do not simply add text to the end. You must REWRITE and CONDENSE the content to integrate the new lesson while staying within the word limits.
4. **Maintain Abstraction:** The script remains a high-level mental model.

Output the revised procedural memory strictly in the following JSON format:
{{
  "procedural_script": "The revised script (must be < 100 words)...",
  "concrete_steps_summary": "The revised summary (must be < 150 words)..."
}}
"""

        try:
            raw_revised_json = self._call_llm(prompt)
            
            if "```json" in raw_revised_json:
                match = re.search(r"```json(.*?)```", raw_revised_json, re.DOTALL)
                if match:
                    raw_revised_json = match.group(1).strip()
            elif "```" in raw_revised_json:
                 match = re.search(r"```(.*?)```", raw_revised_json, re.DOTALL)
                 if match:
                    raw_revised_json = match.group(1).strip()

            if raw_revised_json.startswith("(LLM call"):
                raise ValueError(f"LLM call failed: {raw_revised_json}")
                
            revised_data = json.loads(raw_revised_json)
            
            new_script = revised_data.get("procedural_script")
            new_summary = revised_data.get("concrete_steps_summary")

            if not new_script or not new_summary:
                raise ValueError("LLM returned invalid revision data format (missing script or summary).")

        except Exception as e:
            return False, f"Adjustment: LLM revision failed: {e}"

        original_record["procedural_script"] = new_script
        original_record["concrete_steps_summary"] = new_summary
        original_record["ts"] = int(time.time())
        original_record.setdefault("meta", {})["status"] = "revised_after_failure"
        original_record["meta"]["revision_count"] = original_record["meta"].get("revision_count", 0) + 1
        
        self.memories[record_index] = original_record
        self._save_memories_to_json()

        return True, f"Adjustment successful: Memory {original_id} has been revised."

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        meta = trajectory_data.metadata or {}
        raw_status = meta.get("is_correct", "true") 
        status = str(raw_status).lower()

        if status == "false":
            ids_to_adjust: List[str] = []
            
            query = (trajectory_data.query or "").strip()
            if query:
                cached_mem_ids = self._last_provided_cache.get(query)
                if cached_mem_ids:
                    ids_to_adjust.extend(cached_mem_ids)
            
            if ids_to_adjust:
                success_count = 0
                failure_count = 0
                for mem_id in ids_to_adjust:
                    success, msg = self._adjust_memory(mem_id, trajectory_data)
                    if success:
                        success_count += 1
                    else:
                        failure_count += 1
                
                return True, f"Adjustment complete for {len(ids_to_adjust)} IDs. Success: {success_count}, Failure: {failure_count}."
            
            else:
                return True, "Task failed, but no associated memory ID found for adjustment."

        else:
            return self._add_new_memory(trajectory_data)