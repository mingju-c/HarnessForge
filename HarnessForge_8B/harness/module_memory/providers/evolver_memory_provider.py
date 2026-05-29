# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import uuid
import time
import logging
import sys
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

from sklearn.metrics.pairwise import cosine_similarity

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    raise ImportError("Please install sentence-transformers: pip install sentence-transformers")

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

logger = logging.getLogger(__name__)

def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                         cache_dir: str = './storage/models') -> SentenceTransformer:
    os.makedirs(cache_dir, exist_ok=True)
    local_model_path = os.path.join(cache_dir, model_name.replace('/', '_'))

    try:
        if os.path.exists(local_model_path) and os.listdir(local_model_path):
            logger.info(f"Loading model from local cache: {local_model_path}")
            return SentenceTransformer(local_model_path)
    except Exception as e:
        logger.warning(f"Failed to load local model: {e}")

    try:
        logger.info(f"Downloading model from Hugging Face: {model_name}")
        model = SentenceTransformer(model_name)
        logger.info(f"Saving model to local cache: {local_model_path}")
        model.save(local_model_path)
        return model
    except Exception as e:
        logger.error(f"Model download failed: {e}")
        raise RuntimeError(f"Unable to load embedding model {model_name}: {e}")

DESCRIPTION_PART_SEPARATOR = "[DESCRIPTION]:"
STRUCTURED_PART_SEPARATOR = "[STRUCTURE]:"
SPECIAL_TOKENS_FILTER = [
    "<code>",
    "</code>",
    "Thought:",
    "Observation:",
    "MessageRole.",
    DESCRIPTION_PART_SEPARATOR,
    STRUCTURED_PART_SEPARATOR
]

