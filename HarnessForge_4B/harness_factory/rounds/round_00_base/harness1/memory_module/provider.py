import os
import json
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from module_memory.base_memory import BaseMemoryProvider, atomic_write_json, file_lock
from module_memory.memory_types import (
    MemoryRequest,
    MemoryResponse,
    TrajectoryData,
    MemoryType,
    MemoryItem,
    MemoryStatus,
)

try:
    from sentence_transformers import SentenceTransformer 
    _embedding_import_error = None
except Exception as e: 
    _embedding_import_error = e
    SentenceTransformer = None 
from module_memory.providers.model_loader import load_sentence_transformer

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class MemoryProvider(BaseMemoryProvider):

    def __init__(self, config: Optional[dict] = None):
        super().__init__(MemoryType.EXPEL, config)
        self.insights_file_path = self.config.get("insights_file_path", "./storage/expel/insights.json")
        self.success_trajectories_file_path = self.config.get("success_trajectories_file_path", "./storage/expel/success_trajectories.json")
        self.top_k = int(self.config.get("top_k", 1))
        self.search_weights = self.config.get("search_weights", {"text": 0.3, "semantic": 0.7})
        self.embedding_model_name = self.config.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
        self.embedding_model_cache = self.config.get("embedding_model_cache", "./storage/models")

        self.model = self.config.get("model")

        self.insights: List[Dict[str, Any]] = [] 
        self.success_trajectories: List[Dict[str, Any]] = [] 

        self._insights_vectorizer: Optional[TfidfVectorizer] = None
        self._insights_matrix = None
        self._success_vectorizer: Optional[TfidfVectorizer] = None
        self._success_matrix = None
        self._embedding_model: Optional[SentenceTransformer] = None
        self._success_embeddings = None

    def initialize(self) -> bool:
        try:
            insights_dir = os.path.dirname(self.insights_file_path)
            success_dir = os.path.dirname(self.success_trajectories_file_path)
            if insights_dir:
                os.makedirs(insights_dir, exist_ok=True)
            if success_dir:
                os.makedirs(success_dir, exist_ok=True)

            if os.path.exists(self.insights_file_path):
                with open(self.insights_file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.insights = loaded if isinstance(loaded, list) else loaded.get("insights", [])
            else:
                self.insights = []

            if os.path.exists(self.success_trajectories_file_path):
                with open(self.success_trajectories_file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.success_trajectories = loaded if isinstance(loaded, list) else loaded.get("success_trajectories", [])
            else:
                self.success_trajectories = []

            if SentenceTransformer is None and _embedding_import_error is not None:
                print(f"Warning: sentence-transformers not available: {_embedding_import_error}")
            else:
                self._embedding_model = load_sentence_transformer(
                    model_name=self.embedding_model_name,
                    cache_dir=self.embedding_model_cache,
                    allow_unavailable=SentenceTransformer is None,
                )

            self._build_indices()
            return True
        except Exception as e:
            print(f"Error initializing ExpeL provider: {e}")
            return False

    def _build_indices(self):
        insight_texts = [item.get("text", "") for item in self.insights]
        self._insights_vectorizer = TfidfVectorizer(stop_words='english') if insight_texts else None
        self._insights_matrix = (
            self._insights_vectorizer.fit_transform(insight_texts) if self._insights_vectorizer and insight_texts else None
        )
        success_texts = [item.get("trajectory_text", "") for item in self.success_trajectories]
        self._success_vectorizer = TfidfVectorizer(stop_words='english') if success_texts else None
        self._success_matrix = (
            self._success_vectorizer.fit_transform(success_texts) if self._success_vectorizer and success_texts else None
        )
        if self._embedding_model is not None and success_texts:
            self._success_embeddings = self._embedding_model.encode(
                success_texts,
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        else:
            self._success_embeddings = None

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status == MemoryStatus.IN:
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0,
                request_id=str(uuid.uuid4()),
            )

        memories: List[MemoryItem] = []
        try:
            query = request.query or ""
            insight_results = self._text_search(query, corpus="insights", top_k=self.top_k)
            success_results = self._hybrid_success_search(query, top_k=self.top_k)

            for r in insight_results:
                item = self.insights[r["index"]]
                insight_type = item.get("type", "success") 
                content = self._format_insight_content(item.get("text", ""), request.status, insight_type)
                if not content:
                    continue
                memories.append(MemoryItem(
                    id=item.get("id", f"insight_{r['index']}"),
                    content=content,
                    metadata={
                        "type": "insight",
                        "insight_type": insight_type, 
                        "score": r["score"],
                        "source": item.get("source", "expel"),
                        "timestamp": item.get("timestamp"),
                        "status": request.status.value,
                    },
                    score=float(r["score"]) if r.get("score") is not None else None,
                ))

            for r in success_results:
                item = self.success_trajectories[r["index"]]
                content = self._format_success_content(item, request.status)
                if not content:
                    continue
                memories.append(MemoryItem(
                    id=item.get("id", f"success_{r['index']}"),
                    content=content,
                    metadata={
                        "type": "success",
                        "score": r["score"],
                        "query": item.get("query", ""),
                        "timestamp": item.get("timestamp"),
                        "status": request.status.value,
                    },
                    score=float(r["score"]) if r.get("score") is not None else None,
                ))

            memories.sort(key=lambda m: (m.score or 0.0), reverse=True)
            memories = memories[: max(self.top_k, len(memories))]
            return MemoryResponse(
                memories=memories,
                memory_type=self.memory_type,
                total_count=len(memories),
                request_id=str(uuid.uuid4()),
            )
        except Exception as e:
            print(f"Error providing ExpeL memory: {e}")
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)

    def _text_search(self, query: str, corpus: str, top_k: int) -> List[Dict[str, Any]]:
        if not query.strip():
            return []
        if corpus == "insights":
            if not self._insights_vectorizer or self._insights_matrix is None:
                return []
            qv = self._insights_vectorizer.transform([query])
            sims = cosine_similarity(qv, self._insights_matrix).flatten()
            indices = sims.argsort()[-top_k:][::-1]
            return [{"index": int(i), "score": float(sims[i])} for i in indices]
        elif corpus == "success":
            if not self._success_vectorizer or self._success_matrix is None:
                return []
            qv = self._success_vectorizer.transform([query])
            sims = cosine_similarity(qv, self._success_matrix).flatten()
            indices = sims.argsort()[-top_k:][::-1]
            return [{"index": int(i), "score": float(sims[i])} for i in indices]
        return []

    def _hybrid_success_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        text_results = self._text_search(query, corpus="success", top_k=top_k * 2)
        sem_results: List[Dict[str, Any]] = []
        if self._embedding_model is not None and self.success_trajectories:
            q_emb = self._embedding_model.encode(query, convert_to_numpy=True)
            embs = self._success_embeddings
            if embs is not None and len(embs) == len(self.success_trajectories):
                sims = cosine_similarity([q_emb], embs)[0]
                indices = sims.argsort()[-top_k * 2:][::-1]
                sem_results = [{"index": int(i), "score": float(sims[i])} for i in indices]
            score_map: Dict[int, float] = {}
            for r in text_results:
                score_map[r["index"]] = score_map.get(r["index"], 0.0) + float(self.search_weights.get("text", 0.5)) * float(r["score"])
            for r in sem_results:
                score_map[r["index"]] = score_map.get(r["index"], 0.0) + float(self.search_weights.get("semantic", 0.5)) * float(r["score"])
            merged = sorted(score_map.items(), key=lambda x: x[1], reverse=True)[: top_k]
            return [{"index": int(i), "score": float(s)} for i, s in merged]
        return text_results[:top_k]

    def _format_insight_content(self, text: str, status: MemoryStatus, insight_type: str = "success") -> str:
        if insight_type == "failure":
            if status == MemoryStatus.BEGIN:
                return f"ExpeL Failure Insight: {text}"
            elif status == MemoryStatus.IN:
                return None 
            return f"ExpeL Warning: {text}"
        else: 
            if status == MemoryStatus.BEGIN:
                return f"ExpeL Success Insight: {text}"
            elif status == MemoryStatus.IN:
                return None 
            return f"ExpeL Tip: {text}"

    def _format_success_content(self, item: Dict[str, Any], status: MemoryStatus) -> str:
        query = item.get("query", "")
        traj = item.get("trajectory_text", "")
        result = item.get("result", "")
        if status == MemoryStatus.BEGIN:
            return f"ExpeL Similar successful case for '{query}':\n{traj}"
        elif status == MemoryStatus.IN:
            return None 
        return f"ExpeL Success Pattern: {traj}"

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        try:
            metadata = trajectory_data.metadata or {}
            is_correct = metadata.get("is_correct", False)

            if not self.model:
                print("Error: No model provided for ExpeL memory extraction")
                return False, "Error: No model provided for ExpeL memory extraction"

            insights = self._extract_insights_with_llm(trajectory_data, is_correct)
            absorbed_memory = ""

            if insights:
                self._append_insights(insights, is_correct)
                absorbed_memory += f"Extracted insights: {insights}"

            if is_correct:
                self._append_success_trajectory(trajectory_data)
                absorbed_memory += f" | Stored successful trajectory"

            self._build_indices()
            return True, absorbed_memory
        except Exception as e:
            error_msg = f"Error taking in ExpeL memory: {e}"
            print(error_msg)
            return False, error_msg

    def _extract_insights_with_llm(self, trajectory_data: TrajectoryData, is_correct: bool = True) -> List[str]:
        try:
            trajectory_text = self._format_trajectory_for_model(trajectory_data)

            if is_correct:
                prompt = f"""Analyze the following successful task execution and extract simple, actionable insights.

Task Question: {trajectory_data.query}

Execution Trajectory:
{trajectory_text}

Task Result: {trajectory_data.result if trajectory_data.result else "Task completed successfully"}

Extract 3-6 simple insights that could help with similar future tasks. Each insight should be:
- One clear, actionable sentence
- Focused on what worked well or what to remember
- Useful for similar problem types
- Written as a direct tip or lesson

Format: Return only the insights, one per line, no categories or prefixes.

Example format:
Always verify search results with multiple sources before concluding
Break down complex problems into smaller, manageable steps
Use specific keywords when searching for technical information"""
            else:
                prompt = f"""Analyze the following failed task execution and extract simple, actionable insights to avoid similar failures.

Task Question: {trajectory_data.query}

Execution Trajectory:
{trajectory_text}

Task Result: {trajectory_data.result if trajectory_data.result else "Task failed or produced incorrect result"}

Extract 3-6 simple insights that could help avoid similar failures in future tasks. Each insight should be:
- One clear, actionable sentence
- Focused on what went wrong or what to avoid
- Useful for preventing similar mistakes
- Written as a direct warning or lesson learned

Format: Return only the insights, one per line, no categories or prefixes.

Example format:
Avoid relying on single sources without cross-verification
Double-check calculations before providing final answers
Ensure search queries are specific enough to find relevant information"""

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

            insights = []
            for line in content.strip().split('\n'):
                line = line.strip()
                line = line.lstrip('•-*123456789. ')
                for prefix in ["Do:", "Avoid:", "Insight:", "Tip:", "Note:"]:
                    if line.startswith(prefix):
                        line = line[len(prefix):].strip()
                        break

                if line and len(line) > 10: 
                    insights.append(line)

            return insights[:4] 

        except Exception as e:
            print(f"Error extracting insights with LLM: {e}")
            return []

    def _format_trajectory_for_model(self, trajectory_data: TrajectoryData) -> str:
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

    def _append_insights(self, insights: List[str], is_correct: bool = True):
        os.makedirs(os.path.dirname(self.insights_file_path), exist_ok=True)
        insight_type = "success" if is_correct else "failure"
        with file_lock(self.insights_file_path):
            cur: List[Dict[str, Any]] = []
            if os.path.exists(self.insights_file_path):
                try:
                    with open(self.insights_file_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        cur = loaded if isinstance(loaded, list) else loaded.get("insights", [])
                except Exception:
                    cur = []

            for text in insights:
                cur.append({
                    "id": str(uuid.uuid4()),
                    "text": text,
                    "source": "expel",
                    "type": insight_type,
                    "timestamp": datetime.now().isoformat(),
                })

            atomic_write_json(self.insights_file_path, cur, indent=2)
        self.insights = cur

    def _refine_successful_trajectory_with_llm(self, trajectory_data: TrajectoryData) -> str:
        try:
            trajectory_text = self._format_trajectory_for_model(trajectory_data)

            prompt = f"""Analyze the following successful task execution and create a structured step-by-step summary.

Task Question: {trajectory_data.query}

Successful Execution Trajectory:
{trajectory_text}

Task Result: {trajectory_data.result if trajectory_data.result else "Task completed successfully"}

Create a clear, numbered step-by-step summary of the successful approach that can be reused for similar tasks.

Requirements:
- Format as numbered steps: "1. [Action/Strategy]", "2. [Action/Strategy]", etc.
- Each step should be one clear, actionable sentence
- Focus on the key decisions and actions that led to success
- Make steps generalizable for similar problem types
- Include 4-8 main steps maximum
- Be concise but specific about what was done and why

Example format:
1. Break down the complex question into specific searchable components
2. Use targeted search queries with relevant technical keywords
3. Verify information from multiple reliable sources before proceeding
4. Cross-reference findings to ensure consistency and accuracy
5. Synthesize the verified information into a clear, direct answer"""

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

            return content.strip()

        except Exception as e:
            print(f"Error refining trajectory with LLM: {e}")
            return ""

    def _append_success_trajectory(self, trajectory_data: TrajectoryData):
        os.makedirs(os.path.dirname(self.success_trajectories_file_path), exist_ok=True)
        refined_trajectory = self._refine_successful_trajectory_with_llm(trajectory_data)

        with file_lock(self.success_trajectories_file_path):
            cur: List[Dict[str, Any]] = []
            if os.path.exists(self.success_trajectories_file_path):
                try:
                    with open(self.success_trajectories_file_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        cur = loaded if isinstance(loaded, list) else loaded.get("success_trajectories", [])
                except Exception:
                    cur = []

            cur.append({
                "id": str(uuid.uuid4()),
                "query": trajectory_data.query,
                "trajectory_text": refined_trajectory,
                "result": trajectory_data.result,
                "timestamp": datetime.now().isoformat(),
                "metadata": trajectory_data.metadata or {},
            })

            atomic_write_json(self.success_trajectories_file_path, cur, indent=2)
        self.success_trajectories = cur


ExpeLProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.EXPEL.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "ExpeLProvider"]
