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


PLANNING_SYSTEM = "hop_provenance_planning"
PLANNING_MODULE = PLANNING_SYSTEM
CANDIDATE_NAME = "harness_round03_04_4"
PLAN_FOCUS = "ordered multi-hop dependencies from source entity through relation, intermediate value, transform, and final answer"

STATEFUL_TERMS = {
    "activate", "add", "append", "approve", "assign", "book", "buy", "cancel",
    "change", "close", "complete", "correct", "create", "deactivate", "delete",
    "edit", "enroll", "link", "log", "mark", "move", "order", "patch", "pay",
    "post", "put", "reactivate", "register", "reject", "remove", "renew",
    "reschedule", "reserve", "restore", "schedule", "set", "submit", "transfer",
    "unlink", "update", "write",
}
READ_ONLY_TERMS = {
    "calculate", "check", "count", "crawl", "describe", "fetch", "find", "get",
    "info", "list", "lookup", "query", "read", "retrieve", "search", "validate",
    "verify",
}
TRANSFORM_TERMS = {
    "calculate", "compute", "convert", "count", "date", "difference", "length",
    "number", "sort", "sum", "transform",
}


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    compiled = Template(template, undefined=StrictUndefined)
    try:
        return compiled.render(**variables)
    except Exception:
        return Template(template).render(**variables)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", str(text).lower()))


def _split_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        text = str(value).strip()
        if not text or text.lower() in {"[]", "none", "null", "n/a"}:
            return []
        text = text.strip("[]")
        raw_items = re.split(r"\s*(?:,|;|\|)\s*", text)
    items: list[str] = []
    for item in raw_items:
        text = str(item).strip().strip("'\"")
        if text and text.lower() not in {"none", "null", "n/a"}:
            items.append(text)
    return items


def _format_items(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]" if items else "[]"


def _tool_text(tool: Any) -> str:
    return f"{getattr(tool, 'name', '')} {getattr(tool, 'description', '')}".lower().replace("_", " ")


def _looks_stateful(text: str) -> bool:
    return bool(_tokens(text) & STATEFUL_TERMS)


def _looks_read_only(text: str) -> bool:
    return bool(_tokens(text) & READ_ONLY_TERMS)


def _looks_transform(text: str) -> bool:
    return bool(_tokens(text) & TRANSFORM_TERMS)


def _parse_plan_fields(plan_text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    raw = str(plan_text or "").strip()
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                fields.update(payload)
                tools = payload.get("tools") or payload.get("tool_calls")
                if isinstance(tools, list) and tools:
                    first = tools[0] if isinstance(tools[0], dict) else {}
                    name = str(first.get("name", "") or "")
                    args = first.get("arguments", {})
                    fields.setdefault("next_tool_intent", f"{name} {args}".strip())
                    fields.setdefault("tool_call_plan", name)
        except Exception:
            pass
    for raw_line in raw.splitlines():
        line = raw_line.strip().strip("-")
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        if key:
            fields.setdefault(key, value.strip())
    return fields


def _infer_route(task: str, tools: Dict[str, Tool], fields: dict[str, Any]) -> str:
    route_text = str(fields.get("route") or fields.get("task_type") or "").lower()
    if "stateful" in route_text or "mutation" in route_text:
        return "stateful_mutation"
    if "multi" in route_text or "hop" in route_text:
        return "multi_hop_lookup"
    if "transform" in route_text:
        return "deterministic_transform"
    if "read" in route_text or "lookup" in route_text or "search" in route_text:
        return "read_only_lookup"
    tool_text = " ".join(_tool_text(tool) for tool in tools.values())
    task_text = str(task).lower()
    if _looks_stateful(task_text) or _looks_stateful(tool_text):
        return "stateful_mutation"
    if _looks_transform(task_text):
        return "deterministic_transform"
    if _looks_read_only(task_text) or _looks_read_only(tool_text):
        return "read_only_lookup"
    return "unknown"


def _infer_mutation_slots(task: str, fields: dict[str, Any], route: str) -> list[str]:
    candidates = (
        _split_items(fields.get("required_mutations"))
        or _split_items(fields.get("mutation_slots"))
        or _split_items(fields.get("mutations"))
    )
    if route != "stateful_mutation":
        return []
    stateful = [item for item in candidates if _looks_stateful(item) or not _looks_read_only(item)]
    if stateful:
        return stateful[:8]
    task_text = str(task).strip()
    pieces = re.split(r"\s+(?:and|then)\s+|[,;]", task_text)
    inferred = [piece.strip() for piece in pieces if _looks_stateful(piece)]
    if inferred:
        return inferred[:8]
    intent = str(fields.get("next_tool_intent") or fields.get("tool_call_plan") or "").strip()
    return [intent or "requested state change"]


def _normalize_plan_packet(task: str, plan_text: str, tools: Dict[str, Tool]) -> str:
    fields = _parse_plan_fields(plan_text)
    route = _infer_route(task, tools, fields)
    evidence = (
        _split_items(fields.get("evidence_slots"))
        or _split_items(fields.get("required_evidence"))
    )
    dependencies = (
        _split_items(fields.get("dependency_edges"))
        or _split_items(fields.get("dependencies"))
    )
    mutations = _infer_mutation_slots(task, fields, route)
    verification = (
        _split_items(fields.get("verification_targets"))
        or _split_items(fields.get("verification"))
    )
    if route != "stateful_mutation" and not evidence:
        evidence = ["requested answer slot"]
    if route == "stateful_mutation" and not verification:
        verification = ["all mutation slots have success or verification observations"]
    answer_format = str(fields.get("answer_format") or "").strip()
    if not answer_format:
        answer_format = "state completion" if route == "stateful_mutation" else "raw requested answer"
    terminal_policy = str(fields.get("terminal_policy") or "").strip()
    if not terminal_policy:
        terminal_policy = (
            "complete_task only after every mutation slot is succeeded or verified"
            if route == "stateful_mutation"
            else "final_answer only after slot-bound current evidence or deterministic derivation"
        )
    next_tool_intent = str(fields.get("next_tool_intent") or fields.get("tool_call_plan") or "").strip()
    if not next_tool_intent:
        next_tool_intent = "choose one schema-valid tool that fills the next missing slot"
    return textwrap.dedent(f"""\
validated_ledger: true
task_type: {route}
route: {route}
evidence_slots: {_format_items(evidence)}
dependency_edges: {_format_items(dependencies)}
required_mutations: {_format_items(mutations)}
verification_targets: {_format_items(verification)}
answer_format: {answer_format}
terminal_policy: {terminal_policy}
next_tool_intent: {next_tool_intent}
""").strip()


class PlanningProvider(BasePlanning):
    """Planner that normalizes raw model plans into an action-readable route ledger."""

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
        raw_plan = str(chat_message.content or "").strip()
        plan_text = _normalize_plan_packet(task, raw_plan, self.tools)

        self.logger.log(
            Rule(f"[bold]Round03_04 {CANDIDATE_NAME} Plan Packet", style="orange"),
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
            Rule(f"[bold]Round03_04 {CANDIDATE_NAME} Progress Packet", style="orange"),
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
