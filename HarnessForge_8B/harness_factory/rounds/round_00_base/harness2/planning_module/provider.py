import textwrap
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from rich.rule import Rule
from rich.text import Text
from module_planning.base_planning import BasePlanning

def populate_template(template: str, variables: Dict[str, Any]) -> str:
    """
    Fill Jinja2 template with variables.

    Args:
        template: Jinja2 template string
        variables: Template variable dictionary

    Returns:
        str: Filled string
    """
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")


class PlanningProvider(BasePlanning):
    """
    Planning implementation for a deliberate single-agent planner.

    This class provides concrete implementations of planning methods:
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
        super().__init__(model, tools, prompt_templates, memory, logger)

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
        # Build system prompt messages
        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["planning"]["initial_plan"],
                            variables={
                                "tools": self.tools,
                            },
                        ),
                    }
                ],
            },
        ]
        memory_guidance = self.append_memory_guidance(input_messages)

        # Build task input messages
        task_messages = [{
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": populate_template(self.prompt_templates["planning"]["task_input"], variables={"task": task})}],
        }]

        # Call model to generate plan
        chat_message_plan: ChatMessage = self.model(input_messages + task_messages)
        think_content = chat_message_plan.reasoning_content
        plans = chat_message_plan.content
        plans_think, plans_answer = "", plans

        # Format plan text for log output
        final_plan_redaction = textwrap.dedent(
            f"""Here is the plan of action that I will follow to solve the task:\n```\n{plans_answer}\n```\n"""
        )

        # Output to logger
        self.logger.log(
            Rule("[bold]Initial plan", style="orange"),
            Text(final_plan_redaction),
            level=LogLevel.INFO,
        )

        # Create PlanningStep object
        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plans_answer,
            plan_think=plans_think,
            plan_reasoning=think_content,
            memory_guidance=memory_guidance,
        )

        # Record to memory
        self.memory.steps.append(planning_step)

        return planning_step


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
        # Read execution history from memory (skip system prompt)
        memory_messages = write_memory_to_messages(None, False)[1:]

        # Build summary prompt pre and post messages
        update_pre_messages = {
            "role": MessageRole.SYSTEM,
            "content": [{"type": "text", "text": self.prompt_templates["summary"]["update_pre_messages"]}],
        }
        update_post_messages = {
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": self.prompt_templates["summary"]["update_post_messages"]}],
        }

        # Combine complete input messages
        input_messages = [update_pre_messages] + memory_messages + [update_post_messages]

        # Call model to generate summary
        chat_message_summary: ChatMessage = self.model(input_messages)

        summary_answer = chat_message_summary.content
        summary_cot_content = chat_message_summary.reasoning_content

        # Format summary text for log output
        final_summary_redaction = textwrap.dedent(
            f"""
            Here is my summary of action to solve the task:
            ```
            {summary_answer}
            ```"""
        )

        # Create SummaryStep object
        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_answer,
            summary_reasoning=summary_cot_content,
        )

        # Record to memory
        self.memory.steps.append(summary_step)

        # Output to logger
        self.logger.log(
            Rule("[bold]Summary", style="orange"),
            Text(final_summary_redaction),
            level=LogLevel.INFO,
        )

        return summary_step

PLANNING_SYSTEM = 'concise_reflection'
PLANNING_MODULE = 'concise_reflection'
PlanningClass = PlanningProvider

__all__ = ['PLANNING_SYSTEM', 'PLANNING_MODULE', 'PlanningProvider', 'PlanningClass']

