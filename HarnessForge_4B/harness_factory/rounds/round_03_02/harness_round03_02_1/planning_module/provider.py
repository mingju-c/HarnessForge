from __future__ import annotations

import json
import re
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


PLANNING_SYSTEM = "closure_ledger_planning"
PLANNING_MODULE = "closure_ledger_planning"
CANDIDATE_NAME = "harness_round03_02_1"
PLAN_FOCUS = "route packet with evidence slots, bounded mutation rows, and terminal closure criteria"
PLAN_RULES = """- Normalize any first-action JSON into a packet before action uses it.
- For stateful tasks, list operation-level required_mutations and verification_targets.
- For multi-hop tasks, keep source, relation result, transform input, and final value as linked slots.
- Keep simple SearchQA as one evidence slot with raw answer format."""
FALLBACK_PACKET = """task_type: unknown\nroute: unknown\nevidence_slots: []\ndependency_edges: []\nrequired_mutations: []\nverification_targets: []\nanswer_format: raw requested answer\nterminal_policy: final_answer needs current support; complete_task needs verified mutation closure\nnext_tool_intent: choose one valid schema-matching tool"""


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    compiled = Template(template, undefined=StrictUndefined)
    try:
        return compiled.render(**variables)
    except Exception:
        return Template(template).render(**variables)


def _infer_route(task: str) -> str:
    lowered = task.lower()
    state_words = ["update", "create", "delete", "add", "remove", "set", "schedule", "cancel", "assign", "transfer", "submit"]
    transform_words = ["reverse", "count", "calculate", "convert", "binary", "last letter", "first name", "last name"]
    if any(word in lowered for word in state_words):
        return "stateful_mutation"
    if any(word in lowered for word in transform_words):
        return "deterministic_transform"
    if any(word in lowered for word in ["searchqa", "search", "find", "lookup", "who", "what", "when", "where"]):
        return "read_only_lookup"
    return "unknown"


def _looks_like_tool_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return False
    try:
        parsed = json.loads(stripped)
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    return "tools" in parsed or "name" in parsed or "arguments" in parsed or "think" in parsed


def _ensure_packet_fields(plan_text: str, task: str) -> str:
    text = str(plan_text or "").strip()
    if not text:
        text = FALLBACK_PACKET
    if _looks_like_tool_json(text):
        route = _infer_route(task)
        text = textwrap.dedent(f"""task_type: normalized_from_first_action_json
route: {route}
evidence_slots: [current task support]
dependency_edges: []
required_mutations: [requested operation rows if this is stateful]
verification_targets: [current observation proving each mutation or answer slot]
answer_format: raw requested answer or state completion
terminal_policy: do not treat the first action as the plan; final_answer needs current support; complete_task needs mutation closure
next_tool_intent: repair or execute one schema-valid action that fills the first missing slot
""").strip()
    required = {
        "task_type": "unknown",
        "route": _infer_route(task),
        "evidence_slots": "[]",
        "dependency_edges": "[]",
        "required_mutations": "[]",
        "verification_targets": "[]",
        "answer_format": "raw requested answer",
        "terminal_policy": "final_answer needs current support; complete_task needs verified mutation closure",
        "next_tool_intent": "choose one valid schema-matching tool",
    }
    present = set()
    for line in text.splitlines():
        if ":" in line:
            present.add(line.split(":", 1)[0].strip().lower())
    additions = [f"{key}: {value}" for key, value in required.items() if key not in present]
    if additions:
        text = text.rstrip() + "\n" + "\n".join(additions)
    return text.strip()


class PlanningProvider(BasePlanning):
    """Round03 compact planner with packet normalization and action-visible ledger fields."""

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
                    {"tools": self.tools, "task": task, "plan_focus": PLAN_FOCUS, "plan_rules": PLAN_RULES},
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
                    {"task": task, "plan_focus": PLAN_FOCUS, "plan_rules": PLAN_RULES},
                ),
            }],
        }
        chat_message: ChatMessage = self.model(input_messages + [task_msg])
        plan_text = _ensure_packet_fields(str(chat_message.content or ""), task)
        self.logger.log(
            Rule(f"[bold]Round03_02 {CANDIDATE_NAME} Plan Packet", style="orange"),
            Text(textwrap.dedent(f"Execution packet:\n```\n{plan_text}\n```")),
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
                    {"task": task, "step": step, "plan_focus": PLAN_FOCUS, "plan_rules": PLAN_RULES},
                ),
            }],
        }
        post_msg = {
            "role": MessageRole.USER,
            "content": [{
                "type": "text",
                "text": _render_template(
                    self.prompt_templates["summary"]["update_post_messages"],
                    {"task": task, "step": step, "plan_focus": PLAN_FOCUS, "plan_rules": PLAN_RULES},
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
            Rule(f"[bold]Round03_02 {CANDIDATE_NAME} Progress Packet", style="orange"),
            Text(textwrap.dedent(f"Progress packet:\n```\n{summary_text}\n```")),
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
