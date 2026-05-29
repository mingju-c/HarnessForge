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


MEMORY_SYSTEM = "round02_01_stateful_commit_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM


class MemoryProvider(BaseMemoryProvider):
    """Phase-aware reminders for stateful commits and read-after-write discipline."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(memory_type=MemoryType.LIGHTWEIGHT_MEMORY, config=config or {})
        self._initialized = False
        self.in_interval = int(self.config.get("in_interval", 3))

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
            memories.append(self._item('For stateful workflows, one successful observation closes one required operation row. Do not use intended calls as proof of state.', "begin"))
        elif request.status == MemoryStatus.IN:
            params = request.additional_params or {}
            step_number = int(params.get("step_number", 0) or 0)
            context = (request.context or "").lower()
            has_error = any(marker in context for marker in ("error for tool call", "unknown tool", "invalid", "success': false", '"success": false', "repeated-failure advisory", "not found", "does not exist"))
            has_terminal_risk = "complete_task" in context or "final_answer" in context or "cannot determine" in context or "remaining" in context
            has_raw_value = any(marker in context for marker in ('"result"', '"answer"', '"value"', '"date"', '"count"', "result_date", "output"))
            has_slot_risk = any(marker in context for marker in ("placeholder", "slot", "father", "relation", "intermediate", "pending", "unresolved"))
            if has_error:
                memories.append(self._item('A failed mutation keeps its row open. Repair target ID, parent, status, precondition, or alternate mutator before completion.', "repair"))
            if has_slot_risk and (step_number % self.in_interval == 0 or "placeholder" in context or "unresolved" in context):
                memories.append(self._item('Before complete_task, scan required mutations against observed success rows. If a read-after-write check is needed, do it once and then complete promptly.', "status"))
            if has_raw_value and ("final_answer" in context or step_number % self.in_interval == 0):
                memories.append(self._item('If the final output is a status or ID from a successful write, copy the observed field exactly.', "raw"))
            if has_terminal_risk and not memories and self.in_interval > 0 and step_number > 0 and step_number % self.in_interval == 0:
                memories.append(self._item('Refresh commit ledger: required operation, target object, observed ID, success/failure, remaining rows.', "checkpoint"))
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return True, f"{MEMORY_SYSTEM} stores procedural reminders only; no task facts, IDs, or answers were persisted."


MemoryClass = MemoryProvider
Round0201StatefulCommitMemory = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
    "Round0201StatefulCommitMemory",
]
