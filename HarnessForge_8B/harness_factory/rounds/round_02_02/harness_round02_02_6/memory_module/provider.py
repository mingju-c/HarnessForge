from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from module_memory.base_memory import BaseMemoryProvider
from module_memory.memory_types import (
    MemoryItem,
    MemoryItemType,
    MemoryRequest,
    MemoryResponse,
    MemoryStatus,
    MemoryType,
    TrajectoryData,
)


MEMORY_SYSTEM = "round02_02_schema_route_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM


class MemoryProvider(BaseMemoryProvider):
    """Low-noise procedural memory for SCHEMA_ROUTE."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(memory_type=MemoryType.LIGHTWEIGHT_MEMORY, config=config or {})
        self._initialized = False
        self.in_interval = int(self.config.get("in_interval", 4))

    def initialize(self) -> bool:
        self._initialized = True
        return True

    def _item(self, content: str, tag: str) -> MemoryItem:
        return MemoryItem(
            id=f"{MEMORY_SYSTEM}_{tag}_{uuid.uuid4().hex[:8]}",
            content=content.strip(),
            metadata={"source": MEMORY_SYSTEM, "tag": tag},
            type=MemoryItemType.TEXT,
        )

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if not self._initialized:
            self.initialize()
        memories = []
        if request.status == MemoryStatus.BEGIN:
            memories.append(self._item("First infer whether schemas are read-only, mutable, or mixed. Read-only evidence can be efficient; mutable writes need sequential observation-backed rows.", "begin"))
        elif request.status == MemoryStatus.IN:
            params = request.additional_params or {}
            step_number = int(params.get("step_number", 0) or 0)
            context = (request.context or "").lower()
            has_error = any(marker in context for marker in (
                "error for tool call",
                "unknown tool",
                "invalid",
                "success': false",
                '"success": false',
                "repeated-failure advisory",
                "guard advisory",
                "permission denied",
                "not found",
                "does not exist",
            ))
            has_final_risk = any(marker in context for marker in (
                "final_answer",
                "complete_task",
                "final_criteria",
                "final_ready",
                "remaining",
            ))
            if has_error:
                memories.append(self._item("A route mistake often shows as repeated failure. Switch route or repair arguments only using available schemas and observed values.", "repair"))
            if has_final_risk or (self.in_interval > 0 and step_number > 0 and step_number % self.in_interval == 0):
                memories.append(self._item("Use read-only evidence arbitration for answers and mutable predicate closure for complete_task; both require raw observed support.", "final"))
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return True, f"{MEMORY_SYSTEM} stores procedural reminders only; no task facts, IDs, or answers were persisted."


MemoryClass = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
]
