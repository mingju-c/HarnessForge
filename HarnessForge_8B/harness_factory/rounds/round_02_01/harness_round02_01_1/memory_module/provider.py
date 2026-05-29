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


MEMORY_SYSTEM = "round02_01_observed_ledger_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM


class MemoryProvider(BaseMemoryProvider):
    """Phase-aware reminders for observed ledger and raw final binding."""

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
            memories.append(self._item('Keep planned work separate from observed success. Close a ledger row only after a tool observation confirms the required entity, ID, value, or mutation.', "begin"))
        elif request.status == MemoryStatus.IN:
            params = request.additional_params or {}
            step_number = int(params.get("step_number", 0) or 0)
            context = (request.context or "").lower()
            has_error = any(marker in context for marker in ("error for tool call", "unknown tool", "invalid", "success': false", '"success": false', "repeated-failure advisory", "not found", "does not exist"))
            has_terminal_risk = "complete_task" in context or "final_answer" in context or "cannot determine" in context or "remaining" in context
            has_raw_value = any(marker in context for marker in ('"result"', '"answer"', '"value"', '"date"', '"count"', "result_date", "output"))
            has_slot_risk = any(marker in context for marker in ("placeholder", "slot", "father", "relation", "intermediate", "pending", "unresolved"))
            if has_error:
                memories.append(self._item('Classify the failed call before retrying: schema, bad ID, missing entity, precondition, permission, empty result, or contradiction. Change something before the next call.', "repair"))
            if has_slot_risk and (step_number % self.in_interval == 0 or "placeholder" in context or "unresolved" in context):
                memories.append(self._item('Before terminal completion, review unresolved ledger rows. Planned or attempted writes are not done until an observation says they succeeded.', "status"))
            if has_raw_value and ("final_answer" in context or step_number % self.in_interval == 0):
                memories.append(self._item('For short answers, copy the decisive raw structured field exactly unless the task explicitly asks for a transformation.', "raw"))
            if has_terminal_risk and not memories and self.in_interval > 0 and step_number > 0 and step_number % self.in_interval == 0:
                memories.append(self._item('Refresh the observed ledger: pending, success, failure, remaining, and final criteria should stay separate.', "checkpoint"))
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return True, f"{MEMORY_SYSTEM} stores procedural reminders only; no task facts, IDs, or answers were persisted."


MemoryClass = MemoryProvider
Round0201ObservedLedgerMemory = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
    "Round0201ObservedLedgerMemory",
]
