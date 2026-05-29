# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import uuid
import time
import logging
import numpy as np
from typing import Any, Dict, List, Optional
import re

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    from ..base_memory import BaseMemoryProvider
    from ..memory_types import (
        MemoryRequest, MemoryResponse, MemoryItem, 
        MemoryItemType, TrajectoryData, MemoryType,
        MemoryStatus
    )
except Exception:
    from base_memory import BaseMemoryProvider
    from memory_types import (
        MemoryRequest, MemoryResponse, MemoryItem, 
        MemoryItemType, TrajectoryData, MemoryType,
        MemoryStatus
    )

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                          cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    if SentenceTransformer is None:
        logger.warning("sentence-transformers not available, AgentWorkflowMemory will use lexical fallback.")
        return None

    os.makedirs(cache_dir, exist_ok=True)
    local_model_path = os.path.join(cache_dir, model_name.replace('/', '_'))

    try:
        if os.path.exists(local_model_path) and os.listdir(local_model_path):
            logger.info(f"Loading embedding model from local cache: {local_model_path}")
            return SentenceTransformer(local_model_path)
    except Exception as e:
        logger.warning(f"Failed to load local model: {e}. Attempting download...")

    try:
        logger.info(f"Downloading model from Hugging Face: {model_name}")
        model = SentenceTransformer(model_name)
        logger.info(f"Saving model to local cache: {local_model_path}")
        model.save(local_model_path)
        return model
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        raise RuntimeError(f"Could not load embedding model {model_name}: {e}")

def _now_ts() -> float:
    return time.time()

def cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    if doc_vecs.size == 0:
        return np.array([])
        
    norm_query = np.linalg.norm(query_vec)
    norm_docs = np.linalg.norm(doc_vecs, axis=1)
    
    norm_docs[norm_docs == 0] = 1e-10
    if norm_query == 0:
        norm_query = 1e-10

    dot_products = np.dot(doc_vecs, query_vec)
    
    similarities = dot_products / (norm_docs * norm_query)
    return similarities

