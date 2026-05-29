from __future__ import annotations

import textwrap
from typing import Any, Callable, Dict, List, Optional

from jinja2 import StrictUndefined, Template
from rich.rule import Rule
from rich.text import Text

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from module_planning.base_planning import BasePlanning


PLANNING_SYSTEM = "round02_02_repair_registry_planning"
PLANNING_MODULE = PLANNING_SYSTEM


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    compiled = Template(template, undefined=StrictUndefined)
    try:
        return compiled.render(**variables)
    except Exception:
        return Template(template).render(**variables)


class PlanningProvider(BasePlanning):
    """Compact planner for the REPAIR_REGISTRY contract."""

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
            "content": [{
                "type": "text",
                "text": _render_template(
                    self.prompt_templates["planning"]["initial_plan"],
                    {"tools": self.tools, "task": task, "planning_system": PLANNING_SYSTEM},
                ),
            }],
        }
        task_msg = {
            "role": MessageRole.USER,
            "content": [{
                "type": "text",
                "text": _render_template(
                    self.prompt_templates["planning"]["task_input"],
                    {"task": task},
                ),
            }],
        }
        input_messages = [system_msg]
        memory_guidance = self.append_memory_guidance(input_messages)
        chat_message: ChatMessage = self.model(input_messages + [task_msg])
        plan_text = str(chat_message.content or "").strip()
        plan_reasoning = chat_message.reasoning_content

        self.logger.log(
            Rule("[bold]REPAIR_REGISTRY Plan", style="orange"),
            Text(textwrap.dedent(f"""Plan/status contract:
```
{plan_text}
```""")),
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
            "content": [{
                "type": "text",
                "text": _render_template(
                    self.prompt_templates["summary"]["update_pre_messages"],
                    {"task": task, "step": step},
                ),
            }],
        }
        post_msg = {
            "role": MessageRole.USER,
            "content": [{
                "type": "text",
                "text": _render_template(
                    self.prompt_templates["summary"]["update_post_messages"],
                    {"task": task, "step": step},
                ),
            }],
        }
        input_messages = [pre_msg] + memory_messages + [post_msg]
        chat_message: ChatMessage = self.model(input_messages)
        summary_text = str(chat_message.content or "").strip()
        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_text,
            summary_reasoning=chat_message.reasoning_content,
        )
        self.memory.steps.append(summary_step)
        self.logger.log(
            Rule("[bold]REPAIR_REGISTRY Summary", style="orange"),
            Text(textwrap.dedent(f"""Current status:
```
{summary_text}
```""")),
            level=LogLevel.INFO,
        )
        return summary_step


PlanningClass = PlanningProvider

__all__ = [
    "PLANNING_SYSTEM",
    "PLANNING_MODULE",
    "PlanningProvider",
    "PlanningClass",
]
