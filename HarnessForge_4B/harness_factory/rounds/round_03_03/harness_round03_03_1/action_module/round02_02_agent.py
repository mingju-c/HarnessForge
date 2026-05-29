from __future__ import annotations

import json
import re
from difflib import get_close_matches
from typing import Any

from Agents.agents import ToolCallingAgent
from Agents.memory import ActionStep, PlanningStep, ToolCall
from Agents.tools import Tool
from module_action.base_action import ActionContext, BaseActionProvider


STATEFUL_PATTERNS = [
    r"\bactivate\b", r"\badd\b", r"\bappend\b", r"\bapprove\b",
    r"\bassign\b", r"\bbook\b", r"\bbuy\b", r"\bcancel\b",
    r"\bchange\b", r"\bclose\b", r"\bcomplete\b", r"\bcorrect\b",
    r"\bcreate\b", r"\bdeactivate\b", r"\bdelete\b", r"\bedit\b",
    r"\benroll\b", r"\bjoin\b", r"\blink\b", r"\blog\b",
    r"\bmark\b", r"\bmove\b", r"\bmutate\b", r"\border\b",
    r"\bpatch\b", r"\bpay\b", r"\bpost\b", r"\bput\b",
    r"\breactivate\b", r"\bregister\b", r"\breject\b", r"\bremove\b",
    r"\brenew\b", r"\breschedule\b", r"\breserve\b", r"\brestore\b",
    r"\bschedule\b", r"\bset\b", r"\bsubmit\b", r"\btransfer\b",
    r"\bunlink\b", r"\bupdate\b", r"\bwrite\b",
]
READ_ONLY_PATTERNS = [
    r"\bcalculate\b", r"\bcheck\b", r"\bcount\b", r"\bcrawl\b",
    r"\bdescribe\b", r"\bfetch\b", r"\bfind\b", r"\bget\b", r"\binfo\b",
    r"\blist\b", r"\blookup\b", r"\bquery\b", r"\bread\b",
    r"\bretrieve\b", r"\bsearch\b", r"\bvalidate\b", r"\bverify\b",
]
FAILURE_MARKERS = [
    "error", "unknown tool", "unexpected keyword", "missing required",
    "invalid", "failed", "not found", "does not exist", "guard blocked",
    "exception", "traceback", "unauthorized", "permission denied", "forbidden",
]
SELF_CONTAINED_MARKERS = [
    "given", "provided", "in the question", "calculate", "compute",
    "convert", "count", "sort", "uppercase", "lowercase", "reverse",
    "substring", "string", "digits", "arithmetic",
]
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "with",
    "what", "which", "who", "when", "where", "is", "are", "was", "were",
    "answer", "final", "tool", "call", "task", "question", "return",
}
MONTHS = {
    "january": "01", "jan": "01", "february": "02", "feb": "02",
    "march": "03", "mar": "03", "april": "04", "apr": "04",
    "may": "05", "june": "06", "jun": "06", "july": "07", "jul": "07",
    "august": "08", "aug": "08", "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10", "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}


DEFAULT_GUARD_POLICY: dict[str, Any] = {
    "focus": "round02_02 evidence ledger and recovery routing",
    "evidence_gate": True,
    "support_record_gate": True,
    "support_mode": "route",
    "complete_gate": True,
    "completion_policy": "ledger_or_progress",
    "drop_extra_keys": True,
    "repeat_limit": 2,
    "min_success_before_complete": 1,
    "partial_commit_on_blocker": True,
    "min_successful_mutations_before_partial_complete": 1,
    "planned_mutation_cap": 1,
    "enable_ledger_review_tool": False,
    "date_iso_canonicalization": True,
    "narrow_alias_trim": False,
    "record_support": True,
}


def _json_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    except Exception:
        return str(value)


def _tool_text(tool: Any) -> str:
    return f"{getattr(tool, 'name', '')} {getattr(tool, 'description', '')}".lower().replace("_", " ")


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-zA-Z0-9]+", str(text).lower())
        if len(token) > 1 and token not in STOPWORDS
    }


