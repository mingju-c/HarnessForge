from __future__ import annotations

import json
import re
from typing import Any

from Agents.memory import ActionStep
from module_action.base_action import ActionContext

from .round02_02_agent import (
    DEFAULT_GUARD_POLICY,
    FAILURE_MARKERS,
    READ_ONLY_PATTERNS,
    STATEFUL_PATTERNS,
    LedgerReviewTool,
    Round0202ActionProvider,
    Round0202GuardedAgent,
    _json_key,
    _matches_any,
    _split_plan_items,
    _tokens,
    _tool_text,
)

GENERIC_RELATION_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "which",
    "who", "when", "where", "answer", "final", "task", "question", "return",
    "find", "get", "give", "tell", "show", "name", "value", "raw", "requested",
    "slot", "evidence", "source", "current", "observation", "tool",
}

ROUND03_GUARD_PREFIXES = ("round03_04_guard", "round03_04_support", "round03_04_partial")


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _plan_fields(plan: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    raw = str(plan or "").strip()
    payload = _safe_json_loads(raw) if raw.startswith("{") else None
    if isinstance(payload, dict):
        fields.update({str(k).lower().replace(" ", "_"): v for k, v in payload.items()})
        tools = payload.get("tools") or payload.get("tool_calls")
        if isinstance(tools, list) and tools:
            first = tools[0] if isinstance(tools[0], dict) else {}
            fields.setdefault("next_tool_intent", f"{first.get('name', '')} {first.get('arguments', {})}".strip())
            fields.setdefault("tool_call_plan", first.get("name", ""))
    for raw_line in raw.splitlines():
        line = raw_line.strip().strip("-")
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        if key:
            fields.setdefault(key, value.strip())
    return fields


def _field_items(fields: dict[str, Any], *names: str) -> list[str]:
    for name in names:
        if name in fields:
            items = _split_plan_items(str(fields.get(name, "")))
            if items:
                return items
            value = fields.get(name)
            if isinstance(value, (list, tuple, set)):
                return [str(item).strip() for item in value if str(item).strip()]
    return []


def _useful_tokens(text: str) -> set[str]:
    return {tok for tok in _tokens(text) if tok not in GENERIC_RELATION_STOPWORDS and len(tok) > 2}


class Round0304GuardedAgent(Round0202GuardedAgent):
    """Round03_04 repair layer over the compact single-executor winner."""

    def __init__(self, *args: Any, guard_policy: dict[str, Any] | None = None, **kwargs: Any) -> None:
        merged = {**DEFAULT_GUARD_POLICY, **(guard_policy or {})}
        merged.setdefault("partial_commit_on_blocker", False)
        merged.setdefault("completion_policy", "all_slots")
        merged.setdefault("cap_planned_mutations", False)
        merged.setdefault("support_mode", "slot_bound")
        self._repair_state: dict[str, int] = {}
        self._preflight_failures: dict[tuple[str, str], int] = {}
        super().__init__(*args, guard_policy=merged, **kwargs)

    def _validated_plan_fields(self) -> dict[str, Any]:
        return _plan_fields(self._latest_plan_text())

    def _plan_field(self, *names: str) -> str:
        fields = self._validated_plan_fields()
        for name in names:
            key = name.lower().replace(" ", "_")
            if key in fields:
                value = fields[key]
                if isinstance(value, (list, tuple, set)):
                    return "[" + ", ".join(str(item) for item in value) + "]"
                return str(value)
        return ""

    def _planned_evidence_items(self) -> list[str]:
        fields = self._validated_plan_fields()
        return _field_items(fields, "evidence_slots", "required_evidence")

    def _planned_evidence_count(self) -> int:
        return len(self._planned_evidence_items())

    def _task_stateful_items(self) -> list[str]:
        task = str(getattr(self, "task", "") or "")
        pieces = re.split(r"\s+(?:and|then)\s+|[,;]", task)
        return [piece.strip() for piece in pieces if _matches_any(STATEFUL_PATTERNS, piece.lower())][:8]

    def _planned_mutation_items(self) -> list[str]:
        fields = self._validated_plan_fields()
        route = str(fields.get("route") or fields.get("task_type") or "").lower()
        items = _field_items(fields, "required_mutations", "mutation_slots", "mutations")
        if route and "stateful" not in route and "mutation" not in route:
            return []
        filtered = [item for item in items if _matches_any(STATEFUL_PATTERNS, item.lower()) or not _matches_any(READ_ONLY_PATTERNS, item.lower())]
        if filtered:
            return filtered[:8]
        if self._task_route() == "stateful":
            return self._task_stateful_items() or ["requested state changes"]
        return []

    def _planned_mutation_count(self) -> int:
        return len(self._planned_mutation_items())

    def _task_route(self) -> str:
        fields = self._validated_plan_fields()
        route = str(fields.get("route") or fields.get("task_type") or "").lower()
        if "stateful" in route or "mutation" in route:
            return "stateful"
        if "transform" in route:
            return "transform"
        if "multi" in route or "hop" in route or "read" in route or "lookup" in route or "search" in route:
            return "read_only"
        return super()._task_route()

    def _observation_is_failure(self, observations: str) -> bool:
        lowered_obs = str(observations).lower()
        return (
            any(marker in lowered_obs for marker in FAILURE_MARKERS)
            or lowered_obs.startswith("round02_02_guard")
            or lowered_obs.startswith(ROUND03_GUARD_PREFIXES)
        )

    def _recent_evidence_records(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for idx, step in enumerate(getattr(self.memory, "steps", [])):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or observations == "No observations":
                continue
            lowered = observations.lower()
            if lowered.startswith("round01_guard") or lowered.startswith("round02") or lowered.startswith("round03_04_guard"):
                continue
            for call in getattr(step, "tool_calls", None) or []:
                name = getattr(call, "name", "")
                if self._is_evidence_tool_name(name):
                    records.append({
                        "step": str(getattr(step, "step_number", idx)),
                        "tool": name,
                        "arguments": _json_key(getattr(call, "arguments", {})),
                        "observation": observations,
                    })
        return records[-8:]

    def _successful_mutation_records(self) -> list[str]:
        records: list[str] = []
        for step in getattr(self.memory, "steps", []):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or observations == "No observations" or not self._observation_has_success(observations):
                continue
            for call in getattr(step, "tool_calls", None) or []:
                name = getattr(call, "name", "")
                if self._is_state_changing_tool_name(name):
                    records.append(f"{name} {_json_key(getattr(call, 'arguments', {}))} {observations}")
        return records

    def _mutation_slot_statuses(self) -> list[tuple[str, str]]:
        slots = self._planned_mutation_items()
        records = self._successful_mutation_records()
        if not slots:
            return []
        statuses: list[tuple[str, str]] = []
        used_records: set[int] = set()
        for slot in slots:
            slot_tokens = _useful_tokens(slot)
            matched = False
            for idx, record in enumerate(records):
                if idx in used_records:
                    continue
                record_tokens = _useful_tokens(record)
                if not slot_tokens or slot_tokens & record_tokens:
                    used_records.add(idx)
                    matched = True
                    break
            statuses.append((slot, "succeeded" if matched else "pending"))
        if (
            records
            and self.guard_policy.get("slot_match_fallback", True)
            and any(status == "pending" for _, status in statuses)
        ):
            remaining_records = len(records) - len(used_records)
            repaired: list[tuple[str, str]] = []
            for slot, status in statuses:
                if status == "pending" and remaining_records > 0:
                    repaired.append((slot, "succeeded"))
                    remaining_records -= 1
                else:
                    repaired.append((slot, status))
            statuses = repaired
        return statuses

    def _ledger_status_line(self) -> str:
        statuses = self._mutation_slot_statuses()
        pending = sum(1 for _, status in statuses if status == "pending")
        return (
            f"route={self._task_route()}; "
            f"planned_evidence={self._planned_evidence_count()}; "
            f"planned_mutations={self._planned_mutation_count()}; "
            f"mutation_pending={pending}; "
            f"evidence_records={len(self._recent_evidence_records())}; "
            f"successful_mutations={self._successful_mutation_count()}; "
            f"failed_call_signatures={len(self._failed_signatures)}; "
            f"repair_state={self._repair_state or 'none'}; "
            f"completion_tool={self._completion_tool_name() or 'none'}"
        )

    def _partial_commit_ready(self, include_step: ActionStep | None = None) -> bool:
        return bool(self.guard_policy.get("partial_commit_on_blocker", False)) and super()._partial_commit_ready(include_step)

    def _stateful_slots_ready(self) -> bool:
        statuses = self._mutation_slot_statuses()
        if statuses:
            return all(status in {"succeeded", "verified"} for _, status in statuses)
        required = int(self.guard_policy.get("min_success_before_complete", 1))
        return self._successful_mutation_count() >= required

    def _terminal_ready(self, tool_name: str) -> bool:
        if not self.guard_policy.get("complete_gate", True):
            return True
        if not self._is_terminal_name(tool_name) or tool_name == "final_answer":
            return True
        if self._task_route() == "read_only":
            return False
        policy = str(self.guard_policy.get("completion_policy", "all_slots"))
        if policy in {"all_slots", "verified_or_slots", "all_slots_with_verification"}:
            return self._stateful_slots_ready()
        if policy == "mutation_progress":
            planned = self._planned_mutation_count()
            required = int(self.guard_policy.get("min_success_before_complete", 1))
            if self.guard_policy.get("cap_planned_mutations", False):
                cap = int(self.guard_policy.get("planned_mutation_cap", 1))
                planned = min(planned, cap) if planned else planned
            return self._successful_mutation_count() >= max(required, planned or required)
        return self._stateful_slots_ready()

    def _relation_tokens_for_answer(self, answer_text: str) -> set[str]:
        fields = self._validated_plan_fields()
        slot_text = " ".join(
            self._planned_evidence_items()
            + _field_items(fields, "dependency_edges", "dependencies")
            + [str(getattr(self, "task", "") or "")]
        )
        return _useful_tokens(slot_text) - _useful_tokens(answer_text)

    def _dependency_items(self) -> list[str]:
        fields = self._validated_plan_fields()
        return _field_items(fields, "dependency_edges", "dependencies")

    def _answer_format_problem(self, answer_text: str) -> str | None:
        if not self.guard_policy.get("answer_type_checks", False):
            return None
        answer_format = self._plan_field("answer_format").lower()
        task = str(getattr(self, "task", "") or "").lower()
        if ("number" in answer_format or "numeric" in answer_format) and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", answer_text.strip()):
            return "answer_format expects a number"
        if "iso" in answer_format and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self._canonicalize_date(answer_text).strip()):
            return "answer_format expects an ISO date"
        if "list" in answer_format and any(marker in task for marker in ["all", "list", "which of"]) and not re.search(r"[,;\n]", answer_text):
            return "answer_format expects a list-like answer"
        return None

    def _answer_support_status(self, answer: Any) -> tuple[bool, str]:
        if not self._needs_evidence_for_final():
            return True, "support not required for this route"
        records = self._recent_evidence_records()
        if not records:
            return False, "no non-terminal evidence records exist"
        answer_text = str(answer or "").strip()
        if not answer_text:
            return False, "empty answer candidate"
        lowered_answer = answer_text.lower()
        if any(marker in lowered_answer for marker in ["i don't know", "cannot determine", "not enough evidence", "unable to determine"]):
            return False, "answer candidate is an unsupported refusal or explanation"
        format_problem = self._answer_format_problem(answer_text)
        if format_problem is not None:
            return False, format_problem
        evidence_blob = "\n".join(record["observation"] for record in records).lower()
        canonical = str(self._canonicalize_date(answer_text)).lower()
        direct_span = bool(lowered_answer and lowered_answer in evidence_blob) or (canonical != lowered_answer and canonical in evidence_blob)
        answer_tokens = _useful_tokens(answer_text)
        evidence_tokens = _useful_tokens(evidence_blob)
        relation_tokens = self._relation_tokens_for_answer(answer_text)
        relation_hit = False
        source_steps: list[str] = []
        for record in records:
            record_tokens = _useful_tokens(record["observation"])
            if relation_tokens & record_tokens:
                relation_hit = True
                source_steps.append(record.get("step", "?"))
        task = str(getattr(self, "task", "") or "").lower()
        numeric_transform = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", answer_text) and any(
            marker in task for marker in ["count", "how many", "number of", "calculate", "compute", "vowel", "digit", "length"]
        )
        if numeric_transform and self.guard_policy.get("deterministic_transform_support", True):
            return True, "numeric answer may be deterministically derived from current evidence"
        mode = str(self.guard_policy.get("support_mode", "slot_bound"))
        min_overlap = int(self.guard_policy.get("relation_min_overlap", 1))
        dependencies = self._dependency_items()
        if mode == "hop_provenance" and dependencies:
            min_records = int(self.guard_policy.get("hop_min_records", min(2, len(dependencies) + 1)))
            if len(records) < min_records:
                return False, f"multi-hop provenance needs at least {min_records} evidence records"
        if direct_span and relation_hit:
            return True, f"answer span appears in evidence with relation-token support at steps {source_steps[-3:]}"
        if mode == "soft" and direct_span:
            return True, "soft mode accepts direct evidence span"
        if answer_tokens and answer_tokens <= evidence_tokens and relation_hit and mode not in {"strict", "strict_slot"}:
            return True, "answer tokens are covered by evidence and relation tokens bind the requested slot"
        if direct_span and not relation_tokens:
            return True, "answer span appears in evidence and no distinct relation tokens were planned"
        if mode in {"balanced_slot", "slot_bound"} and answer_tokens & evidence_tokens and len(relation_tokens & evidence_tokens) >= min_overlap:
            return True, "answer/evidence token overlap plus relation-token coverage"
        if mode == "hop_provenance" and len(records) >= 2 and (direct_span or answer_tokens & evidence_tokens) and relation_hit:
            return True, "multi-step provenance has relation support and final candidate coverage"
        if self._task_route() == "stateful":
            return True, "stateful route uses mutation ledger rather than span support"
        return False, "candidate is not bound to the requested slot, relation, or transform in current evidence"

    def _support_record(self, answer: Any) -> str:
        ok, detail = self._answer_support_status(answer)
        records = self._recent_evidence_records()
        last = records[-1] if records else {}
        slots = self._planned_evidence_items()
        relation_tokens = sorted(self._relation_tokens_for_answer(str(answer)))[:8]
        return (
            "ROUND03_04_SUPPORT_RECORD\n"
            f"answer_candidate: {answer}\n"
            f"support_ok: {ok}\n"
            f"support_detail: {detail}\n"
            f"support_slot: {slots[0] if slots else 'requested answer'}\n"
            f"relation_tokens: {relation_tokens}\n"
            f"source_tool: {last.get('tool', 'none')}\n"
            f"source_step: {last.get('step', 'none')}\n"
            f"ledger: {self._ledger_status_line()}"
        )

    def _repair_class(self, reason: str, detail: str) -> str:
        lower = f"{reason} {detail}".lower()
        if "missing required" in lower or "extra argument" in lower or "unexpected keyword" in lower or "schema" in lower:
            return "schema"
        if "repeated" in lower or "low_value_repeat" in lower or "already failed" in lower:
            return "repeat"
        if "not found" in lower or "does not exist" in lower or "no matching" in lower:
            return "not_found"
        if "enum" in lower or "valid option" in lower:
            return "enum"
        if "unauthorized" in lower or "permission" in lower or "forbidden" in lower:
            return "authorization"
        if "terminal" in lower or "complete" in lower:
            return "terminal"
        if "empty" in lower or "unparsed" in lower:
            return "empty"
        if "support" in lower or "unsupported" in lower:
            return "unsupported_final"
        return "general"

    def _recovery_advice(self, reason: str, detail: str) -> str:
        repair_class = self._repair_class(reason, detail)
        self._repair_state[repair_class] = self._repair_state.get(repair_class, 0) + 1
        routes = {
            "schema": "repair schema exactly: drop unsupported keys, fill required keys from observations, then retry once with changed arguments.",
            "repeat": "do not retry the same signature; change identifier source, relation path, query terms, or tool family.",
            "not_found": "broaden to search/list/get for the entity or id before retrying the specific operation.",
            "enum": "inspect valid options or copy the enum value exactly from the latest observation.",
            "authorization": "verify actor/account context or choose a permitted mutation path before another state change.",
            "terminal": "delay completion until every planned mutation slot is succeeded or verified.",
            "empty": "emit exactly one executable JSON tool call from the current schema.",
            "unsupported_final": "collect targeted evidence for the requested slot or derive the value deterministically before final_answer.",
            "general": "make one schema-valid call that fills a missing evidence, mutation, or verification slot.",
        }
        advice = routes[repair_class]
        self._last_recovery_hint = advice
        return f"repair_class={repair_class}; {advice}"

    def _guard_observation(self, reason: str, detail: str) -> str:
        advice = self._recovery_advice(reason, detail)
        return (
            f"ROUND03_04_GUARD_BLOCK: {reason}\n"
            f"{detail}\n"
            f"Ledger: {self._ledger_status_line()}\n"
            f"Recovery route: {advice}\n"
            "Next step: make one schema-valid call that changes the identifier source, relation path, "
            "tool family, or missing slot; commit only when support or all-slot completion is satisfied."
        )


    def execute_tool_call(self, tool_name: str, arguments: Any) -> Any:
        ok, repaired_arguments, message = self._preflight_arguments(tool_name, arguments)
        if not ok:
            signature = (tool_name, _json_key(repaired_arguments))
            self._failed_signatures.add(signature)
            self._preflight_failures[signature] = self._preflight_failures.get(signature, 0) + 1
            if self._preflight_failures[signature] > 1:
                message = (
                    f"{message} This schema/tool strategy has failed "
                    f"{self._preflight_failures[signature]} times; switch tool, identifier source, or argument shape."
                )
            return self._guard_observation("schema_preflight", message)
        return super().execute_tool_call(tool_name, repaired_arguments)


