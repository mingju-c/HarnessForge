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


PLANNING_SYSTEM = "round03_answer_slot_planning"
PLANNING_MODULE = "round03_answer_slot_planning"
CANDIDATE_NAME = "harness_round03_01_2"
PLAN_FOCUS = "target answer slot, relation phrase, source evidence, and ambiguity check"
PLAN_TOPOLOGY = "answer-slot evidence contract"

REQUIRED_FIELDS = [
    "task_type",
    "route",
    "evidence_slots",
    "dependency_edges",
    "required_mutations",
    "answer_format",
    "terminal_policy",
    "verification_questions",
    "next_tool_intent",
]
STATEFUL_WORDS = re.compile(
    r"\b(update|create|delete|remove|add|edit|change|set|assign|transfer|schedule|cancel|approve|submit|post|enroll|move|link|unlink)\b",
    re.IGNORECASE,
)
TRANSFORM_WORDS = re.compile(r"\b(count|calculate|compute|convert|extract|first name|digit|letter|reverse|sort)\b", re.IGNORECASE)
LOOKUP_WORDS = re.compile(r"\b(find|search|lookup|get|retrieve|what|which|who|when|where)\b", re.IGNORECASE)


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    compiled = Template(template, undefined=StrictUndefined)
    try:
        return compiled.render(**variables)
    except Exception:
        return Template(template).render(**variables)


