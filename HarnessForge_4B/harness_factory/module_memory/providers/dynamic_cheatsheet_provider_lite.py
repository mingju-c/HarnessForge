from __future__ import annotations

import io
import json
import os
import re
import time
import uuid
from typing import Any, Optional

from ..base_memory import BaseMemoryProvider
from ..memory_types import (
    MemoryItem,
    MemoryItemType,
    MemoryRequest,
    MemoryResponse,
    MemoryStatus,
    MemoryType,
    TrajectoryData,
)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with io.open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _write_text(path: str, content: str) -> None:
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(content or "")


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"\w+", str(text).lower()) if token]


def _lexical_score(query: str, candidate: str) -> float:
    query_tokens = set(_tokenize(query))
    candidate_tokens = set(_tokenize(candidate))
    if not query_tokens or not candidate_tokens:
        return 0.0
    return len(query_tokens & candidate_tokens) / len(query_tokens)


class DynamicCheatsheetProvider(BaseMemoryProvider):
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            raise ValueError("DynamicCheatsheetProvider requires an explicit config dict.")
        super().__init__(memory_type=MemoryType.DYNAMIC_CHEATSHEET, config=config)
        self.store_path = self.config.get("store_path", "./dynamic_cheatsheet")
        self.records_file = self.config.get("records_file", "dynamic_cheatsheet.json")
        self.cheatsheet_file = self.config.get("cheatsheet_file", "global_cheatsheet.txt")
        self.records_path = os.path.join(self.store_path, self.records_file)
        self.cheatsheet_path = os.path.join(self.store_path, self.cheatsheet_file)
        self.top_k = int(self.config.get("top_k", 1))
        self.model = self.config.get("model")
        self._records: list[dict[str, Any]] = []

    def initialize(self) -> bool:
        _ensure_dir(self.store_path)
        self._load_records()
        if not os.path.exists(self.cheatsheet_path):
            _write_text(self.cheatsheet_path, "")
        return True

    def _load_records(self) -> None:
        if not os.path.exists(self.records_path):
            self._records = []
            return
        try:
            with open(self.records_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self._records = list(payload.get("memories", []))
        except Exception:
            self._records = []

    def _save_records(self) -> None:
        os.makedirs(os.path.dirname(self.records_path) or ".", exist_ok=True)
        with open(self.records_path, "w", encoding="utf-8") as handle:
            json.dump({"memories": self._records}, handle, ensure_ascii=False, indent=2)

    def _call_llm(self, prompt: str) -> str:
        if self.model is None:
            return ""
        try:
            response = self.model([{"role": "user", "content": [{"type": "text", "text": prompt}]}])
            return str(getattr(response, "content", response)).strip()
        except Exception:
            return ""

    def _reconstruct_trajectory(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return f"Task: {trajectory_data.query}"
        parts = [f"Task: {trajectory_data.query}"]
        for index, step in enumerate(trajectory_data.trajectory, 1):
            if isinstance(step, dict):
                step_type = step.get("type", "step")
                content = step.get("content", "")
            else:
                step_type = getattr(step, "type", "step")
                content = getattr(step, "content", str(step))
            parts.append(f"Step {index} ({step_type}): {content}")
        if trajectory_data.result:
            parts.append(f"Final Result: {trajectory_data.result}")
        return "\n".join(parts)

    def _distill_record(self, trajectory_data: TrajectoryData) -> str:
        trace_text = self._reconstruct_trajectory(trajectory_data)
        prompt = f"""Summarize this successful trajectory into a short reusable cheatsheet.
Keep it concrete and under 120 words.
Return plain text only.

{trace_text}"""
        distilled = self._call_llm(prompt)
        if distilled:
            return distilled
        lines = [line.strip() for line in trace_text.splitlines() if line.strip()]
        return "\n".join(lines[:6])

    def _refresh_global_cheatsheet(self) -> None:
        unique_entries: list[str] = []
        seen: set[str] = set()
        for record in reversed(self._records):
            cheat = str(record.get("cheatsheet", "")).strip()
            if not cheat or cheat in seen:
                continue
            seen.add(cheat)
            unique_entries.append(cheat)
            if len(unique_entries) >= 12:
                break
        unique_entries.reverse()
        _write_text(self.cheatsheet_path, "\n\n".join(unique_entries))

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if request.status not in {MemoryStatus.BEGIN, MemoryStatus.IN}:
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)

        query = str(request.query or "")
        context = str(request.context or "")
        combined_query = f"{query}\n{context}".strip()
        memories: list[MemoryItem] = []
        global_cheatsheet = _read_text(self.cheatsheet_path).strip()

        if request.status == MemoryStatus.BEGIN and global_cheatsheet:
            memories.append(
                MemoryItem(
                    id="dynamic_cheatsheet_global",
                    content=f"Dynamic cheatsheet:\n{global_cheatsheet}",
                    metadata={"source": "global_cheatsheet"},
                    score=1.0,
                    type=MemoryItemType.TEXT,
                )
            )

        ranked = sorted(
            (
                (
                    record,
                    _lexical_score(
                        combined_query,
                        f"{record.get('query', '')}\n{record.get('summary', '')}\n{record.get('cheatsheet', '')}",
                    ),
                )
                for record in self._records
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        limit = self.top_k if request.status == MemoryStatus.BEGIN else 1
        for record, score in ranked[: max(1, limit)]:
            if score <= 0 and request.status == MemoryStatus.IN:
                continue
            memories.append(
                MemoryItem(
                    id=str(record.get("id", uuid.uuid4())),
                    content=(
                        "Relevant distilled cheatsheet note:\n"
                        f"Task: {record.get('query', '')}\n"
                        f"Note: {record.get('summary', '')}"
                    ),
                    metadata={
                        "source": "dynamic_cheatsheet_record",
                        "created_at": record.get("created_at"),
                    },
                    score=score,
                    type=MemoryItemType.TEXT,
                )
            )

        return MemoryResponse(
            memories=memories,
            memory_type=self.memory_type,
            total_count=len(self._records),
            request_id=str(uuid.uuid4()),
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        metadata = trajectory_data.metadata or {}
        is_success = bool(
            metadata.get("is_correct")
            or metadata.get("task_success")
            or metadata.get("outcome") == "success"
        )
        if not is_success:
            return False, "Skipped: trajectory not marked successful."

        summary = self._distill_record(trajectory_data).strip()
        if not summary:
            return False, "Skipped: empty distilled cheatsheet."

        record = {
            "id": str(uuid.uuid4()),
            "query": str(trajectory_data.query or ""),
            "summary": summary,
            "cheatsheet": summary,
            "created_at": time.time(),
        }
        self._records.append(record)
        self._save_records()
        self._refresh_global_cheatsheet()
        return True, f"Stored cheatsheet note: {summary[:80]}"


__all__ = ["DynamicCheatsheetProvider"]
