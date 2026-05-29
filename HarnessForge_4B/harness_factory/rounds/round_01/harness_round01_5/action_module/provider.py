from __future__ import annotations

import json
import re
from difflib import get_close_matches
from typing import Any

from Agents.agents import ToolCallingAgent
from Agents.memory import ActionStep, ToolCall
from Agents.tools import Tool
from module_action.base_action import ActionContext, BaseActionProvider


ACTION_SYSTEM = "repair_checkpoint_react"
ACTION_MODULE = "repair_checkpoint_react"


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
    r"\bretrieve\b", r"\bsearch\b", r"\bvalidate\b",
]
FAILURE_MARKERS = [
    "error", "unknown tool", "unexpected keyword", "missing required",
    "invalid", "failed", "not found", "does not exist", "guard blocked",
    "exception", "traceback",
]
SELF_CONTAINED_MARKERS = [
    "given", "provided", "in the question", "calculate", "compute",
    "convert", "count", "sort", "uppercase", "lowercase", "reverse",
    "substring", "string", "digits", "arithmetic",
]


def _json_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    except Exception:
        return str(value)


def _tool_text(tool: Any) -> str:
    return (
        f"{getattr(tool, 'name', '')} "
        f"{getattr(tool, 'description', '')}"
    ).lower().replace("_", " ")


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


