from __future__ import annotations

from typing import Any

import json_repair
from Agents.memory import ActionStep
from Agents.models import MessageRole
from _harness_guards import (
    ReflectionCriticTool,
    guard_task_tools,
    is_read_only_tool_schema,
    schema_route_name,
)
from module_action.base_action import ActionContext, BaseActionProvider, SubAgentTool


class EvidenceReportingSubAgentTool(SubAgentTool):
    """Sub-agent tool that exposes compact internal evidence to the judge."""

    def __init__(
        self,
        *,
        evidence_tool_names: set[str],
        evidence_char_budget: int = 1400,
        **kwargs: Any,
    ) -> None:
        self.evidence_tool_names = set(evidence_tool_names)
        self.evidence_char_budget = evidence_char_budget
        super().__init__(**kwargs)

    def _evidence_digest(self, payload: dict[str, Any]) -> str:
        chunks: list[str] = []
        for step in payload.get("agent_trajectory", []) or []:
            if not isinstance(step, dict) or step.get("name") != "action":
                continue
            observations = str(step.get("obs", "") or "").strip()
            if not observations or observations == "No observations":
                continue
            for call in step.get("tool_calls", []) or []:
                if not isinstance(call, dict):
                    continue
                tool_name = call.get("name")
                if tool_name not in self.evidence_tool_names:
                    continue
                arguments = call.get("arguments", {})
                snippet = observations.replace("\n", " ").strip()
                if len(snippet) > self.evidence_char_budget:
                    snippet = snippet[: self.evidence_char_budget].rstrip() + "..."
                chunks.append(f"- {tool_name}({arguments}): {snippet}")
        return "\n".join(chunks)

    def _reconcile_report(
        self,
        *,
        task: str,
        payload: dict[str, Any],
        digest: str,
    ) -> str | None:
        model = getattr(self.subagent, "model", None)
        if model is None:
            return None

        solver_answer = str(payload.get("agent_result", "") or "").strip()
        prompt = (
            "You are an evidence reconciler for a read-only tool-use solver.\n"
            "Given the assigned task, the solver's stated answer, and the actual "
            "tool observations, produce a concise report for a judge.\n\n"
            "Rules:\n"
            "1. Base the report on the tool observations, not prior knowledge.\n"
            "2. If the stated answer conflicts with the observations, follow the observations.\n"
            "3. If the observations contain a direct date, name, entity, or value requested "
            "by the task, extract that value as the answer.\n"
            "4. Return strict JSON only with keys answer, evidence, uncertainty.\n\n"
            f"Assigned task:\n{task}\n\n"
            f"Solver stated answer:\n{solver_answer}\n\n"
            f"Tool observations:\n{digest}\n"
        )
        try:
            response = model(
                [
                    {
                        "role": MessageRole.USER,
                        "content": [{"type": "text", "text": prompt}],
                    }
                ]
            )
            content = str(getattr(response, "content", response)).strip()
            data = json_repair.loads(content)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None
        answer = str(data.get("answer", "") or "").strip()
        evidence = str(data.get("evidence", "") or "").strip()
        uncertainty = str(data.get("uncertainty", "") or "").strip()
        if not answer:
            return None
        lines = [f"ANSWER: {answer}"]
        if evidence:
            lines.append(f"EVIDENCE: {evidence}")
        if uncertainty:
            lines.append(f"UNCERTAINTY: {uncertainty}")
        return "\n".join(lines)

    def _fallback_evidence_probe(
        self,
        *,
        task: str,
    ) -> tuple[str, dict[str, Any], str] | None:
        candidates = [
            name
            for name in sorted(self.evidence_tool_names)
            if name in getattr(self.subagent, "tools", {})
        ]
        if len(candidates) != 1:
            return None

        tool_name = candidates[0]
        tool = self.subagent.tools.get(tool_name)
        inputs = dict(getattr(tool, "inputs", {}) or {})
        if len(inputs) != 1:
            return None

        argument_name, argument_spec = next(iter(inputs.items()))
        argument_type = str(argument_spec.get("type", "string")).lower()
        if argument_type not in {"string", "str"}:
            return None

        query_text = str(getattr(self.coordinator, "task", "") or task).strip()
        if not query_text:
            return None
        arguments = {argument_name: query_text}
        try:
            observation = tool.__call__(**arguments, sanitize_inputs_outputs=True)
        except Exception as exc:
            observation = f"Fallback evidence probe failed: {exc}"
        return tool_name, arguments, str(observation).strip()

    def forward(self, task: str) -> dict[str, Any]:
        payload = super().forward(task)
        if not isinstance(payload, dict):
            return payload
        digest = self._evidence_digest(payload)
        if not digest:
            fallback = self._fallback_evidence_probe(task=task)
            if fallback is not None:
                tool_name, arguments, observation = fallback
                payload.setdefault("agent_trajectory", []).append(
                    {
                        "name": "action",
                        "tool_calls": [{"name": tool_name, "arguments": arguments}],
                        "obs": (
                            f"Results for fallback evidence probe '{tool_name}' "
                            f"with arguments '{arguments}':\n{observation}"
                        ),
                        "think": "fallback evidence probe",
                    }
                )
                digest = self._evidence_digest(payload)
        if digest:
            payload["evidence_digest"] = digest
            reconciled_report = self._reconcile_report(
                task=task,
                payload=payload,
                digest=digest,
            )
            if reconciled_report:
                payload["reconciled_report"] = reconciled_report
            payload["report"] = (
                f"{payload.get('report', '').rstrip()}\n\n"
                + (
                    f"Evidence-reconciled report:\n{reconciled_report}\n\n"
                    if reconciled_report
                    else ""
                )
                + "Evidence observations used by this solver:\n"
                f"{digest}"
            )
        return payload


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "router_debate"
    DEFAULT_SOLVER_MAX_STEPS = 6
    DEFAULT_STATEFUL_SUMMARY_INTERVAL = 6

    def _solver_max_steps(self, context: ActionContext) -> int:
        remaining_budget = max(1, context.max_steps - 2)
        return max(4, min(self.DEFAULT_SOLVER_MAX_STEPS, remaining_budget))

    def _stateful_tool_budget(self, context: ActionContext) -> int:
        return max(8, min(12, context.max_steps // 2))

    def _evidence_tool_names(self, tools: list[Any]) -> set[str]:
        return {
            str(getattr(tool, "name", ""))
            for tool in tools
            if getattr(tool, "name", None)
            and getattr(tool, "name", None) != "final_answer"
        }

    def _has_completed_evidence_observation(
        self,
        agent: Any,
        evidence_tool_names: set[str],
    ) -> bool:
        for step in getattr(getattr(agent, "memory", None), "steps", []):
            if not isinstance(step, ActionStep):
                continue
            observations = str(getattr(step, "observations", "") or "").strip()
            if not observations or observations == "No observations":
                continue
            for call in getattr(step, "tool_calls", []) or []:
                if getattr(call, "name", None) in evidence_tool_names:
                    return True
        return False

    def _install_read_only_evidence_gate(
        self,
        agent: Any,
        evidence_tool_names: set[str],
    ) -> None:
        if not evidence_tool_names:
            return

        original_step = agent.step
        original_provide_final_answer = agent.provide_final_answer

        def gated_step(memory_step: ActionStep):
            final_answer = original_step(memory_step)
            if final_answer is None:
                return None
            if self._has_completed_evidence_observation(agent, evidence_tool_names):
                return final_answer

            memory_step.observations = (
                "Evidence gate blocked premature final_answer: this read-only solver "
                "has non-final evidence tools available but has not completed any "
                "evidence-tool observation yet. Call one relevant evidence tool first, "
                "then finalize from the observation."
            )
            return None

        def gated_provide_final_answer(task: str):
            if self._has_completed_evidence_observation(agent, evidence_tool_names):
                return original_provide_final_answer(task)
            return (
                "",
                "Evidence gate: no completed non-final evidence-tool observation.",
                (
                    "ANSWER: UNKNOWN; EVIDENCE: no completed evidence-tool "
                    "observation; UNCERTAINTY: solver stopped before using the "
                    "available read-only tools."
                ),
            )

        agent.step = gated_step
        agent.provide_final_answer = gated_provide_final_answer
        setattr(
            agent,
            "read_only_evidence_gate",
            {
                "required_before_final": True,
                "evidence_tools": sorted(evidence_tool_names),
            },
        )

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
        self.organization_planning_system = context.planning_system or self.PROMPTS_TYPE
        self.route_name = schema_route_name(tools)
        self.use_debate = is_read_only_tool_schema(tools)
        if not self.use_debate:
            return

        guarded_read_tools = guard_task_tools(
            tools,
            policy_label="router_debate_read_only_solver",
            max_real_tool_calls=self._solver_max_steps(context),
        )
        solver_max_steps = self._solver_max_steps(context)
        self.solver_a = self.create_subagent(
            context,
            tools=guarded_read_tools,
            planning_system=self.organization_planning_system,
            prompt_templates=self.prompt_templates["solver_a"],
            name="solver_a",
            description=(
                "Independent read-only solver A. It should solve directly and report evidence."
            ),
            max_steps=solver_max_steps,
            summary_interval=context.max_steps + 1,
        )
        self.solver_b = self.create_subagent(
            context,
            tools=guarded_read_tools,
            planning_system=self.organization_planning_system,
            prompt_templates=self.prompt_templates["solver_b"],
            name="solver_b",
            description=(
                "Independent read-only solver B. It should use a different route when possible."
            ),
            max_steps=solver_max_steps,
            summary_interval=context.max_steps + 1,
        )
        evidence_tool_names = self._evidence_tool_names(guarded_read_tools)
        self.evidence_tool_names = evidence_tool_names
        self._install_read_only_evidence_gate(self.solver_a, evidence_tool_names)
        self._install_read_only_evidence_gate(self.solver_b, evidence_tool_names)

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        if self.use_debate:
            solver_tools = [
                EvidenceReportingSubAgentTool(
                    name=solver.name,
                    agent=solver,
                    description=(
                        f"{solver.name}: independent solver for read-only tool-schema tasks."
                    ),
                    max_steps=self._solver_max_steps(context),
                    include_parent_task=True,
                    evidence_tool_names=self.evidence_tool_names,
                    role_instructions=(
                        "- Solve the assigned read-only task independently.\n"
                        "- If non-final evidence tools are available, complete at least "
                        "one relevant evidence-tool call before final_answer.\n"
                        "- Do not answer from parametric memory when an evidence tool can "
                        "verify the answer.\n"
                        "- Use only valid tool schemas.\n"
                        "- Return a concise report with answer, evidence, and uncertainty.\n"
                        "- Do not assume stateful authority; this route is enabled only by read-only tool schemas."
                    ),
                )
                for solver in (self.solver_a, self.solver_b)
            ]
            guarded_solver_tools = guard_task_tools(
                solver_tools,
                policy_label="router_debate_judge",
                max_real_tool_calls=2,
            )
            agent = self.create_agent(
                context,
                tools=self.normalize_tools(guarded_solver_tools),
                prompt_templates=self.prompt_templates,
                prompts_type=self.prompts_type,
                planning_system=self.organization_planning_system,
            )
            agent.summary_interval = context.max_steps + 1
            for solver_tool in solver_tools:
                solver_tool.coordinator = agent
            for solver_tool in guarded_solver_tools:
                solver_tool.coordinator = agent
            agent.managed_agents = {
                solver.name: solver for solver in (self.solver_a, self.solver_b)
            }
            setattr(
                agent,
                "harness_policy",
                {
                    "mode": "router_debate_read_only",
                    "route": self.route_name,
                    "solvers": ["solver_a", "solver_b"],
                    "judge": "root_agent",
                },
            )
            return agent

        guarded_tools = guard_task_tools(
            tools,
            policy_label="router_stateful_single_executor",
            max_real_tool_calls=self._stateful_tool_budget(context),
        )
        critic = ReflectionCriticTool(
            context=context,
            name="stateful_critic",
            description=(
                "Non-environment critic for stateful fallback. It checks tool validity, "
                "arguments, repeated failures, and stop conditions without touching state."
            ),
        )
        root_tools = self.normalize_tools([*guarded_tools, critic])
        stateful_templates = self.prompt_templates.get("stateful", self.prompt_templates)
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=stateful_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        critic.bind_agent(agent, root_tools)
        if agent.summary_interval is None:
            agent.summary_interval = self.DEFAULT_STATEFUL_SUMMARY_INTERVAL
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "router_stateful_single_executor_critic",
                "route": self.route_name,
                "critic_tool": critic.name,
                "real_tool_budget": self._stateful_tool_budget(context),
            },
        )
        return agent


ACTION_SYSTEM = "router_debate"
ACTION_MODULE = "router_debate"


ParallelAgentsActionProvider = ActionProvider


def get_provider():
    return ActionProvider()


__all__ = [
    "ACTION_SYSTEM",
    "ACTION_MODULE",
    "ActionProvider",
    "get_provider",
    "ParallelAgentsActionProvider",
]
