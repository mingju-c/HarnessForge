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


MEMORY_SYSTEM = 'round03_02_repair_sentinel_memory'
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM
BEGIN_GUIDANCE = 'Treat failed calls as repair objects: classify the failure, require a changed route, and never let checker text substitute for evidence.'
RULE_CARDS = [
    ('schema', ('unknown tool', 'schema advisory', 'argument', 'required', 'invalid'), 'Before retrying, copy exact tool names and schema keys from the current Available tool schemas block.'),
    ('repeat', ('repeated-failure advisory', 'route-change guard blocked', 'failed 2 times'), 'Do not repeat identical failed calls; change arguments, tool, entity, or precondition.'),
    ('exhaustion', ('cannot determine', 'unavailable', 'not found'), 'Cannot-determine requires exhausted valid repair routes or observed contradiction, not a first miss.')
]


class MemoryProvider(BaseMemoryProvider):
    """Low-noise procedural memory for REPAIR_ROUTE_SENTINEL failure classes."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(memory_type=MemoryType.LIGHTWEIGHT_MEMORY, config=config or {})
        self._initialized = False
        self.in_interval = int(self.config.get("in_interval", 3))
        self.max_items = int(self.config.get("max_items", 2))

    def initialize(self) -> bool:
        self._initialized = True
        return True

    def _item(self, content: str, tag: str) -> MemoryItem:
        return MemoryItem(
            id=f"{MEMORY_SYSTEM}_{tag}_{uuid.uuid4().hex[:8]}",
            content=content.strip(),
            metadata={"source": MEMORY_SYSTEM, "tag": tag, "contract": 'REPAIR_ROUTE_SENTINEL'},
            type=MemoryItemType.TEXT,
        )

    def _matched_cards(self, context: str) -> list[tuple[str, str]]:
        lowered = context.lower()
        matches: list[tuple[str, str]] = []
        for tag, markers, content in RULE_CARDS:
            if any(str(marker).lower() in lowered for marker in markers):
                matches.append((tag, content))
        return matches

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if not self._initialized:
            self.initialize()
        memories: list[MemoryItem] = []
        if request.status == MemoryStatus.BEGIN:
            memories.append(self._item(BEGIN_GUIDANCE, "begin"))
        elif request.status == MemoryStatus.IN:
            params = request.additional_params or {}
            step_number = int(params.get("step_number", 0) or 0)
            context = request.context or ""
            cards = self._matched_cards(context)
            for tag, content in cards[: self.max_items]:
                memories.append(self._item(content, tag))
            if (
                not memories
                and self.in_interval > 0
                and step_number > 0
                and step_number % self.in_interval == 0
            ):
                memories.append(
                    self._item(
                        "Refresh the compact contract from observations: pending row, observed success, observed failure, blocker, changed route, and terminal criterion.",
                        "checkpoint",
                    )
                )
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return True, f"{MEMORY_SYSTEM} stores procedural rule cards only; no task facts, IDs, answers, or gold labels were persisted."


MemoryClass = MemoryProvider
Round0302RepairSentinelMemory = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
    "Round0302RepairSentinelMemory",
]