def _split_plan_items(value: str) -> list[str]:
    value = value.strip()
    if not value or value in {"[]", "none", "null", "n/a"}:
        return []
    value = value.strip("[]")
    parts = re.split(r"\s*(?:,|;|\|)\s*", value)
    return [part.strip().strip("'\"") for part in parts if part.strip().strip("'\"")]


class LedgerReviewTool(Tool):
    name = "ledger_review"
    description = (
        "Read-only checkpoint that summarizes evidence support, failed calls, "
        "stateful progress, and terminal readiness. It never mutates state."
    )
    inputs = {
        "question": {
            "type": "string",
            "description": "Proposed next action, blocker, or finalization decision to audit.",
        }
    }
    output_type = "string"

    def __init__(self) -> None:
        self.agent = None
        super().__init__()

    def bind_agent(self, agent: Any) -> None:
        self.agent = agent

    def forward(self, question: str) -> str:
        if self.agent is None:
            return "ledger_review unavailable; use exact schemas and current observations only."
        return (
            "ledger_review: read-only audit\n"
            f"question: {question}\n"
            f"route: {self.agent._task_route()}\n"
            f"status: {self.agent._ledger_status_line()}\n"
            f"last_recovery_hint: {self.agent._last_recovery_hint or 'none'}\n"
            "next_safe_move: use one schema-valid tool that fills a missing slot, repairs an identifier, "
            "or commits only when the active terminal policy is satisfied."
        )


