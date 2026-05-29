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


MEMORY_SYSTEM = "round02_02_verifier_contract_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM


class MemoryProvider(BaseMemoryProvider):
    """Low-noise procedural memory for VERIFIER_CONTRACT."""

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
            memories.append(self._item("Verifier calls are rare. They should create a next-action constraint, not replace real evidence or environment progress.", "begin"))
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
                memories.append(self._item("After verifier or guard warnings, address the named missing evidence or failure class before repeating the same finalization or failed call.", "repair"))
            if has_final_risk or (self.in_interval > 0 and step_number > 0 and step_number % self.in_interval == 0):
                memories.append(self._item("Do not finalize from verifier text alone. Final answers require observed evidence, resolved verifier blocks, and exact raw-value copying.", "final"))
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
