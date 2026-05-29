from __future__ import annotations

import json
import os
import re
import textwrap
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


MEMORY_SYSTEM = "review_hint_memory"
MEMORY_MODULE = MEMORY_SYSTEM
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM

BOILERPLATE = {
    "task", "answer", "tool", "tools", "schema", "final", "question", "available",
    "call", "return", "json", "strict", "use", "must", "should", "before", "after",
    "observation", "observations", "current", "memory", "planner", "ledger",
}
FAILURE_CLASSES = {
    "schema": ["missing required", "extra argument", "unexpected keyword", "unknown tool"],
    "repeat": ["repeated_failed_call", "low_value_repeat", "already failed"],
    "not_found": ["not found", "does not exist", "no matching"],
    "authorization": ["unauthorized", "permission", "forbidden", "not allowed"],
    "empty": ["empty_or_unparsed_action", "no executable tool", "no observations"],
    "unsupported_final": ["unsupported_final_answer", "answer_support_missing"],
    "terminal": ["terminal_not_ready", "premature", "complete_task"],
}

DEFAULT_MEMORY_CONFIG: dict[str, Any] = {
    "memory_system": MEMORY_SYSTEM,
    "focus": "checkpoint-oriented hints for terminal readiness, support gaps, and recovery routes",
    "top_k": 2,
    "shortterm_interval": 3,
    "max_records": 120,
    "store_failures": True,
    "store_successes": True,
}


def _tokens(text: str) -> set[str]:
    return {
        tok for tok in re.findall(r"[a-zA-Z0-9_]+", str(text).lower())
        if len(tok) > 1 and tok not in BOILERPLATE
    }


def _route_tokens(text: str) -> set[str]:
    tokens = _tokens(text)
    routed = set()
    for token in tokens:
        if token in {"search", "lookup", "retrieve", "query", "find", "crawl", "read", "get", "list"}:
            routed.add("read_only_lookup")
        elif token in {"update", "create", "delete", "add", "remove", "transfer", "schedule", "cancel", "enroll", "assign"}:
            routed.add("stateful_mutation")
        elif token in {"count", "calculate", "compute", "convert", "date", "vowel", "reverse", "sort", "length"}:
            routed.add("deterministic_transform")
        elif token in {"error", "failed", "invalid", "missing", "unauthorized", "not_found", "blocked"}:
            routed.add("recovery")
        else:
            routed.add(token)
    return routed


def _score(query: str, record: dict[str, Any]) -> float:
    q = _route_tokens(query)
    c = set(record.get("signature_tokens") or []) | _route_tokens(record.get("content", ""))
    if not q or not c:
        return 0.0
    return len(q & c) / max(4, min(len(q), 18))


def _classify_failure(text: str) -> str | None:
    lowered = text.lower()
    for label, markers in FAILURE_CLASSES.items():
        if any(marker in lowered for marker in markers):
            return label
    return None


class MemoryProvider(BaseMemoryProvider):
    """Compact route-aware procedural memory; old traces never count as evidence."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        merged = {**DEFAULT_MEMORY_CONFIG, **(config or {})}
        super().__init__(memory_type=MemoryType.LIGHTWEIGHT_MEMORY, config=merged)
        self.storage_dir = merged.get("storage_dir", os.path.join("storage", MEMORY_SYSTEM))
        self.store_path = merged.get("store_path", os.path.join(self.storage_dir, "records.json"))
        self.top_k = int(merged.get("top_k", 2))
        self.interval = int(merged.get("shortterm_interval", 3))
        self.max_records = int(merged.get("max_records", 120))
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
        atomic_write_json(self.store_path, {"records": self._records[-self.max_records:]}, indent=2)

    def _phase_guidance(self, status: MemoryStatus) -> str:
        focus = self.config.get("focus", "compact route and failure-class lessons with current-observation authority")
        if status == MemoryStatus.BEGIN:
            return textwrap.dedent(f"""Round03_04 procedural memory ({focus}):