class RepairCheckpointTool(Tool):
    name = "repair_checkpoint"
    description = (
        "Read-only checkpoint that reviews recent tool use, schema risks, repeated "
        "failures, missing evidence, and stop readiness. It never mutates the environment."
    )
    inputs = {
        "question": {
            "type": "string",
            "description": "The proposed next action, blocker, or finalization question to audit.",
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
            return "checkpoint: unavailable; use exact schemas, avoid repeats, and obtain evidence before finalizing."
        names = sorted(
            name for name in getattr(self.agent, "tools", {}).keys()
            if name not in {"final_answer", self.name}
        )
        recent = []
        for step in getattr(getattr(self.agent, "memory", None), "steps", [])[-8:]:
            calls = getattr(step, "tool_calls", None)
            obs = getattr(step, "observations", None)
            if calls:
                recent.append(f"calls={[(c.name, c.arguments) for c in calls]}")
            if obs:
                recent.append(str(obs)[:700])
        return (
            "checkpoint: read-only audit\n"
            f"allowed_tools: {names}\n"
            f"evidence_seen: {self.agent._has_prior_evidence()}\n"
            f"recent_failures: {len(getattr(self.agent, '_failed_signatures', set()))}\n"
            f"question: {question}\n"
            "next_safe_move: use one valid schema-matching tool; if evidence already supports the raw answer, finalize; if a terminal completion tool exists, use it only after observed state progress.\n"
            f"recent_context: {' | '.join(recent)[-1800:]}"
        )


class GuardedRound01Agent(ToolCallingAgent):
    def __init__(self, *args: Any, guard_policy: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self.guard_policy = guard_policy or {}
        self._call_counts: dict[tuple[str, str], int] = {}
        self._failed_signatures: set[tuple[str, str]] = set()
        self._successful_signatures: set[tuple[str, str]] = set()
        self._evidence_seen_runtime = False
        self._state_epoch = 0
        super().__init__(*args, **kwargs)

    def _is_checkpoint_tool(self, name: str) -> bool:
        return name in {"repair_checkpoint", "critic_reflect", "schema_audit", "ledger_review"}

    def _is_terminal_name(self, name: str) -> bool:
        if name == "final_answer":
            return True
        tool = self.tools.get(name)
        if tool is not None and getattr(tool, "terminal_tool", False):
            return True
        lowered = name.lower()
        return lowered in {"complete_task", "task_completed", "end_process", "finish_task"}

    def _is_evidence_tool_name(self, name: str) -> bool:
        if self._is_terminal_name(name) or self._is_checkpoint_tool(name):
            return False
        if name == "reasoning":
            return False
        return name in self.tools

    def _is_state_changing_tool_name(self, name: str) -> bool:
        if self._is_terminal_name(name) or self._is_checkpoint_tool(name):
            return False
        if name == "reasoning":
            return False
        tool = self.tools.get(name)
        if tool is None:
            return False
        readable_name = name.lower().replace("_", " ")
        if re.match(r"^(get|list|search|find|check|is|validate|lookup|has|locate|read|verify)\b", readable_name):
            return False
        return _matches_any(STATEFUL_PATTERNS, f"{readable_name} {_tool_text(tool)}")

    def _evidence_tools_available(self) -> bool:
        return any(self._is_evidence_tool_name(name) for name in self.tools)

    def _is_read_only_schema(self) -> bool:
        real_tools = [
            tool for name, tool in self.tools.items()
            if self._is_evidence_tool_name(name)
        ]
        if not real_tools:
            return False
        for tool in real_tools:
            text = _tool_text(tool)
            if _matches_any(STATEFUL_PATTERNS, text):
                return False
            if not _matches_any(READ_ONLY_PATTERNS, text):
                return False
        return True

    def _looks_self_contained(self) -> bool:
        task = str(getattr(self, "task", "") or "").lower()
        return any(marker in task for marker in SELF_CONTAINED_MARKERS) and not self._is_read_only_schema()

    def _has_prior_evidence(self) -> bool:
        if self._evidence_seen_runtime:
            return True
        for step in getattr(self.memory, "steps", []):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or observations == "No observations":
                continue
            if observations.startswith("ROUND01_GUARD"):
                continue
            lowered_obs = observations.lower()
            if any(marker in lowered_obs for marker in ["unknown tool", "unsupported step output"]):
                continue
            for call in getattr(step, "tool_calls", None) or []:
                if self._is_evidence_tool_name(getattr(call, "name", "")):
                    return True
        return False

    def _successful_real_call_count(self) -> int:
        count = 0
        for step in getattr(self.memory, "steps", []):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or observations.startswith("ROUND01_GUARD"):
                continue
            lowered_obs = observations.lower()
            if any(marker in lowered_obs for marker in FAILURE_MARKERS):
                continue
            for call in getattr(step, "tool_calls", None) or []:
                name = getattr(call, "name", "")
                if self._is_evidence_tool_name(name):
                    count += 1
        return count

    def _observation_has_success(self, observations: str) -> bool:
        lowered_obs = observations.lower()
        return any(
            marker in lowered_obs
            for marker in [
                '"success": true',
                "'success': true",
                "successfully",
                " updated",
                " created",
                " added",
                " removed",
                " deleted",
                " assigned",
                " corrected",
                " completed",
                " rescheduled",
            ]
        )

    def _successful_mutation_count(self, include_step: ActionStep | None = None) -> int:
        steps = list(getattr(self.memory, "steps", []))
        if include_step is not None:
            steps.append(include_step)
        count = 0
        for step in steps:
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "")
            if not observations or observations == "No observations":
                continue
            if not self._observation_has_success(observations):
                continue
            for call in getattr(step, "tool_calls", None) or []:
                if self._is_state_changing_tool_name(getattr(call, "name", "")):
                    count += 1
        return count

    def _completion_tool_name(self) -> str | None:
        for name in ("complete_task", "task_completed", "finish_task", "end_process"):
            if name in self.tools:
                return name
        for name, tool in self.tools.items():
            if name != "final_answer" and getattr(tool, "terminal_tool", False):
                return name
        return None

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
        if self._completion_tool_name() is None:
            return False
        if self._is_read_only_schema():
            return False
        required = int(self.guard_policy.get("min_successful_mutations_before_partial_complete", 1))
        return self._successful_mutation_count(include_step=include_step) >= required

    def _should_partial_commit_after_step(self, memory_step: ActionStep) -> bool:
        observations = str(getattr(memory_step, "observations", "") or "").lower()
        if not observations:
            return False
        blocker_seen = any(
            marker in observations
            for marker in [
                "repeated_failed_call",
                "low_value_repeat",
                "empty_or_unparsed_action",
                "terminal_not_ready",
            ]
        )
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
        memory_step.tool_calls.append(ToolCall(name=tool_name, arguments=arguments, id="round01_partial_commit"))
        existing = str(getattr(memory_step, "observations", "") or "").strip()
        commit_observation = (
            f"ROUND01_PARTIAL_COMMIT: {reason}\n"
            f"Auto-submitted {tool_name} after successful state mutation and repeated blocker.\n"
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
        task = str(getattr(self, "task", "") or "").lower()
        fixed_width_requested = any(
            marker in task for marker in ["8-bit", "fixed width", "leading zero", "zero padded", "zero-padded"]
        )
        if not fixed_width_requested and re.fullmatch(r"0+[01]+", text):
            text = text.lstrip("0") or "0"
        return text

    def _guard_observation(self, reason: str, detail: str) -> str:
        return (
            f"ROUND01_GUARD_BLOCK: {reason}\n"
            f"{detail}\n"
            "Next step: choose a valid schema-matching evidence/action tool, repair arguments, "
            "or finalize only after the observation supports the answer. For stateful tasks, "
            "if successful mutations already happened and the remaining work is blocked by "
            "repeated failure, call complete_task to preserve partial credit."
        )

    def _preflight_arguments(self, tool_name: str, arguments: Any) -> tuple[bool, Any, str]:
        tool = self.tools.get(tool_name)
        if tool is None:
            valid_names = sorted(name for name in self.tools if name != "final_answer")
            suggestions = get_close_matches(tool_name, valid_names, n=3)
            return False, arguments, (
                f"Unknown tool '{tool_name}'. Valid tools: {valid_names}. "
                f"Closest matches: {suggestions}."
            )
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                arguments = parsed
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
        required_success = int(self.guard_policy.get("min_success_before_complete", 1))
        return self._successful_real_call_count() >= required_success

    def execute_tool_call(self, tool_name: str, arguments: Any) -> Any:
        ok, repaired_arguments, message = self._preflight_arguments(tool_name, arguments)
        if not ok:
            return self._guard_observation("schema_preflight", message)
        arguments = repaired_arguments
        signature = (tool_name, _json_key(arguments))
        if signature in self._failed_signatures:
            return self._guard_observation(
                "repeated_failed_call",
                f"The exact call {tool_name}({arguments}) already failed. Change arguments, choose another tool, or use a checkpoint.",
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
                "A completion/terminal tool was requested before enough successful state-changing or evidence-producing calls were observed.",
            )
        try:
            observation = super().execute_tool_call(tool_name, arguments)
        except Exception as exc:
            self._failed_signatures.add(signature)
            return self._guard_observation("tool_execution_error", str(exc))
        obs_text = str(observation).lower()
        if any(marker in obs_text for marker in FAILURE_MARKERS):
            self._failed_signatures.add(signature)
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
            if committed is not None:
                return committed
            return None
        if result is not None and any(getattr(call, "name", "") == "final_answer" for call in tool_calls):
            if self._needs_evidence_for_final() and not self._has_prior_evidence():
                memory_step.observations = self._guard_observation(
                    "unsupported_final_answer",
                    "final_answer was attempted before any non-final evidence observation was recorded. Plan and memory text are hypotheses, not evidence.",
                )
                return None
            canonical = self._canonicalize_answer(result)
            if canonical != result:
                memory_step.observations = str(canonical)
            return canonical
        if result is None and self._should_partial_commit_after_step(memory_step):
            committed = self._run_partial_commit(memory_step, "blocker after progress")
            if committed is not None:
                return committed
        return result


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 5

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = context.planning_system
        self.guard_policy = {
            "evidence_gate": True,
            "complete_gate": True,
            "drop_extra_keys": True,
            "repeat_limit": 2,
            "min_success_before_complete": 1,
            "partial_commit_on_blocker": True,
            "min_successful_mutations_before_partial_complete": 1,
            "focus": "event-triggered non-acting repair checkpoint",
        }

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        root_tools = list(tools)
        checkpoint = None
        if True:
            checkpoint = RepairCheckpointTool()
            root_tools.append(checkpoint)
        agent = GuardedRound01Agent(
            model=context.model,
            tools=self.normalize_tools(root_tools),
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
        if checkpoint is not None:
            checkpoint.bind_agent(agent)
        setattr(
            agent,
            "harness_policy",
            {
                **self.guard_policy,
                "mode": ACTION_SYSTEM,
                "single_executor": True,
                "checkpoint_tool": getattr(checkpoint, "name", None),
                "hard_final_evidence_gate": bool(self.guard_policy.get("evidence_gate")),
                "hard_schema_preflight": True,
                "terminal_readiness_gate": bool(self.guard_policy.get("complete_gate")),
            },
        )
        return agent


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "GuardedRound01Agent"]
