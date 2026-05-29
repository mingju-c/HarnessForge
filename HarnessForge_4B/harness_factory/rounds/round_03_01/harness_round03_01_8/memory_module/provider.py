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


MEMORY_SYSTEM = "round03_light_contract_memory"
MEMORY_MODULE = "round03_light_contract_memory"
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM
MEMORY_FOCUS = "sparse compact reminders with topology filtering"

BOILERPLATE = {
    "task", "answer", "tool", "tools", "schema", "final", "question", "available",
    "call", "return", "json", "strict", "use", "must", "should", "before", "after",
    "observation", "observations", "current", "memory", "planner", "ledger",
}
FAILURE_CLASSES = {
    "schema": ["missing required", "extra argument", "unexpected keyword", "unknown tool", "schema_preflight"],
    "repeat": ["repeated_failed_call", "low_value_repeat", "already failed"],
    "not_found": ["not found", "does not exist", "no matching"],
    "authorization": ["unauthorized", "permission", "forbidden", "not allowed"],
    "empty": ["empty_or_unparsed_action", "no executable tool", "no observations"],
    "unsupported_final": ["unsupported_final_answer", "answer_support_missing"],
    "terminal": ["terminal_not_ready", "premature", "complete_task"],
}
DEFAULT_MEMORY_CONFIG: dict[str, Any] = {
    "memory_system": MEMORY_SYSTEM,
    "focus": MEMORY_FOCUS,
    "top_k": 1,
    "shortterm_interval": 4,
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
        elif token in {"update", "create", "delete", "add", "remove", "transfer", "schedule", "cancel", "enroll", "assign", "edit", "set"}:
            routed.add("stateful_mutation")
        elif token in {"count", "calculate", "compute", "convert", "date", "vowel", "reverse", "sort", "digit"}:
            routed.add("deterministic_transform")
        elif token in {"error", "failed", "invalid", "missing", "unauthorized", "not_found", "blocked"}:
            routed.add("recovery")
        else:
            routed.add(token)
    return routed


def _is_searchqa_query(text: str, metadata: dict[str, Any] | None = None) -> bool:
    lowered = str(text or "").lower()
    if "searchqa terminal rule" in lowered or "mixed_searchqa" in lowered:
        return True
    metadata = metadata or {}
    return any(str(metadata.get(key, "")).lower() == "searchqa" for key in ("mixed_benchmark", "benchmark")) or str(metadata.get("data_source", "")).lower() == "mixed_searchqa"


def _classify_failure(text: str) -> str | None:
    lowered = text.lower()
    for label, markers in FAILURE_CLASSES.items():
        if any(marker in lowered for marker in markers):
            return label
    return None


def _score(query: str, record: dict[str, Any]) -> float:
    q = _route_tokens(query)
    c = set(record.get("signature_tokens") or []) | _route_tokens(record.get("content", ""))
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    route_bonus = 0.20 if {"read_only_lookup", "stateful_mutation", "deterministic_transform"} & q & c else 0.0
    failure_bonus = 0.15 if record.get("failure_class") and record.get("failure_class") in q else 0.0
    return overlap / max(4, min(len(q), 18)) + route_bonus + failure_bonus


class MemoryProvider(BaseMemoryProvider):
    """Topology-routed lightweight memory with compact reusable lessons."""

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

    def _phase_guidance(self, status: MemoryStatus, is_searchqa: bool = False) -> str:
        if status == MemoryStatus.BEGIN:
            guidance = textwrap.dedent(f"""Round03 procedural memory ({MEMORY_FOCUS}):
            - observed_fact: value copied from current tool observations.
            - derived_fact: deterministic transform of an observed_fact; keep source and relation path attached.
            - hypothesis: plan text, memory, and guessed identifiers until a tool verifies them.
            - recovery rule: after schema/not-found/repeat errors, change identifier source or tool family.
            - commit rule: final_answer needs relation-bound current support; completion needs required mutation coverage.
            """).strip()
        else:
            guidance = (
                "Round03 in-task memory reminder: memories are workflow hints only; "
                "repair by failure class and commit only from current evidence or verified mutations."
            )
        if is_searchqa:
            guidance += (
                "\nSearchQA override: do not reuse old answers or old rewritten queries; "
                "start from the current question wording and copy the supported surface form."
            )
        return guidance

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
        is_searchqa = _is_searchqa_query(request.query)
        if request.status == MemoryStatus.BEGIN or (request.status == MemoryStatus.IN and step % self.interval == 0):
            memories.append(MemoryItem(
                id=f"{MEMORY_SYSTEM}_phase",
                content=self._phase_guidance(request.status, is_searchqa),
                metadata={"source": "phase_guidance", "provenance": "procedure_hint"},
                score=1.0,
                type=MemoryItemType.TEXT,
            ))
        if request.status == MemoryStatus.BEGIN and self._records and not is_searchqa:
            ranked = sorted(((record, _score(request.query, record)) for record in self._records), key=lambda item: item[1], reverse=True)
            added = 0
            for record, score in ranked:
                if score <= 0 or added >= self.top_k:
                    continue
                label = record.get("kind", "procedure")
                content = str(record.get("content", ""))[:900]
                memories.append(MemoryItem(
                    id=str(record.get("id") or uuid.uuid4()),
                    content=f"Relevant {label} memory ({record.get('route', 'unknown')}):\n{content}",
                    metadata={"source": label, "provenance": "procedure_hint", "route": record.get("route")},
                    score=score,
                    type=MemoryItemType.TEXT,
                ))
                added += 1
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
                    lines.append(f"tools={str(tool_calls)[:220]}")
                if obs:
                    lines.append(f"obs={str(obs)[:300]}")
            else:
                lines.append(str(step)[:300])
        return lines

    def _route(self, query: str, lines: list[str]) -> str:
        routed = _route_tokens(query + " " + " ".join(lines))
        for label in ("stateful_mutation", "deterministic_transform", "read_only_lookup", "recovery"):
            if label in routed:
                return label
        return "unknown"

    def _make_success_record(self, trajectory_data: TrajectoryData, lines: list[str]) -> dict[str, Any]:
        route = self._route(trajectory_data.query, lines)
        content = textwrap.dedent(f"""Procedure recipe: keep exact schemas, maintain slot/mutation coverage, repair identifiers through broader list/search/get tools, and commit in raw requested format.
        Route: {route}
        Task topology tokens: {', '.join(sorted(_route_tokens(trajectory_data.query))[:12])}
        Short sequence sketch: {' | '.join(lines)[:700]}
        """).strip()
        return {
            "id": str(uuid.uuid4()),
            "kind": "successful_procedure",
            "route": route,
            "content": content,
            "signature_tokens": sorted(_route_tokens(trajectory_data.query) | _route_tokens(" ".join(lines)) | {route}),
            "created_at": time.time(),
            "metadata": trajectory_data.metadata or {},
        }

    def _make_failure_record(self, trajectory_data: TrajectoryData, lines: list[str]) -> dict[str, Any] | None:
        text = " | ".join(lines)
        failure_class = _classify_failure(text)
        if failure_class is None:
            return None
        route = self._route(trajectory_data.query, lines)
        recovery = {
            "schema": "use current tool schema exactly; fill missing ids from observations before retrying.",
            "repeat": "do not retry the same failed call; change identifier source, relation path, or tool family.",
            "not_found": "resolve the entity through broader search/list/get before retrying the specific lookup.",
            "authorization": "verify actor/account context or switch to a permitted mutation path.",
            "empty": "emit one executable JSON tool call; avoid terminal calls without support or coverage.",
            "unsupported_final": "obtain current relation-bound evidence for the requested slot before final_answer.",
            "terminal": "delay completion until required mutation coverage is observed.",
        }[failure_class]
        content = textwrap.dedent(f"""Failure recipe ({failure_class}): {recovery}
        Route: {route}
        Task topology tokens: {', '.join(sorted(_route_tokens(trajectory_data.query))[:12])}
        Short trace sketch: {text[:700]}
        """).strip()
        return {
            "id": str(uuid.uuid4()),
            "kind": "failure_lesson",
            "route": route,
            "failure_class": failure_class,
            "content": content,
            "signature_tokens": sorted(_route_tokens(trajectory_data.query) | {route, failure_class, "recovery"}),
            "created_at": time.time(),
            "metadata": trajectory_data.metadata or {},
        }

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        metadata = trajectory_data.metadata or {}
        if _is_searchqa_query(trajectory_data.query, metadata):
            return False, "Skipped SearchQA trajectory to avoid answer/query leakage."
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
            fingerprint = (record.get("kind"), record.get("route"), record.get("failure_class"), record.get("content", "")[:240])
            for old in self._records:
                old_fingerprint = (old.get("kind"), old.get("route"), old.get("failure_class"), old.get("content", "")[:240])
                if old_fingerprint == fingerprint:
                    return False, "Skipped duplicate topology memory."
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
