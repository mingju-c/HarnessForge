from __future__ import annotations

import re
from typing import Any, Optional

from module_memory.memory_types import MemoryRequest, MemoryResponse, MemoryStatus

from .round02_memory import Round02MemoryProvider


MEMORY_SYSTEM = "abstract_quarantine_memory"
MEMORY_MODULE = "abstract_quarantine_memory"
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM


def _mask_concrete_values(text: Any) -> str:
    value = str(text)
    value = re.sub(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){2,}-[0-9a-fA-F]{12}\b", "<ID>", value)
    value = re.sub(r"\b[0-9a-fA-F]{16,}\b", "<ID>", value)
    value = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<EMAIL>", value)
    value = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<DATE>", value)
    value = re.sub(r"\b\d{6,}\b", "<NUMBER>", value)
    value = re.sub(r"\b(?:[A-Z][a-z]+\s+){2,}[A-Z][a-z]+\b", "<ENTITY>", value)
    return value


class MemoryProvider(Round02MemoryProvider):
    MEMORY_SYSTEM = MEMORY_SYSTEM
    MEMORY_MODULE = MEMORY_MODULE
    DEFAULT_CONFIG = {
        "memory_system": MEMORY_SYSTEM,
        "focus": "aggressively masked procedural cards and sparse retrieval",
        "top_k": 1,
        "shortterm_interval": 3,
        "store_failures": True,
        "store_successes": True,
    }

    def _phase_guidance(self, status: MemoryStatus) -> str:
        base = super()._phase_guidance(status)
        quarantine = (
            "\nRound03 quarantine: retrieved memories are procedure_hint_only; "
            "concrete old entities, ids, dates, UUIDs, and answers must be resolved again "
            "from the current task or current tool observations before use."
        )
        return base + quarantine

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        response = super().provide_memory(request)
        for item in response.memories:
            metadata = dict(item.metadata or {})
            if metadata.get("source") != "phase_guidance":
                item.content = "procedure_hint_only; not current evidence:\n" + _mask_concrete_values(item.content)
                metadata["quarantine"] = "do_not_use_memory_values_as_arguments"
                item.metadata = metadata
        return response

    def _trajectory_lines(self, trajectory_data):
        return [_mask_concrete_values(line) for line in super()._trajectory_lines(trajectory_data)]

    def _make_success_record(self, trajectory_data, lines: list[str]) -> dict[str, Any]:
        record = super()._make_success_record(trajectory_data, [_mask_concrete_values(line) for line in lines])
        record["content"] = _mask_concrete_values(record.get("content", ""))
        record["kind"] = "abstract_successful_procedure"
        return record

    def _make_failure_record(self, trajectory_data, lines: list[str]) -> Optional[dict[str, Any]]:
        record = super()._make_failure_record(trajectory_data, [_mask_concrete_values(line) for line in lines])
        if record is not None:
            record["content"] = _mask_concrete_values(record.get("content", ""))
            record["kind"] = "abstract_failure_lesson"
        return record


MemoryClass = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
]
