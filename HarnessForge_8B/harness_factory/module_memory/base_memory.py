"""
Base memory provider interface
"""

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Optional
from .memory_types import MemoryRequest, MemoryResponse, TrajectoryData, MemoryType


@contextmanager
def file_lock(target_path: str, timeout: float = 30.0, poll_interval: float = 0.05):
    lock_path = f"{target_path}.lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    start = time.time()
    fd = None

    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            if time.time() - start >= timeout:
                raise TimeoutError(f"Timed out waiting for file lock: {lock_path}")
            time.sleep(poll_interval)

    try:
        os.write(fd, str(os.getpid()).encode("ascii", "ignore"))
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass


def atomic_write_json(path: str, data: Any, *, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=indent, ensure_ascii=False)
    os.replace(temp_path, path)


def atomic_write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(content if content is not None else "")
    os.replace(temp_path, path)


def resolve_storage_dir(
    config: Optional[dict],
    *,
    preferred_keys: list[str | tuple[str, int]] | tuple[str | tuple[str, int], ...],
    fallback_dir: str = "./storage",
) -> Path:
    cfg = config or {}
    for entry in preferred_keys:
        if isinstance(entry, tuple):
            key, extra_parents = entry
        else:
            key, extra_parents = entry, 0
        value = cfg.get(key)
        if not value:
            continue
        path = Path(str(value)).expanduser()
        if path.suffix:
            path = path.parent
        for _ in range(int(extra_parents)):
            path = path.parent
        return path

    fallback = Path(str(cfg.get("storage_dir", fallback_dir))).expanduser()
    return fallback.parent if fallback.suffix else fallback


def migrate_legacy_json_state(target_path: str | Path, legacy_paths: list[str | Path]) -> Path | None:
    target = Path(target_path)
    if target.exists():
        return None

    for legacy_path in legacy_paths:
        legacy = Path(legacy_path).expanduser()
        if not legacy.exists() or legacy == target:
            continue
        os.makedirs(target.parent, exist_ok=True)
        shutil.copy2(legacy, target)
        return legacy

    return None


class BaseMemoryProvider(ABC):
    """Abstract base class for memory providers"""
    
    def __init__(self, memory_type: MemoryType, config: Optional[dict] = None):
        self.memory_type = memory_type
        self.config = config or {}
    
    @abstractmethod
    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        """
        Retrieve relevant memories based on query, context and status
        
        Args:
            request: MemoryRequest containing query, context, status and optional params
            
        Returns:
            MemoryResponse containing relevant memories
        """
        pass
    
    @abstractmethod
    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        """
        Store/ingest new memory from trajectory data

        Args:
            trajectory_data: TrajectoryData containing query, trajectory and metadata

        Returns:
            tuple[bool, str]: (Success status of memory ingestion, Description of absorbed memory)
        """
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the memory provider (load existing data, setup indices, etc.)
        
        Returns:
            bool: Success status of initialization
        """
        pass
    
    def get_memory_type(self) -> MemoryType:
        """Get the type of this memory provider"""
        return self.memory_type
    
    def get_config(self) -> dict:
        """Get the configuration of this memory provider"""
        return self.config.copy()


class WriteOnlyMemoryProvider(BaseMemoryProvider):
    """Shared wrapper that disables retrieval while preserving ingestion."""

    def __init__(self, wrapped: BaseMemoryProvider):
        super().__init__(
            memory_type=wrapped.get_memory_type(),
            config=wrapped.get_config(),
        )
        self._wrapped = wrapped

    def initialize(self) -> bool:
        return self._wrapped.initialize()

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        return MemoryResponse(
            memories=[],
            memory_type=self.memory_type,
            total_count=0,
        )

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return self._wrapped.take_in_memory(trajectory_data)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


class ReadOnlyMemoryProvider(BaseMemoryProvider):
    """Shared wrapper that allows retrieval while disabling ingestion."""

    def __init__(self, wrapped: BaseMemoryProvider):
        super().__init__(
            memory_type=wrapped.get_memory_type(),
            config=wrapped.get_config(),
        )
        self._wrapped = wrapped

    def initialize(self) -> bool:
        return self._wrapped.initialize()

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        return self._wrapped.provide_memory(request)

    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        return False, "Read-only memory provider: ingestion is disabled."

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)
