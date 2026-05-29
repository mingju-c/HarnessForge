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


MEMORY_SYSTEM = "round03_01_commit_gate_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM
BEGIN_REMINDER = 'Use an observation-closed row ledger: complete_task is ready only when every requested mutation has a successful observation or a task-permitted evidence-backed blocker.'
RISK_RULES = [('terminal', ('complete_task', 'remaining', 'pending', 'mutation', 'stateful'), 'Terminal risk: list open rows before completing; failed rows remain open until repaired by observation.'), ('repair', ('success": false', "success': false", 'permission denied', 'not found', 'schema advisory', 'error'), 'A failed required row is not closed. Change arguments, use another listed mutator, or record an evidence-backed blocker.')]


class MemoryProvider(BaseMemoryProvider):
    """Sparse phase-aware procedural memory for round03 risk cues."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(memory_type=MemoryType.LIGHTWEIGHT_MEMORY, config=config or {})
        self._initialized = False
        self.in_interval = int(self.config.get("in_interval", 4))
        self.max_items = int(self.config.get("max_items", 2))

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
            memories.append(self._item(BEGIN_REMINDER, "begin"))
        elif request.status == MemoryStatus.IN:
            params = request.additional_params or {}
            step_number = int(params.get("step_number", 0) or 0)
            context = (request.context or "").lower()
            for tag, markers, reminder in RISK_RULES:
                if any(marker in context for marker in markers):
                    memories.append(self._item(reminder, tag))
                    if len(memories) >= self.max_items:
                        break
            if (
                not memories
                and self.in_interval > 0
                and step_number > 0
                and step_number % self.in_interval == 0
            ):
                memories.append(self._item("Refresh OBLIGATION_PACKET: closed rows, failed rows, blockers, remaining rows, final readiness.", "checkpoint"))
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return True, f"{MEMORY_SYSTEM} stores procedural risk cues only; no task facts, IDs, or answers were persisted."


MemoryClass = MemoryProvider
Round0301Harness1Memory = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
    "Round0301Harness1Memory",
]
