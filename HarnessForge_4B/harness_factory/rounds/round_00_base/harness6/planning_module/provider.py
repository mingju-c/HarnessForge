from __future__ import annotations

import textwrap
from typing import Any, Callable, Dict, List, Optional

from jinja2 import StrictUndefined, Template
from rich.rule import Rule
from rich.text import Text

from Agents.memory import ActionStep, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import LogLevel
from module_planning.base_planning import BasePlanning


def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception:
        return Template(template).render(**variables)


class PlanningProvider(BasePlanning):
    def topology_initialize(self, task: str) -> PlanningStep:
        system_prompt = populate_template(
            self.prompt_templates["planning"]["initial_plan"],
            {
                "task": task,
                "tools": self.tools,
            },
        )
        task_prompt = populate_template(
            self.prompt_templates["planning"].get("task_input", "Task:\n{{task}}"),
            {"task": task},
        )

        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [{"type": "text", "text": system_prompt}],
            }
        ]
        memory_guidance = self.append_memory_guidance(input_messages)
        task_messages = [
            {
                "role": MessageRole.USER,
                "content": [{"type": "text", "text": task_prompt}],
            }
        ]

        response: ChatMessage = self.model(input_messages + task_messages)
        plan_text = response.content
        plan_reasoning = getattr(response, "reasoning_content", "")

        self.logger.log(
            Rule("Parallel Plan", style="orange"),
            Text(
                textwrap.dedent(
                    f"""Planned execution outline:
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
        pre_text = populate_template(
            self.prompt_templates["summary"]["update_pre_messages"],
            {"task": task, "step": step},
        )
        post_text = populate_template(
            self.prompt_templates["summary"]["update_post_messages"],
            {"task": task, "step": step},
        )

        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [{"type": "text", "text": pre_text}],
            },
            *memory_messages,
            {
                "role": MessageRole.USER,
                "content": [{"type": "text", "text": post_text}],
            },
        ]

        response: ChatMessage = self.model(input_messages)
        summary_text = response.content
        summary_reasoning = getattr(response, "reasoning_content", "")

        self.logger.log(
            Rule("Progress Review", style="orange"),
            Text(f"\n{summary_text}\n"),
            level=LogLevel.INFO,
        )

        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_text,
            summary_reasoning=summary_reasoning,
        )
        self.memory.steps.append(summary_step)
        return summary_step


PLANNING_SYSTEM = "guarded_small_committee"
PLANNING_MODULE = "guarded_small_committee"
PlanningClass = PlanningProvider

__all__ = [
    "PLANNING_SYSTEM",
    "PLANNING_MODULE",
    "PlanningProvider",
    "PlanningClass",
]
