from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Optional

from ..base_memory import BaseMemoryProvider
from ..memory_types import (
    MemoryItem,
    MemoryItemType,
    MemoryRequest,
    MemoryResponse,
    MemoryStatus,
    MemoryType,
    TrajectoryData,
)


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"\w+", str(text).lower()) if token]


def _lexical_score(query: str, content: str) -> float:
    query_tokens = set(_tokenize(query))
    content_tokens = set(_tokenize(content))
    if not query_tokens or not content_tokens:
        return 0.0
    return len(query_tokens & content_tokens) / len(query_tokens)


class AgentWorkflowMemoryProvider(BaseMemoryProvider):
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            raise ValueError("AgentWorkflowMemoryProvider requires an explicit config dict.")
        super().__init__(memory_type=MemoryType.AGENT_WORKFLOW_MEMORY, config=config)
        required = ["store_path", "top_k", "enable_induction"]
        missing = [key for key in required if key not in self.config]
        if missing:
            raise KeyError(f"Missing required config keys: {missing}")
        self.model = self.config.get("model")
        self._items: list[MemoryItem] = []

    def initialize(self) -> bool:
        self._load_store()
        return True

    def _load_store(self) -> None:
        path = self.config["store_path"]
        if not os.path.exists(path):
            self._items = []
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self._items = [
                MemoryItem(
                    id=str(record.get("id") or uuid.uuid4()),
                    content=record.get("content", ""),
                    metadata=record.get("metadata") or {},
                    score=None,
                    type=MemoryItemType(record.get("type") or MemoryItemType.TEXT.value),
                )
                for record in payload.get("memories", [])
            ]
        except Exception:
            self._items = []

    def _save_store(self) -> None:
        path = self.config["store_path"]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        payload = {
            "memories": [
                {
                    "id": item.id,
                    "content": item.content,
                    "metadata": item.metadata,
                    "type": item.type.value,
                }
                for item in self._items
            ]
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _call_llm(self, prompt: str) -> str:
        if self.model is None:
            return ""
        try:
            response = self.model([{"role": "user", "content": [{"type": "text", "text": prompt}]}])
            return str(getattr(response, "content", response)).strip()
        except Exception:
            return ""

    def _reconstruct_trajectory(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return f"Task: {trajectory_data.query}"
        parts = [f"Task: {trajectory_data.query}"]
        for index, step in enumerate(trajectory_data.trajectory, 1):
            if isinstance(step, dict):
                step_type = step.get("type", "step")
                content = step.get("content", "")
            else:
                step_type = getattr(step, "type", "step")
                content = getattr(step, "content", str(step))
            parts.append(f"Step {index} ({step_type}): {content}")
        if trajectory_data.result:
            parts.append(f"Final Result: {trajectory_data.result}")
        return "\n".join(parts)

    def _induce_workflow(self, trajectory_data: TrajectoryData) -> str:
        if not self.config.get("enable_induction", True):
            return self._reconstruct_trajectory(trajectory_data)
        prompt = f"""Extract a reusable workflow from this successful trajectory.
Return JSON only with one key:
{{"workflow":"..."}}

{self._reconstruct_trajectory(trajectory_data)}"""
        raw = self._call_llm(prompt)
        if raw:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            try:
                data = json.loads(cleaned)
                workflow = str(data.get("workflow", "")).strip()
                if workflow:
                    return workflow
            except Exception:
                pass
        lines = [line.strip() for line in self._reconstruct_trajectory(trajectory_data).splitlines() if line.strip()]
        return "\n".join(lines[:6])

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status != MemoryStatus.BEGIN or not self._items:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=len(self._items))

        ranked = sorted(
            ((item, _lexical_score(request.query, str(item.content or ""))) for item in self._items),
            key=lambda pair: pair[1],
            reverse=True,
        )
        top_k = max(1, int(self.config["top_k"]))
        memories: list[MemoryItem] = []
        for item, score in ranked[:top_k]:
            memories.append(
                MemoryItem(
                    id=item.id,
                    content=item.content,
                    metadata=item.metadata,
                    score=score,
                    type=item.type,
                )
            )
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(self._items),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        metadata = trajectory_data.metadata or {}
        if not bool(metadata.get("is_correct") or metadata.get("task_success") or metadata.get("outcome") == "success"):
            return False, "Skipped: trajectory not marked successful."

        workflow = self._induce_workflow(trajectory_data).strip()
        if not workflow:
            return False, "Skipped: empty workflow."

        content = f"Query: {trajectory_data.query}\nWorkflow: {workflow}"
        item = MemoryItem(
            id=str(uuid.uuid4()),
            content=content,
            metadata={**metadata, "created_at": metadata.get("created_at", time.time())},
            type=MemoryItemType.TEXT,
        )
        self._items.append(item)
        self._save_store()
        return True, f"Ingested workflow memory: {workflow[:80]}"


__all__ = ["AgentWorkflowMemoryProvider"]
