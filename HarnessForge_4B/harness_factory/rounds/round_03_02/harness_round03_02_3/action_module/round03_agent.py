from __future__ import annotations

import re
from typing import Any

from Agents.memory import ActionStep
from module_action.base_action import ActionContext

from .round02_agent import (
    LedgerReviewTool,
    Round02ActionProvider,
    Round02GuardedAgent,
    _tokens,
)


def _split_plan_items(value: str) -> list[str]:
    value = str(value or "").strip()
    if not value or value.lower() in {"[]", "none", "null", "n/a"}:
        return []
    value = value.strip("[]")
    parts = re.split(r"\s*(?:,|;|\|)\s*", value)
    return [part.strip().strip("'\"") for part in parts if part.strip().strip("'\"")]


class Round03GuardedAgent(Round02GuardedAgent):
    """Round03 wrapper: shared ledger parsing, bounded closure, span repair, and memory quarantine."""

    def __init__(self, *args: Any, guard_policy: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self._round03_guard_events: list[str] = []
        super().__init__(*args, guard_policy=guard_policy, **kwargs)

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
        items = _split_plan_items(self._plan_field("evidence_slots", "required_evidence"))
        return len(items)

    def _planned_mutation_count(self) -> int:
        items = _split_plan_items(self._plan_field("required_mutations", "mutation_slots"))
        if items:
            return len(items)
        plan = self._latest_plan_text().lower()
        if "stateful_mutation" in plan or "required_mutations" in plan or "mutation" in plan:
            return 1
        return 0

    def _ledger_status_line(self) -> str:
        base = super()._ledger_status_line()
        return (
            f"{base}; planned_evidence={self._planned_evidence_count()}; "
            f"planned_mutations={self._planned_mutation_count()}; "
            f"guard_events={len(self._round03_guard_events)}"
        )

    def _guard_observation(self, reason: str, detail: str) -> str:
        self._round03_guard_events.append(str(reason))
        return super()._guard_observation(reason, detail)

    def _terminal_ready(self, tool_name: str) -> bool:
        if not self.guard_policy.get("complete_gate", True):
            return True
        if not self._is_terminal_name(tool_name) or tool_name == "final_answer":
            return True
        if self._task_route() == "read_only":
            return False

        policy = str(self.guard_policy.get("completion_policy", "progress"))
        if policy not in {"mutation_closure", "verified_mutation_closure"}:
            return super()._terminal_ready(tool_name)

        required = int(self.guard_policy.get("min_success_before_complete", 1))
        planned = self._planned_mutation_count()
        cap = int(self.guard_policy.get("planned_mutation_cap", 3))
        ledger_required = max(required, min(planned, cap)) if planned else required
        enough_mutations = self._successful_mutation_count() >= ledger_required
        if policy == "mutation_closure":
            return enough_mutations
        if not enough_mutations:
            return False
        evidence_needed = self._planned_evidence_count()
        if evidence_needed <= 0:
            return True
        return self._successful_real_call_count() >= min(evidence_needed, 2)

    def _partial_commit_ready(self, include_step: ActionStep | None = None) -> bool:
        mode = str(self.guard_policy.get("partial_mode", "base"))
        if mode != "exceptional":
            return super()._partial_commit_ready(include_step=include_step)
        if not self.guard_policy.get("partial_commit_on_blocker", True):
            return False
        if self._completion_tool_name() is None or self._task_route() == "read_only":
            return False
        required = int(self.guard_policy.get("min_successful_mutations_before_partial_complete", 1))
        if self._successful_mutation_count(include_step=include_step) < required:
            return False
        guard_threshold = int(self.guard_policy.get("partial_guard_events", 2))
        return len(self._round03_guard_events) >= guard_threshold or len(self._failed_signatures) >= guard_threshold

    def _extract_minimal_answer_span(self, text: str) -> str:
        if not self.guard_policy.get("searchqa_minimal_span", False):
            return text
        if not self._is_searchqa_task():
            return text
        stripped = text.strip()
        if len(stripped.split()) <= int(self.guard_policy.get("searchqa_overlong_token_limit", 14)):
            return stripped
        task = str(getattr(self, "task", "") or "").lower()
        patterns: list[str] = []
        if any(marker in task for marker in ["how old", "age", "minimum age", "older"]):
            patterns.extend([
                r"\b\d+(?:\.\d+)?\s*(?:years old|years or older|year old|years|yrs old)\b",
                r"\b\d+(?:\.\d+)?\b",
            ])
        if any(marker in task for marker in ["when", "date", "year", "month", "day"]):
            patterns.extend([
                r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{3,4}\b",
                r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{3,4}\b",
                r"\b\d{4}-\d{2}-\d{2}\b",
                r"\b\d{4}\b",
            ])
        if any(marker in task for marker in ["how many", "number of", "count", "percentage", "percent"]):
            patterns.extend([
                r"\b[-+]?\d+(?:\.\d+)?\s*(?:%|percent|percentage points|times|items|people|years)?\b",
            ])
        quoted = re.search(r"['\"]([^'\"]{1,80})['\"]", stripped)
        if quoted and any(marker in task for marker in ["title", "name", "called", "alias"]):
            return quoted.group(1).strip()
        for pattern in patterns:
            match = re.search(pattern, stripped, flags=re.IGNORECASE)
            if match:
                candidate = match.group(0).strip(" ,.;:")
                if candidate:
                    return candidate
        return stripped

    def _canonicalize_answer(self, answer: Any) -> Any:
        canonical = super()._canonicalize_answer(answer)
        if isinstance(canonical, str):
            canonical = self._extract_minimal_answer_span(canonical)
        return canonical

    def _searchqa_answer_support_status(self, answer_text: str, records: list[dict[str, str]]) -> tuple[bool, str]:
        if self.guard_policy.get("searchqa_minimal_span", False):
            limit = int(self.guard_policy.get("searchqa_overlong_token_limit", 14))
            if len(_tokens(answer_text)) > limit and re.search(r"[.;]|\bthough\b|\bbecause\b|\bhowever\b", answer_text.lower()):
                return False, "SearchQA candidate is overlong; submit the minimal supported raw span"
        return super()._searchqa_answer_support_status(answer_text, records)

    def _answer_support_status(self, answer: Any) -> tuple[bool, str]:
        if self.guard_policy.get("transform_requires_current_evidence", False):
            if self._task_route() == "transform" and not self._looks_self_contained():
                if not self._recent_evidence_records():
                    return False, "transform route needs a current observation supporting the transform input"
        return super()._answer_support_status(answer)

    def _current_evidence_blob(self) -> str:
        parts = [str(getattr(self, "task", "") or "")]
        parts.extend(record.get("observation", "") for record in self._recent_evidence_records())
        return "\n".join(parts).lower()

    def _argument_strings(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            out: list[str] = []
            for nested in value.values():
                out.extend(self._argument_strings(nested))
            return out
        if isinstance(value, (list, tuple, set)):
            out = []
            for nested in value:
                out.extend(self._argument_strings(nested))
            return out
        return []

    def _looks_like_unverified_identifier(self, value: str) -> bool:
        stripped = value.strip()
        if len(stripped) < 8:
            return False
        if re.fullmatch(r"[0-9a-fA-F]{8,}(?:-[0-9a-fA-F]{4,})*", stripped):
            return True
        if re.fullmatch(r"[A-Za-z0-9_-]{10,}", stripped) and re.search(r"\d", stripped):
            return True
        return False

    def _preflight_arguments(self, tool_name: str, arguments: Any) -> tuple[bool, Any, str]:
        ok, repaired_arguments, message = super()._preflight_arguments(tool_name, arguments)
        if not ok:
            return ok, repaired_arguments, message
        if not self.guard_policy.get("memory_argument_quarantine", False):
            return ok, repaired_arguments, message
        if self._is_terminal_name(tool_name) or self._is_checkpoint_tool(tool_name) or tool_name == "reasoning":
            return ok, repaired_arguments, message
        current_blob = self._current_evidence_blob()
        for value in self._argument_strings(repaired_arguments):
            if self._looks_like_unverified_identifier(value) and value.lower() not in current_blob:
                return (
                    False,
                    repaired_arguments,
                    "Concrete identifier argument is not present in the current task or current observations; "
                    "resolve it with a current list/get/search observation before using it.",
                )
        return ok, repaired_arguments, message


class Round03ActionProvider(Round02ActionProvider):
    """Provider that preserves the Round02 lifecycle while instantiating Round03GuardedAgent."""

    def build_organization(self, context: ActionContext, tools: list[Any]) -> Round03GuardedAgent:
        root_tools = self.normalize_tools(list(tools))
        agent = Round03GuardedAgent(
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
        setattr(
            agent,
            "harness_policy",
            {
                **self.guard_policy,
                "mode": self.prompts_type,
                "single_executor": True,
                "hard_schema_preflight": True,
                "ledger_review_tool": self.VARIANT_CONFIG.get("enable_ledger_review_tool", False),
                "round": "round_03_02",
            },
        )
        return agent
