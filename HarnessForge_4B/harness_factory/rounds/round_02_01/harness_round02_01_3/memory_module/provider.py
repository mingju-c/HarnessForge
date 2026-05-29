from __future__ import annotations

from .round02_memory import Round02MemoryProvider


MEMORY_SYSTEM = 'round02_mutation_memory'
MEMORY_MODULE = 'round02_mutation_memory'
DEFAULT_MEMORY_SYSTEM = MEMORY_SYSTEM


class MemoryProvider(Round02MemoryProvider):
    MEMORY_SYSTEM = MEMORY_SYSTEM
    MEMORY_MODULE = MEMORY_MODULE
    DEFAULT_CONFIG = {
        "memory_system": MEMORY_SYSTEM,
        "focus": 'stateful workflow lessons and blocked-mutation recovery',
        "top_k": 2,
        "shortterm_interval": 2,
        "store_failures": True,
        "store_successes": True,
    }


MemoryClass = MemoryProvider

__all__ = [
    "MEMORY_SYSTEM",
    "MEMORY_MODULE",
    "DEFAULT_MEMORY_SYSTEM",
    "MemoryProvider",
    "MemoryClass",
]