class EvolverMemoryProvider(BaseMemoryProvider):
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            raise ValueError("EvolverMemoryProvider requires an explicit config dict.")
        super().__init__(memory_type=MemoryType.EVOLVER, config=config)
        cfg = self.config
        
        self.model = cfg.get("model")
        if not self.model:
             raise ValueError("Config must contain 'model' (the initialized LLM object).")

        self.store_path: str = cfg.get("store_path", "./evolver_memory")
        self.records_file: str = cfg.get("records_file", "principle_records.json")
        self.records_path: str = os.path.join(self.store_path, self.records_file)

        self.embedding_model_name = cfg.get("embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2")
        self.embedding_cache_dir = cfg.get("embedding_cache_dir", "./storage/models")
        self._embedding_client = load_embedding_model(
            model_name=self.embedding_model_name, 
            cache_dir=self.embedding_cache_dir
        )

        self.search_top_k: int = int(cfg.get("search_top_k", 1))
        self.max_pos_examples: int = int(cfg.get("max_pos_examples", 1))
        self.max_neg_examples: int = int(cfg.get("max_neg_examples", 1))
        self.prune_threshold: float = float(cfg.get("prune_threshold", 0.2))

        self._records: List[Dict[str, Any]] = [] 
        self._embs: Optional[np.ndarray] = None
        self._last_provided_cache: Dict[str, List[str]] = {} 

    def _reconstruct_trajectory_string(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return "No execution trajectory available"
        
        trajectory_parts = []
        query_text = trajectory_data.query or getattr(trajectory_data, 'input', "Unknown Task")
        trajectory_parts.append(f"Task: {query_text}")
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

    def initialize(self) -> bool:
        if os.path.exists(self.records_path):
            try:
                with open(self.records_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    self._records = data.get('memories', data.get('principles', []))
                    
                    embeddings_list = data.get('embeddings', [])
                    
                    if embeddings_list and len(embeddings_list) == len(self._records):
                        self._embs = np.array(embeddings_list, dtype=np.float32)
                        logger.info(f"Loaded {len(self._records)} memories and embeddings from {self.records_path}")
                    else:
                        logger.info(f"No embeddings found in file. Re-computing for {len(self._records)} records...")
                        
                        descriptions = [rec.get("description", "") for rec in self._records]
                        if descriptions:
                            self._embs = self._embed_texts(descriptions)
                            logger.info(f"Re-computed embeddings. Shape: {self._embs.shape}")
                        else:
                            self._embs = np.empty((0, 384), dtype=np.float32)

            except json.JSONDecodeError:
                print(f"Warning: Could not parse {self.records_path}. Starting with empty memory.", file=sys.stderr)
                self._records = []
                self._embs = np.empty((0, 384), dtype=np.float32)
            except Exception as e:
                print(f"Error loading memories: {e}. Starting fresh.", file=sys.stderr)
                self._records = []
                self._embs = np.empty((0, 384), dtype=np.float32)
        else:
            logger.info("No memory file found. Starting with empty memory.")
            self._records = []
            self._embs = np.empty((0, 384), dtype=np.float32)
            
        return True

    def _save_store(self) -> None:
        try:
            db_dir = os.path.dirname(self.records_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            
            data = {
                'memories': self._records,
            }
            
            with open(self.records_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"Error saving memories to {self.records_path}: {e}", file=sys.stderr)

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.array([], dtype=np.float32)
        try:
            vecs = self._embedding_client.encode(texts, convert_to_numpy=True)
            return vecs.astype(np.float32)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return np.array([], dtype=np.float32)

    def _chat_complete(self, prompt: str) -> str:
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
            
            response = self.model(messages)
            content = getattr(response, "content", str(response))
            return content
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""

    def _compact_trajectory(self, trajectory_data: TrajectoryData) -> str:
        try:
            trace_txt = self._reconstruct_trajectory_string(trajectory_data)
            if not trace_txt:
                return "[(Compaction failed: Empty trace)]"

            prompt = f"""
You are a Technical Incident Reporter.
Compress this log into a **Single Pure-Text Narrative** (Max 150 words).

### Guidelines:
1.  **Fluid Narrative:** Combine the error trigger, the corrective action, and the result into natural sentences.
2.  **Start with the Trouble:** Begin the sentence directly with the specific error or obstacle encountered (e.g., "Facing a RuntimeError...").
3.  **Technical Precision:** Retain specific **Error Names**, **Tool Names**, and **Key Arguments** used to solve the issue.
4.  **Pruning:** Remove arithmetic calculations and generic internal thoughts.

### Input Log:
{trace_txt}

### Output:
(A concise technical paragraph describing the resolution.)
"""
            
            compressed_text = self._chat_complete(prompt)
            return compressed_text.strip() if compressed_text else "[(Compaction failed: Empty LLM response)]"

        except Exception as e_llm:
            logger.error(f"LLM compaction failed: {e_llm}")
            return "[(Compaction failed: LLM error)]"

    def _parse_summarization_response(self, response: str) -> Optional[Tuple[str, List[List[str]]]]:
        try:
            if DESCRIPTION_PART_SEPARATOR not in response or STRUCTURED_PART_SEPARATOR not in response:
                logger.warning("Response missing separators. Returning raw text as description.")
                clean_text = response.replace(DESCRIPTION_PART_SEPARATOR, "").replace(STRUCTURED_PART_SEPARATOR, "").strip()
                return clean_text, []

            parts = response.split(STRUCTURED_PART_SEPARATOR)
            
            if len(parts) < 2:
                return response.replace(DESCRIPTION_PART_SEPARATOR, "").strip(), []

            description_part = parts[0].replace(DESCRIPTION_PART_SEPARATOR, "").strip()
            structure_json_str = parts[1].strip()

            structure_json_str = structure_json_str.replace("```json", "").replace("```", "").strip()

            try:
                structure = json.loads(structure_json_str)
                if not isinstance(structure, list):
                    structure = []
            except json.JSONDecodeError as je:
                logger.warning(f"Failed to parse structure JSON: {je}")
                structure = []

            return description_part, structure

        except Exception as e:
            logger.error(f"Summarization parsing exception: {e}")
            return None

    def _summarize_trajectory_to_principle(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, Any]]:
        meta = trajectory_data.metadata or {}
        is_success = str(meta.get("is_correct", "true")).lower() == "true"
        
        p_type = "guiding" if is_success else "cautionary"
        
        trace_txt = self._reconstruct_trajectory_string(trajectory_data)
        if not trace_txt:
            return None

        if is_success:
            prompt = f"""
You are an expert in analyzing interaction logs to distill generalizable wisdom.
Analyze the following successful interaction trajectory. Your goal is to extract a "Guiding Principle" from it.

A "Guiding Principle" has two parts:
1.  A concise, one-sentence natural language description. This is the core advice.
2.  A structured representation of the key steps or logic, as a list of simple (subject, predicate, object) triplets.

[Trajectory Log]:
{trace_txt}

Final Outcome: SUCCESS

**Your Task:**
Based on the trajectory, generate the Guiding Principle.
First, on a new line, write `{DESCRIPTION_PART_SEPARATOR}`.
Then, write the one-sentence description of the pitfall.
Then, on a new line, write `{STRUCTURED_PART_SEPARATOR}`.
Finally, provide the structured triplets describing the failure pattern in a valid JSON list format.

[Example]:
{DESCRIPTION_PART_SEPARATOR}
When a file download fails with a 404 error, do not immediately retry the download; instead, verify the source URL's validity first.
{STRUCTURED_PART_SEPARATOR}
[
  ["file download", "results_in", "404 error"],
  ["immediate_retry", "is", "ineffective"],
  ["correct_action", "is", "verify URL"]
]

[Output]:
"""
        else:
            prompt = f"""
You are an expert in analyzing interaction logs to find the root cause of failures.
Analyze the following failed interaction trajectory. Your goal is to extract a "Cautionary Principle" from it.

A "Cautionary Principle" has two parts:
1.  A concise, one-sentence description of the key mistake to avoid and under what circumstances.
2.  A structured representation of the failure pattern, as a list of simple (subject, predicate, object) triplets.

[Trajectory Log]:
{trace_txt}

Final Outcome: FAILURE

**Your Task:**
Based on the trajectory, generate the Cautionary Principle.
First, on a new line, write `{DESCRIPTION_PART_SEPARATOR}`.
Then, write the one-sentence description of the pitfall.
Then, on a new line, write `{STRUCTURED_PART_SEPARATOR}`.
Finally, provide the structured triplets describing the failure pattern in a valid JSON list format.

[Example]:
{DESCRIPTION_PART_SEPARATOR}
When a file download fails with a 404 error, do not immediately retry the download; instead, verify the source URL's validity first.
{STRUCTURED_PART_SEPARATOR}
[
  ["file download", "results_in", "404 error"],
  ["immediate_retry", "is", "ineffective"],
  ["correct_action", "is", "verify URL"]
]

[Output]:
"""
        
        raw_response = self._chat_complete(prompt)
        parsed = self._parse_summarization_response(raw_response)
        
        if parsed:
            description, structure = parsed
            return {
                "description": description,
                "structure": structure,
                "type": p_type
            }
        return None

    def _are_principles_semantically_same(self, desc1: str, desc2: str) -> bool:
        if not desc1 or not desc2:
            return False
            
        prompt = f"""
You are a semantic analysis expert. Determine if two principles describe the same core idea, even if they use different words.

Principle A: "{desc1}"
Principle B: "{desc2}"

Do Principle A and Principle B describe the same essential advice or warning?
Please answer with only "Yes" or "No".
"""
        
        response = self._chat_complete(prompt)
        
        return "yes" in response.strip().lower()
            
    def _calculate_principle_score(self, rec: Dict[str, Any]) -> float:
        c_succ = rec.get("success_count", 0)
        c_use = rec.get("usage_count", 0)
        return (c_succ + 1.0) / (c_use + 2.0)
        
    def _find_record_index_by_id(self, principle_id: str) -> int:
        for i, rec in enumerate(self._records):
            if rec.get("id") == principle_id:
                return i
        return -1

    def _update_scores_for_provided_principles(self, query: str, is_success: bool) -> bool:
        if not query or query not in self._last_provided_cache:
            return False 

        ids_to_update = self._last_provided_cache.get(query, [])
        if not ids_to_update:
            return False
            
        updated_count = 0
        for p_id in ids_to_update:
            record_index = self._find_record_index_by_id(p_id)
            if record_index != -1:
                record = self._records[record_index]
                record["usage_count"] = record.get("usage_count", 0) + 1
                if is_success:
                    record["success_count"] = record.get("success_count", 0) + 1
                updated_count += 1
        
        if updated_count > 0:
            self._save_store()
            
        self._last_provided_cache.pop(query, None)
        return updated_count > 0

    def _prune_low_score_principles(self, threshold: float) -> None:
        if not self._records:
            return

        logger.info(f"Pruning principles with score < {threshold}...")
        
        kept_records: List[Dict[str, Any]] = []
        kept_embs: List[np.ndarray] = []
        deleted_count = 0

        for i, rec in enumerate(self._records):
            score = self._calculate_principle_score(rec)
            if score >= threshold:
                kept_records.append(rec)
                if self._embs is not None and i < len(self._embs):
                    kept_embs.append(self._embs[i])
            else:
                deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Pruned {deleted_count} low-score principles.")
            self._records = kept_records
            self._embs = np.vstack(kept_embs) if kept_embs else np.empty((0, 384), dtype=np.float32)
            self._save_store()

    def _search(self, qvec: np.ndarray, top_k: int) -> Tuple[List[int], List[float]]:
        if self._embs is None or self._embs.size == 0:
            return [], []
        
        k = min(top_k, self._embs.shape[0])
        if len(qvec.shape) == 1:
            qvec = qvec.reshape(1, -1)

        sims = cosine_similarity(qvec, self._embs)[0] 
        idxs = np.argsort(-sims)[:k].tolist()
        scores = [float(sims[i]) for i in idxs]
        return idxs, scores

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status != MemoryStatus.BEGIN:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4()))
        
        query_text = (request.query or "").strip()
        if not query_text:
             return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4()))

        qvec = self._embed_texts([query_text])
        if qvec.size == 0:
             return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4()))

        idxs, scores = self._search(qvec, top_k=self.search_top_k)

        selected: List[Dict[str, Any]] = []
        for i, sc in zip(idxs, scores):
            if i >= len(self._records): continue
            rec = dict(self._records[i])
            description = rec.get("description", "")
            
            if any(token in description for token in SPECIAL_TOKENS_FILTER):
                continue

            rec["_score"] = float(sc)
            rec["_principle_quality_score"] = self._calculate_principle_score(rec)
            selected.append(rec)
        
        if selected:
            top_mem_ids = [rec.get("id") for rec in selected if rec.get("id")]
            if top_mem_ids:
                self._last_provided_cache[query_text] = top_mem_ids
        
        memories: List[MemoryItem] = []
        for rec in selected:
            p_type = rec.get("type", "principle")
            description = rec.get("description", "(No description)")
            structure = rec.get("structure", [])
            sim_score = rec.get("_score", 0.0)
            quality_score = rec.get("_principle_quality_score", 0.0)
            
            positive_examples: List[str] = []
            negative_examples: List[str] = []
            source_trajectories = rec.get("source_trajectories", [])
            
            for traj in reversed(source_trajectories):
                compressed_trace = traj.get("compressed_trace", "{}")
                is_success = str(traj.get("metadata", {}).get("is_correct", "true")).lower() == "true"
                
                if is_success and len(positive_examples) < self.max_pos_examples:
                    positive_examples.append(compressed_trace)
                elif not is_success and len(negative_examples) < self.max_neg_examples:
                    negative_examples.append(compressed_trace)
                
                if len(positive_examples) >= self.max_pos_examples and len(negative_examples) >= self.max_neg_examples:
                    break

            content_parts = [
                f"--- Retrieved {p_type.capitalize()} Principle (Similarity: {sim_score:.4f}, Quality Score: {quality_score:.4f}) ---",
                f"**[Principle]**\n{description}",
            ]
            
            if structure:
                content_parts.append("\n**[Structure/Pattern]**")
                for triplet in structure:
                    if isinstance(triplet, list) and len(triplet) == 3:
                         content_parts.append(f"- {triplet[0]} {triplet[1]} {triplet[2]}")
            
            if positive_examples:
                content_parts.append("\n**[Successful Examples]**")
                for i, ex in enumerate(reversed(positive_examples)):
                    content_parts.append(f"Example {i+1}:\n{ex}")
            
            if negative_examples:
                content_parts.append("\n**[Cautionary Examples]**")
                for i, ex in enumerate(reversed(negative_examples)):
                    content_parts.append(f"Example {i+1}:\n{ex}")

            content_parts.append("--- End of Retrieved Memory ---")
            content = "\n\n".join(content_parts)

            memories.append(
                MemoryItem(
                    id=rec.get("id", str(uuid.uuid4())),
                    content=content,
                    metadata={
                        "kind": "principle_package",
                        "similarity_score": sim_score,
                        "quality_score": quality_score,
                        "principle_type": p_type,
                    },
                    type=MemoryItemType.TEXT,
                    score=sim_score, 
                )
            )
        
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def _create_new_principle(
        self, 
        principle: Dict[str, Any], 
        trajectory_data: TrajectoryData, 
        compressed_traj: str
    ) -> tuple[bool, str]:
        logger.info(f"Creating new {principle['type']} principle...")
        
        description = principle["description"]
        if not description:
            return False, "Creation failed: Principle description is empty."

        p_emb_array = self._embed_texts([description])
        if p_emb_array.size == 0:
             return False, "Creation failed: Description embedding failed."
        p_emb = p_emb_array[0] 

        rid = str(uuid.uuid4())
        
        source_trajectories = [
            {
                "original_query": trajectory_data.query,
                "compressed_trace": compressed_traj,
                "metadata": trajectory_data.metadata
            }
        ]

        rec = {
            "id": rid,
            "description": description,
            "structure": principle["structure"],
            "type": principle["type"],
            "meta": {
                "source_count": 1,
                "original_query": trajectory_data.query,
            },
            "ts": int(time.time()),
            "source_trajectories": source_trajectories,
            "usage_count": 0, 
            "success_count": 0
        }
        
        self._records.append(rec)
        
        if self._embs is None or self._embs.size == 0:
            self._embs = p_emb.reshape(1, -1)
        else:
            self._embs = np.vstack([self._embs, p_emb])

        self._save_store()
        return True, f"Created new principle: id={rid} (Type: {principle['type']})"

    def _merge_into_existing_principle(
        self, 
        record_index: int, 
        trajectory_data: TrajectoryData, 
        compressed_traj: str
    ) -> tuple[bool, str]:
        try:
            original_record = self._records[record_index]
            original_id = original_record.get("id")
            logger.info(f"Merging into existing principle ID: {original_id}")

            new_source = {
                "original_query": trajectory_data.query,
                "compressed_trace": compressed_traj,
                "metadata": trajectory_data.metadata
            }
            original_record.setdefault("source_trajectories", []).append(new_source)
            
            original_record.setdefault("meta", {})
            original_record["meta"]["source_count"] = original_record["meta"].get("source_count", 0) + 1
            original_record["ts"] = int(time.time())

            self._records[record_index] = original_record
            self._save_store()
            
            return True, f"Merge successful: Trajectory merged into principle {original_id}."

        except Exception as e:
            logger.error(f"Merge failed: {e}")
            return False, f"Merge failed: {e}"


    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        logger.info("Received new trajectory. Starting principle workflow...")
        
        query = trajectory_data.query or ""
        meta = trajectory_data.metadata or {}
        is_success = str(meta.get("is_correct", "true")).lower() == "true"

        try:
            self._update_scores_for_provided_principles(query, is_success)
        except Exception as e:
            logger.error(f"Failed to update scores: {e}")

        try:
            self._prune_low_score_principles(self.prune_threshold)
        except Exception as e:
            logger.error(f"Failed to prune principles: {e}")
        
        new_principle = self._summarize_trajectory_to_principle(trajectory_data)
        if new_principle is None:
            return False, "Ingestion failed: Could not summarize trajectory."
        
        logger.info(f"Summarized new {new_principle['type']} principle.")

        compressed_traj = self._compact_trajectory(trajectory_data)

        if self._embs is None or self._embs.size == 0:
            return self._create_new_principle(new_principle, trajectory_data, compressed_traj)

        p_vec = self._embed_texts([new_principle["description"]])
        if p_vec.size == 0:
            return False, "Ingestion failed: Embedding error."

        idxs, scores = self._search(p_vec, top_k=self.search_top_k)
        
        for i, score in zip(idxs, scores):
            try:
                if i >= len(self._records): continue 
                existing_record = self._records[i]
                existing_desc = existing_record.get("description")
                
                if not existing_desc: continue

                if score <= 0.8:
                    continue

                if self._are_principles_semantically_same(new_principle["description"], existing_desc):
                    logger.info(f"Semantic match found. Merging.")
                    return self._merge_into_existing_principle(i, trajectory_data, compressed_traj)
                
            except Exception as e:
                logger.error(f"Error during semantic check: {e}")

        return self._create_new_principle(new_principle, trajectory_data, compressed_traj)