- observed_fact: value copied from current tool observations.
- derived_fact: deterministic transform of an observed_fact; keep the source relation.
- hypothesis: plan text, memory, or guessed entity until a current tool verifies it.
- ledger rule: read-only work fills evidence slots; stateful work fills mutation slots.
- commit rule: final_answer needs slot-bound support; complete_task needs every mutation slot succeeded or verified.
""").strip()
        return (
            "Round03_04 in-task memory reminder: route recovery by failure class; "
            "after schema/not-found/repeat errors, change the identifier source, relation path, or tool family; "
            "memory is never current evidence."
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
            memories.append(MemoryItem(
                id=f"{MEMORY_SYSTEM}_phase",
                content=self._phase_guidance(request.status),
                metadata={"source": "phase_guidance", "provenance": "procedure_hint"},
                score=1.0,
                type=MemoryItemType.TEXT,
            ))
        if request.status == MemoryStatus.BEGIN and self._records:
            ranked = sorted(((record, _score(request.query, record)) for record in self._records), key=lambda item: item[1], reverse=True)
            for record, score in ranked[: self.top_k]:
                if score <= 0:
                    continue
                label = record.get("kind", "procedure")
                memories.append(MemoryItem(
                    id=str(record.get("id") or uuid.uuid4()),
                    content=f"Relevant {label} memory:\n" + str(record.get("content", "")),
                    metadata={"source": label, "provenance": "procedure_hint"},
                    score=score,
                    type=MemoryItemType.TEXT,
                ))
        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(memories),
            request_id=str(uuid.uuid4()),
        )

    def _trajectory_text(self, trajectory_data: TrajectoryData) -> str:
        parts: list[str] = []
        for step in trajectory_data.trajectory or []:
            if isinstance(step, dict):
                parts.append(str(step.get("tool_calls") or step.get("tools") or "")[:180])
                parts.append(str(step.get("obs") or step.get("observations") or step.get("content") or "")[:240])
            else:
                parts.append(str(step)[:240])
        return " | ".join(part for part in parts if part)

    def _make_success_record(self, trajectory_data: TrajectoryData, trace_text: str) -> dict[str, Any]:
        route = ", ".join(sorted(_route_tokens(trajectory_data.query))[:8])
        content = textwrap.dedent(f"""Success procedure ({route}): keep route ledger fields distinct, use exact schemas, bind final answers to current observations, and complete stateful work only after all requested mutations are observed or verified.
""").strip()
        return {
            "id": str(uuid.uuid4()),
            "kind": "successful_procedure",
            "content": content,
            "signature_tokens": sorted(_route_tokens(trajectory_data.query) | _route_tokens(trace_text)),
            "created_at": time.time(),
            "metadata": trajectory_data.metadata or {},
        }

    def _make_failure_record(self, trajectory_data: TrajectoryData, trace_text: str) -> dict[str, Any] | None:
        failure_class = _classify_failure(trace_text)
        if failure_class is None:
            return None
        recovery = {
            "schema": "use current schema keys exactly; drop extras and fill required ids from observations.",
            "repeat": "change identifier source, relation path, query terms, or tool family before retrying.",
            "not_found": "broaden to search/list/get before a specific lookup or mutation retry.",
            "authorization": "verify actor/account context or choose a permitted mutation path.",
            "empty": "emit one executable JSON tool call from the available schema.",
            "unsupported_final": "collect relation-bound current evidence before final_answer.",
            "terminal": "delay complete_task until every mutation slot is succeeded or verified.",
        }[failure_class]
        route = ", ".join(sorted(_route_tokens(trajectory_data.query))[:8])
        content = f"Failure lesson ({failure_class}, route={route}): {recovery}"
        return {
            "id": str(uuid.uuid4()),
            "kind": "failure_lesson",
            "failure_class": failure_class,
            "content": content,
            "signature_tokens": sorted(_route_tokens(trajectory_data.query) | {failure_class, "recovery"}),
            "created_at": time.time(),
            "metadata": trajectory_data.metadata or {},
        }

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        metadata = trajectory_data.metadata or {}
        success = bool(metadata.get("is_correct") or metadata.get("task_success") or metadata.get("outcome") == "success")
        trace_text = self._trajectory_text(trajectory_data)
        if not trace_text:
            return False, "Skipped empty trajectory."
        if success and self.config.get("store_successes", True):
            record = self._make_success_record(trajectory_data, trace_text)
        elif self.config.get("store_failures", True):
            record = self._make_failure_record(trajectory_data, trace_text)
            if record is None:
                return False, "Skipped failure without reusable failure class."
        else:
            return False, "Skipped trajectory by memory write policy."
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        with file_lock(self.store_path):
            if os.path.exists(self.store_path):
                try:
                    with open(self.store_path, "r", encoding="utf-8") as handle:
                        payload = json.load(handle)
                    self._records = list(payload.get("records", []))
                except Exception:
                    self._records = []
            fingerprint = (record.get("kind"), record.get("failure_class"), record.get("content", "")[:220])
            for old in self._records:
                old_fingerprint = (old.get("kind"), old.get("failure_class"), old.get("content", "")[:220])
                if old_fingerprint == fingerprint:
                    return False, "Skipped duplicate route-aware memory."
            self._records.append(record)
            self._save()
        return True, f"Ingested {record.get('kind')} for {MEMORY_SYSTEM}."


MemoryClass = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
]
