import os
import shutil
import uuid
import sys
import json
from typing import Optional

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


class DiluMemoryProvider(BaseMemoryProvider):

    def __init__(self, config: Optional[dict] = None):
        super().__init__(memory_type=MemoryType.DILU, config=config)
        
        self.model = self.config.get('model', None)

        self.db_path = self.config.get('db_path', './storage/dilu_memory.json')
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

            print(f"DiluMemoryProvider initialized. Storing memories in {self.db_path}")
            return True
        except Exception as e:
            print(f"Error initializing DiluMemoryProvider: {e}", file=sys.stderr)
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
                        print(f"Loaded {len(self.memories)} memories and embeddings from {self.db_path}")
                    else:
                        self.embeddings_cache = np.empty((0, self.embedding_dim))
                        print(f"Loaded {len(self.memories)} memories from {self.db_path} (no embeddings found).")
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {self.db_path}. Starting with empty memory.", file=sys.stderr)
                self.memories = []
                self.embeddings_cache = np.empty((0, self.embedding_dim))
            except Exception as e:
                print(f"Error loading memories: {e}. Starting fresh.", file=sys.stderr)
                self.memories = []
                self.embeddings_cache = np.empty((0, self.embedding_dim))
        else:
            print("No memory file found. Starting with empty memory.")
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
        if self.embedding_model is None:
            return (False, "Memory provider not initialized. Call initialize() first.")
            
        try:
            
            trajectory_summary = self._summarize_trajectory_with_llm(trajectory_data)
            
            query_to_embed = trajectory_data.query
            
            query_embedding = self.embedding_model.encode([query_to_embed])[0]

            memory_doc = {
                'page_content': query_to_embed,
                'metadata': {
                    "task_description": trajectory_summary,
                    "original_query": trajectory_data.query
                }
            }
            
            self.memories.append(memory_doc)
            self.embeddings_cache = np.vstack([self.embeddings_cache, query_embedding])
            
            self._save_memories_to_json()
            
            return (True, trajectory_summary)
            
        except Exception as e:
            print(f"Error in take_in_memory: {e}", file=sys.stderr) 
            return (False, f"Failed to add memory: {e}")

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if self.embedding_model is None:
            raise Exception("Memory provider not initialized. Call initialize() first.")
        
        if request.status != MemoryStatus.BEGIN:
            print(f"Request status is '{request.status}', not 'BEGIN'. Skipping memory retrieval.")
            return MemoryResponse(
                memories=[], 
                memory_type=self.memory_type, 
                total_count=0,
                request_id=str(uuid.uuid4())
            )

        if not self.memories or self.embeddings_cache.shape[0] == 0:
            print("No memories available to search.")
            return MemoryResponse(
                memories=[], 
                memory_type=self.memory_type, 
                total_count=0,
                request_id=str(uuid.uuid4())
            )
        
        task_name = request.query
        if not task_name:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, 
                                    status_message="request.query (task_name) is empty.")

        try:
            query_embedding = self.embedding_model.encode([task_name])
            
            similarities = cosine_similarity(query_embedding, self.embeddings_cache)[0]
            
            k = 1
            top_k_indices = np.argsort(similarities)[-k:][::-1]

            retrieved_memories = []

            for i in top_k_indices:
                doc = self.memories[i]
                score = similarities[i]
                original_content = doc['metadata'].get('task_description', '')
                content_with_wrapper = (
                    "Below is the trajectory from a similar task:\n"
                    f"{original_content}\n"
                    "End of similar task trajectory."
                )

                memory_item = MemoryItem(
                    id=str(uuid.uuid4()),
                    content=content_with_wrapper, 
                    metadata={
                        'original_query': doc['metadata'].get('original_query', '')
                    },
                    score=float(score),
                    type=MemoryItemType.TEXT 
                )
                retrieved_memories.append(memory_item)
                
            return MemoryResponse(
                memories=retrieved_memories,
                memory_type=self.memory_type,
                total_count=len(retrieved_memories),
                request_id=str(uuid.uuid4())
            )
        except Exception as e:
            print(f"Error during memory retrieval: {e}", file=sys.stderr)
            raise e

    def _summarize_trajectory_with_llm(self, trajectory_data: TrajectoryData) -> str:

        if self.model is None:
            print("No LLM model provided for summarization. Falling back to full text.", file=sys.stderr)
            return trajectory_data
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