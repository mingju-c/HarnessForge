from __future__ import annotations

from typing import Any

from _harness_guards import guard_task_tools, is_read_only_tool_schema, schema_route_name
from module_action.base_action import ActionContext, BaseActionProvider


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "guarded_small_committee"
    ORGANIZATION_PLANNING_SYSTEM = "guarded_small_committee"
    READ_ONLY_WORKERS = 1
    STATEFUL_WORKERS = 1
    READ_ONLY_WORKER_MAX_STEPS = 5
    STATEFUL_WORKER_MAX_STEPS = 10

    def _worker_max_steps(self, context: ActionContext) -> int:
        limit = (
            self.READ_ONLY_WORKER_MAX_STEPS
            if getattr(self, "route_name", "") == "schema_read_only"
            else self.STATEFUL_WORKER_MAX_STEPS
        )
        remaining_budget = max(1, context.max_steps - 2)
        return max(3, min(limit, remaining_budget))

    def _worker_count(self, context: ActionContext) -> int:
        tools = getattr(self, "_current_tools_for_routing", [])
        return self.READ_ONLY_WORKERS if is_read_only_tool_schema(tools) else self.STATEFUL_WORKERS

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
        self.organization_planning_system = self.ORGANIZATION_PLANNING_SYSTEM
        self._current_tools_for_routing = tools
        self.route_name = schema_route_name(tools)
        worker_count = self._worker_count(context)
        guarded_tools = guard_task_tools(
            tools,
            policy_label="guarded_small_committee_worker",
            max_real_tool_calls=self._worker_max_steps(context),
        )
        self.coordinator_role = {
            "name": "Committee Coordinator",
            "responsibility": "Use a very small worker pool, compare concise reports, and finalize quickly.",
        }
        self.worker_role = {
            "name": "Committee Worker",
            "responsibility": "Solve one focused subtask with short guarded execution.",
        }
        worker_max_steps = self._worker_max_steps(context)
        self.workers = [
            self.create_subagent(
                context,
                tools=guarded_tools,
                planning_system=self.organization_planning_system,
                prompt_templates=self.prompt_templates["worker"],
                name=f"worker_{index}",
                description=(
                    "Guarded delegated worker. Solve one focused subtask and return a concise report."
                ),
                max_steps=worker_max_steps,
                summary_interval=context.max_steps + 1,
            )
            for index in range(1, worker_count + 1)
        ]
        for worker in self.workers:
            if getattr(worker, "planning", None) is not None:
                worker.planning.role_info = self.worker_role

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        worker_tools = [
            self.create_subagent_tool(
                agent=worker,
                description=(
                    f"{worker.name}: assign one focused subtask. "
                    "Use it once for the most important subtask and keep the request short."
                ),
                max_steps=self._worker_max_steps(context),
                include_parent_task=True,
                role_instructions=(
                    "- Stay on the assigned subtask, not the full task.\n"
                    "- Use the available tools to gather decisive evidence.\n"
                    "- For state-changing tasks, perform the required state changes yourself; "
                    "if a terminal completion tool exists and the changes are done, call it.\n"
                    "- Finish in as few steps as possible.\n"
                    "- If a tool call fails, change arguments/tool or stop; do not repeat the same failed call.\n"
                    "- Return a concise report with the outcome, key evidence, and any useful intermediate finding.\n"
                    "- If you hit a guard or max-step condition, report the exact blocker instead of continuing."
                ),
            )
            for worker in self.workers
        ]
        manager_worker_budget = 1 if self.route_name != "schema_read_only" else 2
        guarded_worker_tools = guard_task_tools(
            worker_tools,
            policy_label="guarded_small_committee_manager",
            max_real_tool_calls=manager_worker_budget,
        )
        agent = self.create_agent(
            context,
            tools=self.normalize_tools(guarded_worker_tools),
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        agent.summary_interval = context.max_steps + 1
        if getattr(agent, "planning", None) is not None:
            agent.planning.role_info = self.coordinator_role
        for worker_tool in worker_tools:
            worker_tool.coordinator = agent
        for worker_tool in guarded_worker_tools:
            worker_tool.coordinator = agent
        agent.managed_agents = {worker.name: worker for worker in self.workers}
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "guarded_small_committee",
                "route": self.route_name,
                "worker_count": len(self.workers),
                "worker_max_steps": self._worker_max_steps(context),
                "manager_worker_budget": manager_worker_budget,
            },
        )
        return agent


ACTION_SYSTEM = "guarded_small_committee"
ACTION_MODULE = "guarded_small_committee"


def get_provider():
    return ActionProvider()


__all__ = [
    "ACTION_SYSTEM",
    "ACTION_MODULE",
    "ActionProvider",
    "get_provider",
]