def _looks_like_action_packet(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.search(r"(?im)^\s*tools\s*:", stripped) and not re.search(r"(?im)^\s*evidence_slots\s*:", stripped):
        return True
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
            return isinstance(payload, dict) and "tools" in payload
        except Exception:
            return '"tools"' in stripped and '"think"' in stripped
    return False


def _infer_route(task: str, tools: Dict[str, Tool]) -> tuple[str, str]:
    lowered_tools = " ".join(f"{name} {getattr(tool, 'description', '')}" for name, tool in tools.items()).lower()
    lowered_task = task.lower()
    has_completion = any(name in tools for name in ("complete_task", "task_completed", "finish_task", "end_process"))
    if has_completion or STATEFUL_WORDS.search(lowered_task) or STATEFUL_WORDS.search(lowered_tools):
        return "stateful_mutation", "stateful"
    if TRANSFORM_WORDS.search(lowered_task):
        return "deterministic_transform", "transform"
    if LOOKUP_WORDS.search(lowered_task):
        return "read_only_lookup", "read_only"
    return "unknown", "unknown"


def _mutation_candidates(task: str) -> list[str]:
    clauses = re.split(r"(?:\n|;|\bthen\b|\balso\b|\band\b)", task, flags=re.IGNORECASE)
    items: list[str] = []
    for clause in clauses:
        clean = " ".join(clause.strip().split())
        if not clean or len(clean) < 5:
            continue
        if STATEFUL_WORDS.search(clean):
            items.append(clean[:150])
    deduped: list[str] = []
    for item in items:
        key = item.lower()
        if key not in [old.lower() for old in deduped]:
            deduped.append(item)
    return deduped[:12]


def _fallback_contract(task: str, tools: Dict[str, Tool], reason: str) -> str:
    task_type, route = _infer_route(task, tools)
    mutations = _mutation_candidates(task) if route == "stateful" else []
    evidence = ["primary observed fact for requested answer"]
    if route == "transform":
        evidence = ["source entity", "relation result", "field to transform", "final derived value"]
    elif route == "stateful":
        evidence = ["identifier or current state needed for each mutation"]
    mutation_text = "; ".join(mutations) if mutations else "[]"
    dependency_text = "source evidence -> derived value" if route == "transform" else "[]"
    return textwrap.dedent(f"""
    task_type: {task_type}
    route: {route}
    evidence_slots: {'; '.join(evidence)}
    dependency_edges: {dependency_text}
    required_mutations: {mutation_text}
    answer_format: raw requested answer or completion signal required by task
    terminal_policy: final_answer only with current relation-bound support; completion only after required mutation coverage
    verification_questions: Is the candidate bound to the requested slot? Are all required mutations observed or explicitly blocked?
    next_tool_intent: choose one valid non-terminal tool that fills the next missing slot
    validation_status: normalized fallback because {reason}
    """).strip()


def _ensure_plan_contract(plan_text: str, task: str, tools: Dict[str, Tool]) -> str:
    raw = str(plan_text or "").strip()
    if not raw:
        return _fallback_contract(task, tools, "the model returned an empty plan")
    if _looks_like_action_packet(raw):
        return _fallback_contract(task, tools, "the model emitted an action packet instead of a plan")
    lowered = raw.lower()
    missing = [field for field in REQUIRED_FIELDS if not re.search(rf"(?im)^\s*{re.escape(field)}\s*:", raw)]
    if not missing:
        if re.search(r"(?im)^\s*next_tool_intent\s*:\s*final_answer\b", raw) and "status: missing" in lowered:
            raw += "\nvalidation_note: next_tool_intent final_answer is premature until missing slots are satisfied."
        return raw
    fallback = _fallback_contract(task, tools, "missing fields " + ", ".join(missing))
    existing_lines = [line for line in raw.splitlines() if line.strip()]
    fallback_lines = []
    for line in fallback.splitlines():
        key = line.split(":", 1)[0].strip().lower()
        if key in missing or key == "validation_status":
            fallback_lines.append(line)
    return "\n".join(existing_lines + fallback_lines)


class PlanningProvider(BasePlanning):
    """Validated compact planner that materializes an action-visible contract."""

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
                    {"tools": self.tools, "task": task, "plan_focus": PLAN_FOCUS, "plan_topology": PLAN_TOPOLOGY},
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
                    {"task": task, "plan_focus": PLAN_FOCUS, "plan_topology": PLAN_TOPOLOGY},
                ),
            }],
        }
        chat_message: ChatMessage = self.model(input_messages + [task_msg])
        raw_plan = str(chat_message.content or "").strip()
        plan_text = _ensure_plan_contract(raw_plan, task, self.tools)

        self.logger.log(
            Rule(f"[bold]Round03 {CANDIDATE_NAME} Plan Contract", style="orange"),
            Text(textwrap.dedent(f"""Execution contract:
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
                    {"task": task, "step": step, "plan_focus": PLAN_FOCUS, "plan_topology": PLAN_TOPOLOGY},
                ),
            }],
        }
        post_msg = {
            "role": MessageRole.USER,
            "content": [{
                "type": "text",
                "text": _render_template(
                    self.prompt_templates["summary"]["update_post_messages"],
                    {"task": task, "step": step, "plan_focus": PLAN_FOCUS, "plan_topology": PLAN_TOPOLOGY},
                ),
            }],
        }
        chat_message: ChatMessage = self.model([pre_msg] + memory_messages + [post_msg])
        summary_text = str(chat_message.content or "").strip()
        if _looks_like_action_packet(summary_text) or not summary_text:
            summary_text = textwrap.dedent("""
            completed_evidence_slots: current observations only
            blocked_or_missing_slots: inspect latest guard or missing dependency
            derived_facts: keep source observation attached
            failed_or_repeated_calls: change identifier source or tool family
            mutation_progress: compare successful mutations against required_mutations
            terminal_readiness: final needs relation-bound support; completion needs mutation coverage
            recovery_route: one schema-valid repair call
            next_safe_move: advance the next missing slot
            """).strip()
        summary_step = SummaryStep(
            model_input_messages=[pre_msg] + memory_messages + [post_msg],
            summary=summary_text,
            summary_reasoning=getattr(chat_message, "reasoning_content", ""),
        )
        self.memory.steps.append(summary_step)
        self.logger.log(
            Rule(f"[bold]Round03 {CANDIDATE_NAME} Progress Contract", style="orange"),
            Text(textwrap.dedent(f"""Progress contract:
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
