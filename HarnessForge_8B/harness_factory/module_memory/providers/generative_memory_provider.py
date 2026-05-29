import os
import re
import shutil
import uuid
import sys
import json
from typing import Optional, List, Dict, Any

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from .model_loader import load_sentence_transformer

from ..base_memory import BaseMemoryProvider
from ..memory_types import (
    MemoryRequest,
    MemoryResponse,
    TrajectoryData,
    MemoryType,
    MemoryItem,
    MemoryStatus,
    MemoryItemType
)

def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                         cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    return load_sentence_transformer(
        model_name=model_name,
        cache_dir=cache_dir,
        allow_unavailable=SentenceTransformer is None,
    )


class GenerativeMemoryProvider(BaseMemoryProvider):

    def __init__(self, config: Optional[dict] = None):
        super().__init__(memory_type=MemoryType.GENERATIVE, config=config)

        self.model = self.config.get('model', None)
        self.db_path = self.config.get('db_path', './storage/generative_memory.json')
        
        self.model_name = self.config.get('embedding_model_name', 'sentence-transformers/all-MiniLM-L6-v2')
        self.model_cache_dir = self.config.get('embedding_model_cache', './storage/models')

        self.embedding_model: Optional[SentenceTransformer] = None
        self.embedding_dim: int = 384
        
        self.memories: list[dict] = []
        self.embeddings_cache: Optional[np.ndarray] = None

    def initialize(self) -> bool:
        try:
            self.embedding_model = load_embedding_model(
                model_name=self.model_name,
                cache_dir=self.model_cache_dir
            )
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
            
            self._load_memories_from_json()
            return True
        except Exception as e:
            print(f"Error initializing GenerativeMemoryProvider: {e}", file=sys.stderr)
            return False

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
                        self.embeddings_cache = np.empty((0, self.embedding_dim))
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {self.db_path}. Starting with empty memory.", file=sys.stderr)
                self.memories = []
                self.embeddings_cache = np.empty((0, self.embedding_dim))
            except Exception as e:
                print(f"Error loading memories: {e}. Starting fresh.", file=sys.stderr)
                self.memories = []
                self.embeddings_cache = np.empty((0, self.embedding_dim))
        else:
            self.memories = []
            self.embeddings_cache = np.empty((0, self.embedding_dim))

    def _save_memories_to_json(self):
        if self.embedding_model is None:
            print("Cannot save: Memory provider not initialized.", file=sys.stderr)
            return

        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            
            data = {
                'memories': self.memories,
                'embeddings': self.embeddings_cache.tolist()
            }
            
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"Error saving memories to {self.db_path}: {e}", file=sys.stderr)

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

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        if self.embedding_model is None or self.embeddings_cache is None:
            return (False, "Memory provider not initialized. Call initialize() first.")
            
        try:
            trajectory_summary = self._summarize_trajectory_with_llm(trajectory_data)
            task_name = trajectory_data.query.strip()
            
            if not task_name:
                raise ValueError("trajectory_data.query is empty.")

            task_embedding = self.embedding_model.encode(task_name)
            new_embedding_batch = task_embedding.reshape(1, -1)

            memory_doc = {
                'id': str(uuid.uuid4()),
                'task_name': task_name,
                'metadata': {
                    "task_description": trajectory_summary,
                    "original_query": trajectory_data.query
                }
            }
            
            self.memories.append(memory_doc)
            self.embeddings_cache = np.vstack([self.embeddings_cache, new_embedding_batch])
            self._save_memories_to_json()
            
            return (True, trajectory_summary)
            
        except Exception as e:
            print(f"Error in take_in_memory: {e}", file=sys.stderr) 
            return (False, f"Failed to add memory: {e}")

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if self.embedding_model is None or self.embeddings_cache is None:
            raise Exception("Memory provider not initialized. Call initialize() first.")
        
        if request.status != MemoryStatus.BEGIN:
            return MemoryResponse(
                memories=[], 
                memory_type=self.memory_type, 
                total_count=0,
                request_id=str(uuid.uuid4())
            )

        if not self.memories or self.embeddings_cache.shape[0] == 0:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)
    
        task_name = request.query.strip()
        
        if not task_name:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, 
                                    status_message="request.query (task_name) is empty.")

        try:
            query_embedding = self.embedding_model.encode([task_name])
            scores = cosine_similarity(query_embedding, self.embeddings_cache)[0]
            
            k = 3
            if len(scores) < k:
                k = len(scores)
                
            top_k_indices = np.argsort(scores)[-k:][::-1]
            
            similarity_results = []
            for idx in top_k_indices:
                memory_doc = self.memories[idx]
                sim_score = float(scores[idx])
                similarity_results.append((memory_doc, sim_score))

            if not similarity_results:
                return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)
            
            importance_scores = []
            retrieved_docs = []

            for doc, sim_score in similarity_results:
                trajectory = doc['metadata'].get('task_description', '')
                retrieved_docs.append((doc, sim_score))
                
                prompt = f'''You will be given a successful case where you successfully complete the task. Then you will be given an ongoing task. Do not summarize these two cases, but rather evaluate how relevant and helpful the successful case is for the ongoing task, on a scale of 1-10.
Success Case:
{trajectory}
Ongoing task:
{task_name}
Your output format should be:
Score: '''

                messages = [
                    {"role": "user", "content": [{"type": "text", "text": prompt}]}
                ]
                resp = self.model(messages) 
                response_text = getattr(resp, "content", str(resp)).strip()
                
                score_match = re.search(r'\d+', response_text)
                score = int(score_match.group()) if score_match else 0
                importance_scores.append(score)

            if not importance_scores:
                return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)

            max_score_idx = importance_scores.index(max(importance_scores))
            best_doc, best_sim_score = retrieved_docs[max_score_idx]
            best_importance_score = importance_scores[max_score_idx]
            original_content = best_doc['metadata'].get('task_description', '')
            content_with_wrapper = (
                    "Below is the trajectory from a similar task:\n"
                    f"{original_content}\n"
                    "End of similar task trajectory."
            )

            memory_item = MemoryItem(
                id=best_doc.get('id', str(uuid.uuid4())),
                content=content_with_wrapper, 
                metadata={
                    'task_name': best_doc.get('task_name', ''),
                    'original_query': best_doc['metadata'].get('original_query', ''), 
                    'importance_score': best_importance_score,
                    'similarity_score': best_sim_score
                },
                score=best_sim_score,
                type=MemoryItemType.TEXT 
            )
            retrieved_memories = [memory_item]
                
            return MemoryResponse(
                memories=retrieved_memories,
                memory_type=self.memory_type,
                total_count=len(retrieved_memories),
                request_id=str(uuid.uuid4())
            )
            
        except Exception as e:
            print(f"Error in provide_memory: {e}", file=sys.stderr)
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, status_message=f"Error: {e}")
    
    def _summarize_trajectory_with_llm(self, trajectory_data: TrajectoryData) -> str:

        if self.model is None:
            print("No LLM model provided for summarization. Falling back to full text.", file=sys.stderr)
            return trajectory_data.trajectory
        current_trajectory = self._reconstruct_trajectory_string(trajectory_data)
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
                print("LLM call succeeded but returned an empty summary. Falling back to full text.", file=sys.stderr)
                return current_trajectory
                
            return summary
            
        except Exception as e:
            print(f"Error during trajectory summarization: {e}", file=sys.stderr)
            return current_trajectory