from __future__ import annotations

from typing import Any

from Agents.agents import ToolCallingAgent
from Agents.tools import EnsembleTool, VoteTool

from _harness_guards import guard_task_tools
from module_action.base_action import ActionContext, BaseActionProvider


class ActionProvider(BaseActionProvider):
    PROMPTS_TYPE = "guarded_joy_agent"
    REACT_WORKERS = 2
    DEFAULT_WORKER_MAX_STEPS = 7

    def _worker_max_steps(self, context: ActionContext) -> int:
        remaining_budget = max(1, context.max_steps - 3)
        return max(4, min(self.DEFAULT_WORKER_MAX_STEPS, remaining_budget))

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
        self.organization_planning_system = self.PROMPTS_TYPE
        guarded_tools = guard_task_tools(
            tools,
            policy_label="guarded_joy_worker",
            max_real_tool_calls=self._worker_max_steps(context),
        )
        self.coordinator_role = {
            "name": "Task Augmentation",
            "style": "bold yellow",
            "title_suffix": "",
            "responsibility": "Augment the task, retrieve procedural memory, orchestrate a small guarded ensemble, and stop early.",
        }
        self.pe_role = {
            "name": "PE-Worker",
            "style": "cyan",
            "title_suffix": " Roadmap",
            "responsibility": "Plan once, execute along a stable roadmap, and avoid repeated failed tool calls.",
        }
        self.react_role = {
            "name": "ReAct-Worker",
            "style": "magenta",
            "title_suffix": " Strategy",
            "responsibility": "Explore briefly, then change strategy after any failed observation.",
        }
        planning_class = context.kwargs.get("planning_class")

        self.pe_worker = self.create_subagent(
            context,
            tools=guarded_tools,
            planning_system=self.organization_planning_system,
            planning_class=planning_class,
            prompt_templates=self.prompt_templates["pe_worker"],
            name="pe_expert",
            max_steps=self._worker_max_steps(context),
            summary_interval=context.max_steps + 1,
            description=(
                "Expert at structured logic and high-reliability reports. "
                "Follows a guarded Plan-Execute paradigm."
            ),
        )
        if getattr(self.pe_worker, "planning", None) is not None:
            self.pe_worker.planning.role_info = self.pe_role

        self.react_workers = [
            self.create_subagent(
                context,
                tools=guarded_tools,
                planning_system=self.organization_planning_system,
                planning_class=planning_class,
                prompt_templates=self.prompt_templates["react_worker"],
                name=f"react_expert_{i}",
                max_steps=self._worker_max_steps(context),
                summary_interval=context.max_steps + 1,
                description=(
                    "Fast reactive expert for exploratory search. "
                    "Follows guarded ReAct with early stop."
                ),
            )
            for i in range(1, self.REACT_WORKERS + 1)
        ]
        for worker in self.react_workers:
            if getattr(worker, "planning", None) is not None:
                worker.planning.role_info = self.react_role

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        ensemble_tool = EnsembleTool(
            pe_worker=self.pe_worker,
            react_workers=self.react_workers,
        )
        vote_tool = VoteTool(model=context.model)
        root_tools = self.normalize_tools([ensemble_tool, vote_tool, context.vector_tool])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        if getattr(agent, "planning", None) is not None:
            agent.planning.role_info = self.coordinator_role
        agent.managed_agents = {
            worker.name: worker for worker in [self.pe_worker] + self.react_workers
        }
        ensemble_tool.agent = agent
        vote_tool.agent = agent
        setattr(
            agent,
            "harness_policy",
            {
                "mode": "guarded_joy_agent",
                "pe_workers": 1,
                "react_workers": len(self.react_workers),
                "worker_max_steps": self._worker_max_steps(context),
                "guarded_worker_tools": True,
            },
        )
        return agent

ACTION_SYSTEM = 'guarded_joy_agent'
ACTION_MODULE = 'guarded_joy_agent'

def get_provider():
    return ActionProvider()

__all__ = ['ACTION_SYSTEM', 'ACTION_MODULE', 'ActionProvider', 'get_provider']

