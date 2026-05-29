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


PLANNING_SYSTEM = "round03_03_raw_commit_planning"
PLANNING_MODULE = PLANNING_SYSTEM
PLAN_CONTRACT = "RAW_ANSWER_COMMITTER"
PLAN_FIELDS = (
    "contract", "task_type", "target", "answer_type", "obligations",
    "bindings", "evidence_slots", "observed_success", "observed_failure",
    "blockers", "remaining", "final_criteria", "next_step",
)
SUMMARY_FIELDS = (
    "observed_success", "observed_failure", "bindings_or_ledger",
    "open_rows_or_slots", "terminal_blockers", "remaining",
    "retry_or_repair_guidance", "next_step", "final_readiness",
)
EXECUTABLE_MARKERS = ('"tools"', "'tools'", '"arguments"', '"name"', "```json", '{"think"', '{"tool"')


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    compiled = Template(template, undefined=StrictUndefined)
    try:
        return compiled.render(**variables)
    except Exception:
        return Template(template).render(**variables)


def _looks_executable(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in EXECUTABLE_MARKERS)


def _missing_fields(text: str, fields: tuple[str, ...]) -> list[str]:
    lowered = (text or "").lower()
    missing = []
    for field in fields:
        if f"{field}:" not in lowered and f"{field} -" not in lowered:
            missing.append(field)
    return missing


def _trim_fragment(text: str, limit: int = 1200) -> str:
    fragment = (text or "").strip().replace("```", "~~~")
    if len(fragment) > limit:
        fragment = fragment[:limit] + "..."
    return fragment or "none"


def _repair_plan_text(plan_text: str) -> str:
    missing = _missing_fields(plan_text, PLAN_FIELDS)
    if not _looks_executable(plan_text) and len(missing) <= 3:
        return plan_text.strip()
    fragment = _trim_fragment(plan_text)
    return textwrap.dedent(f"""
    contract: {PLAN_CONTRACT}
    task_type: infer from task and available schemas; mark stateful when mutation or completion is required
    target: requested answer or environment completion
    answer_type: entity, date, number, boolean, ID, raw string, list, calculated, or stateful
    obligations:
    - convert each requested mutation, lookup, hop, or transformation into a pending row
    bindings:
    - keep entity IDs, names, dates, and intermediate variables unresolved until observed
    evidence_slots:
    - bind decisive observations to target relations or raw fields before finalization
    observed_success: none yet unless supplied by user
    observed_failure: none yet unless supplied by user
    blockers: none known yet
    remaining: close pending rows with tool observations, not planned actions
    final_criteria: answer_type, decisive observation, raw field, allowed transformation, and exact output string are all explicit
    next_step: use current schemas for the first unresolved row; do not treat the raw model fragment as observed
    repair_note: planner output was repaired because it missed status fields or looked like an executable tool call
    raw_model_fragment: {fragment}
    """).strip()


def _repair_summary_text(summary_text: str) -> str:
    missing = _missing_fields(summary_text, SUMMARY_FIELDS)
    if len(missing) <= 3:
        return summary_text.strip()
    fragment = _trim_fragment(summary_text)
    return textwrap.dedent(f"""
    observed_success: retain only successes directly supported by tool observations or explicit task facts
    observed_failure: list failed calls, schema advisories, empty results, and unresolved contradictions
    bindings_or_ledger: update IDs, names, state rows, and evidence slots from observations only
    open_rows_or_slots: keep any required mutation, relation slot, or raw field open until observed
    terminal_blockers: unresolved failures, open required rows, missing evidence, or ambiguous raw final form
    remaining: repair blockers or close the next open row
    retry_or_repair_guidance: change tool, arguments, binding, or precondition after failure; do not repeat identical failed calls blindly
    next_step: one schema-listed action that advances an open row
    final_readiness: ready only when answer_type, decisive observation, raw field, allowed transformation, and exact output string are all explicit
    repair_note: summary output was normalized into the harness status contract
    raw_summary_fragment: {fragment}
    """).strip()


class PlanningProvider(BasePlanning):
    """Validated planner for the RAW_ANSWER_COMMITTER contract."""

    def __init__(self, model: Callable[[List[Dict[str, str]]], ChatMessage], tools: Dict[str, Tool], prompt_templates: Dict[str, Any], memory: AgentMemory, logger: AgentLogger):
        super().__init__(model, tools, prompt_templates, memory, logger)

    def topology_initialize(self, task: str) -> PlanningStep:
        system_msg = {"role": MessageRole.SYSTEM, "content": [{"type": "text", "text": _render_template(self.prompt_templates["planning"]["initial_plan"], {"tools": self.tools, "task": task, "planning_system": PLANNING_SYSTEM})}]}
        task_msg = {"role": MessageRole.USER, "content": [{"type": "text", "text": _render_template(self.prompt_templates["planning"]["task_input"], {"task": task})}]}
        input_messages = [system_msg]
        memory_guidance = self.append_memory_guidance(input_messages)
        chat_message: ChatMessage = self.model(input_messages + [task_msg])
        plan_text = _repair_plan_text(str(chat_message.content or "").strip())
        planning_step = PlanningStep(model_input_messages=input_messages, plan=plan_text, plan_think="", plan_reasoning=chat_message.reasoning_content, memory_guidance=memory_guidance)
        self.memory.steps.append(planning_step)
        self.logger.log(Rule("[bold]RAW_ANSWER_COMMITTER Plan", style="orange"), Text(textwrap.dedent(f"""Plan/status contract:\n```\n{plan_text}\n```""")), level=LogLevel.INFO)
        return planning_step

    def adaptation(self, task: str, step: int, write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]]) -> SummaryStep:
        memory_messages = write_memory_to_messages(None, False)[1:]
        pre_msg = {"role": MessageRole.SYSTEM, "content": [{"type": "text", "text": _render_template(self.prompt_templates["summary"]["update_pre_messages"], {"task": task, "step": step})}]}
        post_msg = {"role": MessageRole.USER, "content": [{"type": "text", "text": _render_template(self.prompt_templates["summary"]["update_post_messages"], {"task": task, "step": step})}]}
        input_messages = [pre_msg] + memory_messages + [post_msg]
        chat_message: ChatMessage = self.model(input_messages)
        summary_text = _repair_summary_text(str(chat_message.content or "").strip())
        summary_step = SummaryStep(model_input_messages=input_messages, summary=summary_text, summary_reasoning=chat_message.reasoning_content)
        self.memory.steps.append(summary_step)
        self.logger.log(Rule("[bold]RAW_ANSWER_COMMITTER Summary", style="orange"), Text(textwrap.dedent(f"""Current status:\n```\n{summary_text}\n```""")), level=LogLevel.INFO)
        return summary_step


PlanningClass = PlanningProvider

__all__ = ["PLANNING_SYSTEM", "PLANNING_MODULE", "PlanningProvider", "PlanningClass"]
