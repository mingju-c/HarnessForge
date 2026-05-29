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


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    compiled = Template(template, undefined=StrictUndefined)
    try:
        return compiled.render(**variables)
    except Exception:
        # Keep a lenient fallback so generated/partial templates do not break runtime.
        return Template(template).render(**variables)


class BirdSQLPlanning(BasePlanning):
    """
    Minimal planning module.

    This follows BasePlanning directly and keeps the planning loop simple:
    - one initial plan
    - periodic summary/adaptation
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
        system_msg = {
            "role": MessageRole.SYSTEM,
            "content": [
                {
                    "type": "text",
                    "text": _render_template(
                        self.prompt_templates["planning"]["initial_plan"],
                        {"tools": self.tools, "task": task},
                    ),
                }
            ],
        }
        input_messages = [system_msg]
        memory_guidance = self.append_memory_guidance(input_messages)

        task_msg = {
            "role": MessageRole.USER,
            "content": [
                {
                    "type": "text",
                    "text": _render_template(
                        self.prompt_templates["planning"]["task_input"],
                        {"task": task},
                    ),
                }
            ],
        }

        chat_message: ChatMessage = self.model(input_messages + [task_msg])
        plan_text = chat_message.content
        plan_reasoning = chat_message.reasoning_content

        self.logger.log(
            Rule("[bold]Initial Plan", style="orange"),
            Text(
                textwrap.dedent(
                    f"""Planned strategy for current task:
            ```
            {plan_text}
            ```"""
                )
            ),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plan_text,
            plan_think="",
            plan_reasoning=plan_reasoning,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[
            [Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]
        ],
    ) -> SummaryStep:
        memory_messages = write_memory_to_messages(None, False)[1:]

        pre_msg = {
            "role": MessageRole.SYSTEM,
            "content": [
                {
                    "type": "text",
                    "text": _render_template(
                        self.prompt_templates["summary"]["update_pre_messages"],
                        {"task": task, "step": step},
                    ),
                }
            ],
        }
        post_msg = {
            "role": MessageRole.USER,
            "content": [
                {
                    "type": "text",
                    "text": _render_template(
                        self.prompt_templates["summary"]["update_post_messages"],
                        {"task": task, "step": step},
                    ),
                }
            ],
        }

        input_messages = [pre_msg] + memory_messages + [post_msg]
        chat_message: ChatMessage = self.model(input_messages)
        summary_text = chat_message.content
        summary_reasoning = chat_message.reasoning_content

        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_text,
            summary_reasoning=summary_reasoning,
        )
        self.memory.steps.append(summary_step)

        self.logger.log(
            Rule("[bold]Progress Summary", style="orange"),
            Text(
                textwrap.dedent(
                    f"""Current progress summary:
            ```
            {summary_text}
            ```"""
                )
            ),
            level=LogLevel.INFO,
        )
        return summary_step
