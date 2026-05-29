from __future__ import annotations

import json
import re
from datetime import datetime
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
    "please", "must", "should", "using", "from", "into", "this", "that",
}
MONTHS = {
    "january": "01", "jan": "01", "february": "02", "feb": "02",
    "march": "03", "mar": "03", "april": "04", "apr": "04",
    "may": "05", "june": "06", "jun": "06", "july": "07", "jul": "07",
    "august": "08", "aug": "08", "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10", "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}
WEEKDAY_NAMES = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}
TRANSFORM_TOOL_HINTS = (
    "calculator", "counter", "count", "length", "reverse", "ascii", "palindrome",
    "converter", "combination", "date", "timezone", "vowel", "consonant", "letter",
)
SEARCHQA_MARKERS = ("searchqa terminal rule", "mixed_searchqa")
SEARCHQA_QUERY_KEYS = ("query", "q", "question", "search_query", "keywords")


DEFAULT_GUARD_POLICY: dict[str, Any] = {
    "focus": "round03 contract ledger and recovery routing",
    "evidence_gate": True,
    "support_record_gate": True,
    "support_mode": "strict",
    "relation_min_overlap": 1,
    "strict_single_token_support": True,
    "complete_gate": True,
    "completion_policy": "mutation_coverage",
    "mutation_coverage_cap": 4,
    "drop_extra_keys": True,
    "repair_missing_from_evidence": True,
    "repair_unknown_tool_name": False,
    "repeat_limit": 1,
    "min_success_before_complete": 1,
    "partial_commit_on_blocker": False,
    "min_successful_mutations_before_partial_complete": 2,
    "enable_ledger_review_tool": False,
    "date_iso_canonicalization": True,
    "searchqa_raw_query_guard": True,
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


def _split_inline_items(value: str) -> list[str]:
    value = value.strip()
    if not value or value.lower() in {"[]", "none", "null", "n/a", "unknown"}:
        return []
    value = value.strip("[]")
    parts = re.split(r"\s*(?:,|;|\|)\s*", value)
    return [part.strip().strip("'\"") for part in parts if part.strip().strip("'\"")]


def _sentence_units(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|[\n\r]+", str(text))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _phrase_in_text(phrase: str, text: str) -> bool:
    phrase = str(phrase or "").strip()
    if not phrase:
        return False
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .,'/-]{0,80}", phrase):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(phrase.lower()) + r"(?![A-Za-z0-9])"
        return re.search(pattern, text.lower()) is not None
    return phrase.lower() in text.lower()


class LedgerReviewTool(Tool):
    name = "ledger_review"
    description = (
        "Read-only checkpoint that summarizes evidence slots, mutation coverage, "
        "failed calls, and terminal readiness. It never mutates state."
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
            "next_safe_move: fill the next missing slot, repair the identifier source, "
            "or commit only when the active terminal policy is satisfied."
        )


class Round03LedgerAgent(ToolCallingAgent):
    """Single executor with validated-plan ledger, relation support, and bounded recovery."""

    def __init__(self, *args: Any, guard_policy: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self.guard_policy = {**DEFAULT_GUARD_POLICY, **(guard_policy or {})}
        self._call_counts: dict[tuple[str, str], int] = {}
        self._failed_signatures: set[tuple[str, str]] = set()
        self._successful_signatures: set[tuple[str, str]] = set()
        self._evidence_seen_runtime = False
        self._state_epoch = 0
        self._last_recovery_hint = ""
        super().__init__(*args, **kwargs)

    def _is_searchqa_task(self) -> bool:
        task = str(getattr(self, "task", "") or "").lower()
        return any(marker in task for marker in SEARCHQA_MARKERS)

    def _searchqa_raw_question(self) -> str:
        task = str(getattr(self, "task", "") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not task:
            return ""
        matches = list(re.finditer(r"(?im)^Task:\s*$", task))
        body = task[matches[-1].end():] if matches else re.split(r"(?i)\bTask:\s*", task)[-1]
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        for line in reversed(lines):
            lowered = line.lower()
            if lowered.startswith(("searchqa terminal rule", "strict output", "use the", "you are")):
                continue
            return line
        return lines[-1] if lines else ""

    def _is_search_tool_name(self, name: str) -> bool:
        lowered = name.lower().replace("_", " ").strip()
        return lowered == "search" or lowered.startswith("search ") or lowered.endswith(" search")

    def _searchqa_maybe_repair_search_arguments(self, tool_name: str, arguments: Any) -> Any:
        if not self.guard_policy.get("searchqa_raw_query_guard", True):
            return arguments
        if not self._is_searchqa_task() or self._has_prior_evidence() or not self._is_search_tool_name(tool_name):
            return arguments
        raw_question = self._searchqa_raw_question()
        if not raw_question or not isinstance(arguments, dict):
            return arguments
        query_key = next((key for key in SEARCHQA_QUERY_KEYS if key in arguments and isinstance(arguments.get(key), str)), None)
        if query_key is None:
            return arguments
        proposed = str(arguments.get(query_key) or "").strip()
        proposed_tokens = _tokens(proposed)
        raw_tokens = _tokens(raw_question)
        if not raw_tokens:
            return arguments
        overlap = len(proposed_tokens & raw_tokens) / max(1, len(raw_tokens))
        near_raw_rewrite = overlap >= 0.72 and abs(len(proposed_tokens) - len(raw_tokens)) <= 5
        off_topic_rewrite = overlap <= 0.25
        if near_raw_rewrite or off_topic_rewrite or not proposed:
            repaired = dict(arguments)
            repaired[query_key] = raw_question
            return repaired
        return arguments

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

    def _plan_block(self, *names: str) -> str:
        lines = self._latest_plan_text().splitlines()
        lowered_names = tuple(name.lower() for name in names)
        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            lowered = line.lower()
            for name in lowered_names:
                prefix = name + ":"
                if lowered.startswith(prefix):
                    head = line.split(":", 1)[1].strip()
                    block = [head] if head else []
                    for following in lines[idx + 1:]:
                        stripped = following.strip()
                        if not stripped:
                            continue
                        if not following.startswith((" ", "\t", "-")) and re.match(r"^[A-Za-z_][A-Za-z0-9_ -]*:\s*", stripped):
                            break
                        block.append(stripped.lstrip("- ").strip())
                    return "; ".join(part for part in block if part)
        return ""

    def _plan_items(self, *names: str) -> list[str]:
        return _split_inline_items(self._plan_block(*names))

    def _planned_evidence_count(self) -> int:
        return len(self._plan_items("evidence_slots", "required_evidence", "verification_targets"))

    def _planned_dependency_count(self) -> int:
        return len(self._plan_items("dependency_edges"))

    def _planned_mutation_count(self) -> int:
        items = self._plan_items("required_mutations", "mutation_slots")
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
        if self._completion_tool_name() is not None or "stateful_mutation" in plan or "route: stateful" in plan:
            return "stateful"
        if "multi_hop" in plan or "dependency_edges" in plan and self._planned_dependency_count() > 0:
            return "transform"
        if "deterministic_transform" in plan or "route: transform" in plan:
            return "transform"
        if self._is_read_only_schema():
            return "read_only"
        if _matches_any(STATEFUL_PATTERNS, tool_text):
            return "stateful"
        return "unknown"

    def _looks_self_contained(self) -> bool:
        task = str(getattr(self, "task", "") or "").lower()
        return any(marker in task for marker in SELF_CONTAINED_MARKERS) and not self._is_read_only_schema()

    def _observation_is_failure(self, observations: str) -> bool:
        lowered_obs = str(observations).lower()
        return any(marker in lowered_obs for marker in FAILURE_MARKERS) or lowered_obs.startswith("round03_guard")

    def _recent_evidence_records(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for idx, step in enumerate(getattr(self.memory, "steps", [])):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or observations == "No observations":
                continue
            if observations.startswith(("ROUND01_GUARD", "ROUND02", "ROUND03_GUARD", "ROUND03_SUPPORT")):
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
            " approved", " deactivated", " activated", " saved", " posted",
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
            f"planned_dependencies={self._planned_dependency_count()}; "
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

    def _mutation_completion_required(self) -> int:
        required = int(self.guard_policy.get("min_success_before_complete", 1))
        planned = self._planned_mutation_count()
        if not planned:
            return required
        cap = int(self.guard_policy.get("mutation_coverage_cap", 0) or 0)
        if cap > 0:
            planned = min(planned, cap)
        return max(required, planned)

    def _partial_commit_ready(self, include_step: ActionStep | None = None) -> bool:
        if not self.guard_policy.get("partial_commit_on_blocker", False):
            return False
        if self._completion_tool_name() is None or self._task_route() == "read_only":
            return False
        required = int(self.guard_policy.get("min_successful_mutations_before_partial_complete", 2))
        planned = self._planned_mutation_count()
        if planned:
            required = max(required, min(planned, int(self.guard_policy.get("mutation_coverage_cap", planned) or planned)))
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
        memory_step.tool_calls.append(ToolCall(name=tool_name, arguments=arguments, id="round03_partial_commit"))
        existing = str(getattr(memory_step, "observations", "") or "").strip()
        commit_observation = (
            f"ROUND03_PARTIAL_COMMIT: {reason}\n"
            f"ledger: {self._ledger_status_line()}\n"
            f"Auto-submitted {tool_name} after coverage-aware progress and blocker.\n"
            f"Results for tool call '{tool_name}' with arguments '{arguments}':\n{observation}"
        )
        memory_step.observations = f"{existing}\n\n{commit_observation}" if existing else commit_observation
        terminal_answer = self._terminal_tool_answer(tool_name, arguments, observation)
        return terminal_answer if terminal_answer is not None else str(observation).strip()

    def _needs_evidence_for_final(self) -> bool:
        if not self.guard_policy.get("evidence_gate", True):
            return False
        if not any(self._is_evidence_tool_name(name) for name in self.tools):
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

    def _canonicalize_datetime(self, text: str) -> str:
        stripped = text.strip()
        task = str(getattr(self, "task", "") or "").lower()
        wants_time = "date and time" in task or "what date and time" in task
        match = re.fullmatch(
            r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{3,4}),?\s+(\d{1,2}):(\d{2})(?::\d{2})?.*",
            stripped,
        )
        if match:
            day, month, year, hour, minute = match.groups()
            month_num = MONTHS.get(month.lower())
            if month_num:
                return f"{int(year):04d}-{month_num}-{int(day):02d} {int(hour):02d}:{minute}"
        match = re.fullmatch(
            r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{3,4}),?\s+(\d{1,2}):(\d{2})(?::\d{2})?.*",
            stripped,
        )
        if match:
            month, day, year, hour, minute = match.groups()
            month_num = MONTHS.get(month.lower())
            if month_num:
                return f"{int(year):04d}-{month_num}-{int(day):02d} {int(hour):02d}:{minute}"
        if wants_time:
            match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?", stripped)
            if match:
                return f"{match.group(1)} {match.group(2)}"
        return text

    def _observed_dates(self) -> list[datetime]:
        dates: list[datetime] = []
        for record in self._recent_evidence_records():
            text = record["observation"]
            for match in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", text):
                year, month, day, hour, minute = match.groups()
                try:
                    dates.append(datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0)))
                except ValueError:
                    pass
            for match in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{3,4})(?:,?\s+(\d{1,2}):(\d{2}))?", text):
                day, month, year, hour, minute = match.groups()
                month_num = MONTHS.get(month.lower())
                if month_num:
                    try:
                        dates.append(datetime(int(year), int(month_num), int(day), int(hour or 0), int(minute or 0)))
                    except ValueError:
                        pass
            for match in re.finditer(r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{3,4})(?:,?\s+(\d{1,2}):(\d{2}))?", text):
                month, day, year, hour, minute = match.groups()
                month_num = MONTHS.get(month.lower())
                if month_num:
                    try:
                        dates.append(datetime(int(year), int(month_num), int(day), int(hour or 0), int(minute or 0)))
                    except ValueError:
                        pass
        return dates

    def _canonicalize_day_of_month_answer(self, text: str) -> str:
        task = str(getattr(self, "task", "") or "").lower()
        if text.strip().lower() not in WEEKDAY_NAMES:
            return text
        if "day of week" in task or "weekday" in task:
            return text
        if "day of when" not in task and "what is the day of" not in task:
            return text
        dates = self._observed_dates()
        if dates:
            return str(dates[-1].day)
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
        if not self._is_searchqa_task() and self.guard_policy.get("date_iso_canonicalization", True):
            text = self._canonicalize_datetime(self._canonicalize_date(text))
            text = self._canonicalize_day_of_month_answer(text)
        task = str(getattr(self, "task", "") or "").lower()
        fixed_width_requested = any(marker in task for marker in [
            "8-bit", "fixed width", "leading zero", "zero padded", "zero-padded",
        ])
        if not fixed_width_requested and re.fullmatch(r"0+[01]+", text):
            text = text.lstrip("0") or "0"
        return text

    def _is_transform_result_tool(self, tool_name: str) -> bool:
        lowered = str(tool_name or "").lower().replace("_", " ")
        return any(hint in lowered for hint in TRANSFORM_TOOL_HINTS)

    def _tool_result_value(self, tool_name: str) -> str:
        pattern = re.compile(
            rf"Results for tool call '{re.escape(tool_name)}'.*?:\s*(.*?)(?=\n\s*Results for tool call '|$)",
            re.DOTALL,
        )
        for record in reversed(self._recent_evidence_records()):
            match = pattern.search(record["observation"])
            if not match:
                continue
            value = match.group(1).strip()
            if not value:
                continue
            first_line = value.splitlines()[0].strip()
            if first_line.startswith("{"):
                key_match = re.search(r"['\"](?:first_name|last_name|name)['\"]\s*:\s*['\"]([^'\"]+)", first_line)
                if key_match:
                    return key_match.group(1).strip()
            return first_line.strip("'\"").strip()
        return ""

    def _deterministic_transform_support_detail(self, answer_text: str) -> str:
        task = str(getattr(self, "task", "") or "").lower()
        canonical = self._canonicalize_datetime(self._canonicalize_date(answer_text))
        for record in reversed(self._recent_evidence_records()):
            tool_name = record.get("tool", "")
            if not self._is_transform_result_tool(tool_name):
                continue
            observation = record["observation"]
            if _phrase_in_text(answer_text, observation) or (canonical != answer_text and _phrase_in_text(canonical, observation)):
                return f"answer appears in deterministic transform output from {tool_name}"
        if re.fullmatch(r"[-+]?\d+", answer_text) and "combined length" in task:
            first = self._tool_result_value("extract_first_name") or self._tool_result_value("extract_name_component")
            last = self._tool_result_value("extract_last_name")
            if first and last:
                first_len = len(re.findall(r"[A-Za-z0-9]", first))
                last_len = len(re.findall(r"[A-Za-z0-9]", last))
                possible = {first_len + last_len, first_len + last_len + 1}
                if int(answer_text) in possible:
                    return "numeric answer matches deterministic combined-length derivation from observed name components"
        return ""

    def _best_support_sentence(self, answer_text: str) -> tuple[dict[str, str] | None, str, int]:
        task_tokens = _tokens(str(getattr(self, "task", "") or "")) - _tokens(answer_text)
        best_record: dict[str, str] | None = None
        best_sentence = ""
        best_overlap = -1
        for record in self._recent_evidence_records():
            for sentence in _sentence_units(record["observation"]):
                if not _phrase_in_text(answer_text, sentence):
                    continue
                overlap = len(task_tokens & _tokens(sentence))
                if overlap > best_overlap:
                    best_record = record
                    best_sentence = sentence
                    best_overlap = overlap
        return best_record, best_sentence, max(best_overlap, 0)

    def _answer_support_status(self, answer: Any) -> tuple[bool, str]:
        if not self._needs_evidence_for_final():
            return True, "support not required for this route"
        records = self._recent_evidence_records()
        if not records:
            return False, "no non-terminal evidence records exist"
        answer_text = str(answer or "").strip()
        if not answer_text:
            return False, "empty answer candidate"
        record, sentence, overlap = self._best_support_sentence(answer_text)
        min_overlap = int(self.guard_policy.get("relation_min_overlap", 1))
        if record is not None and overlap >= min_overlap:
            return True, f"answer appears in a relation-overlapping evidence clause from {record.get('tool')}"
        if record is not None and min_overlap <= 0:
            return True, f"answer appears in an evidence clause from {record.get('tool')}"
        canonical = self._canonicalize_date(answer_text)
        if canonical != answer_text:
            record, sentence, overlap = self._best_support_sentence(canonical)
            if record is not None and overlap >= min_overlap:
                return True, "canonical answer appears in a relation-overlapping evidence clause"
        answer_tokens = _tokens(answer_text)
        evidence_blob = "\n".join(record["observation"] for record in records)
        task = str(getattr(self, "task", "") or "").lower()
        transform_detail = self._deterministic_transform_support_detail(answer_text)
        if transform_detail:
            return True, transform_detail
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", answer_text) and any(
            marker in task for marker in ["count", "how many", "number of", "calculate", "compute", "vowel", "digit"]
        ) and records and self._planned_dependency_count() == 0:
            return True, "numeric answer may be deterministically derived from observed evidence"
        if answer_tokens:
            mode = self.guard_policy.get("support_mode", "strict")
            evidence_tokens = _tokens(evidence_blob)
            overlap_tokens = answer_tokens & evidence_tokens
            if mode != "strict" and len(overlap_tokens) >= min(2, len(answer_tokens)):
                return True, f"non-strict token support from evidence: {sorted(overlap_tokens)[:4]}"
            if not self.guard_policy.get("strict_single_token_support", True) and overlap_tokens:
                return True, f"light token support from evidence: {sorted(overlap_tokens)[:4]}"
        if self.guard_policy.get("support_mode") == "route" and self._task_route() == "stateful":
            return True, "stateful route uses mutation ledger rather than answer span support"
        return False, "answer is not bound to a current evidence clause for the requested slot"

    def _support_record(self, answer: Any) -> str:
        ok, detail = self._answer_support_status(answer)
        record, sentence, overlap = self._best_support_sentence(str(answer or ""))
        return (
            "ROUND03_SUPPORT_RECORD\n"
            f"answer_candidate: {answer}\n"
            f"target_slot_hint: {self._plan_block('answer_format') or 'raw requested answer'}\n"
            f"relation_overlap: {overlap}\n"
            f"support_ok: {ok}\n"
            f"support_detail: {detail}\n"
            f"source_tool: {(record or {}).get('tool', 'none')}\n"
            f"source_step: {(record or {}).get('step', 'none')}\n"
            f"source_clause: {sentence[:320]}\n"
            f"ledger: {self._ledger_status_line()}"
        )

    def _extract_value_for_key(self, key: str) -> Any | None:
        key_pattern = re.escape(key)
        for record in reversed(self._recent_evidence_records()):
            text = record["observation"]
            patterns = [
                rf"[\"']{key_pattern}[\"']\s*:\s*[\"']?([^\"',}}\]\n]+)",
                rf"\b{key_pattern}\b\s*(?:=|is|:)\s*[\"']?([^\"',}}\]\n]+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value and len(value) <= 120:
                        return value
        return None

    def _recovery_advice(self, reason: str, detail: str) -> str:
        lower = f"{reason} {detail}".lower()
        if "missing required" in lower:
            advice = "fill missing required keys from the most recent observation, or call a list/search/get tool to obtain them."
        elif "extra argument" in lower or "unexpected keyword" in lower:
            advice = "drop unsupported keys and preserve only schema-listed arguments."
        elif "unknown tool" in lower:
            advice = "choose one exact valid tool name; close matches are hints, not new tools."
        elif "repeated_failed_call" in lower or "low_value_repeat" in lower:
            advice = "change identifier source, query a broader list/search/get tool, or advance a different pending slot."
        elif "not found" in lower or "does not exist" in lower:
            advice = "resolve the entity or id through a broader search/list/get call before retrying the specific operation."
        elif "unauthorized" in lower or "permission" in lower or "forbidden" in lower:
            advice = "check actor/account context or switch to a permitted mutation path before retrying."
        elif "terminal" in lower:
            advice = "delay terminal completion until required mutation coverage or relation-bound answer support is visible."
        elif "empty" in lower or "unparsed" in lower:
            advice = "emit exactly one valid JSON tool call using an available schema."
        elif "unsupported" in lower or "support" in lower:
            advice = "obtain targeted evidence for the requested relation slot, then submit only the supported raw value."
        else:
            advice = "make one schema-valid call that advances the next missing evidence, dependency, or mutation slot."
        self._last_recovery_hint = advice
        return advice

    def _guard_observation(self, reason: str, detail: str) -> str:
        advice = self._recovery_advice(reason, detail)
        valid_tools = sorted(name for name in self.tools if name != "final_answer")[:24]
        return (
            f"ROUND03_GUARD_BLOCK: {reason}\n"
            f"{detail}\n"
            f"Ledger: {self._ledger_status_line()}\n"
            f"Valid tool sample: {valid_tools}\n"
            f"Recovery route: {advice}\n"
            "Next step: use one schema-valid call, repair the identifier or argument source, "
            "or commit only when the active terminal policy is satisfied."
        )

    def _preflight_call(self, tool_name: str, arguments: Any) -> tuple[bool, str, Any, str]:
        tool = self.tools.get(tool_name)
        if tool is None:
            valid_names = sorted(name for name in self.tools if name != "final_answer")
            suggestions = get_close_matches(tool_name, valid_names, n=2, cutoff=0.84)
            if self.guard_policy.get("repair_unknown_tool_name", False) and len(suggestions) == 1:
                tool_name = suggestions[0]
                tool = self.tools.get(tool_name)
            else:
                return False, tool_name, arguments, f"Unknown tool '{tool_name}'. Valid tools: {valid_names}. Closest matches: {suggestions}."
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                if len(getattr(tool, "inputs", {}) or {}) == 1:
                    return True, tool_name, arguments, ""
                return False, tool_name, arguments, f"Arguments for {tool_name} must be a JSON object matching {tool.inputs}."
        if not isinstance(arguments, dict):
            return False, tool_name, arguments, f"Arguments for {tool_name} must be a dict or valid single string input."
        allowed = set((getattr(tool, "inputs", {}) or {}).keys())
        extra = sorted(set(arguments) - allowed)
        required = sorted(
            key for key, spec in (getattr(tool, "inputs", {}) or {}).items()
            if not (isinstance(spec, dict) and spec.get("nullable"))
        )
        missing = [key for key in required if key not in arguments]
        if extra and self.guard_policy.get("drop_extra_keys", False):
            arguments = {key: value for key, value in arguments.items() if key in allowed}
            extra = []
            missing = [key for key in required if key not in arguments]
        if missing and self.guard_policy.get("repair_missing_from_evidence", True):
            repaired = dict(arguments)
            for key in missing:
                value = self._extract_value_for_key(key)
                if value is not None:
                    repaired[key] = value
            arguments = repaired
            missing = [key for key in required if key not in arguments]
        if extra:
            return False, tool_name, arguments, f"Extra argument keys {extra}; allowed keys are {sorted(allowed)}."
        if missing:
            return False, tool_name, arguments, f"Missing required argument keys {missing}; schema is {tool.inputs}."
        return True, tool_name, arguments, ""

    def _terminal_ready(self, tool_name: str) -> bool:
        if not self.guard_policy.get("complete_gate", True):
            return True
        if not self._is_terminal_name(tool_name) or tool_name == "final_answer":
            return True
        if self._task_route() == "read_only":
            return False
        policy = self.guard_policy.get("completion_policy", "mutation_coverage")
        required = self._mutation_completion_required()
        if policy == "progress":
            return self._successful_mutation_count() >= 1 or self._successful_real_call_count() >= 1
        if policy == "verified_or_progress":
            return self._successful_mutation_count() >= required and self._successful_real_call_count() >= 1
        return self._successful_mutation_count() >= required

    def execute_tool_call(self, tool_name: str, arguments: Any) -> Any:
        ok, repaired_tool_name, repaired_arguments, message = self._preflight_call(tool_name, arguments)
        if not ok:
            return self._guard_observation("schema_preflight", message)
        tool_name = repaired_tool_name
        arguments = self._searchqa_maybe_repair_search_arguments(tool_name, repaired_arguments)
        signature = (tool_name, _json_key(arguments))
        if signature in self._failed_signatures:
            return self._guard_observation(
                "repeated_failed_call",
                f"The exact call {tool_name}({arguments}) already failed. Change arguments, choose another tool, or review the ledger.",
            )
        self._call_counts[signature] = self._call_counts.get(signature, 0) + 1
        if self._call_counts[signature] > int(self.guard_policy.get("repeat_limit", 1)):
            return self._guard_observation(
                "low_value_repeat",
                f"The exact call {tool_name}({arguments}) has been attempted {self._call_counts[signature]} times.",
            )
        if not self._terminal_ready(tool_name):
            return self._guard_observation(
                "terminal_not_ready",
                "A completion/terminal tool was requested before evidence support or mutation coverage was ready.",
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
            committed = self._run_partial_commit(memory_step, "empty action after coverage-aware progress") if self._partial_commit_ready() else None
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
                        f"final_answer candidate {canonical!r} lacks relation-bound support: {support_detail}.",
                    )
                    return None
            if self.guard_policy.get("record_support", True):
                memory_step.observations = self._support_record(canonical)
            return canonical
        if result is None and self._should_partial_commit_after_step(memory_step):
            committed = self._run_partial_commit(memory_step, "blocker after coverage-aware progress")
            if committed is not None:
                return committed
        return result


class Round03ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "round03_contract_react"
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

    def build_organization(self, context: ActionContext, tools: list[Any]) -> Round03LedgerAgent:
        root_tools = self.normalize_tools(list(tools))
        agent = Round03LedgerAgent(
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
            "validated_plan_contract": True,
            "relation_aware_support": True,
            "coverage_terminal_gate": self.guard_policy.get("complete_gate", True),
            "ledger_review_tool": self.VARIANT_CONFIG.get("enable_ledger_review_tool", False),
            "round": "round_03_01",
        })
        return agent
