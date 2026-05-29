"""
Base memory provider interface
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from .memory_types import MemoryRequest, MemoryResponse, TrajectoryData, MemoryType


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
