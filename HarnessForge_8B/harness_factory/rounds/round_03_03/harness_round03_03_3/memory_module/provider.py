from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from module_memory.base_memory import BaseMemoryProvider
from module_memory.memory_types import MemoryItem, MemoryItemType, MemoryRequest, MemoryResponse, MemoryStatus, MemoryType, TrajectoryData


MEMORY_SYSTEM = "round03_03_evidence_slot_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM
BEGIN_CUE = 'For multi-hop or retrieval tasks, name the subject, relation chain, target field, expected answer type, and evidence slots.'
REPAIR_CUE = 'If lookup fails, repair the unresolved slot rather than substituting a nearby entity or self-field.'
STATEFUL_CUE = 'Stateful mutations still require observed success; relation evidence does not prove environment completion.'
EVIDENCE_CUE = 'Close a slot only with a source observation and a short reason that it matches the exact relation, not a nearby relation.'
FINAL_CUE = 'Before final_answer, choose the closed slot raw value; do not add aliases or extra alternatives unless requested.'


class MemoryProvider(BaseMemoryProvider):
    """Sparse procedural memory for EVIDENCE_SLOT_CLOSER without task facts."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(memory_type=MemoryType.LIGHTWEIGHT_MEMORY, config=config or {})
        self._initialized = False
        self.in_interval = int(self.config.get("in_interval", 4))

    def initialize(self) -> bool:
        self._initialized = True
        return True

    def _item(self, content: str, tag: str) -> MemoryItem:
        return MemoryItem(id=f"{MEMORY_SYSTEM}_{tag}_{uuid.uuid4().hex[:8]}", content=content.strip(), metadata={"source": MEMORY_SYSTEM, "tag": tag, "scope": "procedural_only"}, type=MemoryItemType.TEXT)

    def _select_in_cue(self, request: MemoryRequest) -> tuple[str, str] | None:
        params = request.additional_params or {}
        step_number = int(params.get("step_number", 0) or 0)
        context = (request.context or "").lower()
        has_error = any(marker in context for marker in ("error for tool call", "unknown tool", "schema advisory", "invalid", "success': false", '"success": false', "repeated-failure advisory", "guard advisory", "permission denied", "not found", "does not exist"))
        has_stateful = any(marker in context for marker in ("complete_task", "terminal_blockers", "postcondition", "mutation", "create_", "update_", "delete_", "add_", "remove_", '"success": false'))
        has_evidence = any(marker in context for marker in ("candidate", "relation", "slot", "hop", "lookup", "search", "binding", "grandfather", "publisher", "alias", "distractor"))
        has_final = any(marker in context for marker in ("final_answer", "answer_type", "raw_field", "allowed_transformation", "final_criteria", "final_readiness"))
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
        return MemoryResponse(memories=memories, memory_type=self.memory_type, total_count=len(memories), request_id=str(uuid.uuid4()))

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return True, f"{MEMORY_SYSTEM} keeps procedural risk cues only; no task facts, IDs, answers, or dataset-specific lessons were persisted."


MemoryClass = MemoryProvider

__all__ = ["MEMORY_SYSTEM", "MEMORY_MODULE", "DEFAULT_MEMORY_SYSTEM", "MemoryProvider", "MemoryClass"]
