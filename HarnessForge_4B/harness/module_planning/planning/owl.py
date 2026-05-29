import textwrap
from typing import Any, Callable, Dict, List, Optional

from jinja2 import StrictUndefined, Template
from rich.rule import Rule
from rich.text import Text

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from .base_planning import BasePlanning


def populate_template(template: str, variables: Dict[str, Any]) -> str:
    """
    Fill Jinja2 template with variables.
    """
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")


class OwlPlanning(BasePlanning):
    """
    OWL-style planning & replanning implementation.
    - topology_initialize(task): initial plan generation (no step/is_first_step args)
    """

    def __init__(
        self,
        model: Callable[[List[Dict[str, str]]], ChatMessage],
        tools: Dict[str, Tool],
        prompt_templates: Dict[str, Any],
        memory: AgentMemory,
        logger: AgentLogger,
    ):
        super().__init__(model, tools, prompt_templates, memory, logger)

    def topology_initialize(self, task: str) -> PlanningStep:
        """
        Generate initial task plan and record to memory and logger.
        """

        # System prompt (planning.initial_plan)
        system_msg = {
            "role": MessageRole.SYSTEM,
            "content": [{
                "type": "text",
                "text": populate_template(
                    self.prompt_templates["planning"]["initial_plan"],
                    variables={"tools": self.tools},
                ),
            }],
        }

        # User prompt (planning.task_input) 鈥?keep it minimal and stable
        user_msg = {
            "role": MessageRole.USER,
            "content": [{
                "type": "text",
                "text": populate_template(
                    self.prompt_templates["planning"]["task_input"],
                    variables={"task": task},
                ),
            }],
        }

        input_messages = [system_msg]
        memory_guidance = self.append_memory_guidance(input_messages)
        input_messages.append(user_msg)

        chat_message_plan: ChatMessage = self.model(input_messages)
        plan_text = chat_message_plan.content
        plan_reasoning = chat_message_plan.reasoning_content

        # Log
        final_plan_redaction = textwrap.dedent(
            f"""Here is the plan of action that I will follow to solve the task:\n```\n{plan_text}\n```\n"""
        )
        self.logger.log(
            Rule("[bold]Initial plan", style="orange"),
            Text(final_plan_redaction),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plan_text,
            plan_think="",  # keep empty unless you have explicit non-cot think
            plan_reasoning=plan_reasoning,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]],
    ) -> SummaryStep:

        summary_step = SummaryStep(
            model_input_messages="",
            summary="",
            summary_reasoning="",
        )
        return summary_step

