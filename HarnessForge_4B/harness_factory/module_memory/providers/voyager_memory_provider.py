import os
import re
import shutil
import uuid
import sys
import json
import numpy as np
from typing import Optional, List, Dict, Any

from sentence_transformers import SentenceTransformer
from .model_loader import load_sentence_transformer
from sklearn.metrics.pairwise import cosine_similarity


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


class VoyagerMemoryProvider(BaseMemoryProvider):
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(memory_type=MemoryType.VOYAGER, config=config)
        
        self.model = self.config.get('model', None)

        self.db_path = self.config.get('db_path', './storage/voyager/voyager_memory.json')
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

            print(f"VoyagerMemoryProvider initialized. Storing memories in {self.db_path}")
            return True
        except Exception as e:
            print(f"Error initializing VoyagerMemoryProvider: {e}", file=sys.stderr)
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
            
            current_situation = self._reconstruct_trajectory_string(trajectory_data)

            voyager_prompt = '''You are a helpful assistant that writes a description of the task resolution trajectory.

            1) Try to summarize the trajectory in no more than 6 sentences.
            2) Your response should be a single line of text.

            For example:
            Trajectory:
            You are in the middle of a room. Looking quickly around you, you see a cabinet 10, a cabinet 9, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 3, a countertop 2, a countertop 1, a diningtable 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.
            Your task is to: heat some egg and put it in diningtable.
            > think: To solve the task, I need to find and take an egg, then heat it with microwave, then put it in diningtable.
            OK.
            > think: First I need to find an egg. An egg is more likely to appear in fridge (1), countertop (1-3), diningtable (1), stoveburner (1-4), toaster (1), garbagecan (1), cabinet (1-10). I can check one by one, starting with fridge 1.
            OK.
            > open fridge 1
            You open the fridge 1. The fridge 1 is open. In it, you see a lettuce 2, a mug 2, and a potato 3.
            > go to countertop 1
            On the countertop 1, you see a bread 1, a fork 1, and a saltshaker 1.
            > go to countertop 2
            On the countertop 2, you see nothing.
            > go to countertop 3
            On the countertop 3, you see a bowl 1, a butterknife 1, a egg 2, a kettle 2, a plate 1, a sink 1, and a spatula 2.
            > think: Now I find an egg (2). Next, I need to take it.
            OK.
            > take egg 2 from countertop 3
            You pick up the egg 2 from the countertop 3.
            > think: Now I take an egg (2). Next, I need go to a microwave (1) and heat it.
            OK.
            > go to microwave 1
            The microwave 1 is closed.
            > heat egg 2 with microwave 1
            You heat the egg 2 using the microwave 1.
            > think: Now I heat an egg (2). Next, I need to put it in/on diningtable 1.
            OK.
            > go to diningtable 1
            On the diningtable 1, you see a apple 2, a bread 3, a egg 1, a kettle 1, a knife 1, a mug 1, a papertowelroll 1, a peppershaker 2, a potato 1, a soapbottle 1, and a spatula 1.
            > put egg 2 in/on diningtable 1
            You put the egg 2 in/on the diningtable 1.

            Then you would write: The trajectory is about finding an egg, heating it with a microwave, and placing it on the dining table after checking various locations like the fridge and countertops.

            Trajectory:
            '''
            
            messages = [
                {"role": "user", "content": [{"type": "text", "text": voyager_prompt + "\n" + current_situation}]}
            ]
            
            resp = self.model(messages)
            trajectory_summary = getattr(resp, "content", str(resp)).strip()
            
            if not trajectory_summary:
                raise Exception("LLM call (for summary) succeeded but returned an empty summary.")
            
            distilled_trajectory = self._summarize_trajectory_with_llm(trajectory_data)

            if not distilled_trajectory:
                raise Exception("LLM call (for distillation) succeeded but returned an empty summary.")

            memory_doc = {
                "page_content": trajectory_summary,
                "metadata": {
                    "task_trajectory": distilled_trajectory,
                    "original_query": trajectory_data.query,
                    "id": str(uuid.uuid4())
                }
            }
            
            self.memories.append(memory_doc)

            new_embedding = self.embedding_model.encode([trajectory_summary])
            
            if self.embeddings_cache is None or self.embeddings_cache.size == 0:
                self.embeddings_cache = new_embedding
            else:
                self.embeddings_cache = np.vstack([self.embeddings_cache, new_embedding])
            
            self._save_memories_to_json() 
            
            return (True, trajectory_summary)
            
        except Exception as e:
            print(f"Error in take_in_memory: {e}", file=sys.stderr) 
            return (False, f"Failed to add memory: {e}")

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if self.embedding_model is None:
            raise Exception("Memory provider not initialized. Call initialize() first.")
        
        if request.status != MemoryStatus.BEGIN:
            return MemoryResponse(
                memories=[], 
                memory_type=self.memory_type, 
                total_count=0,
                request_id=str(uuid.uuid4())
            )
        
        if not self.memories or self.embeddings_cache is None or self.embeddings_cache.size == 0:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4()))
        
        task_name = request.query
        
        try:
            query_embedding = self.embedding_model.encode([task_name])
            
            similarity_scores = cosine_similarity(query_embedding, self.embeddings_cache)
            similarity_scores_1d = similarity_scores[0]
            
            k = 1
            top_k_indices = np.argsort(similarity_scores_1d)[-k:][::-1]

            retrieved_memories = []
            for idx in top_k_indices:
                doc = self.memories[idx]
                score = float(similarity_scores_1d[idx])
                doc_id = doc['metadata'].get('id', str(uuid.uuid4()))
                original_content = doc['metadata'].get('task_trajectory', '')
                content_with_wrapper = (
                    "Below is the trajectory from a similar task:\n"
                    f"{original_content}\n"
                    "End of similar task trajectory."
                )
                
                memory_item = MemoryItem(
                    id=doc_id,
                    content=content_with_wrapper,
                    metadata={
                        'original_query': doc['metadata'].get('original_query', '')
                    },
                    score=score,
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
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0, request_id=str(uuid.uuid4()))

    def _summarize_trajectory_with_llm(self, trajectory_data: TrajectoryData) -> str:

        current_trajectory = self._reconstruct_trajectory_string(trajectory_data)
        if self.model is None:
            print("No LLM model provided for summarization. Falling back to full text.", file=sys.stderr)
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
                print("LLM call succeeded but returned an empty summary. Falling back to full text.", file=sys.stderr)
                return current_trajectory
                
            return summary
            
        except Exception as e:
            print(f"Error during trajectory summarization: {e}", file=sys.stderr)
            return current_trajectory