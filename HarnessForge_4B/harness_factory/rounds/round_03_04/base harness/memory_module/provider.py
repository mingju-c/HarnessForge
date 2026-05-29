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


MEMORY_SYSTEM = "format_contract_memory"
MEMORY_MODULE = "format_contract_memory"
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
    "focus": "format-contract and exact-answer memory",
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


def _signature_tokens(text: str) -> set[str]:
    tokens = _tokens(text)
    routed = set()
    for token in tokens:
        if token in {"search", "lookup", "retrieve", "query", "find", "crawl", "read", "get", "list"}:
            routed.add("read_only_lookup")
        elif token in {"update", "create", "delete", "add", "remove", "transfer", "schedule", "cancel", "enroll", "assign"}:
            routed.add("stateful_mutation")
        elif token in {"count", "calculate", "compute", "convert", "date", "vowel", "reverse", "sort"}:
            routed.add("deterministic_transform")
        elif token in {"error", "failed", "invalid", "missing", "unauthorized", "not_found", "blocked"}:
            routed.add("recovery")
        else:
            routed.add(token)
    return routed


def _score(query: str, record: dict[str, Any]) -> float:
    q = _signature_tokens(query)
    c = set(record.get("signature_tokens") or []) | _signature_tokens(record.get("content", ""))
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
    """Compact task-signature memory with success workflows and failure lessons."""

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
        focus = self.config.get("focus", "format-contract and exact-answer memory")
        if status == MemoryStatus.BEGIN:
            return textwrap.dedent(f"""Round02_02 procedural memory ({focus}):
- observed_fact: value copied from current tool observations.
- derived_fact: deterministic transform of an observed_fact; keep the source in mind.
- hypothesis: plan text, memory, or guessed entity until a tool verifies it.
- retrieval rule: old memories are workflow hints only, never current evidence.
- commit rule: final_answer needs current support; completion needs observed mutation progress or explicit blockers.
""").strip()
        return (
            "Round02_02 in-task memory reminder: route recovery by failure class; "
            "after schema/not-found/repeat errors, change the identifier source or tool strategy; "
            "commit only from current observations or deterministic derivations."
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

    def _trajectory_lines(self, trajectory_data: TrajectoryData) -> list[str]:
        lines: list[str] = []
        for step in trajectory_data.trajectory or []:
            if isinstance(step, dict):
                tool_calls = step.get("tool_calls") or step.get("tools") or []
                obs = step.get("obs") or step.get("observations") or step.get("content") or ""
                if tool_calls:
                    lines.append(f"tools={str(tool_calls)[:260]}")
                if obs:
                    lines.append(f"obs={str(obs)[:420]}")
            else:
                lines.append(str(step)[:420])
        return lines

    def _make_success_record(self, trajectory_data: TrajectoryData, lines: list[str]) -> dict[str, Any]:
        content = textwrap.dedent(f"""Task signature: {', '.join(sorted(_signature_tokens(trajectory_data.query))[:12])}
Reusable procedure: use exact schemas, maintain evidence/mutation progress, repair failed identifiers through search/list/get tools, and commit in the requested raw format.
Observed sequence sketch: {' | '.join(lines)[:1000]}
""").strip()
        return {
            "id": str(uuid.uuid4()),
            "kind": "successful_procedure",
            "content": content,
            "signature_tokens": sorted(_signature_tokens(trajectory_data.query) | _signature_tokens(" ".join(lines))),
            "created_at": time.time(),
            "metadata": trajectory_data.metadata or {},
        }

    def _make_failure_record(self, trajectory_data: TrajectoryData, lines: list[str]) -> dict[str, Any] | None:
        text = " | ".join(lines)
        failure_class = _classify_failure(text)
        if failure_class is None:
            return None
        recovery = {
            "schema": "use the current tool schema exactly; drop extra keys and fill required keys before retrying.",
            "repeat": "do not retry the same failed call; change identifier source, relation path, or tool.",
            "not_found": "resolve the entity through a broader search/list/get call before retrying the specific lookup.",
            "authorization": "verify actor/account context or switch to an authorized mutation path.",
            "empty": "emit one executable JSON tool call; if state progress already exists, consider controlled completion.",
            "unsupported_final": "obtain current evidence for the requested slot before final_answer.",
            "terminal": "delay completion until mutation progress is observed or remaining work is explicitly blocked.",
        }[failure_class]
        content = textwrap.dedent(f"""Failure lesson ({failure_class}): {recovery}
Task signature: {', '.join(sorted(_signature_tokens(trajectory_data.query))[:12])}
Trace sketch: {text[:900]}
""").strip()
        return {
            "id": str(uuid.uuid4()),
            "kind": "failure_lesson",
            "failure_class": failure_class,
            "content": content,
            "signature_tokens": sorted(_signature_tokens(trajectory_data.query) | {failure_class, "recovery"}),
            "created_at": time.time(),
            "metadata": trajectory_data.metadata or {},
        }

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        metadata = trajectory_data.metadata or {}
        success = bool(metadata.get("is_correct") or metadata.get("task_success") or metadata.get("outcome") == "success")
        lines = self._trajectory_lines(trajectory_data)
        if not lines:
            return False, "Skipped empty trajectory."
        if success and self.config.get("store_successes", True):
            record = self._make_success_record(trajectory_data, lines)
        elif self.config.get("store_failures", True):
            record = self._make_failure_record(trajectory_data, lines)
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
            fingerprint = (record.get("kind"), record.get("failure_class"), record.get("content", "")[:260])
            for old in self._records:
                old_fingerprint = (old.get("kind"), old.get("failure_class"), old.get("content", "")[:260])
                if old_fingerprint == fingerprint:
                    return False, "Skipped duplicate task-signature memory."
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
