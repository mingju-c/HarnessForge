from typing import Any, Callable, Dict, List, Optional

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger
from Agents.tools import Tool

from abc import ABC, abstractmethod

class BasePlanning(ABC):
    """
    Planning module for Flash-Searcher agent framework.

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
        logger: AgentLogger
    ):
        """
        Initialize planning module.

        Args:
            model: LLM model instance that accepts message list and returns ChatMessage
            tools: Available tools dictionary, key is tool name, value is Tool object
            prompt_templates: Prompt template dictionary
            memory: Agent memory object for recording steps (passed by reference)
            logger: Logger object for output (passed by reference)
        """
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
        messages.append({
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": formatted_memory}],
        })
        return guidance

    @abstractmethod
    def topology_initialize(self, task: str) -> PlanningStep:
        """
        Generate initial task plan and record to memory and logger.

        This method replaces the MultiStepAgent.planning_step() method with identical functionality:
        1. Build planning prompt messages
        2. Call LLM to generate plan
        3. Extract plan content and reasoning process
        4. Record to memory (via self.memory.steps.append)
        5. Output to logger (via self.logger.log)

        Args:
            task: Task description to execute

        Returns:
            PlanningStep: Step object containing plan information with fields:
                - model_input_messages: Message list sent to model
                - plan: Generated plan text
                - plan_think: Plan thinking content (currently empty string)
                - plan_reasoning: Model reasoning content
        """
        pass

    @abstractmethod
    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]]
    ) -> SummaryStep:
        """
        Generate execution progress summary and record to memory and logger.

        This method replaces the MultiStepAgent.summary_step() method with identical functionality:
        1. Read execution history from memory
        2. Build summary prompt messages
        3. Call LLM to generate summary
        4. Extract summary content and reasoning process
        5. Record to memory (via self.memory.steps.append)
        6. Output to logger (via self.logger.log)

        Args:
            task: Task description to execute
            step: Current step number for context prompting
            write_memory_to_messages: Function to convert memory steps to message list

        Returns:
            SummaryStep: Step object containing summary information with fields:
                - model_input_messages: Message list sent to model
                - summary: Generated summary text
                - summary_reasoning: Model reasoning content
        """
        pass

