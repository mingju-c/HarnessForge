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


MEMORY_SYSTEM = "round03_04_relation_binder_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM
BEGIN_CUE = 'Create evidence slots for the exact relation, qualifier, intermediate variable, source observation, and raw answer form.'
REPAIR_CUE = 'After an empty or mismatched observation, change the relation query or binding instead of accepting a nearby relation.'
STATEFUL_CUE = 'If the task unexpectedly mutates state, fall back to observation-closed mutation rows before completion.'
EVIDENCE_CUE = 'Reject snippets that answer a nearby relation. A candidate is usable only when the requested predicate is supported.'
FINAL_CUE = 'Copy the decisive observed span; do not add source prose or extra context.'


class MemoryProvider(BaseMemoryProvider):
    """Sparse procedural memory for RELATION_EVIDENCE_BINDING without task facts."""

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
            metadata={"source": MEMORY_SYSTEM, "tag": tag, "scope": "procedural_only"},
            type=MemoryItemType.TEXT,
        )

    def _select_in_cue(self, request: MemoryRequest) -> tuple[str, str] | None:
        params = request.additional_params or {}
        step_number = int(params.get("step_number", 0) or 0)
        context = (request.context or "").lower()
        has_error = any(marker in context for marker in (
            "error for tool call",
            "unknown tool",
            "schema advisory",
            "schema preflight blocked",
            "invalid",
            "success': false",
            '"success": false',
            "repeated-failure advisory",
            "guard advisory",
            "permission denied",
            "not found",
            "does not exist",
            "terminal gate advisory",
        ))
        has_stateful = any(marker in context for marker in (
            "complete_task",
            "terminal_blockers",
            "postcondition",
            "mutation",
            "mutable",
            "create_",
            "update_",
            "delete_",
            "add_",
            "remove_",
            "reserve",
        ))
        has_evidence = any(marker in context for marker in (
            "candidate",
            "relation",
            "slot",
            "hop",
            "lookup",
            "search",
            "binding",
            "distractor",
            "qualifier",
            "predicate",
            "empty_result",
        ))
        has_final = any(marker in context for marker in (
            "final_answer",
            "answer_type",
            "raw_field",
            "allowed_transformation",
            "final_criteria",
            "final_readiness",
            "raw final",
        ))
        if has_error:
            return "repair", REPAIR_CUE
        if has_stateful:
            return "stateful", STATEFUL_CUE
        if has_evidence:
            return "evidence", EVIDENCE_CUE
        if has_final or (self.in_interval > 0 and step_number > 0 and step_number % self.in_interval == 0):
            return "final", FINAL_CUE
        return None

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if not self._initialized:
            self.initialize()
        memories = []
        if request.status == MemoryStatus.BEGIN:
            memories.append(self._item(BEGIN_CUE, "begin"))
        elif request.status == MemoryStatus.IN:
            selected = self._select_in_cue(request)
            if selected is not None:
                tag, cue = selected
                memories.append(self._item(cue, tag))
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return True, f"{MEMORY_SYSTEM} keeps procedural risk cues only; no task facts, IDs, answers, or dataset-specific lessons were persisted."


MemoryClass = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
]