class Round0202GuardedAgent(ToolCallingAgent):
    """Single task-tool executor with lightweight ledger, support, and recovery checks."""

    def __init__(self, *args: Any, guard_policy: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self.guard_policy = {**DEFAULT_GUARD_POLICY, **(guard_policy or {})}
        self._call_counts: dict[tuple[str, str], int] = {}
        self._failed_signatures: set[tuple[str, str]] = set()
        self._successful_signatures: set[tuple[str, str]] = set()
        self._evidence_seen_runtime = False
        self._state_epoch = 0
        self._last_recovery_hint = ""
        super().__init__(*args, **kwargs)

    def _is_checkpoint_tool(self, name: str) -> bool:
        return name in {"repair_checkpoint", "critic_reflect", "schema_audit", "ledger_review"}

    def _is_terminal_name(self, name: str) -> bool:
        if name == "final_answer":
            return True
        tool = self.tools.get(name)
        if tool is not None and getattr(tool, "terminal_tool", False):
            return True
        return name.lower() in {"complete_task", "task_completed", "end_process", "finish_task"}

    def _is_evidence_tool_name(self, name: str) -> bool:
        if self._is_terminal_name(name) or self._is_checkpoint_tool(name) or name == "reasoning":
            return False
        return name in self.tools

    def _is_state_changing_tool_name(self, name: str) -> bool:
        if self._is_terminal_name(name) or self._is_checkpoint_tool(name) or name == "reasoning":
            return False
        tool = self.tools.get(name)
        if tool is None:
            return False
        readable_name = name.lower().replace("_", " ")
        if re.match(r"^(get|list|search|find|check|is|validate|lookup|has|locate|read|verify)\b", readable_name):
            return False
        return _matches_any(STATEFUL_PATTERNS, f"{readable_name} {_tool_text(tool)}")

    def _completion_tool_name(self) -> str | None:
        for name in ("complete_task", "task_completed", "finish_task", "end_process"):
            if name in self.tools:
                return name
        for name, tool in self.tools.items():
            if name != "final_answer" and getattr(tool, "terminal_tool", False):
                return name
        return None

    def _latest_plan_text(self) -> str:
        for step in reversed(getattr(self.memory, "steps", [])):
            if isinstance(step, PlanningStep):
                return str(getattr(step, "plan", "") or "")
        return ""

    def _plan_field(self, *names: str) -> str:
        plan = self._latest_plan_text()
        for raw_line in plan.splitlines():
            line = raw_line.strip()
            lowered = line.lower()
            for name in names:
                prefix = name.lower() + ":"
                if lowered.startswith(prefix):
                    return line.split(":", 1)[1].strip()
        return ""

    def _planned_evidence_count(self) -> int:
        return len(_split_plan_items(self._plan_field("evidence_slots", "required_evidence")))

    def _planned_mutation_count(self) -> int:
        items = _split_plan_items(self._plan_field("required_mutations", "mutation_slots"))
        if items:
            return len(items)
        plan = self._latest_plan_text().lower()
        return 1 if "stateful" in plan or "mutation" in plan else 0

    def _is_read_only_schema(self) -> bool:
        real_tools = [tool for name, tool in self.tools.items() if self._is_evidence_tool_name(name)]
        if not real_tools:
            return False
        for tool in real_tools:
            text = _tool_text(tool)
            if _matches_any(STATEFUL_PATTERNS, text):
                return False
            if not _matches_any(READ_ONLY_PATTERNS, text):
                return False
        return True

    def _task_route(self) -> str:
        plan = self._latest_plan_text().lower()
        tool_text = " ".join(_tool_text(tool) for tool in self.tools.values())
        if self._completion_tool_name() is not None or "stateful_mutation" in plan or "stateful" in plan:
            return "stateful"
        if "deterministic_transform" in plan or "transform" in plan:
            return "transform"
        if self._is_read_only_schema():
            return "read_only"
        if _matches_any(STATEFUL_PATTERNS, tool_text):
            return "stateful"
        return "unknown"

    def _looks_self_contained(self) -> bool:
        task = str(getattr(self, "task", "") or "").lower()
        return any(marker in task for marker in SELF_CONTAINED_MARKERS) and not self._is_read_only_schema()

    def _evidence_tools_available(self) -> bool:
        return any(self._is_evidence_tool_name(name) for name in self.tools)

    def _observation_is_failure(self, observations: str) -> bool:
        lowered_obs = str(observations).lower()
        return any(marker in lowered_obs for marker in FAILURE_MARKERS) or lowered_obs.startswith("round02_02_guard")

    def _recent_evidence_records(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for idx, step in enumerate(getattr(self.memory, "steps", [])):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or observations == "No observations":
                continue
            if observations.startswith("ROUND01_GUARD") or observations.startswith("ROUND02"):
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

    def _has_prior_evidence(self) -> bool:
        return self._evidence_seen_runtime or bool(self._recent_evidence_records())

    def _successful_real_call_count(self) -> int:
        count = 0
        for step in getattr(self.memory, "steps", []):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or self._observation_is_failure(observations):
                continue
            for call in getattr(step, "tool_calls", None) or []:
                if self._is_evidence_tool_name(getattr(call, "name", "")):
                    count += 1
        return count

    def _observation_has_success(self, observations: str) -> bool:
        lowered_obs = str(observations).lower()
        return any(marker in lowered_obs for marker in [
            '"success": true', "'success': true", "successfully", " updated", " created",
            " added", " removed", " deleted", " assigned", " corrected", " completed",
            " rescheduled", " transferred", " enrolled", " canceled", " cancelled",
            " approved", " deactivated", " activated",
        ])

    def _successful_mutation_count(self, include_step: ActionStep | None = None) -> int:
        steps = list(getattr(self.memory, "steps", []))
        if include_step is not None:
            steps.append(include_step)
        count = 0
        for step in steps:
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or observations == "No observations" or not self._observation_has_success(observations):
                continue
            for call in getattr(step, "tool_calls", None) or []:
                if self._is_state_changing_tool_name(getattr(call, "name", "")):
                    count += 1
        return count

    def _ledger_status_line(self) -> str:
        return (
            f"route={self._task_route()}; "
            f"planned_evidence={self._planned_evidence_count()}; "
            f"planned_mutations={self._planned_mutation_count()}; "
            f"evidence_records={len(self._recent_evidence_records())}; "
            f"successful_mutations={self._successful_mutation_count()}; "
            f"failed_call_signatures={len(self._failed_signatures)}; "
            f"completion_tool={self._completion_tool_name() or 'none'}"
        )

    def _completion_arguments(self, tool_name: str) -> Any:
        tool = self.tools.get(tool_name)
        inputs = getattr(tool, "inputs", {}) or {}
        if not inputs:
            return {}
        if "answer" in inputs:
            return {"answer": "Task Completed"}
        arguments = {}
        for key, spec in inputs.items():
            if isinstance(spec, dict) and spec.get("nullable"):
                continue
            arguments[key] = "Task Completed"
        return arguments

    def _partial_commit_ready(self, include_step: ActionStep | None = None) -> bool:
        if not self.guard_policy.get("partial_commit_on_blocker", True):
            return False
        if self._completion_tool_name() is None or self._task_route() == "read_only":
            return False
        required = int(self.guard_policy.get("min_successful_mutations_before_partial_complete", 1))
        return self._successful_mutation_count(include_step=include_step) >= required

    def _should_partial_commit_after_step(self, memory_step: ActionStep) -> bool:
        observations = str(getattr(memory_step, "observations", "") or "").lower()
        if not observations:
            return False
        blocker_seen = any(marker in observations for marker in [
            "repeated_failed_call", "low_value_repeat", "empty_or_unparsed_action",
            "terminal_not_ready", "not_found", "authorization_error", "tool_execution_error",
        ])
        return blocker_seen and self._partial_commit_ready(include_step=memory_step)

    def _run_partial_commit(self, memory_step: ActionStep, reason: str) -> Any:
        tool_name = self._completion_tool_name()
        if tool_name is None:
            return None
        arguments = self._completion_arguments(tool_name)
        try:
            observation = super().execute_tool_call(tool_name, arguments)
        except Exception as exc:
            observation = f"partial commit failed: {exc}"
        if getattr(memory_step, "tool_calls", None) is None:
            memory_step.tool_calls = []
        memory_step.tool_calls.append(ToolCall(name=tool_name, arguments=arguments, id="round02_02_partial_commit"))
        existing = str(getattr(memory_step, "observations", "") or "").strip()
        commit_observation = (
            f"ROUND02_02_PARTIAL_COMMIT: {reason}\n"
            f"ledger: {self._ledger_status_line()}\n"
            f"Auto-submitted {tool_name} after observed mutation progress and blocker.\n"
            f"Results for tool call '{tool_name}' with arguments '{arguments}':\n{observation}"
        )
        memory_step.observations = f"{existing}\n\n{commit_observation}" if existing else commit_observation
        terminal_answer = self._terminal_tool_answer(tool_name, arguments, observation)
        return terminal_answer if terminal_answer is not None else str(observation).strip()

    def _needs_evidence_for_final(self) -> bool:
        if not self.guard_policy.get("evidence_gate", True):
            return False
        if not self._evidence_tools_available():
            return False
        if self._looks_self_contained():
            return False
        return True

    def _canonicalize_date(self, text: str) -> str:
        stripped = text.strip()
        match = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{3,4})", stripped)
        if match:
            day, month, year = match.groups()
            month_num = MONTHS.get(month.lower())
            if month_num:
                return f"{int(year):04d}-{month_num}-{int(day):02d}"
        match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{3,4})", stripped)
        if match:
            month, day, year = match.groups()
            month_num = MONTHS.get(month.lower())
            if month_num:
                return f"{int(year):04d}-{month_num}-{int(day):02d}"
        return text

    def _canonicalize_answer(self, answer: Any) -> Any:
        if not isinstance(answer, str):
            return answer
        text = answer.strip().strip('"').strip("'").strip()
        text = re.sub(r"(?is)^answer\s*:\s*", "", text).strip()
        text = re.split(r"(?is)\s*;\s*evidence\s*:", text, maxsplit=1)[0].strip()
        if "\n" in text:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) == 1:
                text = lines[0]
        if self.guard_policy.get("date_iso_canonicalization", True):
            text = self._canonicalize_date(text)
        task = str(getattr(self, "task", "") or "").lower()
        fixed_width_requested = any(marker in task for marker in [
            "8-bit", "fixed width", "leading zero", "zero padded", "zero-padded",
        ])
        if not fixed_width_requested and re.fullmatch(r"0+[01]+", text):
            text = text.lstrip("0") or "0"
        if self.guard_policy.get("narrow_alias_trim", False) and "," in text:
            if any(marker in task for marker in ["what city", "which city", "city is", "what town", "which town"]):
                text = text.split(",", 1)[0].strip()
        return text

    def _answer_support_status(self, answer: Any) -> tuple[bool, str]:
        if not self._needs_evidence_for_final():
            return True, "support not required for this route"
        records = self._recent_evidence_records()
        if not records:
            return False, "no non-terminal evidence records exist"
        answer_text = str(answer or "").strip()
        if not answer_text:
            return False, "empty answer candidate"
        evidence_blob = "\n".join(record["observation"] for record in records).lower()
        normalized = answer_text.lower()
        if normalized and normalized in evidence_blob:
            return True, "answer string appears in recent evidence"
        canonical_answer = self._canonicalize_date(answer_text).lower()
        if canonical_answer != normalized and canonical_answer in evidence_blob:
            return True, "canonical answer appears in recent evidence"
        answer_tokens = _tokens(answer_text)
        evidence_tokens = _tokens(evidence_blob)
        overlap = answer_tokens & evidence_tokens
        if answer_tokens and overlap:
            mode = self.guard_policy.get("support_mode", "route")
            if mode != "strict" or len(overlap) >= min(2, len(answer_tokens)):
                return True, f"answer tokens overlap evidence: {sorted(overlap)[:4]}"
        task = str(getattr(self, "task", "") or "").lower()
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", answer_text) and any(
            marker in task for marker in ["count", "how many", "number of", "calculate", "compute", "vowel", "digit"]
        ):
            return True, "numeric answer may be deterministically derived from evidence"
        mode = self.guard_policy.get("support_mode", "route")
        if mode == "soft":
            return True, "soft support mode accepts existing evidence but records weak linkage"
        if mode == "route" and self._task_route() == "stateful":
            return True, "stateful route uses mutation ledger rather than span support"
        return False, "answer does not appear tied to recent observations"

    def _support_record(self, answer: Any) -> str:
        ok, detail = self._answer_support_status(answer)
        records = self._recent_evidence_records()
        last = records[-1] if records else {}
        return (
            "ROUND02_02_SUPPORT_RECORD\n"
            f"answer_candidate: {answer}\n"
            f"support_ok: {ok}\n"
            f"support_detail: {detail}\n"
            f"source_tool: {last.get('tool', 'none')}\n"
            f"source_step: {last.get('step', 'none')}\n"
            f"ledger: {self._ledger_status_line()}"
        )

    def _recovery_advice(self, reason: str, detail: str) -> str:
        lower = f"{reason} {detail}".lower()
        if "missing required" in lower:
            advice = "repair by using the required schema keys exactly; fill missing ids from a prior observation or lookup."
        elif "extra argument" in lower or "unexpected keyword" in lower:
            advice = "drop unsupported keys and preserve only schema-listed arguments."
        elif "unknown tool" in lower:
            advice = "choose one valid tool name from the current schema; close matches are hints only."
        elif "repeated_failed_call" in lower or "low_value_repeat" in lower:
            advice = "change identifier source, query a list/get/search tool, or move to the next pending slot."
        elif "not found" in lower or "does not exist" in lower:
            advice = "resolve the entity or id through broader search/list/get before retrying the specific operation."
        elif "unauthorized" in lower or "permission" in lower or "forbidden" in lower:
            advice = "check actor/account context or switch to a permitted mutation path before retrying."
        elif "terminal" in lower:
            advice = "delay terminal completion until the ledger has observed support or mutation progress."
        elif "empty" in lower or "unparsed" in lower:
            advice = "emit exactly one valid JSON tool call using an available schema."
        elif "unsupported" in lower or "support" in lower:
            advice = "obtain targeted evidence for the requested slot, then submit only the supported raw value."
        else:
            advice = "make one schema-valid call that advances the next missing evidence or mutation slot."
        self._last_recovery_hint = advice
        return advice

    def _guard_observation(self, reason: str, detail: str) -> str:
        advice = self._recovery_advice(reason, detail)
        return (
            f"ROUND02_02_GUARD_BLOCK: {reason}\n"
            f"{detail}\n"
            f"Ledger: {self._ledger_status_line()}\n"
            f"Recovery route: {advice}\n"
            "Next step: make one schema-valid call, repair the identifier or argument source, "
            "or commit only when the active terminal policy is satisfied."
        )

    def _preflight_arguments(self, tool_name: str, arguments: Any) -> tuple[bool, Any, str]:
        tool = self.tools.get(tool_name)
        if tool is None:
            valid_names = sorted(name for name in self.tools if name != "final_answer")
            suggestions = get_close_matches(tool_name, valid_names, n=3)
            return False, arguments, f"Unknown tool '{tool_name}'. Valid tools: {valid_names}. Closest matches: {suggestions}."
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                if len(getattr(tool, "inputs", {}) or {}) == 1:
                    return True, arguments, ""
                return False, arguments, f"Arguments for {tool_name} must be a JSON object matching {tool.inputs}."
        if not isinstance(arguments, dict):
            return False, arguments, f"Arguments for {tool_name} must be a dict or valid single string input."
        allowed = set((getattr(tool, "inputs", {}) or {}).keys())
        extra = sorted(set(arguments) - allowed)
        required = sorted(
            key for key, spec in (getattr(tool, "inputs", {}) or {}).items()
            if not (isinstance(spec, dict) and spec.get("nullable"))
        )
        missing = [key for key in required if key not in arguments]
        if extra and self.guard_policy.get("drop_extra_keys", False):
            arguments = {key: value for key, value in arguments.items() if key in allowed}
            missing = [key for key in required if key not in arguments]
            extra = []
        if extra:
            return False, arguments, f"Extra argument keys {extra}; allowed keys are {sorted(allowed)}."
        if missing:
            return False, arguments, f"Missing required argument keys {missing}; schema is {tool.inputs}."
        return True, arguments, ""

    def _terminal_ready(self, tool_name: str) -> bool:
        if not self.guard_policy.get("complete_gate", True):
            return True
        if not self._is_terminal_name(tool_name) or tool_name == "final_answer":
            return True
        if self._task_route() == "read_only":
            return False
        required = int(self.guard_policy.get("min_success_before_complete", 1))
        policy = self.guard_policy.get("completion_policy", "ledger_or_progress")
        planned = self._planned_mutation_count()
        cap = int(self.guard_policy.get("planned_mutation_cap", 1))
        ledger_required = max(required, min(planned, cap)) if planned else required
        if policy == "mutation_progress":
            return self._successful_mutation_count() >= ledger_required
        if policy == "verified_or_progress":
            return self._successful_mutation_count() >= ledger_required and self._successful_real_call_count() >= required
        return self._successful_mutation_count() >= ledger_required or self._successful_real_call_count() >= required

    def execute_tool_call(self, tool_name: str, arguments: Any) -> Any:
        ok, repaired_arguments, message = self._preflight_arguments(tool_name, arguments)
        if not ok:
            return self._guard_observation("schema_preflight", message)
        arguments = repaired_arguments
        signature = (tool_name, _json_key(arguments))
        if signature in self._failed_signatures:
            return self._guard_observation(
                "repeated_failed_call",
                f"The exact call {tool_name}({arguments}) already failed. Change arguments, choose another tool, or review the ledger.",
            )
        self._call_counts[signature] = self._call_counts.get(signature, 0) + 1
        if self._call_counts[signature] > int(self.guard_policy.get("repeat_limit", 2)):
            return self._guard_observation(
                "low_value_repeat",
                f"The exact call {tool_name}({arguments}) has been attempted {self._call_counts[signature]} times.",
            )
        if not self._terminal_ready(tool_name):
            return self._guard_observation(
                "terminal_not_ready",
                "A completion/terminal tool was requested before the active evidence or mutation ledger was ready.",
            )
        try:
            observation = super().execute_tool_call(tool_name, arguments)
        except Exception as exc:
            self._failed_signatures.add(signature)
            return self._guard_observation("tool_execution_error", str(exc))
        obs_text = str(observation).lower()
        if any(marker in obs_text for marker in FAILURE_MARKERS):
            self._failed_signatures.add(signature)
            self._recovery_advice("tool_observation_failure", obs_text[:400])
        else:
            self._successful_signatures.add(signature)
            if self._is_evidence_tool_name(tool_name):
                self._evidence_seen_runtime = True
            if self._is_state_changing_tool_name(tool_name):
                self._state_epoch += 1
                self._failed_signatures.clear()
                self._call_counts.clear()
        return observation

    def step(self, memory_step: ActionStep, memory_messages: Any = None) -> Any:
        result = super().step(memory_step, memory_messages=memory_messages)
        tool_calls = getattr(memory_step, "tool_calls", None) or []
        if not tool_calls:
            memory_step.observations = self._guard_observation(
                "empty_or_unparsed_action",
                "The model produced no executable tool call. Recover with exactly one valid tool call from the schema.",
            )
            committed = self._run_partial_commit(memory_step, "empty action after progress") if self._partial_commit_ready() else None
            return committed if committed is not None else None
        if result is not None and any(getattr(call, "name", "") == "final_answer" for call in tool_calls):
            canonical = self._canonicalize_answer(result)
            if self._needs_evidence_for_final() and not self._has_prior_evidence():
                memory_step.observations = self._guard_observation(
                    "unsupported_final_answer",
                    "final_answer was attempted before any non-final evidence observation was recorded. Plan and memory text are hypotheses, not evidence.",
                )
                return None
            if self.guard_policy.get("support_record_gate", True):
                support_ok, support_detail = self._answer_support_status(canonical)
                if not support_ok:
                    memory_step.observations = self._guard_observation(
                        "answer_support_missing",
                        f"final_answer candidate {canonical!r} lacks a usable support record: {support_detail}.",
                    )
                    return None
            if self.guard_policy.get("record_support", True):
                memory_step.observations = self._support_record(canonical)
            return canonical
        if result is None and self._should_partial_commit_after_step(memory_step):
            committed = self._run_partial_commit(memory_step, "blocker after progress")
            if committed is not None:
                return committed
        return result


class Round0202ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "round02_02_guarded_react"
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG: dict[str, Any] = {}

    def build_affordance(self, bench_type: str | None, context: ActionContext) -> list[Any]:
        tools = self.get_primary_task_tools(context, include_reasoning=True)
        if self.VARIANT_CONFIG.get("enable_ledger_review_tool", False):
            tools = list(tools) + [LedgerReviewTool()]
        return tools

    def build_specification(self, context: ActionContext, tools: list[Any]) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = context.planning_system
        self.guard_policy = {**DEFAULT_GUARD_POLICY, **self.VARIANT_CONFIG}

    def build_organization(self, context: ActionContext, tools: list[Any]) -> Round0202GuardedAgent:
        root_tools = self.normalize_tools(list(tools))
        agent = Round0202GuardedAgent(
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
            "round": "round_02_02",
        })
        return agent