class Round0304ActionProvider(Round0202ActionProvider):
    PROMPTS_TYPE = "round03_04_guarded_react"
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG: dict[str, Any] = {}

    def build_organization(self, context: ActionContext, tools: list[Any]) -> Round0304GuardedAgent:
        root_tools = self.normalize_tools(list(tools))
        agent = Round0304GuardedAgent(
            model=context.model,
            tools=root_tools,
            summary_interval=context.summary_interval if context.summary_interval is not None else self.SUMMARY_INTERVAL,
            max_steps=context.max_steps,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
            planning_class=context.kwargs.get("planning_class"),
            max_tool_calls_per_step=context.kwargs.get("max_tool_calls_per_step"),
            prompt_templates=self.prompt_templates,
            memory_provider=context.memory_provider,
            project_root=context.project_root,
            guard_policy=self.guard_policy,
        )
        for tool in root_tools:
            if isinstance(tool, LedgerReviewTool):
                tool.bind_agent(agent)
        setattr(agent, "harness_policy", {
            **self.guard_policy,
            "mode": self.prompts_type,
            "single_executor": True,
            "hard_schema_preflight": True,
            "ledger_review_tool": self.VARIANT_CONFIG.get("enable_ledger_review_tool", False),
            "support_record_gate": self.guard_policy.get("support_record_gate", True),
            "partial_commit_disabled": not self.guard_policy.get("partial_commit_on_blocker", False),
            "round": "round_03_04",
        })
        return agent


__all__ = ["Round0304GuardedAgent", "Round0304ActionProvider"]