class AgentWorkflowMemoryProvider(BaseMemoryProvider):
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            raise ValueError("AgentWorkflowMemoryProvider requires an explicit config dict.")
        super().__init__(memory_type=MemoryType.AGENT_WORKFLOW_MEMORY, config=config)
        
        required = ["store_path", "top_k", "enable_induction"]
        if any(k not in self.config for k in required):
            raise KeyError(f"Missing required config keys: {[k for k in required if k not in self.config]}")

        model_name = self.config.get("embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2")
        cache_dir = self.config.get("embedding_cache_dir", "./storage/models")
        self._embedding_model = load_embedding_model(model_name=model_name, cache_dir=cache_dir)

        self.model = self.config.get("model")
        if not self.model:
             raise ValueError("Config must contain 'model' (the initialized LLM object).")

        self._items: List[MemoryItem] = []
        self._cached_embeddings: Optional[np.ndarray] = None

    @staticmethod
    def _lexical_score(query: str, content: str) -> float:
        query_tokens = set(re.findall(r"\w+", query.lower()))
        content_tokens = set(re.findall(r"\w+", content.lower()))
        if not query_tokens or not content_tokens:
            return 0.0
        return len(query_tokens & content_tokens) / len(query_tokens)

    def _load_store(self) -> None:
        path = self.config["store_path"]
        if not os.path.exists(path):
            logger.info("No memory file found. Starting with empty memory.")
            self._items = []
            self._cached_embeddings = None
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self._items = []
            for rec in data.get('memories', []):
                self._items.append(MemoryItem(
                    id=rec.get("id") or str(uuid.uuid4()),
                    content=rec.get("content"),
                    metadata=rec.get("metadata") or {},
                    score=None,
                    type=MemoryItemType(rec.get("type") or MemoryItemType.TEXT.value),
                ))

            embeddings_list = data.get('embeddings', [])
            
            if embeddings_list and len(embeddings_list) == len(self._items):
                self._cached_embeddings = np.array(embeddings_list, dtype=np.float32)
                logger.info(f"Loaded {len(self._items)} memories and embeddings from {path}")
            else:
                self._cached_embeddings = None
                logger.info(f"Loaded {len(self._items)} memories from {path} (embeddings mismatch or missing).")

        except Exception as e:
            logger.error(f"Error loading memories: {e}. Starting fresh.")
            self._items = []
            self._cached_embeddings = None

    def _save_store(self) -> None:
        path = self.config["store_path"]
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            
            memories_data = [{
                "id": item.id,
                "content": item.content,
                "metadata": item.metadata,
                "type": item.type.value,
            } for item in self._items]
            
            embeddings_data = []
            if self._cached_embeddings is not None:
                embeddings_data = self._cached_embeddings.tolist()

            data = {
                'memories': memories_data,
                'embeddings': embeddings_data 
            }
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error saving memories to {path}: {e}")

    def _ensure_embeddings(self) -> None:
        if self._embedding_model is None:
            self._cached_embeddings = None
            return

        current_count = len(self._items)
        if current_count == 0:
            self._cached_embeddings = None
            return

        if self._cached_embeddings is not None and len(self._cached_embeddings) == current_count:
            return

        logger.info(f"Embeddings missing or out of sync. Re-calculating for {current_count} items...")
        
        texts = [str(it.content or "") for it in self._items]
        
        embeddings = self._embedding_model.encode(texts, convert_to_numpy=True)
        self._cached_embeddings = embeddings
        
        self._save_store()

    def _reconstruct_trajectory_string(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return "No execution trajectory available"
        
        trajectory_parts = []
        task_desc = getattr(trajectory_data, 'query', None) or getattr(trajectory_data, 'input', None) or "Unknown Task"
        trajectory_parts.append(f"Task: {task_desc}")
        trajectory_parts.append("")
        
        for i, step in enumerate(trajectory_data.trajectory, 1):
            if isinstance(step, dict):
                step_type = step.get('type', 'step')
                content = step.get('content', '')
            else:
                step_type = getattr(step, 'type', 'step')
                content = getattr(step, 'content', str(step))
            
            trajectory_parts.append(f"Step {i} ({step_type}): {content}")
        
        if trajectory_data.result:
            trajectory_parts.append("")
            trajectory_parts.append(f"Final Result: {trajectory_data.result}")
        
        return "\n".join(trajectory_parts)

    def _induce_workflow(self, data: TrajectoryData) -> Optional[str]:
        if not self.config["enable_induction"]:
            return None

        formatted_trajectory = self._reconstruct_trajectory_string(data)
        
        prompt = f"""You are an expert analyst for tasks.
Your goal is to extract a generic, reusable workflow from the specific execution trajectory provided below.

Guidelines:
1. **Abstraction**: Convert specific inputs (e.g., filenames, URLs, numbers) into descriptive variable names.
2. **Invariance**: Keep the logical steps and tool names invariant.
3. **Format**: Output strictly valid JSON containing the workflow text.

Output JSON Schema:
{{
    "workflow": "The concise text summary of the steps (under 200 words)"
}}

Trajectory to analyze:
{formatted_trajectory}"""
        
        messages = [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ]
        
        response = self.model(messages)
        refined_query = getattr(response, "content", str(response)).strip()
        
        cleaned_text = refined_query.replace("```json", "").replace("```", "").strip()
        
        try:
            result = json.loads(cleaned_text)
            return result.get("workflow")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON output: {e}")
            return None

    def initialize(self) -> bool:
        self._load_store()
        self._ensure_embeddings() 
        logger.info("AgentWorkflowMemory initialized with %d items.", len(self._items))
        return True

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status != MemoryStatus.BEGIN:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=len(self._items))

        if not self._items:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=len(self._items))

        k = int(self.config["top_k"])
        scores: Optional[np.ndarray] = None
        if self._embedding_model is not None and self._cached_embeddings is not None and len(self._cached_embeddings) == len(self._items):
            query_embedding = self._embedding_model.encode([request.query], convert_to_numpy=True)[0]
            scores = cosine_similarity(query_embedding, self._cached_embeddings)
            top_indices = np.argsort(scores)[::-1][:k]
        else:
            ranked = sorted(
                (
                    (idx, self._lexical_score(request.query, str(item.content or "")))
                    for idx, item in enumerate(self._items)
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            top_indices = [idx for idx, score in ranked[:k] if score > 0]
            if not top_indices and self._items:
                top_indices = list(range(min(k, len(self._items))))

        results: List[MemoryItem] = []
        for idx in top_indices:
            score = float(scores[idx]) if scores is not None else self._lexical_score(request.query, str(self._items[idx].content or ""))
            
            original_item = self._items[idx]
            
            result_item = MemoryItem(
                id=original_item.id,
                content=original_item.content,
                metadata=original_item.metadata,
                score=score,
                type=original_item.type
            )
            results.append(result_item)

        return MemoryResponse(
            memories=results,
            memory_type=self.memory_type,
            total_count=len(self._items),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        meta = trajectory_data.metadata or {}
        
        if not meta.get("is_correct", False):
            return False, "Skipped: Trajectory not correct"

        abstracted_text = self._induce_workflow(trajectory_data)
        
        query = trajectory_data.query
        
        if abstracted_text and abstracted_text.strip():
            workflow_content = abstracted_text.strip()
        else:
            workflow_content = self._reconstruct_trajectory_string(trajectory_data)

        wf_text = f"Query: {query}\nWorkflow: {workflow_content}"
        meta.setdefault("created_at", _now_ts())

        item = MemoryItem(
            id=str(uuid.uuid4()),
            content=wf_text,
            metadata=meta,
            type=MemoryItemType.TEXT,
        )

        self._items.append(item)
        if self._embedding_model is not None:
            new_embedding = self._embedding_model.encode([wf_text], convert_to_numpy=True)[0]
            if self._cached_embeddings is None:
                self._cached_embeddings = np.array([new_embedding])
            else:
                self._cached_embeddings = np.vstack([self._cached_embeddings, new_embedding])

        self._save_store()

        return True, f"Ingested {item.content[:50]}..."
