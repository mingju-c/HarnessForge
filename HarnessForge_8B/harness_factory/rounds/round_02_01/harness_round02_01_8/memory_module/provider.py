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


MEMORY_SYSTEM = "round02_01_compact_status_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM


class MemoryProvider(BaseMemoryProvider):
    """Sparse reminders for compact status fusion across task families."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(memory_type=MemoryType.LIGHTWEIGHT_MEMORY, config=config or {})
        self._initialized = False
        self.in_interval = int(self.config.get("in_interval", 5))

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
            memories.append(self._item('Use the smallest useful status packet: pending, observed success, observed failure, slots/evidence, remaining, final criteria.', "begin"))
        elif request.status == MemoryStatus.IN:
            params = request.additional_params or {}
            step_number = int(params.get("step_number", 0) or 0)
            context = (request.context or "").lower()
            has_error = any(marker in context for marker in ("error for tool call", "unknown tool", "invalid", "success': false", '"success": false', "repeated-failure advisory", "not found", "does not exist"))
            has_terminal_risk = "complete_task" in context or "final_answer" in context or "cannot determine" in context or "remaining" in context
            has_raw_value = any(marker in context for marker in ('"result"', '"answer"', '"value"', '"date"', '"count"', "result_date", "output"))
            has_slot_risk = any(marker in context for marker in ("placeholder", "slot", "father", "relation", "intermediate", "pending", "unresolved"))
            if has_error:
                memories.append(self._item('When an error appears, update observed_failure and change the next move; keep the status packet compact.', "repair"))
            if has_slot_risk and (step_number % self.in_interval == 0 or "placeholder" in context or "unresolved" in context):
                memories.append(self._item('If remaining work exists, do not let final readiness drift ahead of observed success, slot completion, or candidate support.', "status"))
            if has_raw_value and ("final_answer" in context or step_number % self.in_interval == 0):
                memories.append(self._item('When final evidence is decisive, submit the exact raw answer and stop.', "raw"))
            if has_terminal_risk and not memories and self.in_interval > 0 and step_number > 0 and step_number % self.in_interval == 0:
                memories.append(self._item('Refresh compact status only when it changes the next move; avoid verbose self-review.', "checkpoint"))
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return True, f"{MEMORY_SYSTEM} stores procedural reminders only; no task facts, IDs, or answers were persisted."


MemoryClass = MemoryProvider
Round0201CompactStatusMemory = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
    "Round0201CompactStatusMemory",
]
