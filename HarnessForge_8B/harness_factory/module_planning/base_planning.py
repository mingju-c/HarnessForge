from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger
from Agents.tools import Tool


class BasePlanning(ABC):
    """
    Base planning module for harness-specific planning implementations.

    This module provides two core methods to replace planning logic in agents.py:
    - topology_initialize: Generates initial task plan (replaces planning_step)
    - adaptation: Generates periodic progress summaries (replaces summary_step)
    """

    def __init__(
        self,
        model: Callable[[List[Dict[str, str]]], ChatMessage],
        tools: Dict[str, Tool],
        prompt_templates: Dict[str, Any],
        memory: AgentMemory,
        logger: AgentLogger,
    ):
        self.model = model
        self.tools = tools
        self.prompt_templates = prompt_templates
        self.memory = memory
        self.logger = logger
        self.memory_guidance: str | None = None

    def append_memory_guidance(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        guidance = getattr(self, "memory_guidance", None)
        if not guidance:
            return None
        formatted_memory = (
            "----Memory System Guidance----\n"
            f"{guidance}\n"
            "----End Memory----"
        )
        messages.append(
            {
                "role": MessageRole.USER,
                "content": [{"type": "text", "text": formatted_memory}],
            }
        )
        return guidance

    @abstractmethod
    def topology_initialize(self, task: str) -> PlanningStep:
        pass

    @abstractmethod
    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[
            [Optional[List[ActionStep]], Optional[bool]],
            List[Dict[str, str]],
        ],
    ) -> SummaryStep:
        pass
