from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Optional

from module_memory.base_memory import BaseMemoryProvider, atomic_write_json, file_lock
from module_memory.memory_types import (
    MemoryItem,
    MemoryItemType,
    MemoryRequest,
    MemoryResponse,
    MemoryStatus,
    MemoryType,
    TrajectoryData,
)


MEMORY_SYSTEM = "provenance_hint_memory"
MEMORY_MODULE = "provenance_hint_memory"
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM


def _tokens(text: str) -> set[str]:
    return {tok for tok in re.findall(r"\w+", str(text).lower()) if tok}


def _score(query: str, text: str) -> float:
    q = _tokens(query)
    c = _tokens(text)
    if not q or not c:
        return 0.0
    return len(q & c) / len(q)


class MemoryProvider(BaseMemoryProvider):
    """Small provenance-aware procedural memory.

    It gives compact phase guidance by default and stores only successful reusable
    procedures. Runtime facts are explicitly described as observation-backed or
    hypothetical so memory does not amplify unsupported guesses.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(memory_type=MemoryType.LIGHTWEIGHT_MEMORY, config=config or {})
        self.storage_dir = self.config.get("storage_dir", os.path.join("storage", MEMORY_SYSTEM))
        self.store_path = self.config.get("store_path", os.path.join(self.storage_dir, "records.json"))
        self.top_k = int(self.config.get("top_k", 2))
        self.interval = int(self.config.get("shortterm_interval", 3))
        self._records: list[dict[str, Any]] = []

    def initialize(self) -> bool:
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        if os.path.exists(self.store_path):
            try:
                with open(self.store_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                self._records = list(payload.get("records", []))
            except Exception:
                self._records = []
        return True

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        atomic_write_json(self.store_path, {"records": self._records[-80:]}, indent=2)

    def _phase_guidance(self, status: MemoryStatus) -> str:
        if status == MemoryStatus.BEGIN:
            return (
                "Round01 procedural memory (balanced evidence, schema, and closure guards):\n"
                "- observed_fact: only values from completed tool observations.\n"
                "- derived_fact: deterministic transforms of observed facts; name the source observation.\n"
                "- hypothesis: plan, thought, prior knowledge, or old memory until verified.\n"
                "- procedure_hint: Use live observations as facts. Treat plan text, thoughts, and old memory as hypotheses until a tool observation supports them.\n"
                "- commit rule: final_answer needs observed or derived support when evidence tools exist; terminal completion needs observed state progress."
            )
        return (
            "Round01 in-task memory reminder: keep observed facts separate from hypotheses; "
            "after an error, repair schema or change strategy; after evidence supports the requested value, finalize in raw requested format."
        )

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if not self._records and not os.path.exists(self.store_path):
            self.initialize()
        memories: list[MemoryItem] = []
        step = 0
        if request.additional_params:
            try:
                step = int(request.additional_params.get("step_number", 0) or 0)
            except Exception:
                step = 0
        if request.status == MemoryStatus.BEGIN or (request.status == MemoryStatus.IN and step % self.interval == 0):
            memories.append(
                MemoryItem(
                    id=f"{MEMORY_SYSTEM}_phase",
                    content=self._phase_guidance(request.status),
                    metadata={"source": "phase_guidance", "provenance": "procedure_hint"},
                    score=1.0,
                    type=MemoryItemType.TEXT,
                )
            )
        if request.status == MemoryStatus.BEGIN and self._records:
            ranked = sorted(
                ((record, _score(request.query, record.get("content", ""))) for record in self._records),
                key=lambda item: item[1],
                reverse=True,
            )
            for record, score in ranked[: self.top_k]:
                if score <= 0:
                    continue
                memories.append(
                    MemoryItem(
                        id=str(record.get("id") or uuid.uuid4()),
                        content="Relevant reusable procedure:\n" + str(record.get("content", "")),
                        metadata={"source": "successful_trajectory", "provenance": "procedure_hint"},
                        score=score,
                        type=MemoryItemType.TEXT,
                    )
                )
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def _trajectory_lines(self, trajectory_data: TrajectoryData) -> list[str]:
        lines: list[str] = []
        for step in trajectory_data.trajectory or []:
            if isinstance(step, dict):
                tool_calls = step.get("tool_calls") or step.get("tools") or []
                obs = step.get("obs") or step.get("observations") or step.get("content") or ""
                if tool_calls:
                    lines.append(f"tools={tool_calls}")
                if obs:
                    lines.append(f"obs={str(obs)[:500]}")
            else:
                lines.append(str(step)[:500])
        return lines

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        metadata = trajectory_data.metadata or {}
        success = bool(
            metadata.get("is_correct")
            or metadata.get("task_success")
            or metadata.get("outcome") == "success"
        )
        if not success:
            return False, "Skipped unsuccessful trajectory; memory stores reusable successes only."
        lines = self._trajectory_lines(trajectory_data)
        if not lines:
            return False, "Skipped empty trajectory."
        content = (
            f"Task pattern: {str(trajectory_data.query)[:300]}\n"
            "Reusable procedure: use exact tool schemas, ground conclusions in observations, "
            "track state changes before terminal completion, and apply final formatting only after evidence.\n"
            f"Observed sequence sketch: {' | '.join(lines)[:1200]}"
        )
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        with file_lock(self.store_path):
            if os.path.exists(self.store_path):
                try:
                    with open(self.store_path, "r", encoding="utf-8") as handle:
                        payload = json.load(handle)
                    self._records = list(payload.get("records", []))
                except Exception:
                    self._records = []
            if any(record.get("content") == content for record in self._records):
                return False, "Skipped duplicate memory."
            self._records.append(
                {
                    "id": str(uuid.uuid4()),
                    "content": content,
                    "created_at": time.time(),
                    "metadata": metadata,
                }
            )
            self._save()
        return True, f"Ingested provenance-aware procedure memory for {MEMORY_SYSTEM}."


MemoryClass = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
]
