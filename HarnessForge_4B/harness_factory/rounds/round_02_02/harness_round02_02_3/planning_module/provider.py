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


PLANNING_SYSTEM = "hop_chain_planning"
PLANNING_MODULE = "hop_chain_planning"
CANDIDATE_NAME = "harness_round02_02_3"
PLAN_FOCUS = "ordered evidence dependencies, source entity, relation result, transform, and final slot"


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    compiled = Template(template, undefined=StrictUndefined)
    try:
        return compiled.render(**variables)
    except Exception:
        return Template(template).render(**variables)


class PlanningProvider(BasePlanning):
    """Compact structured planner that emits an action-visible ledger packet."""

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
                    {"tools": self.tools, "task": task, "plan_focus": PLAN_FOCUS},
                ),
            }],
        }
        input_messages = [system_msg]
        memory_guidance = self.append_memory_guidance(input_messages)
        task_msg = {
            "role": MessageRole.USER,
            "content": [{
                "type": "text",
                "text": _render_template(
                    self.prompt_templates["planning"]["task_input"],
                    {"task": task, "plan_focus": PLAN_FOCUS},
                ),
            }],
        }
        chat_message: ChatMessage = self.model(input_messages + [task_msg])
        plan_text = str(chat_message.content or "").strip()
        if not plan_text:
            plan_text = textwrap.dedent("""task_type: unknown
route: unknown
evidence_slots: []
dependency_edges: []
required_mutations: []
verification_targets: []
answer_format: raw requested answer
terminal_policy: final_answer needs current support; complete_task needs observed state progress
next_tool_intent: choose one valid schema-matching tool
""").strip()

        self.logger.log(
            Rule(f"[bold]Round02_02 {CANDIDATE_NAME} Plan Packet", style="orange"),
            Text(textwrap.dedent(f"""Execution packet:
```
{plan_text}
```""")),
            level=LogLevel.INFO,
        )
        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plan_text,
            plan_think="",
            plan_reasoning=getattr(chat_message, "reasoning_content", ""),
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
                    {"task": task, "step": step, "plan_focus": PLAN_FOCUS},
                ),
            }],
        }
        post_msg = {
            "role": MessageRole.USER,
            "content": [{
                "type": "text",
                "text": _render_template(
                    self.prompt_templates["summary"]["update_post_messages"],
                    {"task": task, "step": step, "plan_focus": PLAN_FOCUS},
                ),
            }],
        }
        chat_message: ChatMessage = self.model([pre_msg] + memory_messages + [post_msg])
        summary_text = str(chat_message.content or "").strip()
        if not summary_text:
            summary_text = "status: continue with one valid evidence/action step; avoid unsupported finalization."
        summary_step = SummaryStep(
            model_input_messages=[pre_msg] + memory_messages + [post_msg],
            summary=summary_text,
            summary_reasoning=getattr(chat_message, "reasoning_content", ""),
        )
        self.memory.steps.append(summary_step)
        self.logger.log(
            Rule(f"[bold]Round02_02 {CANDIDATE_NAME} Progress Packet", style="orange"),
            Text(textwrap.dedent(f"""Progress packet:
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
