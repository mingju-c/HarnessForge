from __future__ import annotations

from typing import Any

from Agents.agents import ToolCallingAgent
from Agents.tools import EnsembleTool, VoteTool

from module_action.base_action import ActionContext, BaseActionProvider


class JoyAgentActionProvider(BaseActionProvider):
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
        self.prompts_type = "joy_agent"
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        self.organization_planning_system = "joy_agent"
        self.coordinator_role = {
            "name": "Task Augmentation",
            "style": "bold yellow",
            "title_suffix": "",
            "responsibility": "Augment the task, retrieve relevant memory, and orchestrate the ensemble.",
        }
        self.pe_role = {
            "name": "PE-Worker",
            "style": "cyan",
            "title_suffix": " Roadmap",
            "responsibility": "Plan once, then execute along a stable roadmap.",
        }
        self.react_role = {
            "name": "ReAct-Worker",
            "style": "magenta",
            "title_suffix": " Strategy",
            "responsibility": "Iteratively explore and adapt based on observations.",
        }

        self.pe_worker = ToolCallingAgent(
            model=context.model,
            tools=tools,
            planning_system="joy_agent",
            prompt_templates=self.prompt_templates["pe_worker"],
            name="pe_expert",
            summary_interval=context.max_steps + 1,
            description=(
                "Expert at structured logic and high-reliability reports. "
                "Follows Plan-Execute paradigm."
            ),
        )
        if getattr(self.pe_worker, "planning", None) is not None:
            self.pe_worker.planning.role_info = self.pe_role

        self.react_workers = [
            ToolCallingAgent(
                model=context.model,
                tools=tools,
                planning_system="joy_agent",
                prompt_templates=self.prompt_templates["react_worker"],
                name=f"react_expert_{i}",
                summary_interval=context.max_steps + 1,
                description=(
                    "Fast reactive expert for exploratory search. "
                    "Follows ReAct paradigm."
                ),
            )
            for i in range(1, 4)
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
        return agent
